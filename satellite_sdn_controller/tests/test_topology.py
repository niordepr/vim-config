"""Tests for the topology manager."""

import pytest

from satellite_sdn_controller.models import Link, LinkState, Node, NodeType
from satellite_sdn_controller.topology import (
    TopologyManager,
    estimate_propagation_delay_ms,
)


def _make_topology():
    """Create a small test topology.

    Nodes: A -- B -- C -- D
                |         |
                +--- E ---+
    """
    topo = TopologyManager()
    for nid in ("A", "B", "C", "D", "E"):
        topo.add_node(Node(node_id=nid, name=nid, node_type=NodeType.SATELLITE))

    links = [
        Link(link_id="AB", source_id="A", target_id="B", cost=1),
        Link(link_id="BC", source_id="B", target_id="C", cost=1),
        Link(link_id="CD", source_id="C", target_id="D", cost=1),
        Link(link_id="BE", source_id="B", target_id="E", cost=2),
        Link(link_id="ED", source_id="E", target_id="D", cost=2),
    ]
    for l in links:
        topo.add_link(l)
    return topo


class TestTopologyNodeOps:
    def test_add_and_get_node(self):
        topo = TopologyManager()
        node = Node(node_id="n1", name="Sat-1", node_type=NodeType.SATELLITE)
        topo.add_node(node)
        assert topo.get_node("n1") is node
        assert topo.node_count == 1

    def test_remove_node_cleans_links(self):
        topo = _make_topology()
        topo.remove_node("B")
        assert topo.get_node("B") is None
        # Links AB, BC, BE should be removed
        assert topo.get_link("AB") is None
        assert topo.get_link("BC") is None
        assert topo.get_link("BE") is None
        # CD and ED should still exist
        assert topo.get_link("CD") is not None
        assert topo.get_link("ED") is not None

    def test_get_nodes_by_type(self):
        topo = TopologyManager()
        topo.add_node(Node(node_id="s1", node_type=NodeType.SATELLITE))
        topo.add_node(Node(node_id="g1", node_type=NodeType.GROUND_STATION))
        topo.add_node(Node(node_id="s2", node_type=NodeType.SATELLITE))
        assert len(topo.get_nodes_by_type(NodeType.SATELLITE)) == 2
        assert len(topo.get_nodes_by_type(NodeType.GROUND_STATION)) == 1


class TestTopologyLinkOps:
    def test_add_link_requires_existing_nodes(self):
        topo = TopologyManager()
        topo.add_node(Node(node_id="A"))
        with pytest.raises(ValueError):
            topo.add_link(Link(source_id="A", target_id="X"))

    def test_set_link_state(self):
        topo = _make_topology()
        assert topo.set_link_state("AB", LinkState.DOWN)
        assert topo.get_link("AB").state == LinkState.DOWN
        assert not topo.set_link_state("nonexistent", LinkState.UP)

    def test_get_active_links(self):
        topo = _make_topology()
        total = topo.link_count
        topo.set_link_state("AB", LinkState.DOWN)
        assert len(topo.get_active_links()) == total - 1


class TestShortestPath:
    def test_direct_path(self):
        topo = _make_topology()
        path = topo.shortest_path("A", "B")
        assert path == ["A", "B"]

    def test_multi_hop_path(self):
        topo = _make_topology()
        path = topo.shortest_path("A", "D")
        assert path == ["A", "B", "C", "D"]  # cost = 3 vs A-B-E-D = 5

    def test_no_path(self):
        topo = TopologyManager()
        topo.add_node(Node(node_id="X"))
        topo.add_node(Node(node_id="Y"))
        assert topo.shortest_path("X", "Y") is None

    def test_avoids_down_links(self):
        topo = _make_topology()
        topo.set_link_state("BC", LinkState.DOWN)
        path = topo.shortest_path("A", "D")
        # Should go A -> B -> E -> D
        assert path == ["A", "B", "E", "D"]


class TestPropagationDelay:
    def test_same_location_zero_distance(self):
        n = Node(latitude=0, longitude=0, altitude_km=0)
        delay = estimate_propagation_delay_ms(n, n)
        assert delay == pytest.approx(0.0, abs=0.01)

    def test_geo_satellite_reasonable(self):
        ground = Node(latitude=0, longitude=0, altitude_km=0)
        sat = Node(latitude=0, longitude=0, altitude_km=35786)
        delay = estimate_propagation_delay_ms(ground, sat)
        # One-way delay to GEO should be in the hundreds of ms range
        assert 100 < delay < 300
