from __future__ import annotations

from util.MemoryEntry import MemoryEntry, Memory
from util.SocketAddr import SocketAddr
from util.Service import ServiceInstance
from util.EdgeTools import Edge, Switch, SwitchTable
from util.RyuDPID import DPID
from .Context import Context


class EdgeDispatcher:
    """
    Selects the ideal edge server for a given request to a edge service.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, context: Context, log, switchTable: SwitchTable, scheduler, memIdleTimeout=10):

        self.ctx = context
        self.log = log
        self._hosts = switchTable
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

        # Do we already know this flow?
        entry = self.memory.getFwd(src, dst)

        if entry is None:

            # remember vMac
            switch.vMac = dst.mac

            # REVIEW: If edge is different, we would need to route it to the other switch first (destMac = switch).

            dpid = switch.dpid
            svc, edges = self.availServers(dpid, dst)  # running instance available?
            edge, hasRunningInstance = self._scheduler.schedule(dpid, svc.service, edges)

            if not hasRunningInstance:  # try to deploy an instance

                if edge is None:
                    log.warn("No server found for service {} at switch {}.".format(dst, dpid))
                    return None

                svc = self.ctx.serviceMngr.deployService(edge, dst)

                if not svc:
                    log.warn("Could not instantiate service {} at edge {}.".format(dst, edge.ip))
                    return None

            edge = SocketAddr(svc.eAddr.ip, svc.eAddr.port, self._hosts[edge.dpid][svc.edgeIP].mac)

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

    # TODO I could check if rule is active; otherwise (or when stateless) the migration does not matter
    #
    def setClientLocation(self, dpid: DPID, src: SocketAddr):
        prev = None
        log = self.log
        ip = src.ip

        if ip in self.locations:
            prev = self.locations[ip]
            if prev != dpid:
                log.info("---Migration--- {} @ {} -> {}".format(ip, prev, dpid))

        self.locations[ip] = dpid
        log.debug("Location: {} @ {}".format(ip, dpid))
        return prev

    def printClientLocations(self):
        for ip in self.locations:
            self.log.info("Location: {} @ {}".format(ip, self.locations[ip]))

    def availServers(self, dpid, addr: SocketAddr) -> tuple[ServiceInstance, list[Edge, bool]]:

        log = self.log
        result = []
        svcInstance = None

        for switch, edge in self.ctx.edges.items():

            # find a server that hosts (or may host) the required service
            #
            svc = edge.vServices.get(addr)
            if svc is not None:  # we found a running instance

                if svcInstance is None:  # if we have an instance, return it
                    svcInstance = svc

                if svc.edgeIP in self._hosts[switch]:
                    result.append((edge, True))
                else:
                    log.warn("Server {} not available at switch {}".format(svc.edgeIP, dpid))
                    log.debug(self._hosts)
            else:
                if edge.cluster and edge.cluster._ip and edge.cluster._ip in self._hosts[switch]:
                    result.append((edge, False))

                elif edge.cluster and edge.cluster._ip:
                    log.warn("Cluster {} not available at switch {}".format(edge.cluster._ip, dpid))
                    log.debug(self._hosts)

        return svcInstance, result
