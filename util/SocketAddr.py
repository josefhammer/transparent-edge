# Josef Hammer (josef.hammer@aau.at)
#
"""
SocketAddr class.
"""

from util.IPAddr import IPAddr


class SocketAddr(object):
    """
    Tuple: ip, port, (mac)
    """

    def __init__(self, ip, port=0, mac=None):  # port 0: 'any port'
        if not isinstance(ip, IPAddr):
            ip = IPAddr(ip)
        if not isinstance(port, int):
            port = int(port)
        self.ip = ip
        self.port = port
        self.mac = mac

    def __eq__(self, other):
        if (isinstance(other, SocketAddr)):
            return self.ip == other.ip and (self.port == other.port or self.port == 0 or other.port == 0)
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key  # WARNING: Port == 0 won't work for matching!
        return hash((self.ip, self.port))

    def __repr__(self):
        return "{}:{}".format(self.ip, self.port)
