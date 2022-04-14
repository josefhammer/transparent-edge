# Josef Hammer (josef.hammer@aau.at)
#
# Interface to OpenFlow.
#
# Abstraction layer to Ryu to make switching between different controller frameworks easier.
#

from util.RyuDPID import DPID
from util.IPAddr import IPAddr
from util.SocketAddr import SocketAddr
from ryu.lib.packet import packet as ryuPacket, ether_types, ethernet, arp, ipv4, tcp, udp, in_proto

# IP protocol numbers: https://en.wikipedia.org/wiki/List_of_IP_protocol_numbers
# ether_types: https://github.com/faucetsdn/ryu/blob/d1d1dc94278fd81799ac37b09128b306827c8a3d/ryu/lib/packet/ether_types.py
#              https://en.wikipedia.org/wiki/EtherType
# arp: https://github.com/faucetsdn/ryu/blob/d1d1dc94278fd81799ac37b09128b306827c8a3d/ryu/lib/packet/arp.py


class OpenFlow(object):
    """
    Provides an abstraction layer to the OpenFlow controller.
    """

    MAX_PRIORITY = 65535

    ETH_TYPE_IP = ether_types.ETH_TYPE_IP  # 0x0800
    ETH_TYPE_ARP = ether_types.ETH_TYPE_ARP  # 0x0806
    ETH_TYPE_LLDP = ether_types.ETH_TYPE_LLDP  # 0x88cc
    ARP_HW_TYPE_ETHERNET = arp.ARP_HW_TYPE_ETHERNET  # 1
    IPPROTO_TCP = in_proto.IPPROTO_TCP  # 6
    IPPROTO_UDP = in_proto.IPPROTO_UDP  # 17

    def __init__(self, event):
        self.event = event

        self.msg = None
        self.dp = None
        self.isEdge = False  # requires processing by UserRedirector (set by EdgeRedirector)

        if hasattr(event, 'msg'):
            self.msg = event.msg
            self.dp = event.msg.datapath
        elif hasattr(event, 'dp'):
            self.msg = None
            self.dp = event.dp

        assert (self.dp)
        self.proto = self.dp.ofproto
        self.parser = self.dp.ofproto_parser
        self.dpid = DPID(self.dp.id)

        # Create SocketAddresses only once for all components
        #
        if self.msg and hasattr(self.msg, 'data'):
            packet = self._packet = Packet(self.proto, ryuPacket.Packet(self.msg.data), self.msg.match['in_port'])

            l4p = packet.tcp()  # Level-4-packet: TCP and UDP supported
            if not l4p:
                l4p = packet.udp()

            ipp = packet.ipv4()  # REVIEW store as attr?
            ethp = packet.eth()  # REVIEW store as attr?

            self.src = SocketAddr(ipp.src if ipp else None, l4p.src_port if l4p else 0, ethp.src)
            self.dst = SocketAddr(ipp.dst if ipp else None, l4p.dst_port if l4p else 0, ethp.dst)

    def Action(self):
        return Action(self)

    def FlowMod(self):
        return FlowMod(self)

    def PacketOut(self):
        return PacketOut(self)

    def BarrierRequest(self):
        return BarrierRequest(self)

    def ArpRequest(self, dstIP):
        return ArpRequest(self, dstIP)

    def Match(self, *args, **kwargs):
        return Match(self, *args, **kwargs)

    def hasBufferID(self):
        return self.msg.buffer_id != self.proto.OFP_NO_BUFFER

    def isValidPort(self, port):
        return port <= self.proto.OFPP_MAX

    def packet(self):
        return self._packet

    def debug(self, log):
        log.debug("Ev: time={} msgLen={} totalLen={} table={} bufferID={}".format(
            self.event.timestamp, self.msg.msg_len, self.msg.total_len, self.msg.table_id,
            self.msg.buffer_id if self.hasBufferID() else None))

        for item in ryuPacket.Packet(self.msg.data).protocols:
            log.debug(" *: {}".format(item))


