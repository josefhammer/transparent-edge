from unicodedata import name

from .Context import Context
from util.Cluster import Cluster
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

            if not switch is None:  # included in the current configuration?
                edge.cluster = Cluster.init(clusterType, apiServer, filename)

    def loadServices(self, servicesGlob):

        files = glob.glob(servicesGlob)

        for filename in files:
            service = self._loadService(filename)
            self._addService(service.toService(edgeIP=None, target=None), filename)

    def _loadService(self, filename, isSymlink=False):

        if isSymlink:  # symlinks created by us do not contain the label (but do not resolve other symlinks)
            filename = os.readlink(filename)

        return Cluster.initService(self._labelFromServiceFilename(filename), filename)

    def _labelFromServiceFilename(self, filename) -> str:  # REVIEW Move to Service or somewhere else?

        return os.path.splitext(os.path.basename(filename))[0]

    def initServices(self, edge: Edge):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        svcInstances = edge.cluster.services(None, self._target)
        deployments = edge.cluster.deployments()

        for svcList in svcInstances.values():
            for svcInstance in svcList:
                if isinstance(svcInstance, ServiceInstance):
                    assert svcInstance.service.label

                    # we only care about running instances of services we know about
                    #
                    svc = svcInstance.service
                    if svc.vAddr and self._services.contains(svc.vAddr):

                        svcInstance.deployment = deployments.get(svc.label, [Deployment()])[0]
                        self._addServiceInstance(svcInstance, edge)

    def _serviceFilename(self, vAddr: SocketAddr):

        return os.path.join(self._servicesDir, str(vAddr) + '.yml')

    def _addService(self, svc: Service, svcFilename: str = None):

        # Add service to global ServiceTrie
        #
        if not self._services.contains(svc.vAddr):
            self._services.set(svc.vAddr)

            # create a symlink to the original file to be able to load the service details at any time
            #
            assert svcFilename is not None
            filename = self._serviceFilename(svc.vAddr)
            tempfilename = filename + ".tmp"
            os.symlink(svcFilename, tempfilename)  # create symlink with tempname first in case it exists already
            os.replace(tempfilename, filename)  # replace vs remove first avoids a race condition
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

        # Add ServiceInstance to edge
        #
        edge.vServices[svcInstance.service.vAddr] = svcInstance  # REVIEW Requires to have a single instance only
        edge.eServices[svcInstance.eAddr] = svcInstance

        self.log.info("ServiceInstance @ {}: {}".format(edge.dpid, svcInstance))

    def deployService(self, edge: Edge, vAddr: SocketAddr):

        service = self._loadService(self._serviceFilename(vAddr), isSymlink=True)
        service.annotate()

        perf = PerfCounter()
        svcInstance = edge.cluster.deployService(service, self._target)

        if svcInstance is not None:
            self._addServiceInstance(svcInstance, edge)
            self.log.info("Service {} ready after {} ms.".format(str(svcInstance), perf.ms()))
            return svcInstance

        return None
