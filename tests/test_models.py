"""Tests for data models."""

from satellite_sdn.models import (
    InterSatelliteLink,
    LinkStatus,
    NodeStatus,
    SatelliteNode,
)


class TestSatelliteNode:
    def test_load_score_idle(self):
        node = SatelliteNode(
            node_id="sat-1", orbit_id=0, position_index=0,
            cpu_usage=0.0, memory_usage=0.0, bandwidth_mbps=1000.0,
        )
        assert node.load_score == 0.0

    def test_load_score_full(self):
        node = SatelliteNode(
            node_id="sat-1", orbit_id=0, position_index=0,
            cpu_usage=1.0, memory_usage=1.0, bandwidth_mbps=0.0,
        )
        assert node.load_score == 1.0

    def test_load_score_clamped(self):
        node = SatelliteNode(
            node_id="sat-1", orbit_id=0, position_index=0,
            cpu_usage=0.5, memory_usage=0.5, bandwidth_mbps=500.0,
        )
        score = node.load_score
        assert 0.0 <= score <= 1.0

    def test_is_available_online(self):
        node = SatelliteNode(node_id="sat-1", orbit_id=0, position_index=0)
        assert node.is_available is True

    def test_is_available_offline(self):
        node = SatelliteNode(
            node_id="sat-1", orbit_id=0, position_index=0, status=NodeStatus.OFFLINE,
        )
        assert node.is_available is False

    def test_is_available_degraded(self):
        node = SatelliteNode(
            node_id="sat-1", orbit_id=0, position_index=0, status=NodeStatus.DEGRADED,
        )
        assert node.is_available is False


class TestInterSatelliteLink:
    def test_cost_up(self):
        link = InterSatelliteLink(
            link_id="l1", source_id="a", target_id="b", latency_ms=15.0,
        )
        assert link.cost == 15.0

    def test_cost_down(self):
        link = InterSatelliteLink(
            link_id="l1", source_id="a", target_id="b", status=LinkStatus.DOWN,
        )
        assert link.cost == float("inf")
