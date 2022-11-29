# Josef Hammer (josef.hammer@aau.at)
#
"""
Classes regarding edge services.

NOTE: The variable names usually used are:
- service: Service
- svc: ServiceInstance
- serviceDef: K8sService
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
    def uniqueName(label: str):  # REVIEW Move/refactor/...?
        return label.replace('.', '-')

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

    def __init__(self, service: Service, edgeIP: IPAddr):

        self.service = service
        self.edgeIP = edgeIP
        self.eAddr = None  # edge service address (depends on config flags)

        self.publicAddr = None
        self.clusterAddr = None
        self.podAddr = None

        self.deployment: Deployment = None
        self.containers = []  # REVIEW

    def __eq__(self, other):
        if (isinstance(other, ServiceInstance)):
            return self.service == other.service and self.edgeIP == other.edgeIP and self.eAddr == other.eAddr
        return False

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "{} @ {} ({}) [{}]".format(self.service, self.edgeIP, self.eAddr or '-', self.deployment)


class Deployment(object):
    """
    Contains all the data about a single edge service deployment.
    """

    def __init__(self, replicas=0, ready_replicas=0):

        self.replicas = replicas  # configured replicas (not the actual ones)
        self.ready_replicas = ready_replicas

    def __repr__(self):
        return "replicas={}/{}".format(self.ready_replicas, self.replicas)


class Pod(object):
    """
    Contains the necessary data about a single pod.
    """

    def __init__(self, ip, status):

        self.ip = ip
        self.status = status


class Container(object):
    """ 
    Contains all data about a container.
    ---
    imagePullPolicy: https://kubernetes.io/docs/concepts/containers/images/
    
    IfNotPresent: the image is pulled only if it is not already present locally.
    
    Always: every time the kubelet launches a container, the kubelet queries the container image registry to resolve
    the name to an image digest. If the kubelet has a container image with that exact digest cached locally, the
    kubelet uses its cached image; otherwise, the kubelet pulls the image with the resolved digest, and uses that
    image to launch the container.

    Docker: --pull [default: missing]: Pull image before creating ("always"|"missing"|"never").
    """

    def __init__(self, name: str, image: str):

        self.name = name
        self.image = image
        self.ports = []
        self.volumes = {}  # name -> mountPath
        self.imagePullPolicy = "IfNotPresent"  # IfNotPresent | Always | Never

    def __repr__(self):
        return f"{self.name}: {self.image} {self.ports}"
