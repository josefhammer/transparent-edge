from util.MemoryEntry import MemoryEntry, Memory
from util.SocketAddr import SocketAddr
from util.RyuDPID import DPID
from .Context import Context


class EdgeDispatcher:
    """
    Selects the ideal edge server for a given request to a edge service.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, context: Context, log, memIdleTimeout=10):

        self.ctx = context
        self.log = log

        # Remember the locations of the clients to detect client movement
        self.locations = {}

        # We remember where we directed flows so that if they start up again, we can send them to the same server.
        self.memory = Memory(memIdleTimeout)  # (srcip,dstip,srcport,dstport) -> MemoryEntry

    def dispatch(self, dpid: DPID, src: SocketAddr, dst: SocketAddr):
        """
        Find the ideal edge server for a given (virtual) ServiceID address.

        Returns (edge: SocketAddr).
        """

        log = self.log

        # Do we already know this flow?
        entry = self.memory.getFwd(src, dst)

        if entry is None:

            # remember vMac
            self.ctx.switches[dpid].vMac = dst.mac

            services = self.availServers(dpid, dst)
            if not services:

                clusters = self.availClusters(dpid)

                (edge, switch) = clusters[0]
                svc = self.ctx.serviceMngr.deployService(edge, dst)

                if not svc:
                    log.warn("No server found for service {} at switch {}.".format(dst, dpid))
                    return None
            else:
                (svc, switch) = services[0]

            edge = SocketAddr(svc.eAddr.ip, svc.eAddr.port, self.ctx.hosts[switch][svc.edgeIP].mac)

            entry = MemoryEntry(src, dst, edge)
            self.memory.add(entry)
            log.debug("Memorized: {}".format(entry))

        else:
            log.debug("Found:     {}".format(entry))

        assert (entry.edge.mac)
        return entry.edge

    def findServiceID(self, dpid: DPID, src: SocketAddr, dst: SocketAddr):
        """
        Find the original (virtual) ServiceID address that the request went to.

        Returns (serviceID: SocketAddr).
        """

        entry = self.memory.getRet(src, dst)

        if entry is None:
            return None

        # REVIEW Could the vMac be different after migration??
        #
        vMac = self.ctx.switches[dpid].vMac
        if vMac != entry.dst.mac:
            self.log.warn("vMac different: entry={} switch={} dpid={}".format(entry.dst.mac, vMac, dpid))
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

    def availServers(self, dpid, addr: SocketAddr):

        log = self.log
        result = []

        for switch, edge in self.ctx.edges.items():

            # find a server that hosts the required service
            #
            svc = edge.vServices.get(addr)
            if svc is not None:

                if svc.eAddr.ip not in self.ctx.hosts[switch]:
                    log.warn("Server {} not available at switch {}".format(svc.eAddr.ip, dpid))
                    log.debug(self.ctx.hosts)
                else:
                    self._addServer(switch, dpid, result, svc)
        return result

    def availClusters(self, dpid):

        result = []
        for switch, edge in self.ctx.edges.items():

            if edge.cluster and edge.cluster._ip and edge.cluster._ip in self.ctx.hosts[switch]:

                self._addServer(switch, dpid, result, edge)
        return result

    def _addServer(self, switch, dpid, servers, item):

        if switch == dpid:
            servers.insert(0, (item, switch))  # preference for local server
        else:
            servers.append((item, switch))
