from __future__ import annotations

from util.K8sService import K8sService
from util.Service import ServiceInstance

from collections import defaultdict
from abc import ABC, abstractmethod  # abstract base class


class Cluster(ABC):
    """
    Base class for different kinds of clusters.
    """

    @staticmethod
    def init(clusterType: str, apiServer: str, cfgFilename: str) -> Cluster:
        """
        Factory method to allow different kinds of clusters.
        """

        if clusterType == 'k8s':
            from cluster.K8sCluster import K8sCluster
            cluster = K8sCluster
        elif clusterType == 'docker':
            from cluster.DockerCluster import DockerCluster
            cluster = DockerCluster
        else:
            return None

        return cluster(apiServer, cfgFilename)

    @staticmethod
    def initService(service=None, label=None, port=None, filename=None, yml: dict = None):
        """
        Factory method to create a service from its definition (file or yaml).
        
        Currently, only K8s Yaml files are supported.
        """
        return K8sService(service, label, port, filename, yml)

    def getService(self, label: str) -> ServiceInstance:

        svcInst = next(iter(self.services(label)), None)  # [0] or None

        if svcInst:
            svcInst.deployment = next(iter(self.deployments(label)), None)
        return svcInst

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def deploy(self, service: K8sService) -> ServiceInstance:
        pass

    def scale(self, svc: ServiceInstance, replicas: int = 1):

        assert (svc)
        if replicas:
            if not svc.deployment or not svc.deployment.replicas:  # we need to scale up
                self._log.info("Scaling up from zero: " + str(svc))
                self._scale(svc, replicas)
        else:
            if svc.deployment and svc.deployment.replicas:  # we need to scale down
                self._log.info("Scaling down to zero: " + str(svc))
                self._scale(svc, replicas)

    @abstractmethod
    def _scale(self, svc: ServiceInstance, replicas: int = 1):
        pass

    def _toMap(self, label, rawFunc, func):

        items = rawFunc(label)

        # single label requested -> return array
        #
        if label:
            return [func(i) for i in items]

        # otherwise -> return dict[label]
        #
        result = defaultdict(list)
        for i in items:
            result[self._label(i)].append(func(i))
        return result

    @abstractmethod
    def _label(self, item):
        return None