class Packet(object):
    def __init__(self, ofproto, pkt: ryuPacket.Packet, inport):
        self.proto = ofproto
        self.packet = pkt
        self._inport = inport

    def inport(self):
        return self._inport

    def hasValidPort(self):
        return self._inport <= self.proto.OFPP_MAX

    def eth(self):
        return self.packet.get_protocol(ethernet.ethernet)

    def arp(self):
        return self.packet.get_protocol(arp.arp)

    def ipv4(self):
        return self.packet.get_protocol(ipv4.ipv4)

    def tcp(self):
        return self.packet.get_protocol(tcp.tcp)

    def udp(self):
        return self.packet.get_protocol(udp.udp)

    def isArp(self):
        return self.eth().ethertype == ether_types.ETH_TYPE_ARP  # 0x0806

    def isLLDP(self):
        return self.eth().ethertype == ether_types.ETH_TYPE_LLDP  # 0x88cc

    def isTCP(self):
        return self.eth().ethertype == ether_types.ETH_TYPE_IP and self.ipv4().proto == in_proto.IPPROTO_TCP

    def isUDP(self):
        return self.eth().ethertype == ether_types.ETH_TYPE_IP and self.ipv4().proto == in_proto.IPPROTO_UDP


class Action(object):
    """
    Allows to create an OpenFlow Action array without setting anything twice.
    """

    def __init__(self, of: OpenFlow):

        self.of = of

        self._srcMac = None
        self._dstMac = None
        self._srcIP = None
        self._dstIP = None
        self._srcPort = None
        self._dstPort = None
        self._outport = None
        self._toTable = None
        self._isTCP = True

    def build(self):
        actions = []
        if self._srcMac != None:
            actions.append(self.of.parser.OFPActionSetField(eth_src=self._srcMac))
        if self._dstMac != None:
            actions.append(self.of.parser.OFPActionSetField(eth_dst=self._dstMac))
        if self._srcIP != None:
            actions.append(self.of.parser.OFPActionSetField(ipv4_src=self._srcIP))
        if self._dstIP != None:
            actions.append(self.of.parser.OFPActionSetField(ipv4_dst=self._dstIP))
        if self._srcPort != None:
            # TODO https://stackoverflow.com/questions/337688/dynamic-keyword-arguments-in-python
            if self._isTCP:
                actions.append(self.of.parser.OFPActionSetField(tcp_src=self._srcPort))
            else:
                actions.append(self.of.parser.OFPActionSetField(udp_src=self._srcPort))
        if self._dstPort != None:
            if self._isTCP:
                actions.append(self.of.parser.OFPActionSetField(tcp_dst=self._dstPort))
            else:
                actions.append(self.of.parser.OFPActionSetField(udp_dst=self._dstPort))
        if self._outport != None:
            actions.append(self.of.parser.OFPActionOutput(self._outport, 0))  # REVIEW: Is max_len = 0 correct?

        return actions

    def buildInstructions(self):

        actions = self.build()
        inst = []
        instType = self.of.proto.OFPIT_APPLY_ACTIONS

        if actions:
            inst = [self.of.parser.OFPInstructionActions(instType, actions)]

        if self._toTable is not None:
            inst.append(self.of.parser.OFPInstructionGotoTable(self._toTable))

        return inst

    def setUDP(self, isUDP: bool):
        self._isTCP = not isUDP
        return self

    def outport(self, outport):  # outport == None --> flood

        assert self._outport is None  # only one outport is possible
        self._outport = self.of.proto.OFPP_FLOOD if outport is None else outport
        return self

    def sendToController(self):

        return self.outport(self.of.proto.OFPP_CONTROLLER)

    def flood(self):

        return self.outport(self.of.proto.OFPP_FLOOD)

    def gotoTable(self, table):

        self._toTable = table
        return self

    def setDestination(self, mac, ip, port):

        if mac != None:
            self._dstMac = mac
        if ip != None:
            self._dstIP = ip
        if port != None:
            self._dstPort = port
        return self

    def setSource(self, mac, ip, port):

        if mac != None:
            self._srcMac = mac
        if ip != None:
            self._srcIP = ip
        if port != None:
            self._srcPort = port
        return self


