from __future__ import annotations

from util.FlowMemory import FlowMemoryEntry, FlowMemory
from util.SocketAddr import SocketAddr
from util.EdgeTools import Switch
from util.RyuDPID import DPID
from .ServiceManager import ServiceManager

from concurrent.futures import ThreadPoolExecutor as PoolExecutor


class Dispatcher:
    """
    Selects the ideal edge server for a given request to a edge service.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, log, serviceMngr: ServiceManager, scheduler, memIdleTimeout=10):

        self.log = log
        self._serviceMngr = serviceMngr
        self._scheduler = scheduler
        self._executor = PoolExecutor()

        # Remember the locations of the clients to detect client movement
        self.locations = {}

        # We remember where we directed flows so that if they start up again, we can send them to the same server.
        self.memory = FlowMemory(memIdleTimeout)  # (srcip,dstip,srcport,dstport) -> MemoryEntry

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
        #
        entry = self.memory.getFwd(src, dst)
        if entry is not None:
            log.debug("Found:     {}".format(entry))
            assert (entry.edge.mac)
            return entry.edge

        # entry is None
        #
        # remember vMac
        switch.vMac = dst.mac

        # REVIEW: If edge is different, we would need to route it to the other switch first (destMac = switch).

        service, edges = self._serviceMngr.availServers(dst)  # running instances available?
        if not service:
            service = self._serviceMngr.service(dst)
        edge, numDeployed, numRunningInstances = self._scheduler.schedule(dpid, service, edges)

        if numRunningInstances:
            svc = edge.vServices.get(dst)
        else:
            if edge is None:
                self.log.warn("No server found for service {} at switch {}.".format(dst, dpid))
                return None

            future = self._executor.submit(self._serviceMngr.deploy, service, edge, numDeployed)
            svc = future.result()

        return self._memorize(log, src, dst, edge, svc)

    def _memorize(self, log, src, dst, edge, svc):

        if not svc:
            return None

        edgeAddr = SocketAddr(svc.eAddr.ip, svc.eAddr.port, edge.switch.hosts[svc.edgeIP].mac)

        entry = FlowMemoryEntry(src, dst, edgeAddr)
        self.memory.add(entry)
        log.debug("Memorized: {}".format(entry))

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
