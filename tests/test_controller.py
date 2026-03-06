"""Tests for the SDNController."""

import json
import socket
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

from satellite_sdn.controller import SDNController, run_controller_server
from satellite_sdn.models import (
    BroadcastTask,
    InterSatelliteLink,
    LinkStatus,
    NodeStatus,
    SatelliteNode,
)


def _make_node(node_id: str, orbit: int = 0, idx: int = 0, **kwargs) -> SatelliteNode:
    return SatelliteNode(node_id=node_id, orbit_id=orbit, position_index=idx, **kwargs)


def _make_link(link_id: str, src: str, tgt: str, **kwargs) -> InterSatelliteLink:
    return InterSatelliteLink(link_id=link_id, source_id=src, target_id=tgt, **kwargs)


def _free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestControllerBasic:
    def test_register_and_deregister_node(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-1"))
        assert ctrl.topology.get_node("sat-1") is not None
        ctrl.deregister_node("sat-1")
        assert ctrl.topology.get_node("sat-1") is None

    def test_register_link(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-1"))
        ctrl.register_node(_make_node("sat-2"))
        ctrl.register_link(_make_link("l1", "sat-1", "sat-2"))
        assert ctrl.topology.get_link("l1") is not None

    def test_update_node_metrics(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-1"))
        ctrl.update_node_metrics("sat-1", cpu_usage=0.5)
        assert ctrl.topology.get_node("sat-1").cpu_usage == 0.5

    def test_update_link_status(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-1"))
        ctrl.register_node(_make_node("sat-2"))
        ctrl.register_link(_make_link("l1", "sat-1", "sat-2"))
        ctrl.update_link_status("l1", LinkStatus.DOWN)
        assert ctrl.topology.get_link("l1").status == LinkStatus.DOWN

    def test_update_node_status(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-1"))
        ctrl.update_node_status("sat-1", NodeStatus.DEGRADED)
        assert ctrl.topology.get_node("sat-1").status == NodeStatus.DEGRADED


class TestControllerScheduling:
    def test_submit_tasks_installs_rules(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-0", bandwidth_mbps=500))
        ctrl.register_node(_make_node("sat-1", bandwidth_mbps=500))
        ctrl.register_link(_make_link("l0", "sat-0", "sat-1"))
        task = BroadcastTask(
            task_id="t1",
            source_node_id="sat-0",
            target_node_ids=["sat-1"],
            bandwidth_required_mbps=50.0,
        )
        results = ctrl.submit_tasks([task])
        assert results[0].success is True
        assert "t1" in ctrl.installed_rules
        assert len(ctrl.installed_rules["t1"]) > 0

    def test_submit_task_failure(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-0", status=NodeStatus.OFFLINE))
        task = BroadcastTask(task_id="t1", source_node_id="sat-0", target_node_ids=["sat-1"])
        results = ctrl.submit_tasks([task])
        assert results[0].success is False
        assert "t1" not in ctrl.installed_rules


class TestControllerLifecycle:
    def test_start_and_stop(self):
        ctrl = SDNController(reconcile_interval_s=0.1)
        ctrl.start()
        assert ctrl.is_running is True
        ctrl.stop()
        assert ctrl.is_running is False

    def test_topology_snapshot(self):
        ctrl = SDNController()
        ctrl.register_node(_make_node("sat-0"))
        snap = ctrl.topology_snapshot()
        assert "sat-0" in snap["nodes"]


class TestHealthServer:
    """Integration tests for the HTTP health / API server.

    Uses a single server per test with a dynamically allocated port
    to avoid port conflicts between tests.
    """

    def _start_server(self):
        self.ctrl = SDNController()
        self.ctrl.register_node(_make_node("sat-0"))
        self.ctrl.start()
        self.port = _free_port()
        from satellite_sdn.controller import _make_health_handler

        handler_cls = _make_health_handler(self.ctrl)
        self.server = HTTPServer(("127.0.0.1", self.port), handler_cls)
        self.server.allow_reuse_address = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        time.sleep(0.1)

    def _stop_server(self):
        self.server.shutdown()
        self.ctrl.stop()

    def _get(self, path: str) -> tuple[int, dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        conn.close()
        return resp.status, body

    def test_healthz(self):
        self._start_server()
        try:
            status, body = self._get("/healthz")
            assert status == 200
            assert body["status"] == "ok"
        finally:
            self._stop_server()

    def test_readyz(self):
        self._start_server()
        try:
            status, body = self._get("/readyz")
            assert status == 200
            assert body["status"] == "ready"
        finally:
            self._stop_server()

    def test_topology_endpoint(self):
        self._start_server()
        try:
            status, body = self._get("/topology")
            assert status == 200
            assert "nodes" in body
        finally:
            self._stop_server()

    def test_rules_endpoint(self):
        self._start_server()
        try:
            status, body = self._get("/rules")
            assert status == 200
        finally:
            self._stop_server()

    def test_not_found(self):
        self._start_server()
        try:
            status, body = self._get("/nonexistent")
            assert status == 404
        finally:
            self._stop_server()
