from __future__ import annotations

from util.Cluster import Cluster
from util.EdgeTools import Edge, Switches
from util.SocketAddr import SocketAddr
from util.Service import Deployment, ServiceInstance, Service
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie
from util.Performance import PerfCounter
from util.RyuDPID import DPID

import os
import glob


class ServiceManager:
    """
    Manages the available services.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, log, switches: Switches, edges: dict[DPID, Edge], clusterGlob: str, servicesGlob: str,
                 servicesDir: str):

        self.log = log
        self._switches = switches
        self._edges = edges
        self._services: TinyServiceTrie = TinyServiceTrie(servicesDir)

        self.loadClusters(clusterGlob)
        self.loadServices(servicesGlob)

    def isService(self, addr: SocketAddr):
        return self._services.contains(addr)

    def isServiceIP(self, ip: IPAddr):
        return self._services.containsIP(ip)

    def uniquePrefix(self, ip: IPAddr):
        return self._services.uniquePrefix(ip)

    def isServer(self, dpid, addr: SocketAddr):
        return dpid in self._edges and addr in self._edges[dpid].eServices

    def service(self, addr: SocketAddr):
        return self._services.get(addr)

    def loadClusters(self, clusterGlob):

        files = glob.glob(clusterGlob)

        for filename in files:

            clusterName = os.path.splitext(os.path.basename(filename))[0]
            apiServer, clusterType = clusterName.split("-")  # clusterType after '-'
            edgeIP = apiServer.split(":")[0]

            switch = None
            for dpid, edge in self._edges.items():
                if edge.ip == IPAddr(edgeIP):
                    switch = dpid
                    break

            if not switch is None:  # included in the current configuration?
                edge.cluster = Cluster.init(clusterType, apiServer, filename)

    def loadServices(self, servicesGlob):

        files = glob.glob(servicesGlob)

        for filename in files:
            service = Cluster.initService(filename=filename)
            self._addService(service.toService(edgeIP=None, target=None), filename)

    def initServices(self, edge: Edge):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        svcInstances = edge.cluster.services(None, edge.target)
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

    def _addService(self, svc: Service, svcFilename: str = None):

        # Add service to global ServiceTrie
        #
        if not self._services.contains(svc.vAddr):
            self._services.set(svc.vAddr, svcFilename)
            self.log.info("ServiceID " + str(svc))

    def _addServiceInstance(self, svcInstance, edge):

        # If we route directly to the pod, we need to replace ClusterIP with PodIP
        #
        if edge.target == "pod":
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

        service = Cluster.initService(label=self._services[vAddr].label, filename=self._services.serviceFilename(vAddr))
        service.annotate()

        perf = PerfCounter()
        svcInstance = edge.cluster.deployService(service, edge.target)

        if svcInstance is not None:
            self._addServiceInstance(svcInstance, edge)
            self.log.info("Service {} ready after {} ms.".format(str(svcInstance), perf.ms()))
            return svcInstance

        return None

    def availServers(self, dpid, addr: SocketAddr) -> tuple[Service, list[Edge, int]]:
        """
        :returns: A list of edges with the number of running instances in it.
        """
        log = self.log
        result = []
        service = None

        for switch, edge in self._edges.items():

            # find a server that hosts (or may host) the required service
            #
            svc = edge.vServices.get(addr)
            if svc is not None:  # we found a running instance

                service = svc.service  # if we found an instance -> return it (performance)

                if svc.edgeIP in self._switches[switch].hosts:
                    result.append((edge, 1))
                else:
                    log.warn("Server {} not available at switch {}".format(svc.edgeIP, dpid))
                    log.debug(self._switches.hosts)
            else:
                if edge.cluster and edge.cluster._ip and edge.cluster._ip in self._switches[switch].hosts:
                    result.append((edge, 0))

                elif edge.cluster and edge.cluster._ip:
                    log.warn("Cluster {} not available at switch {}".format(edge.cluster._ip, dpid))
                    log.debug(self._switches.hosts)

        return service, result
