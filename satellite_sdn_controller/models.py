"""Data models for the satellite broadcast distribution SDN controller."""

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
        metadata: Arbitrary key/value metadata.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    node_type: NodeType = NodeType.GROUND_STATION
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_km: float = 0.0
    capacity_mbps: float = 1000.0
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
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        data = dict(data)
        if "node_type" in data and isinstance(data["node_type"], str):
            data["node_type"] = NodeType(data["node_type"])
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
    """

    link_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    bandwidth_mbps: float = 100.0
    latency_ms: float = 250.0
    state: LinkState = LinkState.UP
    cost: float = 1.0

    def to_dict(self) -> dict:
        return {
            "link_id": self.link_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "bandwidth_mbps": self.bandwidth_mbps,
            "latency_ms": self.latency_ms,
            "state": self.state.value,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Link":
        data = dict(data)
        if "state" in data and isinstance(data["state"], str):
            data["state"] = LinkState(data["state"])
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BroadcastSession":
        data = dict(data)
        if "destination_node_ids" in data:
            data["destination_node_ids"] = set(data["destination_node_ids"])
        if "tree_links" in data:
            data["tree_links"] = set(data["tree_links"])
        return cls(**data)
