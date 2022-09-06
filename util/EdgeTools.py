# Josef Hammer (josef.hammer@aau.at)
#
"""
Provides containers for the other components.
"""

from util.RyuDPID import DPID
from util.IPAddr import IPAddr


class Host(object):
    """
    Tuple: IPAddr, MacAddr
    """

    def __init__(self, ip, mac):
        self.ip = ip
        if not isinstance(self.ip, IPAddr):
            self.ip = IPAddr(self.ip)
        self.mac = mac

    def __eq__(self, other):
        if (isinstance(other, Host)):
            return self.ip == other.ip and self.mac == other.mac
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash((self.ip, self.mac))

    def __repr__(self):
        return "{} ({})".format(str(self.ip), self.mac)


class Switch(object):
    """
    Tuple: name, mac, [ports], vMac

    The vMac might be different for each switch (it's the MAC of the gateway), 
    thus it's not stored together with the Service.
    """

    def __init__(self, dpid: DPID, gateway: IPAddr):
        self.dpid: DPID = dpid
        self.gateway: IPAddr = gateway
        self.vMac = None  # the virtual MAC address to be used for ServiceIDs
        self.mac2port = {}  # MAC -> outport
        self.hosts = {}  # IPAddr -> Host
        self.edges = []
        self.listeners = []

        self.name = self.mac = self.ports = None  # initialized in self.init(ports)

    def init(self, ports):
        self.name = ports[0].name.decode('UTF-8')
        self.mac = ports[0].hw_addr
        self.ports = ports

    def portFor(self, mac):
        return self.mac2port.get(mac)

    def __eq__(self, other):
        if (isinstance(other, Switch)):
            return self.mac == other.mac
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash(self.mac)

    def __repr__(self):
        return ", ".join(["{}={}".format(port.name.decode('UTF-8'), port.hw_addr)
                          for port in self.ports[0:]]) + " gateway=" + str(self.gateway)


class Switches(dict):
    """ 
    Dict: DPID -> Switch
    """

    def __setitem__(self, key, val):
        if not isinstance(key, DPID):
            key = DPID(key)
        if val is not None and not isinstance(val, Switch):
            val = Switch(val)
        dict.__setitem__(self, key, val)

    def __delitem__(self, key):
        dict.__delitem__(self, key)

    def __str__(self):
        return "{" + ', '.join(['%s: %s' % (key, value) for (key, value) in self.items()]) + "}"


class Edge(object):
    """
    Contains all the data for one edge location.
    """

    def __init__(self, ip, switch, target: str, serviceCidr=[], schedulerName: str = None):

        assert isinstance(serviceCidr, list)

        self.ip = IPAddr(ip)
        self.switch = switch  # each edge is connected to a single switch
        self.target = "pod" if target is None else target  # pod | cluster | exposed
        self.serviceCidr = serviceCidr
        self.cluster = None
        self.schedulerName = schedulerName

        self.vServices = {}  # SocketAddr -> ServiceInstance
        self.eServices = {}  # SocketAddr -> ServiceInstance

    @property
    def dpid(self):
        return self.switch.dpid

    def __eq__(self, other):
        if (isinstance(other, Edge)):
            return self.ip == other.ip
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash(self.ip)

    def __repr__(self):
        return "{}-{} {}".format(self.ip, self.target, self.serviceCidr)
