# Josef Hammer (josef.hammer@aau.at)
#
"""
Provides the context for the main components.
"""

from util.EdgeTools import Switches, SwitchTable


class Context(object):
    """
    Context object to allow easy access. Used instead of a dict to enforce the names. 
    """

    def __init__(self):
        self.serviceMngr = None
        self.switches = Switches()
        self.hosts = SwitchTable()
        self.edges = {}  # dict: DPID -> Edge
