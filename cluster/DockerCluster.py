from __future__ import annotations

# Disable the warnings triggered by verify_ssl=False
#
import urllib3

urllib3.disable_warnings()  # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings

import docker

from util.IPAddr import IPAddr
from util.Service import Deployment, Pod, ServiceInstance, Service
from util.K8sService import K8sService
from util.SocketAddr import SocketAddr
from cluster.Cluster import Cluster

from logging import WARNING, getLogger

from util.Performance import PerfCounter


class DockerCluster(Cluster):
    """
    Interface to a single Docker cluster.
    """

    def __init__(self,
                 apiServer,
                 tokenFileName,
                 namespace="edge",
                 labelName="edge.service",
                 labelPort="edge.port",
                 log=None):

        self._ip = IPAddr(apiServer.split(":")[0])
        self._namespace = namespace
        self._labelName = labelName
        self._labelPort = labelPort
        self._log = log
        if self._log is None:
            self._log = getLogger("Docker." + str(self._ip))

        # disable DEBUG logs
        getLogger("urllib3").setLevel(WARNING)
        getLogger("docker").setLevel(WARNING)

        self._client = docker.from_env()

        # TODO Implement remote access:
        # https://stackoverflow.com/questions/38286564/docker-tls-verify-docker-host-and-docker-cert-path-on-ubuntu
        #
        # client = docker.DockerClient(base_url='tcp://127.0.0.1:1234')

    def deploy(self, serviceDef: K8sService):

        assert (serviceDef and serviceDef.yaml)

        containers = []
        func = self._client.containers.run if serviceDef.replicas else self._client.containers.create
        hostPaths = serviceDef.volumes()

        perf = PerfCounter()
        for cont in serviceDef.containers():

            # generate volume mounts list
            #
            volumes = [f'{hostPaths[name]}:{path}' for name, path in cont.volumes.items()]

            containers.append(
                func(
                    cont.image,
                    # auto_remove=True,  # we want to keep them after scaling down to zero
                    detach=True,
                    environment=None,  # dict or list
                    labels={
                        self._labelName: serviceDef.label,
                        self._labelPort: str(serviceDef.port),
                    },
                    ports={
                        port: None  # if specific IP only: (self._ip, None)
                        for port in cont.ports
                    },  # None -> random host port; TCP by default
                    volumes=volumes,
                    publish_all_ports=False))

        if serviceDef.replicas:
            # update attrs to get the new auto-assigned ports
            # ports are assigned only on run, not on create!
            for cont in containers:
                cont.reload()

        self._log.info(f"Service <{ str(serviceDef) }> deployed ({ perf.ms() } ms).")

        svc = self._apiResponseToService(containers[0])  # REVIEW port from first container only
        svc.containers = containers
        return svc

    def _scale(self, svc: ServiceInstance, replicas: int):

        for cont in svc.containers:
            if replicas:
                cont.start()
                # update attrs to get the new auto-assigned ports
                # ports are assigned only on run, not on create!
                cont.reload()
                if cont.ports:  # REVIEW Duplicate from _apiResonseToService()
                    svc.clusterAddr = SocketAddr(self._ip, self._getLocalPort(cont))  # REVIEW For K8s in K8sService
                    svc.deployment = Deployment(1, 1)
            else:
                cont.stop()

    def services(self, label: str):

        return self._toMap(label, self.rawServices, lambda i: self._apiResponseToService(i))

    def _apiResponseToService(self, i) -> ServiceInstance:

        service = Service(None, label=i.labels.get(self._labelName), port=int(i.labels.get(self._labelPort)))
        svc = ServiceInstance(service, self._ip)
        svc.containers.append(i)  # REVIEW Works only if service consists of a single container
        if i.ports:
            svc.clusterAddr = SocketAddr(self._ip, self._getLocalPort(i))  # REVIEW For K8s in K8sService
            svc.deployment = Deployment(replicas=1, ready_replicas=1)
        else:
            svc.deployment = Deployment()  # deployed, but no instance running
        return svc

    def rawServices(self, label=None):

        return self._getItems(label, self._client.containers.list)

    def _label(self, item):

        return None if not item else item.labels.get(self._labelName)

    def _labelSelector(self, label):

        return {} if not label else {'label': f'{self._labelName}={label}'}

    def _filterLabelAvailable(self, items):

        if self._labelName is None:
            return items
        return filter(lambda i: self._labelName in i.labels and self._labelPort in i.labels, items)

    def _getItems(self, label, func):

        try:
            ret = func(filters=self._labelSelector(label), all=True)  # all: include stopped containers
            return self._filterLabelAvailable(ret)

        except Exception as e:
            self._log.warn(e)
            return []

    def _getLocalPort(self, container):

        # container.ports:
        # {'8080/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '49153'}, {'HostIp': '::', 'HostPort': '49153'}]}
        #
        return int(container.ports[next(iter(container.ports))][0]['HostPort'])  # only first port in first mapping
