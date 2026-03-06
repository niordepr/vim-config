"""Tests for data models."""

import time

from satellite_sdn_controller.models import (
    BroadcastSession,
    FlowAction,
    FlowMatch,
    FlowRule,
    Link,
    LinkState,
    Node,
    NodeType,
)


class TestNode:
    def test_defaults(self):
        node = Node()
        assert node.node_type == NodeType.GROUND_STATION
        assert node.capacity_mbps == 1000.0
        assert node.node_id  # UUID should be generated

    def test_to_dict_round_trip(self):
        node = Node(
            node_id="n1",
            name="Sat-A",
            node_type=NodeType.SATELLITE,
            latitude=35.0,
            longitude=139.0,
            altitude_km=35786.0,
            capacity_mbps=500.0,
            metadata={"orbit": "GEO"},
        )
        d = node.to_dict()
        restored = Node.from_dict(d)
        assert restored.node_id == "n1"
        assert restored.node_type == NodeType.SATELLITE
        assert restored.altitude_km == 35786.0
        assert restored.metadata == {"orbit": "GEO"}


class TestLink:
    def test_defaults(self):
        link = Link()
        assert link.state == LinkState.UP
        assert link.cost == 1.0

    def test_round_trip(self):
        link = Link(
            link_id="l1",
            source_id="a",
            target_id="b",
            bandwidth_mbps=200.0,
            latency_ms=120.0,
            state=LinkState.DEGRADED,
            cost=2.5,
        )
        d = link.to_dict()
        restored = Link.from_dict(d)
        assert restored.state == LinkState.DEGRADED
        assert restored.cost == 2.5


class TestFlowRule:
    def test_round_trip(self):
        rule = FlowRule(
            rule_id="r1",
            node_id="n1",
            match=FlowMatch(multicast_group="239.1.1.1"),
            action=FlowAction.REPLICATE,
            output_ports=["n2", "n3"],
            priority=300,
        )
        d = rule.to_dict()
        restored = FlowRule.from_dict(d)
        assert restored.action == FlowAction.REPLICATE
        assert restored.match.multicast_group == "239.1.1.1"
        assert restored.output_ports == ["n2", "n3"]


class TestBroadcastSession:
    def test_round_trip(self):
        session = BroadcastSession(
            session_id="s1",
            name="TV-1",
            source_node_id="sat1",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1", "gs2"},
            bandwidth_mbps=20.0,
            active=True,
            tree_links={"l1", "l2"},
        )
        d = session.to_dict()
        assert d["active"] is True
        restored = BroadcastSession.from_dict(d)
        assert restored.destination_node_ids == {"gs1", "gs2"}
        assert restored.tree_links == {"l1", "l2"}
