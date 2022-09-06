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

    def __init__(self, label=None, port=None, filename=None, yml: dict = None):

        self.label = label
        self.port = port
        self.nodePort = None
        self.podPort = None
        self.clusterIP = None
        self.type = None
        self.yaml = []

        self.containsService = False
        self.containsDeployment = False

        # NOTE: info from filename has precedence over yaml
        #
        if not filename is None:
            if self.label is None:
                self.label = Service.labelFromServiceFilename(filename)
            if self.port is None:
                self.port = Service.portFromServiceFilename(filename)

        assert (filename is not None or yml is not None)  # only one of both allowed
        if filename is not None:
            self.yaml = self._loadYaml(filename)
        elif yml is not None:
            self.yaml = yml
        self._parseYaml(self.yaml)

    def annotate(self, schedulerName: str = None):

        assert (self.yaml is not None)
        for item in self.yaml:
            #
            # set unique label to be able to query both service and deployment
            #
            self._addLabel(item)

            if item.get("kind") == "Deployment":
                self._addLabel(item["spec"]["template"])  # must be available

                # set schedulerName in case we want a local intra-cluster scheduler for this service
                #
                if schedulerName:
                    item["spec"]["template"]["spec"]["schedulerName"] = schedulerName

    def _addLabel(self, item):
        item.setdefault("metadata", {}).setdefault("labels", {})[K8sService.LABEL_NAME] = self.label

    def toService(self, edgeIP: IPAddr, target: str):  # -> returns Service or ServiceInstance
        #
        # REVIEW Move somewhere else? Refactor?
        #
        if self.label is None:  # e.g. if read from K8s with missing label
            print("missing label")
            return None

        service = Service(vAddr=None, label=self.label, port=self.port)

        # Return only service if no instance is known/available
        #
        if edgeIP is None or self.clusterIP is None:
            return service

        # Exposed / Cluster / Pod
        #
        if target == "pod":
            eAddr = SocketAddr(self.clusterIP, self.podPort)  # FIXME/REVIEW Needs to be replaced by real IP later

        elif target == "cluster":
            eAddr = SocketAddr(self.clusterIP, self.port)

        elif target == "exposed":
            #
            # use LoadBalancer if avail, otherwise NodePort routing
            #
            ePort = self.port if self.type == "LoadBalancer" else self.nodePort
            assert (ePort != None)
            eAddr = SocketAddr(edgeIP, ePort)

        else:
            assert (False, "Invalid target: Must be pod|cluster|exposed.")

        return ServiceInstance(service, edgeIP, eAddr)

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
        if self.label is None:
            self.label = self._get(yml, "metadata", "labels", {}).get(K8sService.LABEL_NAME, self.label)

        # read type (if available)
        #
        self.type = self._get(yml, "spec", 'type')  # e.g. "LoadBalancer"

        # read clusterIP (if available)
        #
        self.clusterIP = self._get(yml, "spec", 'cluster_ip')  # 'clusterIP' when exported via kubectl

        # read the service port (and node_port if available)
        #
        ports = self._get(yml, "spec", "ports", [])
        for port in ports:
            if self.port is None:
                self.port = port.get("port")
            else:
                assert self.port == port.get("port")
            self.nodePort = port.get('node_port')  # 'nodePort' when exported via kubectl

            # K8s: If targetPort is not defined, it is 'port' by default.
            # The key is called 'targetPort' in Yaml and 'target_port' in the API.
            #
            self.podPort = port.get("targetPort", port.get('target_port', self.port))

            # REVIEW currently, we use only one port (could be more, though; in particular with node ports)
            break

    def _get(self, yml, name1, name2, default=None):
        """
        Returns `default` if yml[`name1`][`name2`] does not exist _OR_ **if value is None**.
        """
        value = yml.get(name1, {})
        if value is None:
            return {}
        value = value.get(name2, {})
        return default if value is None else value

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
