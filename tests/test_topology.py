"""Tests for the TopologyManager."""

from satellite_sdn.models import InterSatelliteLink, LinkStatus, NodeStatus, SatelliteNode
from satellite_sdn.topology import TopologyManager


def _make_node(node_id: str, orbit: int = 0, idx: int = 0, **kwargs) -> SatelliteNode:
    return SatelliteNode(node_id=node_id, orbit_id=orbit, position_index=idx, **kwargs)


def _make_link(link_id: str, src: str, tgt: str, **kwargs) -> InterSatelliteLink:
    return InterSatelliteLink(link_id=link_id, source_id=src, target_id=tgt, **kwargs)


# -- Node management ------------------------------------------------------ #


class TestNodeManagement:
    def test_add_and_get_node(self):
        tm = TopologyManager()
        node = _make_node("sat-1")
        tm.add_node(node)
        assert tm.get_node("sat-1") is node

    def test_remove_node(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        removed = tm.remove_node("sat-1")
        assert removed is not None
        assert tm.get_node("sat-1") is None

    def test_remove_node_cleans_links(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.add_node(_make_node("sat-2"))
        tm.add_link(_make_link("l1", "sat-1", "sat-2"))
        tm.remove_node("sat-1")
        assert tm.get_link("l1") is None

    def test_remove_nonexistent_node_returns_none(self):
        tm = TopologyManager()
        assert tm.remove_node("nope") is None

    def test_online_nodes(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1", status=NodeStatus.ONLINE))
        tm.add_node(_make_node("sat-2", status=NodeStatus.OFFLINE))
        assert len(tm.online_nodes) == 1

    def test_update_node_status(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.update_node_status("sat-1", NodeStatus.DEGRADED)
        assert tm.get_node("sat-1").status == NodeStatus.DEGRADED

    def test_update_node_metrics(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.update_node_metrics("sat-1", cpu_usage=0.5, memory_usage=0.6, bandwidth_mbps=500)
        node = tm.get_node("sat-1")
        assert node.cpu_usage == 0.5
        assert node.memory_usage == 0.6
        assert node.bandwidth_mbps == 500


# -- Link management ------------------------------------------------------ #


class TestLinkManagement:
    def test_add_and_get_link(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.add_node(_make_node("sat-2"))
        link = _make_link("l1", "sat-1", "sat-2")
        tm.add_link(link)
        assert tm.get_link("l1") is link

    def test_remove_link(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.add_node(_make_node("sat-2"))
        tm.add_link(_make_link("l1", "sat-1", "sat-2"))
        removed = tm.remove_link("l1")
        assert removed is not None
        assert tm.get_link("l1") is None

    def test_active_links_excludes_down(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.add_node(_make_node("sat-2"))
        tm.add_link(_make_link("l1", "sat-1", "sat-2", status=LinkStatus.UP))
        tm.add_link(_make_link("l2", "sat-2", "sat-1", status=LinkStatus.DOWN))
        assert len(tm.active_links) == 1

    def test_update_link_status(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-1"))
        tm.add_node(_make_node("sat-2"))
        tm.add_link(_make_link("l1", "sat-1", "sat-2"))
        tm.update_link_status("l1", LinkStatus.DOWN)
        assert tm.get_link("l1").status == LinkStatus.DOWN


# -- Shortest path -------------------------------------------------------- #


class TestShortestPath:
    def _build_chain(self, tm: TopologyManager, n: int = 4):
        """Build a chain: sat-0 -> sat-1 -> ... -> sat-(n-1)."""
        for i in range(n):
            tm.add_node(_make_node(f"sat-{i}"))
        for i in range(n - 1):
            tm.add_link(_make_link(f"l-{i}", f"sat-{i}", f"sat-{i+1}", latency_ms=5.0))

    def test_simple_path(self):
        tm = TopologyManager()
        self._build_chain(tm, 4)
        path, cost = tm.shortest_path("sat-0", "sat-3")
        assert path == ["sat-0", "sat-1", "sat-2", "sat-3"]
        assert cost == 15.0

    def test_no_path(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-0"))
        tm.add_node(_make_node("sat-1"))
        path, cost = tm.shortest_path("sat-0", "sat-1")
        assert path == []
        assert cost == float("inf")

    def test_path_avoids_offline_nodes(self):
        tm = TopologyManager()
        self._build_chain(tm, 4)
        tm.update_node_status("sat-1", NodeStatus.OFFLINE)
        path, cost = tm.shortest_path("sat-0", "sat-3")
        assert path == []

    def test_path_prefers_lower_latency(self):
        tm = TopologyManager()
        for i in range(3):
            tm.add_node(_make_node(f"sat-{i}"))
        tm.add_link(_make_link("l-slow", "sat-0", "sat-2", latency_ms=100.0))
        tm.add_link(_make_link("l-fast-a", "sat-0", "sat-1", latency_ms=5.0))
        tm.add_link(_make_link("l-fast-b", "sat-1", "sat-2", latency_ms=5.0))
        path, cost = tm.shortest_path("sat-0", "sat-2")
        assert path == ["sat-0", "sat-1", "sat-2"]
        assert cost == 10.0

    def test_unknown_source_or_target(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-0"))
        path, cost = tm.shortest_path("sat-0", "sat-99")
        assert path == []
        assert cost == float("inf")


# -- Broadcast tree ------------------------------------------------------- #


class TestBroadcastTree:
    def test_broadcast_tree(self):
        tm = TopologyManager()
        for i in range(4):
            tm.add_node(_make_node(f"sat-{i}"))
        tm.add_link(_make_link("l0", "sat-0", "sat-1"))
        tm.add_link(_make_link("l1", "sat-0", "sat-2"))
        tm.add_link(_make_link("l2", "sat-2", "sat-3"))
        tree = tm.broadcast_tree("sat-0", ["sat-1", "sat-3"])
        assert "sat-1" in tree
        assert "sat-3" in tree
        assert tree["sat-1"] == ["sat-0", "sat-1"]


# -- Heartbeat ------------------------------------------------------------ #


class TestHeartbeat:
    def test_heartbeat_timeout(self):
        tm = TopologyManager(heartbeat_timeout_s=0.0)
        node = _make_node("sat-1")
        node.last_heartbeat = 0.0  # way in the past
        tm.add_node(node)
        timed_out = tm.check_heartbeats()
        assert "sat-1" in timed_out
        assert tm.get_node("sat-1").status == NodeStatus.OFFLINE


# -- Snapshot ------------------------------------------------------------- #


class TestSnapshot:
    def test_snapshot_structure(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-0"))
        tm.add_node(_make_node("sat-1"))
        tm.add_link(_make_link("l0", "sat-0", "sat-1"))
        snap = tm.snapshot()
        assert "nodes" in snap
        assert "links" in snap
        assert "sat-0" in snap["nodes"]
        assert "l0" in snap["links"]
