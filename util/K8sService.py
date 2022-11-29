# Josef Hammer (josef.hammer@aau.at)
#
from __future__ import annotations
import yaml

from util.Service import Service, ServiceInstance, Container
from util.IPAddr import IPAddr
from util.SocketAddr import SocketAddr


class K8sService(object):
    """
    Interface to K8s edge services.
    """
    LABEL_NAME = "edge.service"

    def __init__(self, service=None, label=None, port=None, filename=None, yml: dict = None):

        self.service = service
        if service:
            self.label = service.label
            self.port = service.vAddr.port
        else:
            self.label = label
            self.port = port
        self.nodePort = None
        self.podPort = None
        self.clusterIP = None
        self.type = None
        self.replicas = 0
        self.yaml = []

        self._serviceDef = None  # pointer to the yaml item (if avail)
        self._deploymentDef = None  # pointer to the yaml item (if avail)
        self._containers = None

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

    def annotate(self, schedulerName: str = None, replicas: int = 0):

        assert (self.yaml is not None)
        self.replicas = replicas

        if not self._serviceDef:
            self.yaml.append({'apiVersion': 'v1', 'kind': 'Service'})

        for item in self.yaml:
            self._setName(item)
            self._addLabel(item)  # set unique label

            if item.get("kind") == "Deployment":
                self._addLabel(item["spec"]["template"])  # spec.template must be available
                self._setSelector(item, matchLabels=True)

                # set (initial) number of replicas
                #
                item["spec"]["replicas"] = replicas

                # set schedulerName in case we want a local intra-cluster scheduler for this service
                #
                if schedulerName:
                    item["spec"]["template"]["spec"]["schedulerName"] = schedulerName

            if item.get("kind") == 'Service':

                self._setSelector(item)
                item.setdefault('spec', {})['type'] = 'NodePort'  # or 'LoadBalancer'

                # if no targetPort is defined, we use the first containerPort  # REVIEW
                #
                if not self.podPort:
                    for cont in self._containers:
                        for port in cont.ports:
                            self.podPort = port
                            break
                        if self.podPort:
                            break

                # REVIEW Currently, we completely replace any existing port definitions.
                #
                item.setdefault('spec', {})['ports'] = [{
                    'port': self.port,
                    'targetPort': self.podPort or self.port,
                    'protocol': 'TCP'
                }]

    def _addLabel(self, item):
        item.setdefault("metadata", {}).setdefault("labels", {})[K8sService.LABEL_NAME] = self.label

    def _setName(self, item):
        item.setdefault('metadata', {})['name'] = Service.uniqueName(self.label)

    def _setSelector(self, item, matchLabels=False):

        sel = item.setdefault('spec', {}).setdefault('selector', {})
        if matchLabels:
            sel = sel.setdefault('matchLabels', {})
        sel[K8sService.LABEL_NAME] = self.label

    def toService(self, edgeIP: IPAddr) -> ServiceInstance:
        #
        # REVIEW Move somewhere else? Refactor?
        #
        if self.label is None:  # e.g. if read from K8s with missing label
            print("missing label")
            return None

        if edgeIP is None or self.clusterIP is None:
            return None

        service = ServiceInstance(
            Service(vAddr=self.service.vAddr if self.service else None, label=self.label, port=self.port), edgeIP)
        service.clusterAddr = SocketAddr(self.clusterIP, self.port)

        if self.podPort:
            service.podAddr = SocketAddr(0, self.podPort)  # REVIEW Needs to be replaced by real Pod IP later

        # public address: use LoadBalancer if avail, otherwise NodePort routing
        #
        if self.type == "LoadBalancer":
            service.publicAddr = SocketAddr(edgeIP, self.port)
        elif self.nodePort:
            service.publicAddr = SocketAddr(edgeIP, self.nodePort)
        # else publicAddr==None
        return service

    def _parseYaml(self, yml):
        """
        Extracts the necessary service information.
        """
        for item in yml:
            kind = item.get("kind")

            if "Deployment" == kind:
                self._parseDeployDef(item)

            if "Service" == kind:
                self._parseServiceDef(item)

    def _parseDeployDef(self, yml: dict):
        """
        Extracts the necessary information from a K8s Service definition.
        """
        self._deploymentDef = yml
        self._containers = self.containers()
        self.replicas = self._get(yml, "spec", "replicas", 0)

    def containers(self) -> list[Container]:

        if self._containers:
            return self._containers

        assert (self._deploymentDef)
        result = []

        # read template (if available)
        #
        template = self._get(self._deploymentDef, "spec", 'template')
        containers = self._get(template, "spec", 'containers')

        # Example: [{'name': 'web-tiny-asm', 'image': 'josefhammer/web-tiny-asm:amd64',
        #            'ports': [{'containerPort': 8080}]}]
        #
        for container in containers:

            cont = Container(container.get('name'), container.get('image'))
            result.append(cont)

            for port in container.get('ports', []):
                containerPort = port.get("containerPort")

                if containerPort:
                    cont.ports.append(containerPort)

        return result

    def _parseServiceDef(self, yml: dict):
        """
        Extracts the necessary information from a K8s Service definition.
        """
        self._serviceDef = yml

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
            self.podPort = port.get("targetPort", port.get('target_port', None))

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
