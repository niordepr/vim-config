"""Resource scheduling algorithm for satellite broadcast distribution.

The scheduler assigns broadcast tasks to satellite nodes considering:
- Current node load (CPU, memory, bandwidth)
- Network topology and path quality
- Task priority and bandwidth requirements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .models import BroadcastTask, FlowRule, SatelliteNode
from .topology import TopologyManager

logger = logging.getLogger(__name__)


@dataclass
class ScheduleResult:
    """Result of scheduling a single broadcast task.

    Attributes:
        task_id: The scheduled task id.
        assigned_paths: Mapping of target node id to the path (list of node ids).
        flow_rules: Generated SDN flow rules.
        success: Whether scheduling succeeded.
        reason: Human-readable reason on failure.
    """

    task_id: str
    assigned_paths: dict[str, list[str]] = field(default_factory=dict)
    flow_rules: list[FlowRule] = field(default_factory=list)
    success: bool = True
    reason: str = ""


class ResourceScheduler:
    """Priority-aware resource scheduler for broadcast distribution tasks.

    The scheduling algorithm works as follows:
    1. Tasks are sorted by descending priority.
    2. For each task the scheduler checks that the source node is available
       and has sufficient bandwidth.
    3. A broadcast tree is computed via the topology manager.
    4. For every path in the tree the scheduler verifies that each
       intermediate node satisfies the load threshold.
    5. Flow rules are generated for the valid paths and bandwidth is
       reserved on traversed nodes.
    """

    def __init__(
        self,
        topology: TopologyManager,
        *,
        load_threshold: float = 0.8,
        max_retries: int = 2,
    ) -> None:
        self._topology = topology
        self._load_threshold = load_threshold
        self._max_retries = max_retries
        self._rule_counter = 0
        self._scheduled: dict[str, ScheduleResult] = {}

    # -- Public API ------------------------------------------------------- #

    def schedule(self, tasks: list[BroadcastTask]) -> list[ScheduleResult]:
        """Schedule a batch of broadcast tasks.

        Returns a list of :class:`ScheduleResult` in the same order as
        the input *tasks*.
        """
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)
        results: dict[str, ScheduleResult] = {}
        for task in sorted_tasks:
            result = self._schedule_single(task)
            results[task.task_id] = result
            self._scheduled[task.task_id] = result
        return [results[t.task_id] for t in tasks]

    def get_result(self, task_id: str) -> Optional[ScheduleResult]:
        return self._scheduled.get(task_id)

    # -- Internal --------------------------------------------------------- #

    def _schedule_single(self, task: BroadcastTask) -> ScheduleResult:
        source = self._topology.get_node(task.source_node_id)
        if source is None or not source.is_available:
            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                reason=f"Source node {task.source_node_id} is unavailable",
            )

        if source.bandwidth_mbps < task.bandwidth_required_mbps:
            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                reason=f"Source node {task.source_node_id} has insufficient bandwidth",
            )

        tree = self._topology.broadcast_tree(task.source_node_id, task.target_node_ids)
        if not tree:
            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                reason="No reachable targets",
            )

        assigned_paths: dict[str, list[str]] = {}
        flow_rules: list[FlowRule] = []
        failed_targets: list[str] = []

        for target_id, path in tree.items():
            if self._validate_path(path, task.bandwidth_required_mbps):
                assigned_paths[target_id] = path
                rules = self._generate_flow_rules(task, path)
                flow_rules.extend(rules)
                self._reserve_bandwidth(path, task.bandwidth_required_mbps)
            else:
                failed_targets.append(target_id)

        if not assigned_paths:
            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                reason="All paths exceed load threshold or lack bandwidth",
            )

        if failed_targets:
            logger.warning(
                "Task %s: %d/%d targets unreachable due to overload",
                task.task_id,
                len(failed_targets),
                len(task.target_node_ids),
            )

        return ScheduleResult(
            task_id=task.task_id,
            assigned_paths=assigned_paths,
            flow_rules=flow_rules,
            success=True,
        )

    def _validate_path(self, path: list[str], bw_required: float) -> bool:
        """Check that every node on the path is below the load threshold
        and has enough available bandwidth."""
        for node_id in path:
            node = self._topology.get_node(node_id)
            if node is None or not node.is_available:
                return False
            if node.load_score > self._load_threshold:
                return False
            if node.bandwidth_mbps < bw_required:
                return False
        return True

    def _generate_flow_rules(self, task: BroadcastTask, path: list[str]) -> list[FlowRule]:
        """Generate flow rules for each hop in the path."""
        rules: list[FlowRule] = []
        for i in range(len(path) - 1):
            self._rule_counter += 1
            rule = FlowRule(
                rule_id=f"rule-{self._rule_counter}",
                node_id=path[i],
                source=task.source_node_id,
                destination=path[-1],
                next_hop=path[i + 1],
                priority=task.priority * 10,
                bandwidth_mbps=task.bandwidth_required_mbps,
            )
            rules.append(rule)
        return rules

    def _reserve_bandwidth(self, path: list[str], bw: float) -> None:
        """Deduct bandwidth from nodes along the path."""
        for node_id in path:
            node = self._topology.get_node(node_id)
            if node is not None:
                node.bandwidth_mbps = max(0.0, node.bandwidth_mbps - bw)
