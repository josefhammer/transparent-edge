from __future__ import annotations

from util.EdgeTools import Edge
from util.Service import Service
from util.RyuDPID import DPID


class ProximityScheduler:
    """
    Selects the closest edge server that has the service running already for a given request to an edge service.
    If no service instance is running yet, then the closest edge cluster is chosen.

    'Closest' here means 'the edge that is directly attached to the switch that got the request'.
    """

    def __init__(self, log, cfg: dict):

        self.log = log
        self.cfg = cfg

    def schedule(self, dpid: DPID, service: Service, edges: list[Edge, bool]) -> tuple[Edge, bool]:
        # input: list of [edge -> True|False] if a service is running already there or not

        choices = [(edge, avail) for (edge, avail) in edges if avail]  # preference for running instance first

        if not len(choices):  # no instance running yet? -> choose from all
            choices = edges

        closest = [(edge, avail) for (edge, avail) in choices if edge.dpid == dpid]  # preference for closest second

        return edges[0] if len(closest) else (None, None)  # return the first one
