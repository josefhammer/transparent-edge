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

    def deployService(self, service: K8sService):

        assert (service and service.yaml)

        exposedContainer = None

        for name, (image, port) in service.containers().items():
            container = self._client.containers.run(
                image,
                auto_remove=True,
                detach=True,
                environment=None,  # dict or list
                labels={
                    self._labelName: service.label,
                    self._labelPort: str(service.port),
                },
                ports={} if not port else {str(port) + '/tcp': None},  # None -> random host port
                publish_all_ports=False)

            if port:
                assert (not exposedContainer)  # REVIEW: only one port mapping supported
                exposedContainer = container

        self._log.info("Service <" + str(service) + "> deployed.")

        assert (exposedContainer)
        exposedContainer.reload()  # update attrs to get the new auto-assigned ports
        svcInst = self._apiResponseToService(exposedContainer)
        assert (svcInst)

        # REVIEW self.scaleDeployment(svcInst)
        return svcInst

    def scaleDeployment(self, svc: ServiceInstance):

        assert (svc)

        if not svc.deployment or not svc.deployment.replicas:  # we need to scale up
            self._scaleDeployment(svc.service.label, 1)
            self._log.info("Scaling up from zero: " + str(svc))

    def watchDeployment(self, svcInst: ServiceInstance):

        assert (svcInst)
        return self.getService(svcInst.service.label)

    def _scaleDeployment(self, label: str, replicas: int):
        pass

    def services(self, label: str):

        return self._toMap(label, self.rawServices, lambda i: self._apiResponseToService(i))

    def _apiResponseToService(self, i) -> ServiceInstance:

        service = Service(None, label=i.labels.get(self._labelName), port=int(i.labels.get(self._labelPort)))
        svc = ServiceInstance(service, self._ip)
        if i.ports:
            svc.clusterAddr = SocketAddr(self._ip, self._getLocalPort(i))  # REVIEW For K8s in K8sService
            svc.deployment = self._toDeployment(None)
        return svc

    def deployments(self, label=None):

        #FIXME
        if label:
            return {label: self._toDeployment(None)}

        return self._toMap(label, self.rawDeployments, lambda i: self._toDeployment(i))

    def pods(self, label=None):

        return self._toMap(label, self.rawPods, lambda i: Pod(i.status.pod_ip, i.status.phase))

    def rawServices(self, label=None):

        return self._getItems(label, self._client.containers.list)

    def rawDeployments(self, label=None):

        #FIXME
        return self._getItems(label, self._emptyList)

    def _emptyList(self, filters=None):
        return [None]

    def rawPods(self, label=None):

        # FIXME
        return [None]
        return filter(lambda p: p.metadata.deletion_timestamp is None,
                      self._getItems(label, self._k8s.list_namespaced_pod, self._k8s.list_pod_for_all_namespaces))

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
            ret = func(filters=self._labelSelector(label))
            return self._filterLabelAvailable(ret)

        except Exception as e:
            self._log.warn(e)
            return []

    def _toDeployment(self, response):

        # FIXME
        return Deployment(replicas=1, ready_replicas=1)

    def _getLocalPort(self, container):

        # container.ports:
        # {'8080/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '49153'}, {'HostIp': '::', 'HostPort': '49153'}]}
        #
        return int(container.ports[next(iter(container.ports))][0]['HostPort'])  # first port in first mapping
