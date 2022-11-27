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
    def initService(label=None, port=None, filename=None, yml: dict = None):
        """
        Factory method to create a service from its definition (file or yaml).
        
        Currently, only K8s Yaml files are supported.
        """
        return K8sService(label, port, filename, yml)

    def getService(self, label: str) -> ServiceInstance:

        svcInst = next(iter(self.services(label)), None)  # [0] or None

        if svcInst:
            svcInst.deployment = next(iter(self.deployments(label)), None)
        return svcInst

    @abstractmethod
    def deploy(self, service: K8sService) -> ServiceInstance:
        pass

    def scale(self, svc: ServiceInstance, replicas: int = 1):

        assert (svc)
        if replicas:
            if not svc.deployment or not svc.deployment.replicas:  # we need to scale up
                self._scale(svc, replicas)
                self._log.info("Scaling up from zero: " + str(svc))
        else:
            if svc.deployment and svc.deployment.replicas:  # we need to scale down
                self._scale(svc, replicas)
                self._log.info("Scaling down to zero: " + str(svc))

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
