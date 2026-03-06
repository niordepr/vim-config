"""Multicast tree computation for satellite broadcast distribution.

Provides algorithms to build minimum-cost Steiner-like trees connecting a
source node to a set of destination nodes, suitable for broadcast / multicast
distribution over a satellite SDN network.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .models import Link
from .topology import TopologyManager


def compute_shortest_path_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Build a shortest-path tree from *source_id* to every destination.

    This is a simple approach: compute the shortest path to each destination
    independently and merge the paths.  Shared links are included only once.

    Returns a list of :class:`Link` objects forming the tree, or an empty list
    if any destination is unreachable.
    """
    tree_link_ids: Set[str] = set()
    tree_links: List[Link] = []

    for dst_id in destination_ids:
        path = topology.shortest_path(source_id, dst_id)
        if path is None:
            return []  # unreachable destination
        for i in range(len(path) - 1):
            link = topology.find_link_between(path[i], path[i + 1])
            if link is None:
                return []
            if link.link_id not in tree_link_ids:
                tree_link_ids.add(link.link_id)
                tree_links.append(link)

    return tree_links


def compute_minimum_cost_tree(
    topology: TopologyManager,
    source_id: str,
    destination_ids: Set[str],
) -> List[Link]:
    """Approximate Steiner tree using a greedy heuristic.

    1. Start with the source in the tree.
    2. Repeatedly find the closest un-covered destination (by shortest path
       cost to the current tree) and add the path to the tree.

    This is a well-known 2-approximation for the Steiner tree problem on
    graphs with metric costs.

    Returns a list of :class:`Link` objects forming the tree.
    """
    if not destination_ids:
        return []

    covered: Set[str] = {source_id}
    remaining = set(destination_ids) - covered
    tree_link_ids: Set[str] = set()
    tree_links: List[Link] = []

    while remaining:
        best_path: Optional[List[str]] = None
        best_cost = float("inf")
        best_dst: Optional[str] = None

        for dst in remaining:
            # Try from every node already in the tree
            for tree_node in list(covered):
                path = topology.shortest_path(tree_node, dst)
                if path is None:
                    continue
                cost = _path_cost(topology, path)
                if cost < best_cost:
                    best_cost = cost
                    best_path = path
                    best_dst = dst

        if best_path is None or best_dst is None:
            return []  # some destinations are unreachable

        # Add the path to the tree
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


def _path_cost(topology: TopologyManager, path: List[str]) -> float:
    """Sum of link costs along *path*."""
    total = 0.0
    for i in range(len(path) - 1):
        link = topology.find_link_between(path[i], path[i + 1])
        if link is None:
            return float("inf")
        total += link.cost
    return total


def validate_tree_bandwidth(
    tree_links: List[Link], required_mbps: float
) -> List[Link]:
    """Return list of links in the tree that lack sufficient bandwidth."""
    return [l for l in tree_links if l.bandwidth_mbps < required_mbps]
