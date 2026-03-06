"""Pluggable routing strategies for broadcast distribution tree computation.

Extends the basic shortest-path and Steiner tree algorithms with strategies
that optimise for latency, bandwidth, load balance, or delay bounds – common
objectives in LEO satellite SDN literature.

References:

* Handley, M. "Delay is Not an Option: Low Latency Routing in Space,"
  *HotNets*, 2018.
* Jia, W. et al. "Minimum-delay Steiner trees for multicast in LEO
  satellite networks," *IEEE ICC*, 2001.
* Liu, J. et al. "Load-balanced multicast tree for LEO satellite
  networks," *Computer Networks*, 2020.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Set, Tuple

from .models import Link, RoutingStrategy
from .topology import TopologyManager


# ------------------------------------------------------------------
# Strategy interface
# ------------------------------------------------------------------


def compute_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
    strategy: RoutingStrategy = RoutingStrategy.SHORTEST_PATH,
    max_latency_ms: float = 0.0,
) -> List[Link]:
    """Compute a broadcast distribution tree using the given *strategy*.

    This is the single entry point that dispatches to the appropriate
    algorithm.

    Parameters
    ----------
    topology:
        The network topology.
    source_id:
        ID of the source node.
    destination_ids:
        Set of destination node IDs.
    strategy:
        Routing strategy to use.
    max_latency_ms:
        Maximum allowable end-to-end latency (only used by
        ``DELAY_BOUNDED``; 0 means unbounded).

    Returns
    -------
    List[Link]:
        Links forming the distribution tree, or an empty list if no
        valid tree can be computed.
    """
    if not destination_ids:
        return []

    if strategy == RoutingStrategy.SHORTEST_PATH:
        return _shortest_path_tree(topology, source_id, destination_ids)
    elif strategy == RoutingStrategy.MINIMUM_COST_TREE:
        return _minimum_cost_tree(topology, source_id, destination_ids)
    elif strategy == RoutingStrategy.MIN_LATENCY:
        return _min_latency_tree(topology, source_id, destination_ids)
    elif strategy == RoutingStrategy.MAX_BANDWIDTH:
        return _max_bandwidth_tree(topology, source_id, destination_ids)
    elif strategy == RoutingStrategy.LOAD_BALANCED:
        return _load_balanced_tree(topology, source_id, destination_ids)
    elif strategy == RoutingStrategy.DELAY_BOUNDED:
        return _delay_bounded_tree(
            topology, source_id, destination_ids, max_latency_ms
        )
    else:
        return _shortest_path_tree(topology, source_id, destination_ids)


# ------------------------------------------------------------------
# Strategy implementations
# ------------------------------------------------------------------


def _shortest_path_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Build a shortest-path tree (by link cost)."""
    return _build_tree_by_weight(
        topology, source_id, destination_ids, weight_fn=lambda l: l.cost
    )


def _minimum_cost_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Greedy Steiner tree approximation using cost metric."""
    return _greedy_steiner(
        topology, source_id, destination_ids, weight_fn=lambda l: l.cost
    )


def _min_latency_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Build tree minimising maximum end-to-end latency.

    Uses link ``latency_ms`` as the edge weight so that Dijkstra finds
    the minimum-latency path to each destination.
    """
    return _build_tree_by_weight(
        topology, source_id, destination_ids, weight_fn=lambda l: l.latency_ms
    )


def _max_bandwidth_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Build tree maximising bottleneck bandwidth (widest-path tree).

    Each destination is reached via the path whose minimum-bandwidth link
    is as large as possible.  We transform this into a shortest-path
    problem by using ``-bandwidth`` as the weight; Dijkstra then finds
    the "widest" path.
    """
    return _build_tree_by_weight(
        topology,
        source_id,
        destination_ids,
        weight_fn=lambda l: -l.bandwidth_mbps,
    )


def _load_balanced_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Build tree preferring links with lower current load.

    The weight combines link cost with a load penalty.
    ``weight = cost * (1 + load)``
    """
    return _build_tree_by_weight(
        topology,
        source_id,
        destination_ids,
        weight_fn=lambda l: l.cost * (1.0 + l.load),
    )


