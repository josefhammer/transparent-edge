from .EdgeDispatcher import EdgeDispatcher
from .Context import Context
from util.SocketAddr import SocketAddr
from util.RyuOpenFlow import OpenFlow, Packet
from logging import DEBUG, INFO


class EdgeRedirector:
    """
    Redirects requests for registered services to edge nodes.
    """

    def __init__(self, context: Context, log, dispatcher: EdgeDispatcher, tableID, defaultTableID, flowIdleTimeout=10):

        self.ctx = context
        self.log = log
        self.dispatcher = dispatcher
        self.table = tableID
        self.defaultTable = defaultTableID
        self.idleTimeout = flowIdleTimeout

        self.isDebugLogLevel = log.isEnabledFor(DEBUG)
        self.isInfoLogLevel = log.isEnabledFor(INFO)

    def connect(self, of: OpenFlow):

        log = self.log
        log.info("Connected.")

        of.FlowMod().table(self.table).clearTable()

        # Fallthrough rule for user table: send to controller
        #
        of.FlowMod().table(self.table).priority(0).actions(of.Action().sendToController()).send()

    def connected(self, of: OpenFlow):
        pass

    def packetIn(self, of: OpenFlow):

        # watch both userTable and edgeTable (the latter to proactively install the flows to speed things up)
        #
        if not (of.msg.table_id == self.table or of.isEdge):  # of.isEdge is set by EdgeDetector
            return  # not our business

        src = of.src
        dst = of.dst

        if of.isEdge or self.ctx.serviceMngr.isService(dst):  # isEdge: Avoid searching twice

            if self.fwdToEdge(self.log, of, of.packet(), src, dst):
                return

        elif self.ctx.serviceMngr.isServer(of.dpid, src):

            if self.fwdFromEdge(self.log, of, of.packet(), src, dst):
                return

        # default forwarding (also for those cases where we could not select an edge flow)
        #
        self.log.debug("redirectDefault: {} -> {}".format(src, dst))
        self.redirectDefault(of, src, dst, self.ctx.switches[of.dpid].portFor(dst.mac))

    def fwdToEdge(self, log, of: OpenFlow, packet: Packet, src: SocketAddr, dst: SocketAddr):
        #
        #  It's for our service IP
        #
        dpid = of.dpid

        edge = self.dispatcher.dispatch(dpid, src, dst)
        if edge is None:
            log.warn("No servers available for %s --> regular forwarding.", dst)
            return False

        # Track user location
        #
        self.dispatcher.setClientLocation(dpid, src)

        # Set up table entry towards selected server
        #
        match = of.Match().srcIP(src.ip).dstIP(dst.ip).dstPort(dst.port)  # no srcPort

        outport = self.ctx.switches[of.dpid].portFor(edge.mac)

        actions = of.Action().setUDP(packet.isUDP()).setDestination(
            edge.mac, edge.ip.ip, edge.port if edge.port != dst.port else None).outport(outport)
        self.redirect(of, match, actions, packetOut=True)

        # Install return flow proactively (instead of waiting for the packet-in) to speed things up.
        # Nevertheless, we still need to monitor the return path:
        #    * the response might come earlier than the FlowMod
        #    * the FlowMod towards the edge server might be in a different switch!
        #
        self.fwdFromEdge(log, of, packet, edge, src, proactive=True)  # ignore result since this is optional

        if self.isDebugLogLevel:
            of.debug(log)  # takes a few milliseconds
        if self.isInfoLogLevel:
            log.info("==> {} -> {} ({}) => {} ({}) |t{}|l={}".format(src, dst, dst.mac, edge, edge.mac, of.msg.table_id,
                                                                     of.msg.total_len))
        return True

    def fwdFromEdge(self, log, of: OpenFlow, packet: Packet, src: SocketAddr, dst: SocketAddr, proactive=False):
        #
        # It's FROM one of our edge servers: Rewrite it BACK to the client
        #
        dpid = of.dpid

        serviceID = self.dispatcher.findServiceID(dpid, src, dst)
        if serviceID is None:
            # We either didn't install it, or we forgot about it.
            log.warn("No memory for %s/%s --> regular forwarding.", src, dst)
            return False

        match = of.Match().srcIP(src.ip).srcPort(src.port).dstIP(dst.ip)  # no dstPort

        outport = self.ctx.switches[of.dpid].portFor(of.src.mac if proactive else of.dst.mac)

        # ATTENTION: We must NOT go through a default forwarder afterwards (without faking the inport), since we would
        # confuse it with a fake combination of inport + vMac!! An L2 forwarder might learn the wrong out_port for vMac.
        #
        actions = of.Action().setUDP(packet.isUDP()).setSource(
            serviceID.mac, serviceID.ip.ip, serviceID.port if serviceID.port != src.port else None).outport(outport)
        self.redirect(of, match, actions, packetOut=not proactive)

        if not proactive and self.isInfoLogLevel:
            log.info("<== {} <= {} ({}) @@ {} ({}) |t{}|l={}".format(dst, serviceID, serviceID.mac, src, src.mac,
                                                                     of.msg.table_id, of.msg.total_len))
        return True

    def redirectDefault(self, of: OpenFlow, src: SocketAddr, dst: SocketAddr, outport):

        actions = of.Action().gotoTable(self.defaultTable)
        match = of.Match().srcIP(src.ip).srcPort(src.port).dstIP(dst.ip)

        if not dst.ip.isPrivateIP:  # dstPort is required only for traffic to the public cloud
            match.dstPort(dst.port)

        self.redirect(of, match, actions, packetOut=outport)

    def redirect(self, of, match, actions, packetOut=False):

        of.FlowMod().table(self.table).idleTimeout(self.idleTimeout).match(match).actions(actions, packetOut).send()
