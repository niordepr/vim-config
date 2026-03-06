"""Tests for multicast tree computation."""

from satellite_sdn_controller.models import Link, Node, NodeType
from satellite_sdn_controller.multicast import (
    compute_minimum_cost_tree,
    compute_shortest_path_tree,
    validate_tree_bandwidth,
)
from satellite_sdn_controller.topology import TopologyManager


def _diamond_topology():
    """Diamond topology: S -> A -> D, S -> B -> D (bidirectional for tree building)."""
    topo = TopologyManager()
    for nid in ("S", "A", "B", "D"):
        topo.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))

    links = [
        Link(link_id="SA", source_id="S", target_id="A", cost=1, bandwidth_mbps=100),
        Link(link_id="SB", source_id="S", target_id="B", cost=2, bandwidth_mbps=50),
        Link(link_id="AD", source_id="A", target_id="D", cost=1, bandwidth_mbps=100),
        Link(link_id="BD", source_id="B", target_id="D", cost=1, bandwidth_mbps=50),
    ]
    for l in links:
        topo.add_link(l)
    return topo


def _star_topology():
    """Star topology: S -> A, S -> B, S -> C."""
    topo = TopologyManager()
    for nid in ("S", "A", "B", "C"):
        topo.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))
    links = [
        Link(link_id="SA", source_id="S", target_id="A", cost=1, bandwidth_mbps=100),
        Link(link_id="SB", source_id="S", target_id="B", cost=1, bandwidth_mbps=100),
        Link(link_id="SC", source_id="S", target_id="C", cost=1, bandwidth_mbps=100),
    ]
    for l in links:
        topo.add_link(l)
    return topo


class TestShortestPathTree:
    def test_single_destination(self):
        topo = _diamond_topology()
        tree = compute_shortest_path_tree(topo, "S", {"D"})
        ids = {l.link_id for l in tree}
        assert "SA" in ids
        assert "AD" in ids

    def test_multiple_destinations_star(self):
        topo = _star_topology()
        tree = compute_shortest_path_tree(topo, "S", {"A", "B", "C"})
        ids = {l.link_id for l in tree}
        assert ids == {"SA", "SB", "SC"}

    def test_unreachable_returns_empty(self):
        topo = TopologyManager()
        topo.add_node(Node(node_id="X"))
        topo.add_node(Node(node_id="Y"))
        tree = compute_shortest_path_tree(topo, "X", {"Y"})
        assert tree == []

    def test_empty_destinations(self):
        topo = _star_topology()
        tree = compute_shortest_path_tree(topo, "S", set())
        assert tree == []


class TestMinimumCostTree:
    def test_single_destination(self):
        topo = _diamond_topology()
        tree = compute_minimum_cost_tree(topo, "S", {"D"})
        ids = {l.link_id for l in tree}
        # Shortest path S-A-D cost = 2
        assert "SA" in ids
        assert "AD" in ids

    def test_star_destinations(self):
        topo = _star_topology()
        tree = compute_minimum_cost_tree(topo, "S", {"A", "B", "C"})
        ids = {l.link_id for l in tree}
        assert ids == {"SA", "SB", "SC"}


class TestBandwidthValidation:
    def test_all_sufficient(self):
        topo = _star_topology()
        tree = compute_shortest_path_tree(topo, "S", {"A", "B"})
        assert validate_tree_bandwidth(tree, 50.0) == []

    def test_bottleneck_detected(self):
        topo = _diamond_topology()
        tree = compute_shortest_path_tree(topo, "S", {"D"})
        # All links have 100 Mbps; require 200 -> all are bottlenecks
        bottlenecks = validate_tree_bandwidth(tree, 200.0)
        assert len(bottlenecks) == len(tree)
