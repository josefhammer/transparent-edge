from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.controller import dpset

from util.RyuOpenFlow import OpenFlow
from util.EdgeTools import Switch

from ryu_ctrl.EdgeController import EdgeController


class EdgeMainRyu(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'dpset': dpset.DPSet}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dpset = kwargs['dpset']

        # Turn off verbose logging
        self.logger.root.getChild("ryu").getChild("base").getChild("app_manager").setLevel("INFO")

        # Launch main component
        #
        self.logger.name = "Edge"
        self.ctrl = EdgeController(self.logger)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):

        self.ctrl.connect(OpenFlow(ev))

    @set_ev_cls(dpset.EventDP, MAIN_DISPATCHER)
    def _event_dp_handler(self, ev):

        self.ctrl.connected(OpenFlow(ev), ev.ports)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):

        self.ctrl.packetIn(OpenFlow(ev))

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def barrier_reply_handler(self, ev):
        pass

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):

        self.ctrl.flowRemoved(OpenFlow(ev))
