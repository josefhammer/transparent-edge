# Josef Hammer (josef.hammer@aau.at)
#
from __future__ import annotations
import yaml

from util.Service import Service, ServiceInstance
from util.IPAddr import IPAddr
from util.SocketAddr import SocketAddr


class K8sService(object):
    """
    Interface to K8s edge services.
    """
    LABEL_NAME = "edge.service"

    def __init__(self, label, filename=None, yml: dict = None):

        self.label = label
        self.port = None
        self.nodePort = None
        self.podPort = None
        self.clusterIP = None
        self.type = None
        self.yaml = None

        self.containsService = False
        self.containsDeployment = False

        assert (filename is not None or yml is not None)  # only one of both allowed
        if filename is not None:
            self.yaml = self._loadYaml(filename)
        else:
            self.yaml = yml
        self._parseYaml(self.yaml)

    def annotate(self):

        assert (self.yaml is not None)
        for item in self.yaml:
            #
            # set unique label to be able to query it
            #
            self._addLabel(item)

            if item.get("kind") == "Deployment":
                self._addLabel(item["spec"]["template"])  # must be available

    def _addLabel(self, item):
        item.setdefault("metadata", {}).setdefault("labels", {})[K8sService.LABEL_NAME] = self.label

    def toService(self, edgeIP: IPAddr):  # -> returns Service or ServiceInstance
        #
        # REVIEW Move somewhere else? Refactor?
        #
        if self.label is None:  # e.g. if read from K8s with missing label
            print("missing label")
            return None

        service = Service(vAddr=None, label=self.label)
        service.vAddr = SocketAddr(IPAddr.get_ipv4_by_hostname(service.domain())[0], self.port)

        # Return service only if no instance is known/available
        #
        if edgeIP is None or self.clusterIP is None:
            return service

        if self.type == "LoadBalancer":
            ePort = self.port
        else:
            # ATTENTION: We use the 'node'Port as edgePort !! e.g. 31097
            ePort = self.nodePort
            if ePort == None:
                ePort = 0

        # REVIEW Have only eAddr or nAddr in the future? (depending on config flag?)
        #
        eAddr = SocketAddr(edgeIP, ePort)
        nAddr = SocketAddr(self.clusterIP, self.port)  # nodeAddr

        return ServiceInstance(service, eAddr, nAddr)

    def _parseYaml(self, yml):
        """
        Extracts the necessary service information.
        """
        for item in yml:
            kind = item.get("kind")

            if "Deployment" == kind:
                self.containsDeployment = True

            if "Service" == kind:
                self._parseServiceDef(item)

    def _parseServiceDef(self, yml: dict):
        """
        Extracts the necessary information from a K8s Service definition.
        """
        self.containsService = True

        # read label (if available)
        #
        self.label = yml.get("metadata", {}).get('labels', {}).get(K8sService.LABEL_NAME, self.label)

        # read type (if available)
        #
        self.type = yml.get("spec", {}).get('type')  # e.g. "LoadBalancer"

        # read clusterIP (if available)
        #
        self.clusterIP = yml.get("spec", {}).get('cluster_ip')  # 'clusterIP' when exported via kubectl

        # read the service port (and node_port if available)
        #
        ports = yml.get("spec", {}).get("ports", [])
        for port in ports:
            self.port = port.get("port")
            self.nodePort = port.get('node_port')  # 'nodePort' when exported via kubectl

            # K8s: If targetPort is not defined, it is 'port' by default.
            # The key is called 'targetPort' in Yaml and 'target_port' in the API.
            #
            self.podPort = port.get("targetPort", port.get('target_port', self.port))

            # REVIEW currently, we use only one port (could be more, though; in particular with node ports)
            break

    def _loadYaml(self, filename):

        with open(filename) as file:
            return list(yaml.safe_load_all(file))

    def _saveYaml(self, filename):

        with open(filename, 'w') as file:
            yaml.dump_all(self.yaml, file, default_flow_style=False)

    def __eq__(self, other):
        if (isinstance(other, K8sService)):
            return self.label == other.label
        return False

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "{}:{}".format(self.label, self.port)
