"""SDN controller for satellite broadcast distribution system.

The controller is the central component that:
- Maintains the network topology via :class:`TopologyManager`
- Schedules broadcast tasks via :class:`ResourceScheduler`
- Installs / removes flow rules on satellite nodes
- Exposes a REST-like API for K8s health checks and management
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

from .models import (
    BroadcastTask,
    InterSatelliteLink,
    LinkStatus,
    NodeStatus,
    SatelliteNode,
)
from .scheduler import ResourceScheduler, ScheduleResult
from .topology import TopologyManager

logger = logging.getLogger(__name__)

_HEALTH_PORT = 8081


class SDNController:
    """Central SDN controller for the satellite broadcast distribution system.

    This controller is designed to run as a single-replica K8s Deployment.
    It periodically checks heartbeats, re-evaluates the topology, and
    provides a health endpoint for K8s liveness / readiness probes.
    """

    def __init__(
        self,
        *,
        heartbeat_timeout_s: float = 30.0,
        load_threshold: float = 0.8,
        reconcile_interval_s: float = 10.0,
    ) -> None:
        self._topology = TopologyManager(heartbeat_timeout_s=heartbeat_timeout_s)
        self._scheduler = ResourceScheduler(self._topology, load_threshold=load_threshold)
        self._reconcile_interval = reconcile_interval_s
        self._installed_rules: dict[str, list[dict[str, Any]]] = {}
        self._running = False
        self._lock = threading.Lock()

    # -- Topology operations ---------------------------------------------- #

    def register_node(self, node: SatelliteNode) -> None:
        with self._lock:
            self._topology.add_node(node)

    def deregister_node(self, node_id: str) -> Optional[SatelliteNode]:
        with self._lock:
            return self._topology.remove_node(node_id)

    def register_link(self, link: InterSatelliteLink) -> None:
        with self._lock:
            self._topology.add_link(link)

    def update_node_metrics(self, node_id: str, **kwargs: Any) -> None:
        with self._lock:
            self._topology.update_node_metrics(node_id, **kwargs)

    def update_link_status(self, link_id: str, status: LinkStatus) -> None:
        with self._lock:
            self._topology.update_link_status(link_id, status)

    def update_node_status(self, node_id: str, status: NodeStatus) -> None:
        with self._lock:
            self._topology.update_node_status(node_id, status)

    # -- Scheduling ------------------------------------------------------- #

    def submit_tasks(self, tasks: list[BroadcastTask]) -> list[ScheduleResult]:
        """Schedule broadcast tasks and install flow rules."""
        with self._lock:
            results = self._scheduler.schedule(tasks)
        for result in results:
            if result.success:
                self._install_flow_rules(result)
        return results

    def _install_flow_rules(self, result: ScheduleResult) -> None:
        """Persist / apply flow rules (simulation)."""
        rules_data = [
            {
                "rule_id": r.rule_id,
                "node_id": r.node_id,
                "source": r.source,
                "destination": r.destination,
                "next_hop": r.next_hop,
                "priority": r.priority,
                "bandwidth_mbps": r.bandwidth_mbps,
            }
            for r in result.flow_rules
        ]
        self._installed_rules[result.task_id] = rules_data
        logger.info("Installed %d flow rules for task %s", len(rules_data), result.task_id)

    # -- Reconciliation loop ---------------------------------------------- #

    def _reconcile(self) -> None:
        """Periodic reconciliation: check heartbeats and update topology."""
        while self._running:
            with self._lock:
                timed_out = self._topology.check_heartbeats()
            if timed_out:
                logger.warning("Reconcile: %d nodes timed out: %s", len(timed_out), timed_out)
            time.sleep(self._reconcile_interval)

    # -- Lifecycle -------------------------------------------------------- #

    def start(self, *, blocking: bool = False) -> None:
        """Start the controller reconciliation loop.

        If *blocking* is ``True`` the call blocks until :meth:`stop` is
        called from another thread.
        """
        self._running = True
        self._reconcile_thread = threading.Thread(target=self._reconcile, daemon=True)
        self._reconcile_thread.start()
        logger.info("SDN controller started")
        if blocking:
            self._reconcile_thread.join()

    def stop(self) -> None:
        self._running = False
        logger.info("SDN controller stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # -- Introspection ---------------------------------------------------- #

    def topology_snapshot(self) -> dict:
        with self._lock:
            return self._topology.snapshot()

    @property
    def installed_rules(self) -> dict[str, list[dict[str, Any]]]:
        return dict(self._installed_rules)

    @property
    def topology(self) -> TopologyManager:
        return self._topology

    @property
    def scheduler(self) -> ResourceScheduler:
        return self._scheduler


# -- HTTP health / API server --------------------------------------------- #


def _make_health_handler(controller: SDNController) -> type:
    """Create an HTTP request handler bound to *controller*."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._json_response(200, {"status": "ok"})
            elif self.path == "/readyz":
                status = "ready" if controller.is_running else "not_ready"
                code = 200 if controller.is_running else 503
                self._json_response(code, {"status": status})
            elif self.path == "/topology":
                self._json_response(200, controller.topology_snapshot())
            elif self.path == "/rules":
                self._json_response(200, controller.installed_rules)
            else:
                self._json_response(404, {"error": "not found"})

        def _json_response(self, code: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug(format, *args)

    return _Handler


def run_controller_server(
    controller: SDNController,
    host: str = "0.0.0.0",
    port: int = _HEALTH_PORT,
) -> None:
    """Start the health / API HTTP server (blocking)."""
    handler_cls = _make_health_handler(controller)
    server = HTTPServer((host, port), handler_cls)
    logger.info("Health server listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
