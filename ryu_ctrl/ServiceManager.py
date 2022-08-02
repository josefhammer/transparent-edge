from .Context import Context
from util.ClusterK8s import ClusterK8s
from util.EdgeTools import Edge
from util.SocketAddr import SocketAddr
from util.Service import ServiceInstance, Service
from util.RyuDPID import DPID
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie

import os
import glob


class ServiceManager:
    """
    Manages the available services.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, context: Context, log, svcFolder, fileExt, useGlobalServiceMap: bool = False):

        self.ctx = context
        self.log = log
        self._useGlobalServiceMap = useGlobalServiceMap

        self.log.debug("useGlobalServiceMap=" + str(useGlobalServiceMap))

        self._services: TinyServiceTrie = TinyServiceTrie(keysOnly=not useGlobalServiceMap)  # SocketAddr

        if svcFolder != None:
            self.loadServices(svcFolder, fileExt)

    def isService(self, addr: SocketAddr):
        return self._services.contains(addr)

    def isServiceIP(self, ip: IPAddr):
        return self._services.containsIP(ip)

    def uniquePrefix(self, ip: IPAddr):
        return self._services.uniquePrefix(ip)

    def isServer(self, dpid, addr: SocketAddr):
        return dpid in self.ctx.edges and addr in self.ctx.edges[dpid].nServices

    def loadServices(self, folder, fileExt):

        files = glob.glob(os.path.join(folder, '*' + fileExt))

        for filename in files:

            clusterName = os.path.basename(filename).split(fileExt)[0]
            apiServer, clusterType = clusterName.split("-")
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
                    edge.cluster = ClusterK8s(apiServer, filename)

    def initServices(self, edge: Edge, svcInstances: list):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        for svcInstance in svcInstances:

            svc = svcInstance.service

            # Add service to global ServiceTrie
            #
            if not self._services.contains(svc.vAddr):
                self._services.set(svc.vAddr, svc)
                self.log.info("ServiceID {}:{} {} -> {}".format(svc.vAddr.ip, svc.vAddr.port,
                                                                '(' + svc.domain + ')' if svc.domain else '', svc.name))

            # ... or get the existing one
            elif self._useGlobalServiceMap:
                service = self._services[svc.vAddr]
                assert service.domain == svc.domain and service.name == svc.name  # same service in all edges
                svcInstance.service = service  # single instance to save memory

            # Add ServiceInstance to edge (register with IP addresses for both directions if different)
            #
            edge.vServices[svcInstance.service.vAddr] = svcInstance  # REVIEW Requires to have a single instance only
            edge.eServices[svcInstance.eAddr] = svcInstance
            edge.nServices[svcInstance.nAddr] = svcInstance

            self.log.info("ServiceInstance @ {}: {}".format(edge.dpid, svcInstance))
