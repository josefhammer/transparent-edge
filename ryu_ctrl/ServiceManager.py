from __future__ import annotations

from cluster import initCluster
from cluster.Cluster import Cluster
from util.EdgeTools import Edge, Switches
from util.SocketAddr import SocketAddr
from util.Service import ServiceInstance, Service
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie
from util.Performance import PerfCounter

from time import sleep, time

import socket
import os
import glob


class ServiceManager:
    """
    Manages the available services.
    """

    def __init__(self, log, switches: Switches, clusterGlob: str, servicesGlob: str, servicesDir: str):

        self.log = log
        self._switches = switches
        self._services: TinyServiceTrie = TinyServiceTrie(servicesDir)

        # Remember currently running deployments
        #
        self._curDeployments = {}

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

            # e.g.: 10.0.3.100:6443-k8s.json
            #
            clusterName = os.path.splitext(os.path.basename(filename))[0]
            apiServer, clusterType = clusterName.split("-")  # clusterType after '-'
            edgeIP = apiServer.split(":")[0]

            for _, sw in self._switches.items():
                for edge in sw.edges:
                    if edge.ip == IPAddr(edgeIP):

                        edge.cluster = initCluster(clusterType, apiServer, filename)
                        break

    def loadServices(self, servicesGlob):

        for filename in glob.glob(servicesGlob):
            self._addService(filename)

    def initServices(self, edge: Edge):
        """
        Will be called after the switch connected. Before that, we may not be able to connect to the cluster.
        """
        edge.cluster.connect()

        svcInstances = edge.cluster.services(None)

        for svcList in svcInstances.values():
            for svcInstance in svcList:
                if svcInstance:
                    assert svcInstance.service.label

                    # we only care about running instances of services we know about
                    #
                    svc = svcInstance.service
                    if svc.vAddr and self._services.contains(svc.vAddr):

                        # if no deployment info yet -> query explicitly (only for K8s)
                        #
                        if not svcInstance.deployment:
                            svcInstance.deployment = next(iter(edge.cluster.deployments(svc.label)), None)

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

    def bookDeployment(self, service, edge):
        """
        Records that we are about to deploy this service. 

        Note: To be called in the main thread to avoid race conditions (while deploy() runs in a separate thread).

        Returns 0 if no deployment is running already.
        """
        result = self._curDeployments.get((service, edge), 0)
        self._curDeployments[(service, edge)] = 1  # REVIEW/TODO Clean up dict
        return result

    def deploy(self, service: Service, edge: Edge, src: SocketAddr, numDeployed, waitOnly: bool):

        assert service
        startTime_s = time()
        perf = PerfCounter()
        portWaitTime = 0
        svc = None

        # Is the same deployment currently running?
        #
        if waitOnly:
            task = 'wait'
            svc = edge.vServices.get(service.vAddr)
            while svc is None or svc.eAddr is None:
                sleep(1 / 100)  # 10 ms
                svc = edge.vServices.get(service.vAddr)
            portWaitTime = self._waitForOpenPort(svc)

        else:
            for _ in range(3):  # try at most 3 times
                try:
                    if numDeployed:
                        task = 'scaleUp'
                        svc = edge.vServices.get(service.vAddr)
                    else:
                        task = 'deploy'
                        svc = self._deployService(edge, service)  # try to deploy an instance
                    portWaitTime = self._scaleService(edge, svc)  # (wait for) scaling up instance
                    break
                except Exception as e:
                    self.log.error(f'{task}: Exception when instantiating service {service} at edge {edge.ip}: {e}')

            if not svc:
                self.log.error(f'{task}: Could not instantiate service {service} at edge {edge.ip}.')
                return None

        # use double curlies to escape curly braces in f-strings
        self.log.warn(f'#perfDeploy: {{"t":"{task}", "total":{round(perf.ms())}, "wait":{round(portWaitTime)}, ' +
                      f'"svc": "{str(svc)}", "src":"{str(src)}", "ts":{startTime_s}}}')
        return svc

    def _deployService(self, edge: Edge, service: Service) -> ServiceInstance:

        serviceDef = Cluster.initService(service=service, filename=self._services.serviceFilename(service.vAddr))

        # REVIEW For a higher total speed, immediately scale to 1
        #
        return edge.cluster.deploy(serviceDef.annotate(edge.schedulerName, replicas=1))

    def _scaleService(self, edge: Edge, svc: ServiceInstance):

        edge.cluster.scale(svc, replicas=1)

        if svc and svc.deployment and svc.deployment.ready_replicas:
            portWaitTime = self._waitForOpenPort(svc)
            self._addServiceInstance(svc, edge)  # add only after port is open!!
            return portWaitTime
        return 0

    def _waitForOpenPort(self, svc):
        """
        Waits until the service port is open for connections. 
        
        Rationale: Even if the (Docker) container is in state "running", the web service might not be ready for
        connections yet.

        Returns 0 if port was open on first attempt; waiting time in ms otherwise.
        """
        perf = PerfCounter()

        for i in range(0, 3000):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            try:
                s.connect((str(svc.clusterAddr.ip), svc.clusterAddr.port))
                s.shutdown(socket.SHUT_RDWR)
                break
            except:
                sleep(0.01)  # 10 ms
            finally:
                s.close()

        return perf.ms() if i else 0  # returns > 0 only if port was still closed on first attempt

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