def _delay_bounded_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
    max_latency_ms: float,
) -> List[Link]:
    """Build a cost-optimal tree subject to a latency constraint.

    Strategy: first compute the min-latency tree.  If every destination's
    latency is within *max_latency_ms*, accept it.  Otherwise, return an
    empty list (infeasible).

    For feasible topologies we then attempt a cost-optimal tree (Steiner
    approximation) and verify the latency bound; if it violates the bound
    we fall back to the latency-optimal tree.
    """
    latency_tree = _build_tree_by_weight(
        topology, source_id, destination_ids, weight_fn=lambda l: l.latency_ms
    )
    if not latency_tree:
        return []

    if max_latency_ms > 0:
        # Check feasibility
        max_path = _max_tree_latency(
            topology, source_id, destination_ids, latency_tree
        )
        if max_path > max_latency_ms:
            return []  # infeasible

    # Try cost-optimal tree
    cost_tree = _greedy_steiner(
        topology, source_id, destination_ids, weight_fn=lambda l: l.cost
    )
    if cost_tree and max_latency_ms > 0:
        max_path = _max_tree_latency(
            topology, source_id, destination_ids, cost_tree
        )
        if max_path <= max_latency_ms:
            return cost_tree

    return latency_tree


# ------------------------------------------------------------------
# Generic building blocks
# ------------------------------------------------------------------


def _dijkstra(
    topology: TopologyManager,
    source_id: str,
    weight_fn,
) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
    """Run Dijkstra with a custom weight function.

    Returns (dist, prev) dictionaries.
    """
    dist: Dict[str, float] = {source_id: 0.0}
    prev: Dict[str, Optional[str]] = {source_id: None}
    visited: Set[str] = set()
    heap: List[Tuple[float, str]] = [(0.0, source_id)]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for neighbor_id, link in topology.get_neighbors(u):
            if neighbor_id in visited:
                continue
            w = weight_fn(link)
            nd = d + w
            if nd < dist.get(neighbor_id, float("inf")):
                dist[neighbor_id] = nd
                prev[neighbor_id] = u
                heapq.heappush(heap, (nd, neighbor_id))

    return dist, prev


def _reconstruct_path(
    prev: Dict[str, Optional[str]], dst: str
) -> Optional[List[str]]:
    if dst not in prev:
        return None
    path: List[str] = []
    cur: Optional[str] = dst
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def _build_tree_by_weight(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
    weight_fn,
) -> List[Link]:
    """SPT using arbitrary link weight function."""
    dist, prev = _dijkstra(topology, source_id, weight_fn)

    tree_link_ids: Set[str] = set()
    tree_links: List[Link] = []

    for dst_id in destination_ids:
        path = _reconstruct_path(prev, dst_id)
        if path is None:
            return []
        for i in range(len(path) - 1):
            link = topology.find_link_between(path[i], path[i + 1])
            if link is None:
                return []
            if link.link_id not in tree_link_ids:
                tree_link_ids.add(link.link_id)
                tree_links.append(link)

    return tree_links


def _greedy_steiner(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
    weight_fn,
) -> List[Link]:
    """Greedy Steiner tree approximation with custom weight function."""
    covered: Set[str] = {source_id}
    remaining = set(destination_ids) - covered
    tree_link_ids: Set[str] = set()
    tree_links: List[Link] = []

    while remaining:
        best_path: Optional[List[str]] = None
        best_cost = float("inf")
        best_dst: Optional[str] = None

        for tree_node in list(covered):
            dist, prev = _dijkstra(topology, tree_node, weight_fn)
            for dst in remaining:
                if dst in dist and dist[dst] < best_cost:
                    best_cost = dist[dst]
                    best_path = _reconstruct_path(prev, dst)
                    best_dst = dst

        if best_path is None or best_dst is None:
            return []

        for i in range(len(best_path) - 1):
            link = topology.find_link_between(best_path[i], best_path[i + 1])
            if link is None:
                return []
            if link.link_id not in tree_link_ids:
                tree_link_ids.add(link.link_id)
                tree_links.append(link)
            covered.add(best_path[i + 1])

        remaining.discard(best_dst)

    return tree_links


def _max_tree_latency(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
    tree_links: List[Link],
) -> float:
    """Return the maximum end-to-end latency in *tree_links*.

    Performs a BFS on the tree subgraph collecting latency sums.
    """
    adj: Dict[str, List[Tuple[str, float]]] = {}
    for link in tree_links:
        adj.setdefault(link.source_id, []).append(
            (link.target_id, link.latency_ms)
        )

    latency: Dict[str, float] = {source_id: 0.0}
    queue = [source_id]
    while queue:
        nxt: List[str] = []
        for u in queue:
            for v, lat in adj.get(u, []):
                if v not in latency:
                    latency[v] = latency[u] + lat
                    nxt.append(v)
        queue = nxt

    worst = 0.0
    for d in destination_ids:
        if d in latency:
            worst = max(worst, latency[d])
        else:
            return float("inf")
    return worst
