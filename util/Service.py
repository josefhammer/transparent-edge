# Josef Hammer (josef.hammer@aau.at)
#
"""
Classes regarding edge services.
"""

from util.SocketAddr import SocketAddr


class Service(object):
    """
    Contains the data about a virtual service.
    """

    def __init__(self, vAddr: SocketAddr, domain, name):

        self.vAddr = vAddr
        self.domain = domain
        self.name = name  # e.g. K8s service label or name

    def __eq__(self, other):
        if (isinstance(other, Service)):
            return self.vAddr == other.vAddr
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash(self.vAddr)

    def __repr__(self):
        return "{}:{} ({}, {})".format(self.domain, self.vAddr.port, self.name, self.vAddr.ip)


class ServiceInstance(dict):
    """
    Contains all the data for a single edge service instance.
    """

    def __init__(self, service: Service, eAddr: SocketAddr, nAddr: SocketAddr):

        self.service = service
        self.eAddr = eAddr  # edge address (= ingress)
        self.nAddr = nAddr  # node address (= actual edge node)

    def __eq__(self, other):
        if (isinstance(other, ServiceInstance)):
            return self.service == other.service and self.eAddr == other.eAddr and self.nAddr == other.nAddr
        return False

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "{} @ {} ({})".format(self.service, self.eAddr, self.nAddr)
