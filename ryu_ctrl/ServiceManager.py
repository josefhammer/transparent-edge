from unicodedata import name

from util.K8sService import K8sService
from .Context import Context
from util.K8sCluster import K8sCluster
from util.EdgeTools import Edge
from util.SocketAddr import SocketAddr
from util.Service import Deployment, ServiceInstance, Service
from util.RyuDPID import DPID
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie

from util.Performance import PerfCounter

import os
import glob
import time


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
                 useGlobalServiceMap: bool = False,
                 target: str = "pod"):

        self.ctx = context
        self.log = log
        self._useGlobalServiceMap = useGlobalServiceMap
        self._target = target

        self.log.debug("useGlobalServiceMap=" + str(useGlobalServiceMap))

        self._services: TinyServiceTrie = TinyServiceTrie(keysOnly=not useGlobalServiceMap)  # SocketAddr

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
            service = K8sService(self._labelFromServiceFilename(filename), filename)
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

        # ... or get the existing one
        elif self._useGlobalServiceMap:
            service = self._services[svc.vAddr]
            if service.label != svc.label:
                print("service=", service, "svc=", svc)
            assert service.label == svc.label  # same service in all edges
            return service  # single instance to save memory

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
        assert (service)

        perf = PerfCounter()
        svc = K8sService(service.label, self._filenameFromServiceLabel(service.label))
        svc.annotate()

        edge.cluster.applyYaml(yml=svc.yaml)
        self.log.info("Service " + str(svc) + " deployed.")

        svcInsts = edge.cluster.services(service.label, self._target)

        if svcInsts:
            svcInst = svcInsts[0]
            if not svcInst:
                return None

            # TODO Replace with 'watch'
            #
            # Unfortunately, filtering pods by label is not perfectly reliable. Should use pod-template-hash instead:
            # (https://stackoverflow.com/questions/52957227/kubectl-command-to-list-pods-of-a-deployment-in-kubernetes)
            #
            while (True):

                pods = edge.cluster.pods(service.label)
                deps = edge.cluster.deployments(service.label)

                if len(pods) and len(deps):
                    self.log.debug("Deployment: ready={} podStatus={}".format(deps[0].ready_replicas, pods[0].status))

                # if len(pods) and pods[0]["status"]["phase"] == "Running":  # not reliable
                if len(deps) and deps[0].ready_replicas:

                    svcInst.deployment = deps[0]
                    break
                time.sleep(0.1)

            self.log.info("Service ready after {}ms, pod={}".format(perf.ms(), pods[0].ip))
            self._addServiceInstance(svcInst, edge)

            return svcInst

        return None
