from __future__ import annotations

from util.MemoryEntry import MemoryEntry, Memory
from util.SocketAddr import SocketAddr
from util.Service import Service
from util.EdgeTools import Edge, Switch, Switches
from util.RyuDPID import DPID
from .ServiceManager import ServiceManager


class EdgeDispatcher:
    """
    Selects the ideal edge server for a given request to a edge service.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self,
                 log,
                 serviceMngr: ServiceManager,
                 switches: Switches,
                 edges: dict[DPID, Edge],
                 scheduler,
                 memIdleTimeout=10):

        self.log = log
        self._serviceMngr = serviceMngr
        self._switches = switches
        self._edges = edges
        self._scheduler = scheduler

        # Remember the locations of the clients to detect client movement
        self.locations = {}

        # We remember where we directed flows so that if they start up again, we can send them to the same server.
        self.memory = Memory(memIdleTimeout)  # (srcip,dstip,srcport,dstport) -> MemoryEntry

    def dispatch(self, switch: Switch, src: SocketAddr, dst: SocketAddr):
        """
        Find the ideal edge server for a given (virtual) ServiceID address.

        Returns (edge: SocketAddr).
        """
        log = self.log
        dpid = switch.dpid

        # Track user location
        #
        self._setClientLocation(dpid, src)

        # Do we already know this flow?
        entry = self.memory.getFwd(src, dst)

        if entry is None:

            # remember vMac
            switch.vMac = dst.mac

            # REVIEW: If edge is different, we would need to route it to the other switch first (destMac = switch).

            service, edges = self._availServers(dpid, dst)  # running instances available?
            if not service:
                service = self._serviceMngr.service(dst)
            edge, numRunningInstances = self._scheduler.schedule(dpid, service, edges)

            if numRunningInstances:
                svc = edge.vServices.get(dst)
            else:
                if edge is None:
                    log.warn("No server found for service {} at switch {}.".format(dst, dpid))
                    return None

                svc = self._serviceMngr.deployService(edge, dst)  # try to deploy an instance

                if not svc:
                    log.warn("Could not instantiate service {} at edge {}.".format(dst, edge.ip))
                    return None

            edge = SocketAddr(svc.eAddr.ip, svc.eAddr.port, self._switches[edge.dpid].hosts[svc.edgeIP].mac)

            entry = MemoryEntry(src, dst, edge)
            self.memory.add(entry)
            log.debug("Memorized: {}".format(entry))

        else:
            log.debug("Found:     {}".format(entry))

        assert (entry.edge.mac)
        return entry.edge

    def findServiceID(self, switch: Switch, src: SocketAddr, dst: SocketAddr):
        """
        Find the original (virtual) ServiceID address that the request went to.

        Returns (serviceID: SocketAddr).
        """

        entry = self.memory.getRet(src, dst)

        if entry is None:
            return None

        # REVIEW Could the vMac be different after migration??
        #
        vMac = switch.vMac
        if vMac != entry.dst.mac:
            self.log.warn("vMac different: entry={} switch={} dpid={}".format(entry.dst.mac, vMac, switch.dpid))
            if vMac != None:
                entry.dst.mac = vMac

        return entry.dst  # original destination (= ServiceID)

    def printClientLocations(self):
        for ip in self.locations:
            self.log.info("Location: {} @ {}".format(ip, self.locations[ip]))

    def _setClientLocation(self, dpid: DPID, src: SocketAddr):
        prev = None
        log = self.log
        ip = src.ip

        if ip in self.locations:
            prev = self.locations[ip]
            if prev != dpid:
                log.info("---Migration--- {} @ {} -> {}".format(ip, prev, dpid))

        self.locations[ip] = dpid
        log.debug("Location: {} @ {}".format(ip, dpid))
        return prev

    def _availServers(self, dpid, addr: SocketAddr) -> tuple[Service, list[Edge, int]]:
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
