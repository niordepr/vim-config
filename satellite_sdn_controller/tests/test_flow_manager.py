"""Tests for the flow manager."""

import pytest

from satellite_sdn_controller.flow_manager import FlowManager
from satellite_sdn_controller.models import (
    BroadcastSession,
    FlowAction,
    FlowMatch,
    FlowRule,
    Link,
    Node,
    NodeType,
)
from satellite_sdn_controller.topology import TopologyManager


def _simple_topo():
    topo = TopologyManager()
    for nid in ("S", "A", "B"):
        topo.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))
    topo.add_link(Link(link_id="SA", source_id="S", target_id="A", cost=1))
    topo.add_link(Link(link_id="SB", source_id="S", target_id="B", cost=1))
    return topo


class TestFlowManagerCrud:
    def test_install_and_get_rule(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        rule = FlowRule(node_id="S", match=FlowMatch(), action=FlowAction.FORWARD)
        fm.install_rule(rule)
        assert fm.get_rule(rule.rule_id) is rule
        assert fm.rule_count == 1

    def test_install_on_missing_node_raises(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        with pytest.raises(ValueError):
            fm.install_rule(FlowRule(node_id="X"))

    def test_remove_rule(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        rule = FlowRule(node_id="S")
        fm.install_rule(rule)
        removed = fm.remove_rule(rule.rule_id)
        assert removed is rule
        assert fm.rule_count == 0

    def test_get_rules_for_node(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        r1 = FlowRule(node_id="S")
        r2 = FlowRule(node_id="A")
        fm.install_rule(r1)
        fm.install_rule(r2)
        assert len(fm.get_rules_for_node("S")) == 1
        assert len(fm.get_rules_for_node("A")) == 1

    def test_clear_all(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        fm.install_rule(FlowRule(node_id="S"))
        fm.install_rule(FlowRule(node_id="A"))
        assert fm.clear_all_rules() == 2
        assert fm.rule_count == 0


class TestBroadcastTreeInstallation:
    def test_install_broadcast_tree(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        session = BroadcastSession(
            source_node_id="S",
            multicast_group="239.1.1.1",
            destination_node_ids={"A", "B"},
        )
        links = [topo.get_link("SA"), topo.get_link("SB")]
        rules = fm.install_broadcast_tree(session, links)
        # S has two outputs -> REPLICATE
        assert len(rules) == 1
        assert rules[0].action == FlowAction.REPLICATE
        assert set(rules[0].output_ports) == {"A", "B"}

    def test_remove_session_rules(self):
        topo = _simple_topo()
        fm = FlowManager(topo)
        session = BroadcastSession(
            source_node_id="S",
            multicast_group="239.1.1.1",
            destination_node_ids={"A", "B"},
        )
        links = [topo.get_link("SA"), topo.get_link("SB")]
        rules = fm.install_broadcast_tree(session, links)
        removed = fm.remove_session_rules([r.rule_id for r in rules])
        assert removed == 1
        assert fm.rule_count == 0
