from .ArpTracker import ArpTracker
from .EdgeDispatcher import EdgeDispatcher
from .EdgeDetector import EdgeDetector
from .PortTracker import PortTracker
from .L2TableForwarder import L2TableForwarder
from .ServiceManager import ServiceManager
from .EdgeRedirector import EdgeRedirector

from util.RyuOpenFlow import OpenFlow
from util.RyuDPID import DPID

from util.EdgeTools import Edge, Switches, SwitchTable, HostTable, Switch
from util.IPAddr import IPAddr
from util.Performance import PerfCounter

from datetime import datetime
from os import getenv as os_getenv
from json import load as json_load


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

        self.forwarders = {}
        self.ofPerSwitch = {}
        self._switches = Switches()
        self._hosts = SwitchTable()
        self._edges: dict[DPID, Edge] = {}

        # Load configuration
        #
        self._clusterGlob = "/var/emu/*-k8s.json"  # default value
        self._servicesGlob = "/var/emu/services/*.yml"  # default value
        self._servicesDir = "/var/emu/svcMngr/"  # default value
        self._switchConfig = None
        self._useUniqueMask = True
        self._logPerformance = False
        self._scheduler = {
            "class": "ryu_ctrl.ProximityScheduler.ProximityScheduler",
            "logName": "ProxScheduler"
        }  # default value

        self.loadConfig(os_getenv('EDGE_CONFIG'))

        logLevel = os_getenv('EDGE_LOGLEVEL')
        if logLevel:
            self.log.setLevel(logLevel)
            self.log.warn("Loglevel set to " + logLevel)

        self._serviceMngr = ServiceManager(
            self.logger("ServiceMngr"),
            self._edges,
            clusterGlob=self._clusterGlob,
            servicesGlob=self._servicesGlob,
            servicesDir=self._servicesDir)

        # dynamically load scheduler
        #
        moduleName, className = self._scheduler["class"].rsplit(".", 1)
        schedulerModule = __import__(moduleName, fromlist=[className])
        scheduler = getattr(schedulerModule, className)

        self.dispatcher = EdgeDispatcher(
            self.logger("Dispatcher"), self._serviceMngr, self._hosts, self._edges,
            scheduler(self.logger(self._scheduler["logName"]), self._scheduler), self.flowIdleTimeout * 2)

        for dpid, edge in self._edges.items():
            self.log.info("Switch {} -> {}".format(dpid, edge))

    def connect(self, of: OpenFlow):

        dpid = of.dpid

        switch = self._switches.get(dpid)
        if switch is None:  # configured switches only
            return
        of.switch = switch

        # Do we already have a forwarder for this switch?
        #
        # REVIEW: Is it safe to reconnect without setting up the default forwarding rules again?
        #
        if dpid in self.forwarders:
            self.log.warn("Reconnected {}".format(dpid))

        # REVIEW Necessary / useful?
        # elif dpid not in self.servers:

        elif dpid in self._switches:  # we only care about configured switches
            self.log.info("{} connected.".format(dpid))

            hostTable = self._hosts.get(dpid)
            if hostTable is None:
                self._hosts[dpid] = hostTable = HostTable()

            fwds = []
            fwds.append(
                EdgeDetector(
                    self.logger("Detect", dpid),
                    self._serviceMngr,
                    preSelectTableID=self.PRESELECT_TABLE,
                    tableID=self.EDGE_DETECT_TABLE,
                    userTableID=self.EDGE_REDIR_TABLE,
                    defaultTableID=self.DEFAULT_TABLE,
                    useUniqueMask=self._useUniqueMask,
                    flowIdleTimeout=self.flowIdleTimeout))
            fwds.append(
                EdgeRedirector(
                    self.logger("Redir", dpid),
                    self._serviceMngr,
                    self.dispatcher,
                    tableID=self.EDGE_REDIR_TABLE,
                    defaultTableID=self.DEFAULT_TABLE,
                    flowIdleTimeout=self.flowIdleTimeout))
            fwds.append(
                L2TableForwarder(
                    self.logger("L2Fwd", dpid),
                    table1ID=self.DEFAULT_TABLE,
                    table2ID=self.DEFAULT_TABLE + 1,
                    flowIdleTimeout=self.flowIdleTimeout * 4))  # few + stable rules: use a longer timeout here
            fwds.append(
                ArpTracker(
                    self.logger("ArpTracker", dpid),
                    hostTable,
                    self.PRESELECT_TABLE,
                    srcMac=self.arpSrcMac,
                    installFlow=True,
                    fwdTable=self.DEFAULT_TABLE))
            fwds.append(PortTracker(self.logger("PortTracker", dpid)))

            self.forwarders[dpid] = fwds

            # forward call to all forwarders
            #
            of.switch = self._switches[dpid]  # look it up only once per request (not in every module)
            for fwd in self.forwarders[dpid]:
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
            for dpid in self._switches:
                for fwd in self.forwarders[dpid]:
                    fwd.connected(self.ofPerSwitch[dpid])
            self.ofPerSwitch = {}  # not required anymore

            # get data about all services from the attached clusters
            #
            for dpid in self._switches:
                edge = self._edges.get(dpid)
                if edge and edge.cluster:
                    self._serviceMngr.initServices(edge)

            self.log.info("")
            self.log.info("")
            self.log.info("**** Fully connected. ****")
            self.log.info("")
            self.log.info("")

    def packetIn(self, of: OpenFlow):

        switch = self._switches.get(of.dpid)
        if switch is None:  # configured switches only
            return

        perf = PerfCounter()
        of.switch = self._switches[of.dpid]  # look it up only once per request (not in every module)

        for fwd in self.forwarders[of.dpid]:
            fwd.packetIn(of)
            perf.lap()

        if self._logPerformance and (of.msg.table_id == 1 or of.msg.table_id == 2):
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

        xid = of.AggregateStatsRequest().table(msg.table_id).send()
        self.log.info("AggregateStatsRequest: table=%d xid=%d", msg.table_id, xid)

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

    def loadConfig(self, filename):

        self.log.info("Loading config file: " + filename)

        with open(filename) as file:

            cfg = json_load(file)

            # NOTE: is deliberately supposed to crash if one of the values is missing
            #
            self.arpSrcMac = cfg['arpSrcMac']
            self.flowIdleTimeout = int(cfg['flowIdleTimeout'])
            self._switchConfig = cfg['switches']

            self._clusterGlob = cfg.get('clusterGlob', self._clusterGlob)
            self._servicesGlob = cfg.get('servicesGlob', self._servicesGlob)
            self._servicesDir = cfg.get('servicesDir', self._servicesDir)
            self._useUniqueMask = cfg.get('useUniqueMask', self._useUniqueMask)
            self._logPerformance = cfg.get('logPerformance', self._logPerformance)
            self._scheduler = cfg.get('scheduler', self._scheduler)

            for dpid, switchCfg in cfg['switches'].items():

                dpid = DPID(dpid)
                switch = Switch(dpid, IPAddr(switchCfg["gateway"]))  # gateway is required
                self._switches[dpid] = switch

                for edgeCfg in switchCfg['edges']:
                    edge = Edge(edgeCfg['ip'], dpid, edgeCfg.get('target'), edgeCfg['serviceCidr'])
                    switch.edges.append(edge)
                    self._edges[dpid] = edge  # REVIEW Store only in Switch object?
