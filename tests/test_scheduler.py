"""Tests for the ResourceScheduler."""

from satellite_sdn.models import BroadcastTask, InterSatelliteLink, NodeStatus, SatelliteNode
from satellite_sdn.scheduler import ResourceScheduler
from satellite_sdn.topology import TopologyManager


def _make_node(node_id: str, orbit: int = 0, idx: int = 0, **kwargs) -> SatelliteNode:
    return SatelliteNode(node_id=node_id, orbit_id=orbit, position_index=idx, **kwargs)


def _make_link(link_id: str, src: str, tgt: str, **kwargs) -> InterSatelliteLink:
    return InterSatelliteLink(link_id=link_id, source_id=src, target_id=tgt, **kwargs)


def _build_topology() -> TopologyManager:
    """Build a small topology: sat-0 -> sat-1 -> sat-2, sat-0 -> sat-3."""
    tm = TopologyManager()
    for i in range(4):
        tm.add_node(_make_node(f"sat-{i}", bandwidth_mbps=500.0))
    tm.add_link(_make_link("l0", "sat-0", "sat-1"))
    tm.add_link(_make_link("l1", "sat-1", "sat-2"))
    tm.add_link(_make_link("l2", "sat-0", "sat-3"))
    return tm


class TestScheduleSingleTask:
    def test_schedule_success(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        task = BroadcastTask(
            task_id="t1",
            source_node_id="sat-0",
            target_node_ids=["sat-2", "sat-3"],
            bandwidth_required_mbps=50.0,
        )
        results = sched.schedule([task])
        assert len(results) == 1
        r = results[0]
        assert r.success is True
        assert "sat-2" in r.assigned_paths
        assert "sat-3" in r.assigned_paths
        assert len(r.flow_rules) > 0

    def test_schedule_unavailable_source(self):
        tm = _build_topology()
        tm.update_node_status("sat-0", NodeStatus.OFFLINE)
        sched = ResourceScheduler(tm)
        task = BroadcastTask(task_id="t1", source_node_id="sat-0", target_node_ids=["sat-2"])
        results = sched.schedule([task])
        assert results[0].success is False
        assert "unavailable" in results[0].reason

    def test_schedule_insufficient_bandwidth(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        task = BroadcastTask(
            task_id="t1",
            source_node_id="sat-0",
            target_node_ids=["sat-2"],
            bandwidth_required_mbps=9999.0,
        )
        results = sched.schedule([task])
        assert results[0].success is False

    def test_schedule_no_reachable_targets(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-0"))
        tm.add_node(_make_node("sat-1"))
        sched = ResourceScheduler(tm)
        task = BroadcastTask(task_id="t1", source_node_id="sat-0", target_node_ids=["sat-1"])
        results = sched.schedule([task])
        assert results[0].success is False


class TestSchedulePriority:
    def test_higher_priority_scheduled_first(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        lo = BroadcastTask(
            task_id="lo", source_node_id="sat-0", target_node_ids=["sat-2"],
            bandwidth_required_mbps=50.0, priority=1,
        )
        hi = BroadcastTask(
            task_id="hi", source_node_id="sat-0", target_node_ids=["sat-2"],
            bandwidth_required_mbps=50.0, priority=10,
        )
        results = sched.schedule([lo, hi])
        # Both should succeed in this topology
        assert results[0].task_id == "lo"
        assert results[1].task_id == "hi"
        assert all(r.success for r in results)


class TestScheduleLoadThreshold:
    def test_overloaded_node_rejected(self):
        tm = TopologyManager()
        tm.add_node(_make_node("sat-0", cpu_usage=0.0, bandwidth_mbps=500.0))
        tm.add_node(_make_node("sat-1", cpu_usage=0.9, memory_usage=0.9, bandwidth_mbps=100.0))
        tm.add_link(_make_link("l0", "sat-0", "sat-1"))
        sched = ResourceScheduler(tm, load_threshold=0.8)
        task = BroadcastTask(
            task_id="t1", source_node_id="sat-0", target_node_ids=["sat-1"],
            bandwidth_required_mbps=50.0,
        )
        results = sched.schedule([task])
        assert results[0].success is False


class TestBandwidthReservation:
    def test_bandwidth_decremented(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        task = BroadcastTask(
            task_id="t1",
            source_node_id="sat-0",
            target_node_ids=["sat-3"],
            bandwidth_required_mbps=100.0,
        )
        sched.schedule([task])
        # sat-0 and sat-3 should have bandwidth reduced
        assert tm.get_node("sat-0").bandwidth_mbps == 400.0
        assert tm.get_node("sat-3").bandwidth_mbps == 400.0


class TestFlowRuleGeneration:
    def test_flow_rules_match_path_hops(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        task = BroadcastTask(
            task_id="t1",
            source_node_id="sat-0",
            target_node_ids=["sat-2"],
            bandwidth_required_mbps=50.0,
        )
        results = sched.schedule([task])
        r = results[0]
        path = r.assigned_paths["sat-2"]
        # One flow rule per hop (len(path) - 1)
        expected_rules = len(path) - 1
        sat2_rules = [fr for fr in r.flow_rules if fr.destination == "sat-2"]
        assert len(sat2_rules) == expected_rules

    def test_get_result(self):
        tm = _build_topology()
        sched = ResourceScheduler(tm)
        task = BroadcastTask(
            task_id="t1", source_node_id="sat-0", target_node_ids=["sat-3"],
            bandwidth_required_mbps=50.0,
        )
        sched.schedule([task])
        assert sched.get_result("t1") is not None
        assert sched.get_result("nonexistent") is None
