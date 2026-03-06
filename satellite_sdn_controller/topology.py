"""Topology manager for the satellite broadcast distribution network.

Maintains a graph of nodes and links, and provides topology query operations.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from .models import Link, LinkState, Node, NodeType

# Speed of light in km/s – used for propagation delay estimation.
SPEED_OF_LIGHT_KM_S = 299_792.458


def _haversine_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Return great-circle distance in km between two points on Earth."""
    r = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_propagation_delay_ms(src: Node, dst: Node) -> float:
    """Estimate one-way propagation delay between two nodes (ms).

    For satellite links the signal must travel up to the satellite altitude and
    back down, so we approximate the slant range.
    """
    ground_dist = _haversine_distance_km(
        src.latitude, src.longitude, dst.latitude, dst.longitude
    )
    altitude_diff = abs(src.altitude_km - dst.altitude_km)
    slant_range = math.sqrt(ground_dist**2 + altitude_diff**2)
    # Add the larger altitude to represent the up-leg
    total_path = slant_range + max(src.altitude_km, dst.altitude_km)
    return (total_path / SPEED_OF_LIGHT_KM_S) * 1000.0


class TopologyManager:
    """Manages the satellite network topology as a directed graph."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._links: Dict[str, Link] = {}
        # Adjacency: node_id -> set of link_ids originating from that node
        self._adj: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add or update a node in the topology."""
        self._nodes[node.node_id] = node
        self._adj.setdefault(node.node_id, set())

    def remove_node(self, node_id: str) -> Optional[Node]:
        """Remove a node and all its connected links."""
        node = self._nodes.pop(node_id, None)
        if node is None:
            return None
        # Remove all links connected to this node
        links_to_remove = [
            lid
            for lid, lnk in self._links.items()
            if lnk.source_id == node_id or lnk.target_id == node_id
        ]
        for lid in links_to_remove:
            self.remove_link(lid)
        self._adj.pop(node_id, None)
        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[Node]:
        return list(self._nodes.values())

    def get_nodes_by_type(self, node_type: NodeType) -> List[Node]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    # ------------------------------------------------------------------
    # Link operations
    # ------------------------------------------------------------------

    def add_link(self, link: Link) -> None:
        """Add or update a link in the topology."""
        if link.source_id not in self._nodes:
            raise ValueError(f"Source node {link.source_id} not in topology")
        if link.target_id not in self._nodes:
            raise ValueError(f"Target node {link.target_id} not in topology")
        self._links[link.link_id] = link
        self._adj.setdefault(link.source_id, set()).add(link.link_id)

    def remove_link(self, link_id: str) -> Optional[Link]:
        link = self._links.pop(link_id, None)
        if link is None:
            return None
        self._adj.get(link.source_id, set()).discard(link_id)
        return link

    def get_link(self, link_id: str) -> Optional[Link]:
        return self._links.get(link_id)

    def get_all_links(self) -> List[Link]:
        return list(self._links.values())

    def get_active_links(self) -> List[Link]:
        return [l for l in self._links.values() if l.state != LinkState.DOWN]

    def set_link_state(self, link_id: str, state: LinkState) -> bool:
        link = self._links.get(link_id)
        if link is None:
            return False
        link.state = state
        return True

    # ------------------------------------------------------------------
    # Topology queries
    # ------------------------------------------------------------------

    def get_neighbors(self, node_id: str) -> List[Tuple[str, Link]]:
        """Return list of (neighbor_node_id, link) pairs reachable from *node_id*."""
        result: List[Tuple[str, Link]] = []
        for lid in self._adj.get(node_id, set()):
            link = self._links[lid]
            if link.state != LinkState.DOWN:
                result.append((link.target_id, link))
        return result

    def shortest_path(
        self, src_id: str, dst_id: str
    ) -> Optional[List[str]]:
        """Dijkstra shortest-cost path, returning list of node IDs or *None*."""
        if src_id not in self._nodes or dst_id not in self._nodes:
            return None

        import heapq

        dist: Dict[str, float] = {src_id: 0.0}
        prev: Dict[str, Optional[str]] = {src_id: None}
        visited: Set[str] = set()
        heap: List[Tuple[float, str]] = [(0.0, src_id)]

        while heap:
            d, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)
            if u == dst_id:
                break
            for neighbor_id, link in self.get_neighbors(u):
                if neighbor_id in visited:
                    continue
                nd = d + link.cost
                if nd < dist.get(neighbor_id, float("inf")):
                    dist[neighbor_id] = nd
                    prev[neighbor_id] = u
                    heapq.heappush(heap, (nd, neighbor_id))

        if dst_id not in prev:
            return None

        path: List[str] = []
        cur: Optional[str] = dst_id
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def find_link_between(self, src_id: str, dst_id: str) -> Optional[Link]:
        """Return the link from *src_id* to *dst_id*, or *None*."""
        for lid in self._adj.get(src_id, set()):
            link = self._links[lid]
            if link.target_id == dst_id and link.state != LinkState.DOWN:
                return link
        return None

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def link_count(self) -> int:
        return len(self._links)
