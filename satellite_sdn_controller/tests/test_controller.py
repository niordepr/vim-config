"""Tests for the main SDN controller."""

import pytest

from satellite_sdn_controller.controller import SatelliteSDNController
from satellite_sdn_controller.models import (
    Link,
    LinkState,
    Node,
    NodeType,
    QosPriority,
    RoutingStrategy,
)


def _build_controller():
    """Build a controller with a simple satellite network.

    Topology:
        GW -> SAT1 -> GS1
                   -> GS2
    """
    ctrl = SatelliteSDNController()
    ctrl.add_node(Node(node_id="gw", name="Gateway", node_type=NodeType.GATEWAY))
    ctrl.add_node(Node(node_id="sat1", name="SAT-1", node_type=NodeType.SATELLITE))
    ctrl.add_node(Node(node_id="gs1", name="GS-Tokyo", node_type=NodeType.GROUND_STATION))
    ctrl.add_node(Node(node_id="gs2", name="GS-Sydney", node_type=NodeType.GROUND_STATION))

    ctrl.add_link(Link(link_id="gw-sat1", source_id="gw", target_id="sat1", cost=1))
    ctrl.add_link(Link(link_id="sat1-gs1", source_id="sat1", target_id="gs1", cost=1))
    ctrl.add_link(Link(link_id="sat1-gs2", source_id="sat1", target_id="gs2", cost=1))
    return ctrl


class TestControllerNodeLink:
    def test_add_remove_node(self):
        ctrl = SatelliteSDNController()
        ctrl.add_node(Node(node_id="n1"))
        assert ctrl.topology.get_node("n1") is not None
        ctrl.remove_node("n1")
        assert ctrl.topology.get_node("n1") is None

    def test_add_remove_link(self):
        ctrl = SatelliteSDNController()
        ctrl.add_node(Node(node_id="a"))
        ctrl.add_node(Node(node_id="b"))
        ctrl.add_link(Link(link_id="ab", source_id="a", target_id="b"))
        assert ctrl.topology.get_link("ab") is not None
        ctrl.remove_link("ab")
        assert ctrl.topology.get_link("ab") is None


class TestBroadcastSession:
    def test_create_and_activate(self):
        ctrl = _build_controller()
        session = ctrl.create_broadcast_session(
            name="TV-1",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1", "gs2"},
            bandwidth_mbps=20.0,
        )
        assert not session.active
        assert ctrl.activate_session(session.session_id)
        session = ctrl.get_session(session.session_id)
        assert session.active
        assert len(session.flow_rule_ids) > 0
        assert len(session.tree_links) > 0

    def test_deactivate(self):
        ctrl = _build_controller()
        session = ctrl.create_broadcast_session(
            name="TV-1",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
        )
        ctrl.activate_session(session.session_id)
        assert ctrl.deactivate_session(session.session_id)
        session = ctrl.get_session(session.session_id)
        assert not session.active
        assert session.flow_rule_ids == []

    def test_remove_session(self):
        ctrl = _build_controller()
        session = ctrl.create_broadcast_session(
            name="TV-1",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
        )
        ctrl.activate_session(session.session_id)
        removed = ctrl.remove_session(session.session_id)
        assert removed is not None
        assert ctrl.get_session(session.session_id) is None
        assert ctrl.flow_manager.rule_count == 0

    def test_activate_nonexistent_session(self):
        ctrl = _build_controller()
        assert not ctrl.activate_session("no-such-id")


class TestLinkFailure:
    def test_link_down_reroutes(self):
        """When a link used by an active session goes down, the session is re-routed."""
        ctrl = SatelliteSDNController()
        # Create a topology with an alternate path
        for nid in ("S", "A", "B", "D"):
            ctrl.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))
        ctrl.add_link(Link(link_id="SA", source_id="S", target_id="A", cost=1))
        ctrl.add_link(Link(link_id="AD", source_id="A", target_id="D", cost=1))
        ctrl.add_link(Link(link_id="SB", source_id="S", target_id="B", cost=2))
        ctrl.add_link(Link(link_id="BD", source_id="B", target_id="D", cost=2))

        session = ctrl.create_broadcast_session(
            name="TV",
            source_node_id="S",
            multicast_group="239.1.1.1",
            destination_node_ids={"D"},
        )
        ctrl.activate_session(session.session_id)
        session = ctrl.get_session(session.session_id)
        # Initially the tree should use the cheaper S-A-D path
        assert "SA" in session.tree_links or "AD" in session.tree_links

        # Bring down link AD
        ctrl.set_link_state("AD", LinkState.DOWN)
        session = ctrl.get_session(session.session_id)
        # Session should have been re-routed via S-B-D
        assert session.active
        assert "BD" in session.tree_links


class TestControllerStatus:
    def test_status_reflects_state(self):
        ctrl = _build_controller()
        status = ctrl.get_status()
        assert status["nodes"] == 4
        assert status["links"] == 3
        assert status["sessions_total"] == 0
        assert status["sessions_active"] == 0

        session = ctrl.create_broadcast_session(
            name="TV",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
        )
        ctrl.activate_session(session.session_id)
        status = ctrl.get_status()
        assert status["sessions_total"] == 1
        assert status["sessions_active"] == 1
        assert status["flow_rules"] > 0


