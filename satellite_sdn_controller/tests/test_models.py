"""Tests for data models."""

import time

from satellite_sdn_controller.models import (
    BroadcastSession,
    FlowAction,
    FlowMatch,
    FlowRule,
    ISLType,
    Link,
    LinkState,
    Node,
    NodeType,
    OrbitType,
    QosPriority,
    RoutingStrategy,
)


class TestNode:
    def test_defaults(self):
        node = Node()
        assert node.node_type == NodeType.GROUND_STATION
        assert node.capacity_mbps == 1000.0
        assert node.node_id  # UUID should be generated
        assert node.orbit_type is None
        assert node.orbital_plane is None

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

    def test_leo_satellite_round_trip(self):
        node = Node(
            node_id="sat-P0-S0",
            name="Iridium-P0-S0",
            node_type=NodeType.SATELLITE,
            latitude=45.0,
            longitude=120.0,
            altitude_km=780.0,
            orbit_type=OrbitType.LEO,
            orbital_plane=0,
            orbital_index=0,
            inclination_deg=86.4,
            period_minutes=100.4,
        )
        d = node.to_dict()
        assert d["orbit_type"] == "LEO"
        assert d["orbital_plane"] == 0
        restored = Node.from_dict(d)
        assert restored.orbit_type == OrbitType.LEO
        assert restored.orbital_plane == 0
        assert restored.inclination_deg == 86.4


class TestLink:
    def test_defaults(self):
        link = Link()
        assert link.state == LinkState.UP
        assert link.cost == 1.0
        assert link.isl_type is None
        assert link.load == 0.0

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

    def test_isl_type_round_trip(self):
        link = Link(
            link_id="isl1",
            source_id="a",
            target_id="b",
            isl_type=ISLType.INTRA_PLANE,
            load=0.5,
        )
        d = link.to_dict()
        assert d["isl_type"] == "intra_plane"
        assert d["load"] == 0.5
        restored = Link.from_dict(d)
        assert restored.isl_type == ISLType.INTRA_PLANE
        assert restored.load == 0.5


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

    def test_qos_and_strategy_round_trip(self):
        session = BroadcastSession(
            session_id="s2",
            name="TV-Critical",
            source_node_id="sat1",
            multicast_group="239.2.2.2",
            destination_node_ids={"gs1"},
            qos_priority=QosPriority.CRITICAL,
            routing_strategy=RoutingStrategy.MIN_LATENCY,
            max_latency_ms=100.0,
        )
        d = session.to_dict()
        assert d["qos_priority"] == "critical"
        assert d["routing_strategy"] == "min_latency"
        assert d["max_latency_ms"] == 100.0
        restored = BroadcastSession.from_dict(d)
        assert restored.qos_priority == QosPriority.CRITICAL
        assert restored.routing_strategy == RoutingStrategy.MIN_LATENCY

    def test_default_qos_and_strategy(self):
        session = BroadcastSession()
        assert session.qos_priority == QosPriority.MEDIUM
        assert session.routing_strategy is None
        assert session.max_latency_ms == 0.0
