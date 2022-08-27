from .ArpTracker import ArpTracker
from .EdgeDispatcher import EdgeDispatcher
from .EdgeDetector import EdgeDetector
from .PortTracker import PortTracker
from .L2TableForwarder import L2TableForwarder
from .ServiceManager import ServiceManager
from .EdgeRedirector import EdgeRedirector
from .Context import Context
from .ProximityScheduler import ProximityScheduler

from util.RyuOpenFlow import OpenFlow
from util.RyuDPID import DPID

from util.EdgeTools import Edge
from util.IPAddr import IPAddr
from util.Performance import PerfCounter

from datetime import datetime
from os import getenv as os_getenv
from json import load as json_load


class EdgeController:
    """
    Maintains the overall system state.
    """

    def __init__(self, logParent):

        self.log = logParent.getChild("Ctrl")

        # Log startup time for debugging purposes
        self.log.info(datetime.now().strftime("%Y-%m-%d %H:%M"))

        self.forwarders = {}
        self.ofPerSwitch = {}
        self.ctx = Context()

        # Load configuration
        #
        self._clusterGlob = "/var/emu/*-k8s.json"  # default value
        self._servicesGlob = "/var/emu/services/*.yml"  # default value
        self._servicesDir = "/var/emu/svcMngr/"  # default value
        self._switchConfig = None
        self._useUniqueMask = True
        self._logPerformance = False
        self.loadConfig(os_getenv('EDGE_CONFIG'))

        logLevel = os_getenv('EDGE_LOGLEVEL')
        if logLevel:
            self.log.setLevel(logLevel)
            self.log.warn("Loglevel set to " + logLevel)

        self.ctx.serviceMngr = ServiceManager(
            self.ctx,
            self.logger("ServiceMngr"),
            clusterGlob=self._clusterGlob,
            servicesGlob=self._servicesGlob,
            servicesDir=self._servicesDir)

        self.scheduler = ProximityScheduler(self.logger("ProxScheduler"))

        self.dispatcher = EdgeDispatcher(self.ctx, self.logger("Dispatcher"), self.scheduler, self.flowIdleTimeout * 2)

        for dpid, edge in self.ctx.edges.items():
            self.log.info("Switch {} -> {}".format(dpid, edge))

    def connect(self, of: OpenFlow):

        dpid = of.dpid

        # Do we already have a forwarder for this switch?
        #
        # REVIEW: Is it safe to reconnect without setting up the default forwarding rules again?
        #
        if dpid in self.forwarders:
            self.log.warn("Reconnected {}".format(dpid))

        # REVIEW Necessary / useful?
        # elif dpid not in self.servers:

        else:
            self.log.info("{} connected.".format(dpid))

            # OpenFlow: Resubmit (gotoTable) is only possible with ascending table IDs!
            #
            preSelectTable = 0
            edgeRedirTable = 1
            userRedirTable = 2
            defaultTable = 3

            fwds = []
            fwds.append(
                EdgeDetector(
                    self.ctx,
                    self.logger("Detect", dpid),
                    preSelectTableID=preSelectTable,
                    tableID=edgeRedirTable,
                    userTableID=userRedirTable,
                    defaultTableID=defaultTable,
                    useUniqueMask=self._useUniqueMask,
                    flowIdleTimeout=self.flowIdleTimeout))
            fwds.append(
                EdgeRedirector(
                    self.ctx,
                    self.logger("Redir", dpid),
                    self.dispatcher,
                    tableID=userRedirTable,
                    defaultTableID=defaultTable,
                    flowIdleTimeout=self.flowIdleTimeout))
            fwds.append(
                L2TableForwarder(
                    self.ctx,
                    self.logger("L2Fwd", dpid),
                    table1ID=defaultTable,
                    table2ID=defaultTable + 1,
                    flowIdleTimeout=self.flowIdleTimeout * 4))  # few + stable rules: use a longer timeout here
            fwds.append(
                ArpTracker(
                    self.ctx,
                    self.logger("ArpTracker", dpid),
                    preSelectTable,
                    srcMac=self.arpSrcMac,
                    installFlow=True,
                    fwdTable=defaultTable))
            fwds.append(PortTracker(self.ctx, self.logger("PortTracker", dpid)))

            self.forwarders[dpid] = fwds

        # forward call to all forwarders
        #
        for fwd in self.forwarders[dpid]:
            fwd.connect(of)

        of.BarrierRequest().send()  # send barrier before we start to listen (just to be safe)

    def connected(self, of: OpenFlow, switch):

        # we need to temporarily store the OpenFlow object
        #
        self.ofPerSwitch[of.dpid] = of
        self.ctx.switches[of.dpid] = switch

        switchCfg = self._switchConfig.get(str(of.dpid.asShortInt()))
        if switchCfg:
            switch.gateway = IPAddr(switchCfg["gateway"])

        self.log.info("Added Switch {}: {}".format(of.dpid, switch))

        # check if all switches are connected already
        #
        if not len([dpid for (dpid, value) in self.ctx.switches.items() if value == None]):
            #
            # Now all forwarders should be able to retrieve responses for their network requests.
            # Otherwise, an intermediate switch might not be able yet to forward them correctly.
            #
            for dpid in self.ctx.switches:
                for fwd in self.forwarders[dpid]:
                    fwd.connected(self.ofPerSwitch[dpid])
            self.ofPerSwitch = {}  # not required anymore

            # get data about all services from the attached clusters
            #
            for dpid in self.ctx.switches:
                edge = self.ctx.edges.get(dpid)
                if edge and edge.cluster:
                    self.ctx.serviceMngr.initServices(edge)

            self.log.info("")
            self.log.info("")
            self.log.info("**** Fully connected. ****")
            self.log.info("")
            self.log.info("")

    def packetIn(self, of: OpenFlow):

        perf = PerfCounter()
        for fwd in self.forwarders[of.dpid]:
            fwd.packetIn(of)
            perf.lap()

        if self._logPerformance and (of.msg.table_id == 1 or of.msg.table_id == 2):
            self.log.warn("packetIn: {}ms".format(perf.laps()))

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

            for dpid, switch in cfg['switches'].items():

                dpid = DPID(dpid)
                self.ctx.switches[dpid] = None  # not connected yet

                for edge in switch['edges']:
                    self.ctx.edges[dpid] = Edge(edge['ip'], dpid, edge.get('target'), edge['serviceCidr'])
