"""Data models for the satellite broadcast distribution SDN controller.

Supports LEO/MEO/GEO constellations at various scales, multiple routing
strategies, QoS priority levels, and inter-satellite link (ISL) types.
References:

* Walker, J.G. "Satellite constellations," *J. Br. Interplanet. Soc.*, 1984.
* Handley, M. "Delay is Not an Option: Low Latency Routing in Space," *HotNets*, 2018.
* Papa, A. et al. "Design and Evaluation of Reconfigurable Intelligent
  Surface-Aided LEO Satellite Networks," *IEEE Trans. Commun.*, 2022.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


class NodeType(enum.Enum):
    """Type of network node."""

    SATELLITE = "satellite"
    GROUND_STATION = "ground_station"
    GATEWAY = "gateway"


class OrbitType(enum.Enum):
    """Orbit classification for satellite nodes."""

    LEO = "LEO"
    MEO = "MEO"
    GEO = "GEO"
    HEO = "HEO"


class ISLType(enum.Enum):
    """Inter-satellite link type.

    * INTRA_PLANE – link between adjacent satellites in the same orbital plane.
    * INTER_PLANE – link between satellites in neighbouring orbital planes.
    * GROUND_LINK – uplink / downlink between a satellite and a ground station.
    """

    INTRA_PLANE = "intra_plane"
    INTER_PLANE = "inter_plane"
    GROUND_LINK = "ground_link"


class RoutingStrategy(enum.Enum):
    """Available routing / tree-computation strategies."""

    SHORTEST_PATH = "shortest_path"
    MINIMUM_COST_TREE = "minimum_cost_tree"
    MIN_LATENCY = "min_latency"
    MAX_BANDWIDTH = "max_bandwidth"
    LOAD_BALANCED = "load_balanced"
    DELAY_BOUNDED = "delay_bounded"


class QosPriority(enum.Enum):
    """QoS priority levels for broadcast sessions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BEST_EFFORT = "best_effort"


class LinkState(enum.Enum):
    """Operational state of a network link."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class FlowAction(enum.Enum):
    """Action to apply to matched traffic."""

    FORWARD = "forward"
    DROP = "drop"
    REPLICATE = "replicate"


@dataclass
class Node:
    """A network node (satellite, ground station, or gateway).

    Attributes:
        node_id: Unique identifier for the node.
        name: Human-readable name.
        node_type: The type of this node.
        latitude: Geographic latitude in degrees.
        longitude: Geographic longitude in degrees.
        altitude_km: Altitude above sea level in kilometres.
        capacity_mbps: Maximum throughput capacity in Mbps.
        orbit_type: Orbit classification (LEO / MEO / GEO / HEO).
        orbital_plane: Orbital plane index (0-based) for constellation satellites.
        orbital_index: Index within the orbital plane (0-based).
        inclination_deg: Orbital inclination in degrees.
        period_minutes: Orbital period in minutes.
        metadata: Arbitrary key/value metadata.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    node_type: NodeType = NodeType.GROUND_STATION
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_km: float = 0.0
    capacity_mbps: float = 1000.0
    orbit_type: Optional[OrbitType] = None
    orbital_plane: Optional[int] = None
    orbital_index: Optional[int] = None
    inclination_deg: Optional[float] = None
    period_minutes: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type.value,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_km": self.altitude_km,
            "capacity_mbps": self.capacity_mbps,
            "orbit_type": self.orbit_type.value if self.orbit_type else None,
            "orbital_plane": self.orbital_plane,
            "orbital_index": self.orbital_index,
            "inclination_deg": self.inclination_deg,
            "period_minutes": self.period_minutes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        data = dict(data)
        if "node_type" in data and isinstance(data["node_type"], str):
            data["node_type"] = NodeType(data["node_type"])
        if "orbit_type" in data and isinstance(data["orbit_type"], str):
            data["orbit_type"] = OrbitType(data["orbit_type"])
        return cls(**data)


