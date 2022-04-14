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


class HostTable(dict):
    """ 
    Dict: IPAddr -> Host
    """

    def __setitem__(self, key, val):
        if not isinstance(val, Host):
            val = Host(val)
        if not isinstance(key, IPAddr):
            key = IPAddr(key)
        assert key == val.ip
        dict.__setitem__(self, key, val)

    def __delitem__(self, key):
        dict.__delitem__(self, key)

    def __repr__(self):
        return str(self.values())


class SwitchTable(dict):
    """ 
    Dict: DPID -> HostTable
    """

    def __setitem__(self, key, val):
        if not isinstance(val, HostTable):
            val = HostTable(val)
        if not isinstance(key, DPID):
            key = DPID(key)
        dict.__setitem__(self, key, val)

    def __delitem__(self, key):
        dict.__delitem__(self, key)

    def __str__(self):
        return "{" + ', '.join(['%s: %s' % (key, value) for (key, value) in self.items()]) + "}"


class Switch(object):
    """
    Tuple: name, mac, [ports], vMac

    The vMac might be different for each switch (it's the MAC of the gateway), 
    thus it's not stored together with the Service.
    """

    def __init__(self, ports):
        self.name = ports[0].name.decode('UTF-8')
        self.mac = ports[0].hw_addr
        self.ports = ports
        self.vMac = None  # the virtual MAC address to be used for ServiceIDs
        self.mac2port = {}  # MAC -> outport
        self.gateway = None

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
        return ", ".join(["{}={}".format(port.name.decode('UTF-8'), port.hw_addr) for port in self.ports[0:]])


class Switches(dict):
    """ 
    Dict: DPID -> Switch
    """

    def __setitem__(self, key, val):
        if not isinstance(key, DPID):
            key = DPID(key)
        if not isinstance(val, Switch):
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

    def __init__(self, ip, dpid, serviceCidr=[]):

        assert isinstance(serviceCidr, list)

        self.ip = IPAddr(ip)
        self.dpid = DPID(dpid)
        self.serviceCidr = serviceCidr

        self.vServices = {}  # SocketAddr -> ServiceInstance
        self.eServices = {}  # SocketAddr -> ServiceInstance
        self.nServices = {}  # SocketAddr -> ServiceInstance

    def __eq__(self, other):
        if (isinstance(other, Edge)):
            return self.ip == other.ip
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash(self.ip)

    def __repr__(self):
        return "{}".format(self.ip)
