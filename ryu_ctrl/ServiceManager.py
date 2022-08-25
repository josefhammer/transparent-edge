from unicodedata import name

from .Context import Context
from util.K8sCluster import K8sCluster
from util.EdgeTools import Edge
from util.SocketAddr import SocketAddr
from util.Service import Deployment, ServiceInstance, Service
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie
from util.Performance import PerfCounter

import os
import glob


class ServiceManager:
    """
    Manages the available services.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self,
                 context: Context,
                 log,
                 clusterGlob: str,
                 servicesGlob: str,
                 servicesDir: str,
                 target: str = "pod"):

        self.ctx = context
        self.log = log
        self._servicesDir = servicesDir
        self._target = target

        self._services: TinyServiceTrie = TinyServiceTrie()

        self.loadClusters(clusterGlob)
        self.loadServices(servicesGlob)

    def isService(self, addr: SocketAddr):
        return self._services.contains(addr)

    def isServiceIP(self, ip: IPAddr):
        return self._services.containsIP(ip)

    def uniquePrefix(self, ip: IPAddr):
        return self._services.uniquePrefix(ip)

    def isServer(self, dpid, addr: SocketAddr):
        return dpid in self.ctx.edges and addr in self.ctx.edges[dpid].eServices

    def loadClusters(self, clusterGlob):

        files = glob.glob(clusterGlob)

        for filename in files:

            clusterName = os.path.splitext(os.path.basename(filename))[0]
            apiServer, clusterType = clusterName.split("-")  # clusterType after '-'
            edgeIP = apiServer.split(":")[0]

            switch = None
            for dpid, edge in self.ctx.edges.items():
                if edge.ip == IPAddr(edgeIP):
                    switch = dpid
                    break

            if switch is not None:  # included in the current configuration?

                # NOTE: designed to allow different types of edge clusters, not only K8s
                #
                if clusterType == "k8s":
                    edge.cluster = K8sCluster(apiServer, filename)

    def loadServices(self, servicesGlob):

        files = glob.glob(servicesGlob)

        for filename in files:
            #
            # REVIEW Currently, only K8s Yaml files supported.
            #
            service = K8sCluster.initService(self._labelFromServiceFilename(filename), filename)
            svc = service.toService(edgeIP=None, target=self._target)

            self._addService(svc)

    def _labelFromServiceFilename(self, filename) -> str:  # REVIEW Move to Service or somewhere else?

        return os.path.splitext(os.path.basename(filename))[0]

    def _filenameFromServiceLabel(self, label) -> str:  # REVIEW Move to Service or somewhere else?

        # REVIEW Does not support files in subdirectories or different extensions!! (i.e., the glob pattern)
        # Store filename instead of label? But: Initialization from K8s?
        #
        return os.path.join("/var/emu/services/", label + ".yml")

    def initServices(self, edge: Edge):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        svcInstances = edge.cluster.services(None, self._target)
        deployments = edge.cluster.deployments()

        for svcList in svcInstances.values():
            for svcInstance in svcList:
                if isinstance(svcInstance, ServiceInstance):  # might just be Service

                    label = svcInstance.service.label
                    svcInstance.service = self._addService(svcInstance.service)
                    svcInstance.deployment = deployments.get(label, [Deployment()])[0]
                    self._addServiceInstance(svcInstance, edge)

    def _addService(self, svc: Service):

        # Add service to global ServiceTrie
        #
        if not self._services.contains(svc.vAddr):
            self._services.set(svc.vAddr, svc)
            self.log.info("ServiceID " + str(svc))
            return svc

    def _addServiceInstance(self, svcInstance, edge):

        # If we route directly to the pod, we need to replace ClusterIP with PodIP
        #
        if self._target == "pod":
            #
            # REVIEW Inefficient to ask twice or for every pod
            #
            pods = edge.cluster.pods(svcInstance.service.label)
            assert (len(pods))

            svcInstance.eAddr.ip = IPAddr(pods[0].ip)

        # Add ServiceInstance to edge (register with IP addresses for both directions if different)
        #
        edge.vServices[svcInstance.service.vAddr] = svcInstance  # REVIEW Requires to have a single instance only
        edge.eServices[svcInstance.eAddr] = svcInstance

        self.log.info("ServiceInstance @ {}: {}".format(edge.dpid, svcInstance))

    def deployService(self, edge: Edge, vAddr: SocketAddr):

        service = self._services.get(vAddr)
        assert (service and service.label)

        perf = PerfCounter()
        svc = edge.cluster.initService(service.label, self._filenameFromServiceLabel(service.label))
        svc.annotate()

        svcInstance = edge.cluster.deployService(svc, self._target)

        if svcInstance is not None:
            self._addServiceInstance(svcInstance, edge)
            self.log.info("Service {} ready after {} ms.".format(str(svcInstance), perf.ms()))
            return svcInstance

        return None