@dataclass
class Link:
    """A network link between two nodes.

    Attributes:
        link_id: Unique identifier for the link.
        source_id: ID of the source node.
        target_id: ID of the target node.
        bandwidth_mbps: Available bandwidth in Mbps.
        latency_ms: One-way propagation delay in milliseconds.
        state: Operational state.
        cost: Routing cost metric (lower is better).
        isl_type: Inter-satellite link type classification.
        load: Current traffic load as a fraction in [0.0, 1.0].
    """

    link_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    bandwidth_mbps: float = 100.0
    latency_ms: float = 250.0
    state: LinkState = LinkState.UP
    cost: float = 1.0
    isl_type: Optional[ISLType] = None
    load: float = 0.0

    def to_dict(self) -> dict:
        return {
            "link_id": self.link_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "bandwidth_mbps": self.bandwidth_mbps,
            "latency_ms": self.latency_ms,
            "state": self.state.value,
            "cost": self.cost,
            "isl_type": self.isl_type.value if self.isl_type else None,
            "load": self.load,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Link":
        data = dict(data)
        if "state" in data and isinstance(data["state"], str):
            data["state"] = LinkState(data["state"])
        if "isl_type" in data and isinstance(data["isl_type"], str):
            data["isl_type"] = ISLType(data["isl_type"])
        return cls(**data)


@dataclass
class FlowMatch:
    """Packet-match criteria for a flow rule.

    Attributes:
        src_ip: Source IP prefix (CIDR notation or empty for any).
        dst_ip: Destination IP prefix.
        protocol: IP protocol number (None = any).
        src_port: Source transport port (None = any).
        dst_port: Destination transport port (None = any).
        multicast_group: Multicast group address (empty for unicast).
    """

    src_ip: str = ""
    dst_ip: str = ""
    protocol: Optional[int] = None
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    multicast_group: str = ""

    def to_dict(self) -> dict:
        return {
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
            "protocol": self.protocol,
            "src_port": self.src_port,
            "dst_port": self.dst_port,
            "multicast_group": self.multicast_group,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FlowMatch":
        return cls(**data)


@dataclass
class FlowRule:
    """An SDN flow rule installed on a node.

    Attributes:
        rule_id: Unique identifier.
        node_id: ID of the node where this rule is installed.
        match: Packet-match criteria.
        action: Action to take on matched packets.
        output_ports: List of output node IDs for forwarding / replication.
        priority: Rule priority (higher = more specific).
        idle_timeout: Seconds of inactivity before automatic removal (0 = permanent).
        created_at: Unix timestamp of creation.
    """

    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str = ""
    match: FlowMatch = field(default_factory=FlowMatch)
    action: FlowAction = FlowAction.FORWARD
    output_ports: List[str] = field(default_factory=list)
    priority: int = 100
    idle_timeout: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "node_id": self.node_id,
            "match": self.match.to_dict(),
            "action": self.action.value,
            "output_ports": list(self.output_ports),
            "priority": self.priority,
            "idle_timeout": self.idle_timeout,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FlowRule":
        data = dict(data)
        if "match" in data and isinstance(data["match"], dict):
            data["match"] = FlowMatch.from_dict(data["match"])
        if "action" in data and isinstance(data["action"], str):
            data["action"] = FlowAction(data["action"])
        return cls(**data)


@dataclass
class BroadcastSession:
    """A broadcast distribution session.

    Attributes:
        session_id: Unique session identifier.
        name: Human-readable session name.
        source_node_id: Node originating the broadcast.
        multicast_group: Multicast group address for this session.
        destination_node_ids: Set of destination node IDs.
        bandwidth_mbps: Required bandwidth for the session.
        active: Whether the session is currently active.
        tree_links: Set of link IDs forming the distribution tree.
        flow_rule_ids: IDs of installed flow rules for this session.
        qos_priority: QoS priority level.
        routing_strategy: Routing strategy override (None = use controller default).
        max_latency_ms: Maximum acceptable end-to-end latency (0 = unbounded).
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_node_id: str = ""
    multicast_group: str = ""
    destination_node_ids: Set[str] = field(default_factory=set)
    bandwidth_mbps: float = 10.0
    active: bool = False
    tree_links: Set[str] = field(default_factory=set)
    flow_rule_ids: List[str] = field(default_factory=list)
    qos_priority: QosPriority = QosPriority.MEDIUM
    routing_strategy: Optional[RoutingStrategy] = None
    max_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "source_node_id": self.source_node_id,
            "multicast_group": self.multicast_group,
            "destination_node_ids": sorted(self.destination_node_ids),
            "bandwidth_mbps": self.bandwidth_mbps,
            "active": self.active,
            "tree_links": sorted(self.tree_links),
            "flow_rule_ids": list(self.flow_rule_ids),
            "qos_priority": self.qos_priority.value,
            "routing_strategy": (
                self.routing_strategy.value if self.routing_strategy else None
            ),
            "max_latency_ms": self.max_latency_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BroadcastSession":
        data = dict(data)
        if "destination_node_ids" in data:
            data["destination_node_ids"] = set(data["destination_node_ids"])
        if "tree_links" in data:
            data["tree_links"] = set(data["tree_links"])
        if "qos_priority" in data and isinstance(data["qos_priority"], str):
            data["qos_priority"] = QosPriority(data["qos_priority"])
        if "routing_strategy" in data and isinstance(data["routing_strategy"], str):
            data["routing_strategy"] = RoutingStrategy(data["routing_strategy"])
        return cls(**data)
