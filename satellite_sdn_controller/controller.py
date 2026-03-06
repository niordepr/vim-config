"""Main SDN controller for the satellite broadcast distribution system.

Orchestrates topology management, multicast tree computation, and flow rule
installation to provide end-to-end broadcast distribution over a satellite
network.  Supports various constellation scales (small/medium/large LEO),
multiple routing strategies, QoS-aware session management, and proactive
handover for LEO dynamics.

References:

* Handley, M. "Delay is Not an Option: Low Latency Routing in Space,"
  *HotNets*, 2018.
* Papa, A. et al. "Dynamic SDN-based Radio Access Network Slicing for LEO
  Satellite Networks," *IEEE Trans. on Network and Service Management*, 2022.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from .constellation import (
    ConstellationConfig,
    PRESETS,
    add_ground_station,
    generate_constellation,
)
from .flow_manager import FlowManager
from .handover import HandoverManager
from .models import (
    BroadcastSession,
    FlowRule,
    ISLType,
    Link,
    LinkState,
    Node,
    NodeType,
    OrbitType,
    QosPriority,
    RoutingStrategy,
)
from .multicast import (
    compute_minimum_cost_tree,
    compute_shortest_path_tree,
    validate_tree_bandwidth,
)
from .routing_strategy import compute_tree
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

    LEO constellation workflow::

        ctrl = SatelliteSDNController(
            default_strategy=RoutingStrategy.MIN_LATENCY,
        )
        ctrl.load_constellation("iridium")
        ctrl.add_ground_station("gs-tokyo", "GS-Tokyo", 35.68, 139.69)
        session = ctrl.create_broadcast_session(...)
        ctrl.activate_session(session.session_id)
    """

    def __init__(
        self,
        use_steiner_tree: bool = False,
        default_strategy: RoutingStrategy = RoutingStrategy.SHORTEST_PATH,
    ) -> None:
        self.topology = TopologyManager()
        self.flow_manager = FlowManager(self.topology)
        self.handover_manager = HandoverManager(self.topology)
        self._sessions: Dict[str, BroadcastSession] = {}
        self._use_steiner = use_steiner_tree
        self._default_strategy = default_strategy
        self._constellation_config: Optional[ConstellationConfig] = None

    # ------------------------------------------------------------------
    # Constellation management
    # ------------------------------------------------------------------

    def load_constellation(
        self,
        preset_name: str,
    ) -> ConstellationConfig:
        """Generate a constellation from a named preset.

        Available presets: ``iridium``, ``oneweb``, ``starlink_shell1``,
        ``small_leo``.
        """
        config = PRESETS.get(preset_name)
        if config is None:
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Available: {sorted(PRESETS.keys())}"
            )
        return self.generate_constellation(config)

    def generate_constellation(
        self,
        config: ConstellationConfig,
    ) -> ConstellationConfig:
        """Generate a custom constellation and populate the topology."""
        generate_constellation(config, self.topology)
        self._constellation_config = config
        logger.info(
            "Constellation '%s' generated: %d planes × %d sats = %d total, "
            "altitude=%.0f km, incl=%.1f°",
            config.name,
            config.num_planes,
            config.sats_per_plane,
            config.num_planes * config.sats_per_plane,
            config.altitude_km,
            config.inclination_deg,
        )
        return config

    def add_ground_station(
        self,
        station_id: str,
        name: str,
        latitude: float,
        longitude: float,
        min_elevation_deg: float = 25.0,
        bandwidth_mbps: float = 1_000.0,
        max_links: int = 4,
    ) -> Node:
        """Add a ground station and connect it to visible satellites."""
        gs = add_ground_station(
            self.topology,
            station_id,
            name,
            latitude,
            longitude,
            min_elevation_deg,
            bandwidth_mbps,
            max_links,
        )
        logger.info(
            "Ground station added: %s (%s) at (%.2f, %.2f)",
            station_id,
            name,
            latitude,
            longitude,
        )
        return gs

    # ------------------------------------------------------------------
    # Routing strategy
    # ------------------------------------------------------------------

    @property
    def default_strategy(self) -> RoutingStrategy:
        return self._default_strategy

    @default_strategy.setter
    def default_strategy(self, strategy: RoutingStrategy) -> None:
        self._default_strategy = strategy
        logger.info("Default routing strategy set to %s", strategy.value)

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
        qos_priority: QosPriority = QosPriority.MEDIUM,
        routing_strategy: Optional[RoutingStrategy] = None,
        max_latency_ms: float = 0.0,
    ) -> BroadcastSession:
        """Create a new broadcast session (initially inactive)."""
        session = BroadcastSession(
            name=name,
            source_node_id=source_node_id,
            multicast_group=multicast_group,
            destination_node_ids=set(destination_node_ids),
            bandwidth_mbps=bandwidth_mbps,
            qos_priority=qos_priority,
            routing_strategy=routing_strategy,
            max_latency_ms=max_latency_ms,
        )
        self._sessions[session.session_id] = session
        logger.info(
            "Broadcast session created: %s (%s) qos=%s strategy=%s",
            session.session_id,
            name,
            qos_priority.value,
            routing_strategy.value if routing_strategy else "default",
        )
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

        # Determine routing strategy
        strategy = session.routing_strategy or self._default_strategy

        # Use legacy path for backward compatibility when strategy is
        # SHORTEST_PATH or MINIMUM_COST_TREE and the routing_strategy
        # module would give the same result.
        if strategy in (
            RoutingStrategy.SHORTEST_PATH,
            RoutingStrategy.MINIMUM_COST_TREE,
        ) and not session.max_latency_ms:
            tree_func = (
                compute_minimum_cost_tree
                if strategy == RoutingStrategy.MINIMUM_COST_TREE
                or self._use_steiner
                else compute_shortest_path_tree
            )
            tree_links = tree_func(
                self.topology,
                session.source_node_id,
                session.destination_node_ids,
            )
        else:
            tree_links = compute_tree(
                self.topology,
                session.source_node_id,
                session.destination_node_ids,
                strategy=strategy,
                max_latency_ms=session.max_latency_ms,
            )

        if not tree_links:
            logger.error(
                "Cannot compute distribution tree for session %s "
                "(strategy=%s)",
                session_id,
                strategy.value,
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

        # Install flow rules (higher-priority QoS gets higher flow priority)
        qos_priority_map = {
            QosPriority.CRITICAL: 500,
            QosPriority.HIGH: 400,
            QosPriority.MEDIUM: 200,
            QosPriority.LOW: 100,
            QosPriority.BEST_EFFORT: 50,
        }
        flow_priority = qos_priority_map.get(session.qos_priority, 200)
        rules = self.flow_manager.install_broadcast_tree(
            session, tree_links, priority=flow_priority
        )
        session.tree_links = {l.link_id for l in tree_links}
        session.flow_rule_ids = [r.rule_id for r in rules]
        session.active = True
        logger.info(
            "Session %s activated with %d links, %d rules "
            "(strategy=%s, qos=%s)",
            session_id,
            len(tree_links),
            len(rules),
            strategy.value,
            session.qos_priority.value,
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
    # Handover management
    # ------------------------------------------------------------------

    def trigger_handover(self) -> Dict[str, Dict[str, List[str]]]:
        """Evaluate and perform ground-station handovers.

        Should be called whenever satellite positions are updated.
        Active sessions affected by removed links will be re-routed.

        Returns a dict of handover results per ground station.
        """
        results = self.handover_manager.evaluate_handovers()
        # Re-route sessions affected by removed links
        for gs_id, changes in results.items():
            if changes["removed"]:
                self._reroute_affected_sessions()
        return results

    def _reroute_affected_sessions(self) -> None:
        """Re-route any active session whose tree links are broken."""
        for session in list(self._sessions.values()):
            if not session.active:
                continue
            # Check if any tree link no longer exists
            broken = any(
                self.topology.get_link(lid) is None
                for lid in session.tree_links
            )
            if broken:
                logger.warning(
                    "Session %s has broken links – re-routing",
                    session.session_id,
                )
                self.deactivate_session(session.session_id)
                if not self.activate_session(session.session_id):
                    logger.error(
                        "Failed to re-route session %s after handover",
                        session.session_id,
                    )

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
        sats = self.topology.get_nodes_by_type(NodeType.SATELLITE)
        gs_list = self.topology.get_nodes_by_type(NodeType.GROUND_STATION)
        status = {
            "nodes": self.topology.node_count,
            "satellites": len(sats),
            "ground_stations": len(gs_list),
            "links": self.topology.link_count,
            "active_links": len(self.topology.get_active_links()),
            "flow_rules": self.flow_manager.rule_count,
            "sessions_total": len(self._sessions),
            "sessions_active": sum(
                1 for s in self._sessions.values() if s.active
            ),
            "default_strategy": self._default_strategy.value,
        }
        if self._constellation_config:
            status["constellation"] = {
                "name": self._constellation_config.name,
                "num_planes": self._constellation_config.num_planes,
                "sats_per_plane": self._constellation_config.sats_per_plane,
                "altitude_km": self._constellation_config.altitude_km,
                "inclination_deg": self._constellation_config.inclination_deg,
            }
        return status
