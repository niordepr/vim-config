"""LEO satellite constellation topology manager.

Tracks satellites, inter-satellite links and computes shortest paths
as the topology changes due to orbital dynamics.
"""

from __future__ import annotations

import heapq
import logging
import time
from typing import Optional

from .models import (
    InterSatelliteLink,
    LinkStatus,
    NodeStatus,
    SatelliteNode,
)

logger = logging.getLogger(__name__)


class TopologyManager:
    """Manages the dynamic LEO satellite network topology.

    The topology is represented as a directed graph where nodes are
    :class:`SatelliteNode` instances and edges are
    :class:`InterSatelliteLink` instances.

    The manager exposes methods to add / remove / update nodes and links
    and to compute shortest paths using Dijkstra's algorithm.
    """

    def __init__(self, heartbeat_timeout_s: float = 30.0) -> None:
        self._nodes: dict[str, SatelliteNode] = {}
        self._links: dict[str, InterSatelliteLink] = {}
        # Adjacency list: node_id -> list of link_ids
        self._adjacency: dict[str, list[str]] = {}
        self._heartbeat_timeout_s = heartbeat_timeout_s

    # -- Node management -------------------------------------------------- #

    def add_node(self, node: SatelliteNode) -> None:
        """Register a satellite node."""
        self._nodes[node.node_id] = node
        self._adjacency.setdefault(node.node_id, [])
        logger.info("Node %s added (orbit=%d, idx=%d)", node.node_id, node.orbit_id, node.position_index)

    def remove_node(self, node_id: str) -> Optional[SatelliteNode]:
        """Remove a satellite node and its associated links."""
        node = self._nodes.pop(node_id, None)
        if node is None:
            return None
        # Remove links referencing this node
        link_ids_to_remove = [
            lid
            for lid, link in self._links.items()
            if link.source_id == node_id or link.target_id == node_id
        ]
        for lid in link_ids_to_remove:
            self.remove_link(lid)
        self._adjacency.pop(node_id, None)
        logger.info("Node %s removed", node_id)
        return node

    def get_node(self, node_id: str) -> Optional[SatelliteNode]:
        """Return a node by id or ``None``."""
        return self._nodes.get(node_id)

    def update_node_status(self, node_id: str, status: NodeStatus) -> None:
        """Update the status of a node."""
        node = self._nodes.get(node_id)
        if node is not None:
            node.status = status
            logger.debug("Node %s status -> %s", node_id, status.value)

    def update_node_metrics(
        self,
        node_id: str,
        *,
        cpu_usage: Optional[float] = None,
        memory_usage: Optional[float] = None,
        bandwidth_mbps: Optional[float] = None,
    ) -> None:
        """Update resource metrics reported by a node."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        if cpu_usage is not None:
            node.cpu_usage = cpu_usage
        if memory_usage is not None:
            node.memory_usage = memory_usage
        if bandwidth_mbps is not None:
            node.bandwidth_mbps = bandwidth_mbps
        node.last_heartbeat = time.time()

    @property
    def nodes(self) -> dict[str, SatelliteNode]:
        return dict(self._nodes)

    @property
    def online_nodes(self) -> list[SatelliteNode]:
        """Return nodes that are currently online."""
        return [n for n in self._nodes.values() if n.is_available]

    # -- Link management -------------------------------------------------- #

    def add_link(self, link: InterSatelliteLink) -> None:
        """Register an inter-satellite link."""
        self._links[link.link_id] = link
        self._adjacency.setdefault(link.source_id, []).append(link.link_id)
        logger.info("Link %s added: %s -> %s", link.link_id, link.source_id, link.target_id)

    def remove_link(self, link_id: str) -> Optional[InterSatelliteLink]:
        """Remove a link."""
        link = self._links.pop(link_id, None)
        if link is None:
            return None
        adj = self._adjacency.get(link.source_id, [])
        if link_id in adj:
            adj.remove(link_id)
        logger.info("Link %s removed", link_id)
        return link

    def get_link(self, link_id: str) -> Optional[InterSatelliteLink]:
        return self._links.get(link_id)

    def update_link_status(self, link_id: str, status: LinkStatus) -> None:
        link = self._links.get(link_id)
        if link is not None:
            link.status = status

    @property
    def links(self) -> dict[str, InterSatelliteLink]:
        return dict(self._links)

    @property
    def active_links(self) -> list[InterSatelliteLink]:
        return [l for l in self._links.values() if l.status == LinkStatus.UP]

    # -- Heartbeat checking ----------------------------------------------- #

    def check_heartbeats(self) -> list[str]:
        """Mark nodes whose heartbeat has timed out as *OFFLINE*.

        Returns a list of node ids that were marked offline.
        """
        now = time.time()
        timed_out: list[str] = []
        for node in self._nodes.values():
            if node.status == NodeStatus.ONLINE and (now - node.last_heartbeat) > self._heartbeat_timeout_s:
                node.status = NodeStatus.OFFLINE
                timed_out.append(node.node_id)
                logger.warning("Node %s heartbeat timeout -> OFFLINE", node.node_id)
        return timed_out

    # -- Shortest path ---------------------------------------------------- #

    def shortest_path(self, source_id: str, target_id: str) -> tuple[list[str], float]:
        """Compute shortest path using Dijkstra with link cost.

        Returns:
            A tuple ``(path, total_cost)`` where *path* is a list of node ids
            from *source_id* to *target_id* (inclusive).  If no path exists
            the path list is empty and cost is ``inf``.
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return [], float("inf")

        dist: dict[str, float] = {nid: float("inf") for nid in self._nodes}
        dist[source_id] = 0.0
        prev: dict[str, Optional[str]] = {nid: None for nid in self._nodes}
        visited: set[str] = set()
        heap: list[tuple[float, str]] = [(0.0, source_id)]

        while heap:
            d, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)
            if u == target_id:
                break
            for lid in self._adjacency.get(u, []):
                link = self._links[lid]
                v = link.target_id
                if v in visited:
                    continue
                node_v = self._nodes.get(v)
                if node_v is None or not node_v.is_available:
                    continue
                new_dist = d + link.cost
                if new_dist < dist[v]:
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(heap, (new_dist, v))

        if dist[target_id] == float("inf"):
            return [], float("inf")

        path: list[str] = []
        cur: Optional[str] = target_id
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path, dist[target_id]

    def broadcast_tree(self, source_id: str, target_ids: list[str]) -> dict[str, list[str]]:
        """Build a simple broadcast distribution tree.

        Computes shortest paths from *source_id* to every target and
        returns a mapping ``{target_id: path}``.
        """
        tree: dict[str, list[str]] = {}
        for tid in target_ids:
            path, _ = self.shortest_path(source_id, tid)
            if path:
                tree[tid] = path
        return tree

    # -- Topology snapshot ------------------------------------------------ #

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the current topology."""
        return {
            "nodes": {
                nid: {
                    "orbit_id": n.orbit_id,
                    "position_index": n.position_index,
                    "status": n.status.value,
                    "cpu_usage": n.cpu_usage,
                    "memory_usage": n.memory_usage,
                    "bandwidth_mbps": n.bandwidth_mbps,
                    "load_score": n.load_score,
                }
                for nid, n in self._nodes.items()
            },
            "links": {
                lid: {
                    "source": l.source_id,
                    "target": l.target_id,
                    "latency_ms": l.latency_ms,
                    "bandwidth_mbps": l.bandwidth_mbps,
                    "status": l.status.value,
                }
                for lid, l in self._links.items()
            },
        }
