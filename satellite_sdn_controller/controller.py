"""Main SDN controller for the satellite broadcast distribution system.

Orchestrates topology management, multicast tree computation, and flow rule
installation to provide end-to-end broadcast distribution over a satellite
network.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from .flow_manager import FlowManager
from .models import (
    BroadcastSession,
    FlowRule,
    Link,
    LinkState,
    Node,
    NodeType,
)
from .multicast import (
    compute_minimum_cost_tree,
    compute_shortest_path_tree,
    validate_tree_bandwidth,
)
from .topology import TopologyManager

logger = logging.getLogger(__name__)


class SatelliteSDNController:
    """Central SDN controller for satellite broadcast distribution.

    Typical usage::

        ctrl = SatelliteSDNController()
        ctrl.add_node(Node(...))
        ctrl.add_link(Link(...))
        session = ctrl.create_broadcast_session(
            name="TV-1",
            source_node_id="sat-1",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs-1", "gs-2"},
            bandwidth_mbps=20.0,
        )
        ctrl.activate_session(session.session_id)
    """

    def __init__(self, use_steiner_tree: bool = False) -> None:
        self.topology = TopologyManager()
        self.flow_manager = FlowManager(self.topology)
        self._sessions: Dict[str, BroadcastSession] = {}
        self._use_steiner = use_steiner_tree

    # ------------------------------------------------------------------
    # Node / link management (delegates to TopologyManager)
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        self.topology.add_node(node)
        logger.info("Node added: %s (%s)", node.node_id, node.name)

    def remove_node(self, node_id: str) -> Optional[Node]:
        node = self.topology.remove_node(node_id)
        if node:
            logger.info("Node removed: %s", node_id)
        return node

    def add_link(self, link: Link) -> None:
        self.topology.add_link(link)
        logger.info(
            "Link added: %s -> %s (id=%s)",
            link.source_id,
            link.target_id,
            link.link_id,
        )

    def remove_link(self, link_id: str) -> Optional[Link]:
        link = self.topology.remove_link(link_id)
        if link:
            logger.info("Link removed: %s", link_id)
        return link

    def set_link_state(self, link_id: str, state: LinkState) -> bool:
        ok = self.topology.set_link_state(link_id, state)
        if ok:
            logger.info("Link %s state -> %s", link_id, state.value)
            self._handle_link_state_change(link_id, state)
        return ok

    # ------------------------------------------------------------------
    # Broadcast session management
    # ------------------------------------------------------------------

    def create_broadcast_session(
        self,
        name: str,
        source_node_id: str,
        multicast_group: str,
        destination_node_ids: Set[str],
        bandwidth_mbps: float = 10.0,
    ) -> BroadcastSession:
        """Create a new broadcast session (initially inactive)."""
        session = BroadcastSession(
            name=name,
            source_node_id=source_node_id,
            multicast_group=multicast_group,
            destination_node_ids=set(destination_node_ids),
            bandwidth_mbps=bandwidth_mbps,
        )
        self._sessions[session.session_id] = session
        logger.info("Broadcast session created: %s (%s)", session.session_id, name)
        return session

    def activate_session(self, session_id: str) -> bool:
        """Compute distribution tree and install flow rules for a session."""
        session = self._sessions.get(session_id)
        if session is None:
            logger.error("Session %s not found", session_id)
            return False
        if session.active:
            logger.warning("Session %s already active", session_id)
            return True

        # Compute multicast tree
        tree_func = (
            compute_minimum_cost_tree
            if self._use_steiner
            else compute_shortest_path_tree
        )
        tree_links = tree_func(
            self.topology, session.source_node_id, session.destination_node_ids
        )
        if not tree_links:
            logger.error(
                "Cannot compute distribution tree for session %s", session_id
            )
            return False

        # Validate bandwidth
        bottlenecks = validate_tree_bandwidth(tree_links, session.bandwidth_mbps)
        if bottlenecks:
            logger.warning(
                "Bandwidth bottlenecks on %d links for session %s",
                len(bottlenecks),
                session_id,
            )

        # Install flow rules
        rules = self.flow_manager.install_broadcast_tree(session, tree_links)
        session.tree_links = {l.link_id for l in tree_links}
        session.flow_rule_ids = [r.rule_id for r in rules]
        session.active = True
        logger.info(
            "Session %s activated with %d links and %d rules",
            session_id,
            len(tree_links),
            len(rules),
        )
        return True

    def deactivate_session(self, session_id: str) -> bool:
        """Remove flow rules and deactivate a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        if not session.active:
            return True
        self.flow_manager.remove_session_rules(session.flow_rule_ids)
        session.flow_rule_ids.clear()
        session.tree_links.clear()
        session.active = False
        logger.info("Session %s deactivated", session_id)
        return True

    def remove_session(self, session_id: str) -> Optional[BroadcastSession]:
        """Deactivate and delete a broadcast session."""
        self.deactivate_session(session_id)
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info("Session %s removed", session_id)
        return session

    def get_session(self, session_id: str) -> Optional[BroadcastSession]:
        return self._sessions.get(session_id)

    def get_all_sessions(self) -> List[BroadcastSession]:
        return list(self._sessions.values())

    # ------------------------------------------------------------------
    # Reactive link-failure handling
    # ------------------------------------------------------------------

    def _handle_link_state_change(
        self, link_id: str, new_state: LinkState
    ) -> None:
        """Re-route affected sessions when a link goes down."""
        if new_state != LinkState.DOWN:
            return
        affected = [
            s
            for s in self._sessions.values()
            if s.active and link_id in s.tree_links
        ]
        for session in affected:
            logger.warning(
                "Link %s failure affects session %s – re-routing",
                link_id,
                session.session_id,
            )
            self.deactivate_session(session.session_id)
            if not self.activate_session(session.session_id):
                logger.error(
                    "Failed to re-route session %s after link failure",
                    session.session_id,
                )

    # ------------------------------------------------------------------
    # Status / statistics
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return a summary of the controller state."""
        return {
            "nodes": self.topology.node_count,
            "links": self.topology.link_count,
            "active_links": len(self.topology.get_active_links()),
            "flow_rules": self.flow_manager.rule_count,
            "sessions_total": len(self._sessions),
            "sessions_active": sum(
                1 for s in self._sessions.values() if s.active
            ),
        }
