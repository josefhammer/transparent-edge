import time


class FlowMemoryEntry(object):
    """
    Memorize our flows so we can use short timeouts on the switches.

    Short timeouts for the flows on the switches help to reduce the number of
    flows, increasing switching speed.
    """

    idleTimeout = 60  # seconds

    def __init__(self, src, dst, edge):
        self.src = src
        self.dst = dst
        self.edge = edge
        # we do not call refresh() here for performance reasons

    def refresh(self):
        self.timeout = time.time() + FlowMemoryEntry.idleTimeout
        return self

    @property
    def is_expired(self):
        return time.time() > self.timeout

    @property
    def fwdkey(self):
        return (self.src.ip, self.dst)  # client to serviceID  # does not use client port

    @property
    def retkey(self):
        return (self.edge, self.src.ip)  # edge to client # does not use client port

    def __repr__(self):
        return "s={},d={},e={}".format(self.src.ip, self.dst, self.edge)


class FlowMemory(object):
    """ 
    Manages FlowMemoryEntries. Client port is _not_ used for search, only the IP.
    """

    def __init__(self, idleTimeout=60):  # seconds

        self._fwd = {}
        self._ret = {}
        FlowMemoryEntry.idleTimeout = idleTimeout

    def getFwd(self, src, dst):  # client to serviceID

        self._expireOldFlows()  # expire on fwd event only
        entry = self._fwd.get(FlowMemoryEntry(src, dst, None).fwdkey)
        return entry if entry is None else entry.refresh()

    def getRet(self, edge, src):  # edge to client

        entry = self._ret.get(FlowMemoryEntry(src, None, edge).retkey)
        return entry if entry is None else entry.refresh()

    def add(self, entry: FlowMemoryEntry):

        entry.refresh()
        self._fwd[entry.fwdkey] = entry  # does not use client port
        self._ret[entry.retkey] = entry  # does not use client port

    def _expireOldFlows(self):

        self._fwd = {k: v for k, v in self._fwd.items() if not v.is_expired}
        self._ret = {k: v for k, v in self._ret.items() if not v.is_expired}
