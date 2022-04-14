from .ArpTracker import ArpTracker
from .EdgeDispatcher import EdgeDispatcher
from .EdgeDetector import EdgeDetector
from .PortTracker import PortTracker
from .L2TableForwarder import L2TableForwarder
from .ServiceManager import ServiceManager
from .EdgeRedirector import EdgeRedirector
from .Context import Context

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
        self.ctx = Context()

        # Load configuration
        #
        self.servicesFolder = None
        self.servicesFileExt = None
        self.switchConfig = None
        self.loadConfig(os_getenv('EDGE_CONFIG'))

        logLevel = os_getenv('EDGE_LOGLEVEL')
        if logLevel:
            self.log.setLevel(logLevel)
            self.log.warn("Loglevel set to " + logLevel)

        self.ctx.serviceMngr = ServiceManager(self.ctx, self.logger("ServiceMngr"), self.servicesFolder,
                                              self.servicesFileExt)

        self.dispatcher = EdgeDispatcher(self.ctx, self.logger("Dispatcher"), self.useEdgePort,
                                         self.flowIdleTimeout * 2)

        for dpid, edge in self.ctx.edges.items():
            self.log.info("Switch {} -> {} {}".format(dpid, edge.ip, edge.serviceCidr))

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
                    self.logger("Redir", dpid),
                    preSelectTableID=preSelectTable,
                    tableID=edgeRedirTable,
                    userTableID=userRedirTable,
                    defaultTableID=defaultTable,
                    flowIdleTimeout=self.flowIdleTimeout))
            fwds.append(
                EdgeRedirector(
                    self.ctx,
                    self.logger("User", dpid),
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

        self.ctx.switches[of.dpid] = switch

        switchCfg = self.switchConfig.get(str(of.dpid.asShortInt()))
        if switchCfg:
            switch.gateway = IPAddr(switchCfg["gateway"])

        self.log.info("Added Switch {}: {}".format(of.dpid, switch))

        for fwd in self.forwarders[of.dpid]:
            fwd.connected(of)
        self.log.info("")
        self.log.info("")
        self.log.info("**** {} fully connected. ****".format(of.dpid))
        self.log.info("")
        self.log.info("")

    def packetIn(self, of: OpenFlow):

        perf = PerfCounter()
        for fwd in self.forwarders[of.dpid]:
            fwd.packetIn(of)
            perf.lap()

        if of.msg.table_id == 1 or of.msg.table_id == 2:
            self.log.warn("packetIn: {}ms".format(perf.laps()))

    def logger(self, name, dpid=None):
        #
        # Returns the child logger including the DPID.
        #
        log = self.log.getChild(name)
        return log if not dpid else log.getChild(str(dpid))

    def loadConfig(self, filename):

        with open(filename) as file:

            cfg = json_load(file)

            # NOTE: is deliberately supposed to crash if one of the values is missing
            #
            self.arpSrcMac = cfg['arpSrcMac']
            self.flowIdleTimeout = int(cfg['flowIdleTimeout'])
            self.servicesFolder = cfg['servicesFolder']
            self.servicesFileExt = cfg['servicesFileExt']
            self.switchConfig = cfg['switches']

            self.useEdgePort = cfg.get('useEdgePort', False)

            for dpid, switch in cfg['switches'].items():

                dpid = DPID(dpid)
                for edge in switch['edges']:
                    self.ctx.edges[dpid] = Edge(edge['ip'], dpid, edge['serviceCidr'])
