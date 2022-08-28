# (c) 2022 Josef Hammer (josef.hammer@aau.at)
#
from util.RyuOpenFlow import OpenFlow
from .Context import Context


class PortTracker:
    """
    Level 2 tracker for the switch ports to send out packets for a specific MAC address.

    Does NOT track hosts -- the MAC address might be a gateway address only.
    """

    def __init__(self, context: Context, log):

        self.log = log

    def connect(self, of: OpenFlow):

        log = self.log
        log.info("Connected.")

    def connected(self, of: OpenFlow):
        pass

    def packetIn(self, of: OpenFlow):

        packet = of.packet()
        if not packet.hasValidPort() or packet.isLLDP():
            return  # ignore

        log = self.log
        mac2port = of.switch.mac2port

        inport = packet.inport()
        mac = of.src.mac

        prevInport = mac2port.get(mac)

        if not prevInport:
            mac2port[mac] = inport
            log.debug("Learned %s on port %s" % (mac, inport))

        elif prevInport != inport:
            mac2port[mac] = inport
            log.debug("Updated %s: port %s -> %s" % (mac, prevInport, inport))
