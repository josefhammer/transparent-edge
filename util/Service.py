# Josef Hammer (josef.hammer@aau.at)
#
"""
Classes regarding edge services.
"""

from util.IPAddr import IPAddr
from util.SocketAddr import SocketAddr

import re
import os


class Service(object):
    """
    Contains the data about a virtual service.
    """

    _ip_pattern = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')

    def __init__(self, vAddr: SocketAddr, label, port: int = None):

        self.vAddr = vAddr
        self.label = label

        if (vAddr is None) and (not label is None) and (not port is None):

            self.vAddr = SocketAddr(IPAddr.get_ipv4_by_hostname(self.domain)[0], port)

    @property
    def domain(self):
        address = self.label.split('.')[:-1]  # remove last part (= name)

        if self._ip_pattern.match('.'.join(address)) != None:  # is an IP address
            return '.'.join(address)
        else:  # is a domain name
            return '.'.join(reversed(address))  # reverse the parts

    @property
    def name(self):
        return self.label.rsplit('.', 1)[1]

    @staticmethod
    def labelFromServiceFilename(filename) -> str:
        return os.path.basename(filename).rsplit('.', 2)[0]  # [label, port, extension]

    @staticmethod
    def portFromServiceFilename(filename) -> int:
        return int(os.path.basename(filename).rsplit('.', 2)[1])  # [label, port, extension]

    def __eq__(self, other):
        if (isinstance(other, Service)):
            return self.vAddr == other.vAddr
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):  # necessary to be used as dict key
        return hash(self.vAddr)

    def __repr__(self):
        return "{} ({})".format(self.vAddr, self.label)


class ServiceInstance(object):
    """
    Contains all the data for a single edge service instance.
    """

    def __init__(self, service: Service, edgeIP: IPAddr, eAddr: SocketAddr):

        self.service = service
        self.edgeIP = edgeIP
        self.eAddr = eAddr  # edge service address (depends on config flags)
        self.deployment = Deployment()

    def __eq__(self, other):
        if (isinstance(other, ServiceInstance)):
            return self.service == other.service and self.edgeIP == other.edgeIP and self.eAddr == other.eAddr
        return False

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "{} @ {} ({}) [{}/{} ready]".format(self.service, self.edgeIP, self.eAddr,
                                                   self.deployment.ready_replicas, self.deployment.available_replicas)


class Deployment(object):
    """
    Contains all the data about a single edge service deployment.
    """

    def __init__(self, available_replicas=0, ready_replicas=0):

        self.available_replicas = available_replicas
        self.ready_replicas = ready_replicas


class Pod(object):
    """
    Contains the necessary data about a single pod.
    """

    def __init__(self, ip, status):

        self.ip = ip
        self.status = status
