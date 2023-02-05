from .ArpTracker import ArpTracker
from .Dispatcher import Dispatcher
from .EdgeDetector import EdgeDetector
from .PortTracker import PortTracker
from .L2TableForwarder import L2TableForwarder
from .ServiceManager import ServiceManager
from .EdgeRedirector import EdgeRedirector

from util.RyuOpenFlow import OpenFlow
from util.RyuDPID import DPID

from util.EdgeTools import Edge, Switches, Switch
from util.IPAddr import IPAddr
from util.Performance import PerfCounter
from util.Config import Config

from datetime import datetime
from os import getenv as os_getenv


class EdgeController:
    """
    Maintains the overall system state.
    """
    # OpenFlow: Resubmit (gotoTable) is only possible with ascending table IDs!
    #
    PRESELECT_TABLE = 0
    EDGE_DETECT_TABLE = 1
    EDGE_REDIR_TABLE = 2
    DEFAULT_TABLE = 3

    def __init__(self, logParent):

        self.log = logParent.getChild("Ctrl")

        # Log startup time for debugging purposes
        self.log.info(datetime.now().strftime("%Y-%m-%d %H:%M"))

        self.ofPerSwitch = {}
        self._switches = Switches()

        # set config vars with default values
        self._cfg = Config(os_getenv('EDGE_CONFIG'))
        self._cfg.clusterGlob = "/var/emu/clusters/*-*.json"  # default value
        self._cfg.servicesGlob = "/var/emu/services/*.yml"  # default value
        self._cfg.servicesDir = "/var/emu/svcMngr/"  # default value
        self._cfg.arpSrcMac = "02:00:00:00:00:ff"
        self._cfg.flowIdleTimeout = 5
        self._cfg.useUniquePrefix = True
        self._cfg.useUniqueMask = True
        self._cfg.logPerformance = False
        self._cfg.switches = None
        self._cfg.logLevel = None
        self._cfg.scheduler = {
            "class": "ryu_ctrl.ProximityScheduler.ProximityScheduler",
            "logName": "ProxScheduler"
        }  # default value

        # update from ENV or JSON
        self.loadConfig()
        self.log.info("Config: " + str(self._cfg))

        if self._cfg.logLevel:
            self.log.setLevel(self._cfg.logLevel)
            self.log.warn("Loglevel set to " + self._cfg.logLevel)

        self._serviceMngr = ServiceManager(self.logger("ServiceMngr"),
                                           self._switches,
                                           clusterGlob=self._cfg.clusterGlob,
                                           servicesGlob=self._cfg.servicesGlob,
                                           servicesDir=self._cfg.servicesDir)

        # dynamically load scheduler
        #
        moduleName, className = self._cfg.scheduler["class"].rsplit(".", 1)
        schedulerModule = __import__(moduleName, fromlist=[className])
        scheduler = getattr(schedulerModule, className)

        self.dispatcher = Dispatcher(self.logger("Dispatcher"), self._serviceMngr,
                                     scheduler(self.logger(self._cfg.scheduler["logName"]), self._cfg.scheduler),
                                     self._cfg.flowIdleTimeout * 10)

        for dpid, sw in self._switches.items():
            for edge in sw.edges:
                self.log.info("Switch {} -> {}".format(dpid, edge))

    def connect(self, of: OpenFlow):

        dpid = of.dpid

        switch = self._switches.get(dpid)
        if switch is None:  # configured switches only
            return
        of.switch = switch  # look it up only once per request (not in every module)

        # Do we already have a forwarder for this switch?
        #
        # REVIEW: Is it safe to reconnect without setting up the default forwarding rules again?
        #
        if len(switch.listeners):
            self.log.warn("Reconnected {}".format(dpid))

        else:
            self.log.info("{} connected.".format(dpid))

            fwds = switch.listeners
            fwds.append(
                EdgeDetector(self.logger("Detect", dpid),
                             self._serviceMngr,
                             preSelectTableID=self.PRESELECT_TABLE,
                             tableID=self.EDGE_DETECT_TABLE,
                             userTableID=self.EDGE_REDIR_TABLE,
                             defaultTableID=self.DEFAULT_TABLE,
                             useUniquePrefix=self._cfg.useUniquePrefix,
                             useUniqueMask=self._cfg.useUniqueMask,
                             flowIdleTimeout=self._cfg.flowIdleTimeout))
            fwds.append(
                EdgeRedirector(self.logger("Redir", dpid),
                               self._serviceMngr,
                               self.dispatcher,
                               tableID=self.EDGE_REDIR_TABLE,
                               defaultTableID=self.DEFAULT_TABLE,
                               flowIdleTimeout=self._cfg.flowIdleTimeout))
            fwds.append(
                L2TableForwarder(self.logger("L2Fwd", dpid),
                                 table1ID=self.DEFAULT_TABLE,
                                 table2ID=self.DEFAULT_TABLE + 1,
                                 flowIdleTimeout=self._cfg.flowIdleTimeout *
                                 4))  # few + stable rules: use a longer timeout here
            fwds.append(
                ArpTracker(self.logger("ArpTracker", dpid),
                           self.PRESELECT_TABLE,
                           srcMac=self._cfg.arpSrcMac,
                           installFlow=True,
                           fwdTable=self.DEFAULT_TABLE))
            fwds.append(PortTracker(self.logger("PortTracker", dpid)))

            # forward call to all forwarders
            #
            for fwd in fwds:
                fwd.connect(of)

        of.BarrierRequest().send()  # send barrier before we start to listen (just to be safe)

    def connected(self, of: OpenFlow, switchPorts):

        switch = self._switches.get(of.dpid)
        if switch is None:  # configured switches only
            return

        switch.init(switchPorts)
        of.switch = switch  # look it up only once per request (not in every module)

        # we need to temporarily store the OpenFlow object
        #
        self.ofPerSwitch[of.dpid] = of

        self.log.info("Added Switch {}: {}".format(of.dpid, switch))

        # check if all switches are connected already
        #
        if not len([dpid for (dpid, sw) in self._switches.items() if sw.ports is None]):
            #
            # Now all forwarders should be able to retrieve responses for their network requests.
            # Otherwise, an intermediate switch might not be able yet to forward them correctly.
            #
            for dpid, sw in self._switches.items():
                for fwd in sw.listeners:
                    fwd.connected(self.ofPerSwitch[dpid])
            self.ofPerSwitch = {}  # not required anymore

            # get data about all services from the attached clusters
            #
            for dpid, sw in self._switches.items():
                for edge in sw.edges:
                    if edge and edge.cluster:
                        self._serviceMngr.initServices(edge)

            self.log.info("")
            self.log.info("")
            self.log.warn("**** Fully connected. ****")
            self.log.info("")
            self.log.info("")

    def packetIn(self, of: OpenFlow):

        switch = self._switches.get(of.dpid)
        if switch is None:  # configured switches only
            return

        perf = PerfCounter()
        of.switch = self._switches[of.dpid]  # look it up only once per request (not in every module)

        for fwd in switch.listeners:
            fwd.packetIn(of)
            perf.lap()

        if self._cfg.logPerformance and (of.msg.table_id == 1 or of.msg.table_id == 2):
            self.log.warn("packetIn: {}ms".format(perf.laps()))

    def flowRemoved(self, of: OpenFlow):

        switch = self._switches.get(of.dpid)
        if switch is None:  # configured switches only
            return

        msg = of.msg
        if (msg.reason == of.proto.OFPRR_IDLE_TIMEOUT):

            self.log.info('-=FLOW tbl=%d src=%s:%s dst=%s:%s proto=%s cookie=%d %dsec packets=%d bytes=%d',
                          msg.table_id, msg.match.get('ipv4_src'), msg.match.get('tcp_src'), msg.match.get('ipv4_dst'),
                          msg.match.get('tcp_dst'), msg.match.get('ip_proto'), msg.cookie, msg.duration_sec,
                          msg.packet_count, msg.byte_count)

        # xid = of.AggregateStatsRequest().table(msg.table_id).send()
        # self.log.info("AggregateStatsRequest: table=%d xid=%d", msg.table_id, xid)

    def aggregateStats(self, of: OpenFlow):

        body = of.msg.body
        self.log.info('AggregateStats: xid=%d packet_count=%d byte_count=%d '
                      'flow_count=%d', of.msg.xid, body.packet_count, body.byte_count, body.flow_count)

    def logger(self, name, dpid=None):
        #
        # Returns the child logger including the DPID.
        #
        log = self.log.getChild(name)
        return log if not dpid else log.getChild(str(dpid))

    def loadConfig(self):

        self._cfg.loadConfig()

        for dpid, switchCfg in self._cfg.switches.items():

            dpid = DPID(dpid)
            switch = Switch(dpid, IPAddr(switchCfg["gateway"]))  # gateway is required
            self._switches[dpid] = switch

            for edgeCfg in switchCfg['edges']:
                edge = Edge(edgeCfg['ip'], switch, edgeCfg.get('target'), edgeCfg['serviceCidr'],
                            edgeCfg.get('scheduler'))
                switch.edges.append(edge)