class Match(object):
    """
    Allows to create a combined OpenFlow Match object over several classes.
    """

    def __init__(self, of: OpenFlow, *args, **kwargs):

        self.of = of
        self.args = args
        self.kwargs = kwargs

    def inport(self, inport):
        self.kwargs["in_port"] = inport
        return self

    def srcIP(self, ip, mask="255.255.255.255"):
        self.kwargs["eth_type"] = OpenFlow.ETH_TYPE_IP
        self.kwargs["ipv4_src"] = (ip.ip, mask) if isinstance(ip, IPAddr) else (ip, mask)
        return self

    def dstIP(self, ip, mask="255.255.255.255"):
        self.kwargs["eth_type"] = OpenFlow.ETH_TYPE_IP
        self.kwargs["ipv4_dst"] = (ip.ip, mask) if isinstance(ip, IPAddr) else (ip, mask)
        return self

    def srcPort(self, port):
        self.kwargs["ip_proto"] = self.of.packet().ipv4().proto

        if self.kwargs["ip_proto"] == OpenFlow.IPPROTO_TCP:
            self.kwargs["tcp_src"] = port
        else:
            self.kwargs["udp_src"] = port
        return self

    def dstPort(self, port):
        self.kwargs["ip_proto"] = self.of.packet().ipv4().proto

        if self.kwargs["ip_proto"] == OpenFlow.IPPROTO_TCP:
            self.kwargs["tcp_dst"] = port
        else:
            self.kwargs["udp_dst"] = port
        return self

    def build(self):

        return self.of.parser.OFPMatch(*self.args, **self.kwargs)


class Message(object):
    """
    Base class for OpenFlow messages.
    """

    def __init__(self, of: OpenFlow):
        self.of = of
        self._event = of.event
        self._dp = of.dp
        self.msg = None

    def _initBufferID(self):
        # Set buffer_id to the incoming value (but messages like OFPSwitchFeatures do not have the attribute)
        #
        if hasattr(self._event, 'msg') and hasattr(self._event.msg, 'buffer_id'):
            self.msg.buffer_id = self._event.msg.buffer_id

    def hasBufferID(self):
        return self.of.hasBufferID()

    def send(self):
        assert self._event is not None
        assert self._dp is not None
        assert self.msg is not None

        self._dp.send_msg(self.msg)


