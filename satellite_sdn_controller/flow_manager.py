"""Flow manager for the satellite broadcast distribution SDN controller.

Responsible for installing, removing, and querying flow rules on network
nodes.  Flow rules are the forwarding directives that implement broadcast
distribution trees computed by the multicast module.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from .models import BroadcastSession, FlowAction, FlowMatch, FlowRule, Link
from .topology import TopologyManager


class FlowManager:
    """Manages SDN flow rules across the satellite network."""

    def __init__(self, topology: TopologyManager) -> None:
        self._topology = topology
        # rule_id -> FlowRule
        self._rules: Dict[str, FlowRule] = {}
        # node_id -> set of rule_ids installed on that node
        self._node_rules: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Rule CRUD
    # ------------------------------------------------------------------

    def install_rule(self, rule: FlowRule) -> None:
        """Install a flow rule on the specified node."""
        if self._topology.get_node(rule.node_id) is None:
            raise ValueError(f"Node {rule.node_id} not in topology")
        self._rules[rule.rule_id] = rule
        self._node_rules.setdefault(rule.node_id, set()).add(rule.rule_id)

    def remove_rule(self, rule_id: str) -> Optional[FlowRule]:
        """Remove a flow rule by ID."""
        rule = self._rules.pop(rule_id, None)
        if rule is not None:
            self._node_rules.get(rule.node_id, set()).discard(rule_id)
        return rule

    def get_rule(self, rule_id: str) -> Optional[FlowRule]:
        return self._rules.get(rule_id)

    def get_rules_for_node(self, node_id: str) -> List[FlowRule]:
        rule_ids = self._node_rules.get(node_id, set())
        return [self._rules[rid] for rid in rule_ids if rid in self._rules]

    def get_all_rules(self) -> List[FlowRule]:
        return list(self._rules.values())

    # ------------------------------------------------------------------
    # Broadcast session helpers
    # ------------------------------------------------------------------

    def install_broadcast_tree(
        self,
        session: BroadcastSession,
        tree_links: List[Link],
    ) -> List[FlowRule]:
        """Install flow rules to realise a broadcast distribution tree.

        For each node in the tree that has outgoing links in *tree_links*, a
        REPLICATE flow rule is installed directing matched traffic to all
        downstream neighbours.

        Returns the list of newly installed flow rules.
        """
        # Build per-node output map: node_id -> [next_hop_ids]
        output_map: Dict[str, List[str]] = {}
        for link in tree_links:
            output_map.setdefault(link.source_id, []).append(link.target_id)

        installed: List[FlowRule] = []
        for node_id, outputs in output_map.items():
            action = FlowAction.REPLICATE if len(outputs) > 1 else FlowAction.FORWARD
            rule = FlowRule(
                node_id=node_id,
                match=FlowMatch(multicast_group=session.multicast_group),
                action=action,
                output_ports=outputs,
                priority=200,
            )
            self.install_rule(rule)
            installed.append(rule)

        return installed

    def remove_session_rules(self, rule_ids: List[str]) -> int:
        """Remove all flow rules associated with a broadcast session.

        Returns the number of rules actually removed.
        """
        count = 0
        for rid in rule_ids:
            if self.remove_rule(rid) is not None:
                count += 1
        return count

    def clear_all_rules(self) -> int:
        """Remove every installed flow rule.  Returns count removed."""
        count = len(self._rules)
        self._rules.clear()
        self._node_rules.clear()
        return count

    @property
    def rule_count(self) -> int:
        return len(self._rules)
