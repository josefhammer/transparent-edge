from util.IPAddr import IPAddr
from util.SocketAddr import SocketAddr
from util.RyuOpenFlow import OpenFlow
from .Context import Context
from logging import DEBUG, INFO


class EdgeDetector:
    """
    Redirects requests for registered services to the UserRedirector.
    """

    def __init__(self,
                 context: Context,
                 log,
                 preSelectTableID,
                 tableID,
                 userTableID,
                 defaultTableID,
                 useUniqueMask,
                 flowIdleTimeout=10):

        self.ctx = context
        self.log = log
        self.preSelectTable = preSelectTableID
        self.table = tableID
        self.userTable = userTableID
        self.defaultTable = defaultTableID
        self.useUniqueMask = useUniqueMask
        self.idleTimeout = flowIdleTimeout

        self.aPrivateIP = self.ctx.edges[next(iter(self.ctx.edges))].ip  # any private IP to calculate the netmask
        assert (self.aPrivateIP is not None)
        assert (self.aPrivateIP.isPrivateIP())

        self.isDebugLogLevel = log.isEnabledFor(DEBUG)
        self.isInfoLogLevel = log.isEnabledFor(INFO)

    def connect(self, of: OpenFlow):

        log = self.log
        log.info("Connected.")

        of.FlowMod().table(self.preSelectTable).clearTable()
        of.FlowMod().table(self.table).clearTable()

        self.configurePreSelectTable(of)
        self.configureEdgeTable(of)

    def configurePreSelectTable(self, of: OpenFlow):
        #
        # This separate table is used for performance reasons. Only potential edge traffic shall go through
        # the specific switching rules. Rationale for using a separate table: OpenFlow does not allow
        # negation matches, and on a separate table a simple inclusion list can be used instead.

        # Send only IPv4-TCP + IPv4-UDP traffic to edgeTable
        #
        # Furthermore, match only traffic coming from a private IP - incoming traffic goes directly to the
        # default forwarder. This reduces the number of flows in the edge table on the switch.
        #
        gotoEdgeRedir = of.Action().gotoTable(self.table)

        for proto in [of.IPPROTO_TCP, of.IPPROTO_UDP]:
            of.FlowMod().table(self.preSelectTable).priority(1).match(
                of.Match(ip_proto=proto).srcIP(self.aPrivateIP,
                                               self.aPrivateIP.privateIPMask())).actions(gotoEdgeRedir).send()

        # Fallthrough rule: send to defaultTable
        #
        of.FlowMod().table(self.preSelectTable).priority(0).actions(of.Action().gotoTable(self.defaultTable)).send()

    def configureEdgeTable(self, of: OpenFlow):
        #
        # Fallthrough rule for the edge table: send to controller
        #
        of.FlowMod().table(self.table).priority(0).actions(of.Action().sendToController()).send()

        # any private IP - just to calculate the netmask of the private network
        #
        aPrivateIP = self.ctx.edges[next(iter(self.ctx.edges))].ip

        # Proactively install edge return-flows (permanent):
        #
        # If UserRedirector is run on the same switch, there might be some by-catch (i.e. non-edge traffic coming from
        # edge servers). However, the UserRedirector will correctly handle these cases, and the core objective is to
        # speed up the 'main' traffic (i.e. to reduce the number of rules and packet-ins for this table).
        #
        #
        if of.dpid in self.ctx.edges:
            edge = self.ctx.edges[of.dpid]  # TODO allow multiple edges
            for cidr in edge.serviceCidr:

                # If src is edge and dst is private -> userTable
                #
                # Note: If dst is public, it could be a call to a virtual socket – edge services may use other edge
                # services.
                #
                srcIP = IPAddr(cidr.split('/')[0])
                srcMask = IPAddr.cidrToIPMask(cidr)
                match = of.Match().srcIP(srcIP, srcMask).dstIP(
                    aPrivateIP, aPrivateIP.privateIPMask())  # simple mask that fits any private network

                actions = of.Action().gotoTable(self.userTable)
                of.FlowMod().table(self.table).priority(of.MAX_PRIORITY).match(match).actions(actions).send()

        # Since the previous rules already send all traffic from edge servers to the controller, we can use the
        # default forwarder for any other traffic that goes to an internal destination.
        #
        # ATTENTION: This rule must have a lower priority than the previous.
        #
        match = of.Match().dstIP(aPrivateIP, aPrivateIP.privateIPMask())  # simple mask that fits any private network
        of.FlowMod().table(self.table).priority(of.MAX_PRIORITY - 1).match(match).actions(of.Action().gotoTable(
            self.defaultTable)).send()

    def connected(self, of: OpenFlow):
        pass

    def packetIn(self, of: OpenFlow):

        if not of.msg.table_id == self.table:
            return  # not our business

        log = self.log

        src = of.src
        dst = of.dst

        # Main goal: Make the switching of regular traffic as fast as possible.

        if self.ctx.serviceMngr.isService(dst):

            if self.isInfoLogLevel:
                log.info("-> {}".format(dst))
            self.redirectEdge(of, of.Match().dstIP(dst.ip).dstPort(dst.port))
            of.isEdge = True  # continue processing in UserRedirector (performance improvement only)

        else:
            # Forward all connections that have not been handled so far
            #
            if self.isDebugLogLevel:
                log.debug("IN: {} -> {}".format(src, dst))

            # do not proactively add a return flow here since (due to wildcards) one might exist already anyway
            #
            outport = of.switch.portFor(dst.mac)
            self.redirectDefault(of, self.defaultTrafficMatch(of, dst), outport)

    def defaultTrafficMatch(self, of: OpenFlow, dst: SocketAddr):
        #
        # NOTE: Only traffic from private to public IPs can arrive here.
        #       Any potential traffic from edge servers has already been redirected, so the srcIP does not matter.

        # UniquePrefix vs UniqueMask
        #
        # Calculate the UniquePrefix to match as much default traffic as possible with a single OpenFlow rule.
        # The uniquePrefix is the number of bits that are required for the current destination IP to _not_ match
        # _any_ available ServiceIP.
        #
        # E.g.: We do not want to match 194.232.104.150/32 but a much more inclusive 192.0.0.0/2 in case the first
        # two bits are different for _every_ available ServiceIP.
        #
        # The UniqueMask goes a step further. OpenFlow does not only allow to set a prefix, but a more precise bitmask.
        # Thus, we can take the parent prefixes into account as well. We just need to match all parent prefixes in
        # addition to the UniquePrefix; all the other bits in between do not matter. This way, we can match even more
        # possible public IPs with a single flow.
        #
        # Example:
        #
        # 194.232.104.150                                            = 11000010.11101000.01101000.10010110
        # 194.232.104.150, uniquePrefix=24:                     mask = 11111111.11111111.11111111.00000000
        # 194.232.104.150, uniquePrefix=24, prefixes=[8]:       mask = 00000001.00000000.00000001.00000000
        #
        uniquePrefix, prefixes = self.ctx.serviceMngr.uniquePrefix(dst.ip)
        match = of.Match()

        # if not a ServiceIP then the port does not matter (to reduce the number of OpenFlow rules)
        #
        if uniquePrefix > 32:  # == 32 would mean that the IP is unique and thus _not_ a ServiceIP
            match.dstPort(dst.port)

        uniquePrefix = min(32, uniquePrefix)

        if not self.useUniqueMask:  # use uniquePrefix only: all bits up to (incl.) uniquePrefix are set
            mask = (1 << uniquePrefix) - 1  # set num(uniquePrefix) bits to 1
            mask <<= (32 - uniquePrefix)  # and move them to the far left

        else:  # set the mask to the prefix bits only

            prefixes.append(uniquePrefix)
            for prefix in prefixes:
                mask = 1 << (32 - prefix)  # add bit at position(prefix)

        ipMask = str(IPAddr(mask))
        match.dstIP(dst.ip, ipMask)

        if self.isDebugLogLevel and (uniquePrefix < 32 or self.useUniqueMask):
            self.log.debug("Extended match for {}/{} (mask={}, prefixes={})".format(
                dst.ip, ipMask if self.useUniqueMask else uniquePrefix, mask, prefixes))
        return match

    def redirectEdge(self, of: OpenFlow, match):

        actions = of.Action().gotoTable(self.userTable)
        of.FlowMod().table(self.table).idleTimeout(self.idleTimeout).match(match).actions(actions).send()

        # REVIEW No idea how to 'packet-out' the packet to another table (in case it was not buffered by the
        # switch). However, since UserRedirector is listening to this table too, it will do the job for us
        # (i.e. send the packet to an actual outport).

    def redirectDefault(self, of: OpenFlow, match, outport):

        # REVIEW Longer timeout for default flows (better for testing)
        #
        actions = of.Action().gotoTable(self.defaultTable)
        of.FlowMod().table(self.table).idleTimeout(
            self.idleTimeout).match(match).actions(  #FIXME * 4).match(match).actions(
                actions, packetOut=outport).send()