class TestConstellationIntegration:
    def test_load_preset(self):
        ctrl = SatelliteSDNController()
        config = ctrl.load_constellation("small_leo")
        assert config.name == "small_leo"
        assert ctrl.topology.node_count == 24  # 4 × 6

    def test_load_unknown_preset_raises(self):
        ctrl = SatelliteSDNController()
        with pytest.raises(ValueError):
            ctrl.load_constellation("unknown")

    def test_add_ground_station_to_constellation(self):
        ctrl = SatelliteSDNController()
        ctrl.load_constellation("small_leo")
        gs = ctrl.add_ground_station(
            "gs-test", "GS-Test", 0.0, 0.0,
            min_elevation_deg=10.0,
        )
        assert gs.node_type == NodeType.GROUND_STATION
        assert ctrl.topology.get_node("gs-test") is not None

    def test_constellation_broadcast_session(self):
        """End-to-end: generate constellation, add GS, create and activate session."""
        ctrl = SatelliteSDNController()
        ctrl.load_constellation("small_leo")
        ctrl.add_ground_station(
            "gs1", "GS-1", 0.0, 0.0, min_elevation_deg=10.0
        )
        ctrl.add_ground_station(
            "gs2", "GS-2", 35.0, 139.0, min_elevation_deg=10.0
        )
        session = ctrl.create_broadcast_session(
            name="Broadcast-1",
            source_node_id="gs1",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs2"},
        )
        result = ctrl.activate_session(session.session_id)
        assert result is True
        session = ctrl.get_session(session.session_id)
        assert session.active


class TestRoutingStrategies:
    def _build_latency_controller(self):
        ctrl = SatelliteSDNController()
        for nid in ("S", "A", "B", "D"):
            ctrl.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))
        ctrl.add_link(Link(
            link_id="SA", source_id="S", target_id="A",
            cost=1, latency_ms=100, bandwidth_mbps=50,
        ))
        ctrl.add_link(Link(
            link_id="AD", source_id="A", target_id="D",
            cost=1, latency_ms=100, bandwidth_mbps=50,
        ))
        ctrl.add_link(Link(
            link_id="SB", source_id="S", target_id="B",
            cost=5, latency_ms=10, bandwidth_mbps=200,
        ))
        ctrl.add_link(Link(
            link_id="BD", source_id="B", target_id="D",
            cost=5, latency_ms=10, bandwidth_mbps=200,
        ))
        return ctrl

    def test_default_strategy(self):
        ctrl = SatelliteSDNController(
            default_strategy=RoutingStrategy.MIN_LATENCY,
        )
        assert ctrl.default_strategy == RoutingStrategy.MIN_LATENCY

    def test_set_strategy(self):
        ctrl = SatelliteSDNController()
        ctrl.default_strategy = RoutingStrategy.LOAD_BALANCED
        assert ctrl.default_strategy == RoutingStrategy.LOAD_BALANCED

    def test_min_latency_session(self):
        ctrl = self._build_latency_controller()
        session = ctrl.create_broadcast_session(
            name="Low-Latency",
            source_node_id="S",
            multicast_group="239.1.1.1",
            destination_node_ids={"D"},
            routing_strategy=RoutingStrategy.MIN_LATENCY,
        )
        ctrl.activate_session(session.session_id)
        session = ctrl.get_session(session.session_id)
        assert session.active
        # Min latency path should go S-B-D
        assert "SB" in session.tree_links
        assert "BD" in session.tree_links

    def test_qos_priority_affects_flow_priority(self):
        ctrl = _build_controller()
        session = ctrl.create_broadcast_session(
            name="Critical",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
            qos_priority=QosPriority.CRITICAL,
        )
        ctrl.activate_session(session.session_id)
        rules = ctrl.flow_manager.get_all_rules()
        assert len(rules) > 0
        # Critical sessions should have priority 500
        assert all(r.priority == 500 for r in rules)

    def test_delay_bounded_session(self):
        ctrl = self._build_latency_controller()
        session = ctrl.create_broadcast_session(
            name="Bounded",
            source_node_id="S",
            multicast_group="239.1.1.1",
            destination_node_ids={"D"},
            routing_strategy=RoutingStrategy.DELAY_BOUNDED,
            max_latency_ms=250.0,
        )
        result = ctrl.activate_session(session.session_id)
        assert result is True


class TestHandoverIntegration:
    def test_trigger_handover(self):
        ctrl = SatelliteSDNController()
        ctrl.load_constellation("small_leo")
        ctrl.add_ground_station(
            "gs1", "GS-1", 0.0, 0.0, min_elevation_deg=10.0
        )
        results = ctrl.trigger_handover()
        assert isinstance(results, dict)

    def test_status_includes_constellation_info(self):
        ctrl = SatelliteSDNController()
        ctrl.load_constellation("small_leo")
        status = ctrl.get_status()
        assert "constellation" in status
        assert status["constellation"]["name"] == "small_leo"
        assert status["satellites"] == 24
        assert status["default_strategy"] == "shortest_path"
