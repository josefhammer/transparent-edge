from __future__ import annotations

from util.Cluster import Cluster
from util.EdgeTools import Edge, Switches
from util.SocketAddr import SocketAddr
from util.Service import ServiceInstance, Service
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

    def __init__(self, log, switches: Switches, clusterGlob: str, servicesGlob: str, servicesDir: str):

        self.log = log
        self._switches = switches
        self._services: TinyServiceTrie = TinyServiceTrie(servicesDir)

        self.loadClusters(clusterGlob)
        self.loadServices(servicesGlob)

        log.info(f"NumServices={len(self._services)}")

    def isService(self, addr: SocketAddr):
        return self._services.contains(addr)

    def isServiceIP(self, ip: IPAddr):
        return self._services.containsIP(ip)

    def uniquePrefix(self, ip: IPAddr):
        return self._services.uniquePrefix(ip)

    def isServer(self, dpid, addr: SocketAddr):

        switch = self._switches.get(dpid)
        if switch:
            for edge in switch.edges:  # REVIEW Inefficient data structure for search (but method is rarely used)
                if addr in edge.eServices:
                    return True
        return False

    def service(self, addr: SocketAddr):
        return self._services.get(addr)

    def loadClusters(self, clusterGlob):

        files = glob.glob(clusterGlob)

        for filename in files:

            clusterName = os.path.splitext(os.path.basename(filename))[0]
            apiServer, clusterType = clusterName.split("-")  # clusterType after '-'
            edgeIP = apiServer.split(":")[0]

            for _, sw in self._switches.items():
                for edge in sw.edges:
                    if edge.ip == IPAddr(edgeIP):

                        edge.cluster = Cluster.init(clusterType, apiServer, filename)
                        break

    def loadServices(self, servicesGlob):

        for filename in glob.glob(servicesGlob):
            self._addService(filename)

    def initServices(self, edge: Edge):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        svcInstances = edge.cluster.services(None)
        deployments = edge.cluster.deployments()

        for svcList in svcInstances.values():
            for svcInstance in svcList:
                if svcInstance:
                    assert svcInstance.service.label

                    # we only care about running instances of services we know about
                    #
                    svc = svcInstance.service
                    if svc.vAddr and self._services.contains(svc.vAddr):

                        svcInstance.deployment = next(iter(deployments.get(svc.label)), None)
                        if svcInstance.deployment:
                            self._addServiceInstance(svcInstance, edge)

    def _addService(self, filename: str = None):

        # get info from filename only (do not parse yaml for performance reasons - there might be millions)
        #
        svc = Service(vAddr=None,
                      label=Service.labelFromServiceFilename(filename),
                      port=Service.portFromServiceFilename(filename))

        # Add service to global ServiceTrie
        #
        if not self._services.contains(svc.vAddr):
            self._services.set(svc.vAddr, filename)
            numServices = len(self._services)
            if (numServices < 20):
                self.log.info("ServiceID " + str(svc))
            elif numServices == 20:
                self.log.info("[... more ServiceIDs ...]")

    def _addServiceInstance(self, svcInstance: ServiceInstance, edge):

        # Set correct eAddr for service instance: Exposed / Cluster / Pod
        #
        if edge.target == "pod":
            #
            # If we route directly to the pod, we need to get the PodIP
            #
            pods = edge.cluster.pods(svcInstance.service.label)
            if len(pods) and pods[0].ip:
                svcInstance.podAddr.ip = IPAddr(pods[0].ip)
                svcInstance.eAddr = svcInstance.podAddr

        elif edge.target == "cluster":
            svcInstance.eAddr = svcInstance.clusterAddr

        elif edge.target == "exposed":
            svcInstance.eAddr = svcInstance.publicAddr

        else:
            assert (False, "Invalid target: Must be pod|cluster|exposed.")

        # Add ServiceInstance to edge
        #
        edge.vServices[svcInstance.service.vAddr] = svcInstance  # REVIEW Requires to have a single instance only
        if svcInstance.eAddr:
            edge.eServices[svcInstance.eAddr] = svcInstance

        self.log.info("ServiceInstance @ {}: {}".format(edge.dpid, svcInstance))

    def deployService(self, edge: Edge, vAddr: SocketAddr, svc: ServiceInstance = None):

        perf = PerfCounter()
        if not svc:
            service = Cluster.initService(label=self._services[vAddr].label,
                                          port=vAddr.port,
                                          filename=self._services.serviceFilename(vAddr))
            service.annotate(edge.schedulerName, replicas=0)

            svc = edge.cluster.deployService(service)
        else:
            edge.cluster.scaleDeployment(svc)

        svcInstance = edge.cluster.watchDeployment(svc)

        if svcInstance:
            self._addServiceInstance(svcInstance, edge)
            self.log.info("Service {} ready after {} ms.".format(str(svcInstance), perf.ms()))

        return svcInstance

    def availServers(self, addr: SocketAddr) -> tuple[Service, list[Edge, int, int]]:
        """
        :returns: A list of edges with the number of deployed + running instances in it.
        """
        log = self.log
        result = []
        service = None

        for _, switch in self._switches.items():
            for edge in switch.edges:

                # find a server that hosts (or may host) the required service
                #
                svc = edge.vServices.get(addr)
                if svc is not None:  # we found a deployed instance

                    service = svc.service  # if we found an instance -> return it (performance)

                    if svc.edgeIP in switch.hosts:
                        result.append((edge, 1, 1 if (svc.deployment and svc.deployment.ready_replicas) else 0))
                    else:
                        log.warn("Server {} not available at switch {}".format(svc.edgeIP, switch.dpid))
                        log.debug(switch.hosts)
                else:
                    if edge.cluster and edge.cluster._ip and edge.cluster._ip in switch.hosts:
                        result.append((edge, 0, 0))

                    elif edge.cluster and edge.cluster._ip:
                        log.warn("Cluster {} not available at switch {}".format(edge.cluster._ip, switch.dpid))
                        log.debug(switch.hosts)

        return service, result
