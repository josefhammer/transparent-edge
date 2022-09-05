# Josef Hammer (josef.hammer@aau.at)
#
"""
Layer2 forwarder using two tables.

This forwarder uses two tables on the switch to forward based on 
ethernet source and destination addresses - one for the source address
and one for destination addresses.

First table:
Is the source address known? If not, (1) send to controller to learn it 
_and_ (2) forward the packet to the second table.

Second table:
Is the destination address known? If yes, forward to the correct port.
If no, flood on all ports.
"""

from util.RyuOpenFlow import OpenFlow


class L2TableForwarder:
    """
    Level 2 (MAC) forwarder using two tables.

    Table 1: Source MACs already known.
    Table 2: Destination MACs with out_ports already known.
    """

    def __init__(self, log, table1ID, table2ID, flowIdleTimeout=10):

        self.log = log
        self.table1 = table1ID
        self.table2 = table2ID
        self.flowIdleTimeout = flowIdleTimeout

    def connect(self, of: OpenFlow):

        log = self.log
        log.info("Connected. Number of tables: {}".format(of.msg.n_tables))
        assert of.msg.n_tables > self.table2

        # clear all existing flows on both tables
        #
        of.FlowMod().table(self.table1).clearTable()
        of.FlowMod().table(self.table2).clearTable()

        # Fallthrough rule for table1: flood and send to controller

        of.FlowMod().table(self.table1).priority(0).actions(of.Action().sendToController().gotoTable(
            self.table2)).send()

        # Fallthrough rule for table2: flood
        of.FlowMod().table(self.table2).priority(0).actions(of.Action().flood()).send()

    def connected(self, of: OpenFlow):
        pass

    def packetIn(self, of: OpenFlow):

        if not of.msg.table_id == self.table1:
            return  # not our business

        src = of.src

        packet = of.packet()
        if not packet.hasValidPort() or packet.isLLDP():
            return  # ignore

        # Add to source table
        match = of.Match(in_port=packet.inport(), eth_src=src.mac)  # only if in_port did not change!
        actions = of.Action().gotoTable(self.table2)

        of.FlowMod().table(self.table1).idleTimeout(self.flowIdleTimeout).match(match).actions(actions).send()

        # Add to destination table
        match = of.Match(eth_dst=src.mac)
        actions = of.Action().outport(packet.inport())

        of.FlowMod().table(self.table2).idleTimeout(self.flowIdleTimeout).match(match).actions(actions).send()

        self.log.debug("Learned %s on port %s" % (src.mac, packet.inport()))
