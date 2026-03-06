"""Tests for routing strategies."""

from satellite_sdn_controller.models import Link, Node, NodeType, RoutingStrategy
from satellite_sdn_controller.routing_strategy import compute_tree
from satellite_sdn_controller.topology import TopologyManager


def _latency_topology():
    """Topology with varying latency and cost.

    S -> A -> D  (low cost, high latency)
    S -> B -> D  (high cost, low latency)
    """
    topo = TopologyManager()
    for nid in ("S", "A", "B", "D"):
        topo.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))

    topo.add_link(Link(
        link_id="SA", source_id="S", target_id="A",
        cost=1, latency_ms=100, bandwidth_mbps=50,
    ))
    topo.add_link(Link(
        link_id="AD", source_id="A", target_id="D",
        cost=1, latency_ms=100, bandwidth_mbps=50,
    ))
    topo.add_link(Link(
        link_id="SB", source_id="S", target_id="B",
        cost=5, latency_ms=10, bandwidth_mbps=200,
    ))
    topo.add_link(Link(
        link_id="BD", source_id="B", target_id="D",
        cost=5, latency_ms=10, bandwidth_mbps=200,
    ))
    return topo


def _load_topology():
    """Topology with varying load.

    S -> A -> D  (low load)
    S -> B -> D  (high load)
    """
    topo = TopologyManager()
    for nid in ("S", "A", "B", "D"):
        topo.add_node(Node(node_id=nid, node_type=NodeType.SATELLITE))

    topo.add_link(Link(
        link_id="SA", source_id="S", target_id="A",
        cost=1, latency_ms=50, bandwidth_mbps=100, load=0.1,
    ))
    topo.add_link(Link(
        link_id="AD", source_id="A", target_id="D",
        cost=1, latency_ms=50, bandwidth_mbps=100, load=0.1,
    ))
    topo.add_link(Link(
        link_id="SB", source_id="S", target_id="B",
        cost=1, latency_ms=50, bandwidth_mbps=100, load=0.9,
    ))
    topo.add_link(Link(
        link_id="BD", source_id="B", target_id="D",
        cost=1, latency_ms=50, bandwidth_mbps=100, load=0.9,
    ))
    return topo


class TestShortestPathStrategy:
    def test_picks_cheapest_path(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"}, strategy=RoutingStrategy.SHORTEST_PATH
        )
        ids = {l.link_id for l in tree}
        # Shortest-path by cost: S-A-D (cost=2 vs S-B-D=10)
        assert "SA" in ids and "AD" in ids

    def test_empty_destinations(self):
        topo = _latency_topology()
        tree = compute_tree(topo, "S", set(), strategy=RoutingStrategy.SHORTEST_PATH)
        assert tree == []


class TestMinLatencyStrategy:
    def test_picks_lowest_latency_path(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"}, strategy=RoutingStrategy.MIN_LATENCY
        )
        ids = {l.link_id for l in tree}
        # Min latency: S-B-D (20ms vs S-A-D=200ms)
        assert "SB" in ids and "BD" in ids


class TestMaxBandwidthStrategy:
    def test_picks_widest_path(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"}, strategy=RoutingStrategy.MAX_BANDWIDTH
        )
        ids = {l.link_id for l in tree}
        # Max bandwidth: S-B-D (200 Mbps vs S-A-D=50 Mbps)
        assert "SB" in ids and "BD" in ids


class TestLoadBalancedStrategy:
    def test_avoids_loaded_links(self):
        topo = _load_topology()
        tree = compute_tree(
            topo, "S", {"D"}, strategy=RoutingStrategy.LOAD_BALANCED
        )
        ids = {l.link_id for l in tree}
        # Load-balanced prefers low-load: S-A-D (load=0.1)
        assert "SA" in ids and "AD" in ids


class TestDelayBoundedStrategy:
    def test_feasible_with_loose_bound(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"},
            strategy=RoutingStrategy.DELAY_BOUNDED,
            max_latency_ms=500.0,
        )
        assert len(tree) > 0

    def test_infeasible_with_tight_bound(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"},
            strategy=RoutingStrategy.DELAY_BOUNDED,
            max_latency_ms=5.0,  # tighter than any path
        )
        assert tree == []

    def test_prefers_cost_when_feasible(self):
        topo = _latency_topology()
        # With a 250ms bound, both paths are feasible, should prefer cost-optimal
        tree = compute_tree(
            topo, "S", {"D"},
            strategy=RoutingStrategy.DELAY_BOUNDED,
            max_latency_ms=250.0,
        )
        ids = {l.link_id for l in tree}
        assert len(tree) > 0
        # The Steiner approx should pick the cheaper path S-A-D (cost=2)
        assert "SA" in ids and "AD" in ids


class TestMinimumCostTreeStrategy:
    def test_steiner_approximation(self):
        topo = _latency_topology()
        tree = compute_tree(
            topo, "S", {"D"}, strategy=RoutingStrategy.MINIMUM_COST_TREE
        )
        ids = {l.link_id for l in tree}
        assert "SA" in ids and "AD" in ids
