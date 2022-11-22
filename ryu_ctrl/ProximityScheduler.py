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

    def schedule(self, dpid: DPID, service: Service, edges: list[Edge, int, int]) -> tuple[Edge, int, int]:
        # input: list of [edge, numDeployedInstancesInEdge, numRunningInstancesInEdge]

        choices = [(edge, dep, avail) for (edge, dep, avail) in edges if avail]  # preference for running instance first

        if not len(choices):  # no instance running yet? -> choose from deployed
            choices = [(edge, dep, avail) for (edge, dep, avail) in edges
                       if dep]  # preference for deployed instance second

        if not len(choices):  # no instance running yet? -> choose from all
            choices = edges

        closest = [(edge, dep, avail) for (edge, dep, avail) in choices
                   if edge.dpid == dpid]  # preference for closest third

        return closest[0] if len(closest) else (None, None, None)  # return the first one
