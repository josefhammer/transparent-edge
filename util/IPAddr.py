# Josef Hammer (josef.hammer@aau.at)
#
"""
IPAddr class.
"""

# ipaddress lib: https://docs.python.org/3/library/ipaddress.html

from ipaddress import ip_address, IPv4Address, IPv4Network
import socket


class IPAddr(object):
    """
    IPv4Address class. 
    """
    __slots__ = ["ip"]

    def __init__(self, ip):
        if isinstance(ip, str):
            ip = int(IPv4Address(ip))
        elif isinstance(ip, IPAddr):
            ip = ip.ip
        self.ip = ip
        """ IPv4 address as int (most significant octet first). """

    def isPrivateIP(self):
        return ip_address(self.ip).is_private

    def privateIPMask(self):
        """ Returns an IP mask that matches all IP addresses in the same private network. """

        ip = str(self)

        if ip.startswith("192.") or ip.startswith("172.") or ip.startswith("169."):
            return "255.255.0.0"
        if ip.startswith("10."):
            return "255.0.0.0"
        return None  # includes "0.0.0.0" and "255.255.255.255"

    @staticmethod
    def cidrToIPMask(cidr):

        return IPv4Network(cidr, False).netmask

    @staticmethod
    def get_ipv4_by_hostname(hostname) -> list:
        #
        # Source: https://stackoverflow.com/questions/2805231/how-can-i-do-dns-lookups-in-python-including-referring-to-etc-hosts
        #
        return list(i  # raw socket structure
                    [4]  # internet protocol info
                    [0]  # address
                    for i in socket.getaddrinfo(
                        hostname,
                        0  # port, required
                    ) if i[0] is socket.AddressFamily.AF_INET  # ipv4

                    # ignore duplicate addresses with other socket types
                    and i[1] is socket.SocketKind.SOCK_RAW)

    def __eq__(self, other):
        if (isinstance(other, IPAddr)):
            return self.ip == other.ip
        return False

    def __ne__(self, other):
        return not self == other

    # necessary to be used as dict key
    #
    def __hash__(self):
        return hash(self.ip)

    def __repr__(self):
        return str(IPv4Address(self.ip))