class FlowMod(Message):
    """
    Sends out OpenFlow FlowMod messages (ofp_parser.OFPFlowMod).
    """

    def __init__(self, of: OpenFlow):
        super().__init__(of)
        self._packetOutAction = None

        # initialize message with default values (see https://github.com/faucetsdn/ryu/blob/master/ryu/ofproto/ofproto_v1_3_parser.py)
        self.msg = self._dp.ofproto_parser.OFPFlowMod(self._dp)
        self._initBufferID()

    def priority(self, priority):

        self.msg.priority = priority
        return self

    def table(self, tableID):

        self.msg.table_id = tableID
        return self

    def idleTimeout(self, timeout):

        if timeout != None:
            self.msg.idle_timeout = timeout
        return self

    def match(self, match):

        if isinstance(match, Match):
            match = match.build()
        self.msg.match = match
        return self

    # If packetOut == 'True' then the output action is already included in the action. Otherwise, it's the output port.
    #
    # NOTE: Any gotoTable actions will be ignored (for the PacketOut only!) since these are not possible for PacketOut.
    #
    def actions(self, actions: Action, packetOut=False):

        self.msg.instructions = actions.buildInstructions()

        if isinstance(packetOut, bool):
            if packetOut:  # output action is already included
                assert actions._outport != None and actions._outport != self.of.proto.OFPP_CONTROLLER
                self._packetOutAction = actions.build()
        else:  # outport or None
            self._packetOutAction = self.of.Action().outport(packetOut).build()
        return self

    def send(self):
        super().send()

        if self._packetOutAction != None:
            #
            # If there is no valid bufferID, the packet was not buffered by the switch -> we need to send it out.
            # With a valid bufferID, however, if we already sent a FlowMod for the same message, we would like
            # to avoid this unnecessary message.
            #
            if not self.hasBufferID():
                self.of.PacketOut().actions(self._packetOutAction).send()

    def clearTable(self):
        """
        Clear table number `tableID` (0..n).
        """

        self.msg.command = self._dp.ofproto.OFPFC_DELETE

        self.msg.out_port = self._dp.ofproto.OFPP_ANY  # required for DELETE to work !!!
        self.msg.out_group = self._dp.ofproto.OFPG_ANY  # required for DELETE to work !!!
        self.send()

        # Set barrier (otherwise flows added later might be deleted)
        #
        self.of.BarrierRequest().send()


class PacketOut(Message):
    """
    Sends out OpenFlow PacketOut messages (ofp_parser.OFPPacketOut).
    """

    def __init__(self, of: OpenFlow):
        super().__init__(of)

        self.msg = self._dp.ofproto_parser.OFPPacketOut(self._dp, in_port=self._event.msg.match['in_port'])
        self._initBufferID()

        if self.msg.buffer_id == self._dp.ofproto.OFP_NO_BUFFER:
            self.msg.data = self._event.msg.data

    def actions(self, actions):

        if isinstance(actions, Action):  # FlowMod might pass an actions list
            actions = actions.build()
        self.msg.actions = actions
        return self


class BarrierRequest(Message):
    def __init__(self, of: OpenFlow):
        super().__init__(of)

        self.msg = of.parser.OFPBarrierRequest(self._dp)


class ArpRequest(Message):
    def __init__(self, of: OpenFlow, dstIP: IPAddr):
        super().__init__(of)

        self.dstIP = dstIP
        self.msg = self._dp.ofproto_parser.OFPPacketOut(
            self._dp, buffer_id=0xffffffff, in_port=self._dp.ofproto.OFPP_CONTROLLER)

    def src(self, mac, ip):
        self.srcMac = mac
        self.srcIP = IPAddr(ip)
        return self

    def send(self):
        #
        # Real-world ARP request:
        #
        # arp(dst_ip='10.0.2.100',dst_mac='00:00:00:00:00:00',hlen=6,hwtype=1,opcode=1,plen=4,proto=2048,src_ip='10.0.1.100',src_mac='02:00:00:00:01:01')
        # ethernet(dst='ff:ff:ff:ff:ff:ff',ethertype=2054,src='02:00:00:00:01:01')
        #
        e = ethernet.ethernet(dst="ff:ff:ff:ff:ff:ff", src=self.srcMac, ethertype=ether_types.ETH_TYPE_ARP)
        a = arp.arp(
            hwtype=arp.ARP_HW_TYPE_ETHERNET,
            proto=ether_types.ETH_TYPE_IP,
            hlen=6,
            plen=4,
            opcode=arp.ARP_REQUEST,
            src_mac=self.srcMac,
            src_ip=str(self.srcIP),
            dst_mac="00:00:00:00:00:00",
            dst_ip=str(self.dstIP))

        p = ryuPacket.Packet()
        p.add_protocol(e)
        p.add_protocol(a)
        p.serialize()
        self.msg.data = p.data
        self.msg.actions = [self._dp.ofproto_parser.OFPActionOutput(self._dp.ofproto.OFPP_FLOOD, 0)]
        super().send()
