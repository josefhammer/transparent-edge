# Josef Hammer (josef.hammer@aau.at)
#
"""
Listens to ARP requests/replies to gather information about IP->MAC mapping 
and the corresponding switch ports.
"""

from util.RyuOpenFlow import OpenFlow
from util.IPAddr import IPAddr
from util.EdgeTools import Host


class ArpTracker(object):
    """
    Does NOT clear the table!
    """

    def __init__(self, log, tableID, srcMac, installFlow=False, fwdTable=None, flowPriority=3):

        self.log = log
        self.table = tableID
        self.srcMac = srcMac
        self.installFlow = installFlow
        self.fwdTable = fwdTable
        self.flowPrio = flowPriority

    def connect(self, of: OpenFlow):

        log = self.log
        log.info("Connected.")

        # Install default flow to send ARP packets to the controller.
        #
        # To keep the load low, we send only ARP packets intended for us to the controller.
        #
        if self.installFlow:
            actions = of.Action().sendToController()
            if self.fwdTable:
                actions.gotoTable(self.fwdTable)

            of.FlowMod().table(self.table).priority(self.flowPrio).match(
                of.Match(eth_dst=self.srcMac, eth_type=of.ETH_TYPE_ARP)).actions(actions).send()

    def connected(self, of: OpenFlow):

        # ATTENTION: We won't receive any ARP responses if we use our own MAC address as source!
        #
        srcMac = self.srcMac
        switch = of.switch
        assert (srcMac != switch.mac)

        # populate default forwarding table with data about the gateway to speed things up
        #
        if switch.gateway:
            of.ArpRequest(switch.gateway).src(srcMac, "169.254.42.42").send()  # use an APIPA private IP

        # ARP request for all local edge servers we need to track
        #
        # ATTENTION: Do not use a known IP address ... we might not get an answer then.
        #
        for edge in switch.edges:
            of.ArpRequest(edge.ip).src(srcMac, "169.254.42.42").send()  # use an APIPA private IP
            self.log.info("ARP request sent for {}".format(edge.ip))

            # Unfortunately, we don't get a response for the gateway if we are the gateway switch. Thus,
            # we add our own MAC address manually.
            #
            if edge.ip == switch.gateway:
                self._setArp(self.log, of.dpid, switch.hosts, eth_src=switch.mac, ip_src=switch.gateway)

    def packetIn(self, of: OpenFlow):
        # Note: arp.hwsrc is not necessarily equal to ethernet.src
        # (one such example are arp replies generated by this module itself
        # as ethernet mac is set to switch dpid) so we should be careful
        # to use only arp addresses in the learning code!

        if not of.msg.table_id == self.table:
            return  # not our business

        packet = of.packet()
        arp = packet.arp()
        if not arp:
            return  # not our business

        log = self.log

        log.debug("ARP %s/%s => %s/%s", str(arp.src_ip), str(arp.src_mac), str(arp.dst_ip), str(arp.dst_mac))

        if arp.proto == of.ETH_TYPE_IP:
            if arp.hwtype == of.ARP_HW_TYPE_ETHERNET:
                if arp.src_ip != 0:
                    self._setArp(log, of.dpid, of.switch.hosts, eth_src=arp.src_mac, ip_src=arp.src_ip)

    def _setArp(self, log, dpid, swHosts, eth_src, ip_src):
        #
        # Adds or updates an Arp entry
        #
        ip_src = IPAddr(ip_src)
        newHost = Host(ip_src, eth_src)

        if ip_src not in swHosts:

            log.info("*** Added %s", newHost)

        else:
            old = swHosts[ip_src]

            if old != newHost:
                log.info("*** Updated %s (%s->%s)", ip_src, old.mac, eth_src)
            else:
                log.debug("*** Refreshed %s", old)

        swHosts[ip_src] = newHost

        for _, host in swHosts.items():
            log.debug("({}) {}".format(dpid, host))
