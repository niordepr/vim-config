"""Data models for satellite broadcast distribution system."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class NodeStatus(enum.Enum):
    """Status of a cluster node."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class LinkStatus(enum.Enum):
    """Status of an inter-satellite or ground link."""

    UP = "up"
    DOWN = "down"


@dataclass
class SatelliteNode:
    """A LEO satellite node in the constellation.

    Attributes:
        node_id: Unique identifier for the satellite.
        orbit_id: Orbital plane identifier.
        position_index: Index within the orbital plane.
        latitude: Current latitude in degrees.
        longitude: Current longitude in degrees.
        altitude_km: Altitude in kilometers.
        status: Current node status.
        cpu_usage: CPU utilisation ratio (0.0 – 1.0).
        memory_usage: Memory utilisation ratio (0.0 – 1.0).
        bandwidth_mbps: Available bandwidth in Mbps.
        last_heartbeat: Epoch timestamp of the last heartbeat.
    """

    node_id: str
    orbit_id: int
    position_index: int
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_km: float = 550.0
    status: NodeStatus = NodeStatus.ONLINE
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    bandwidth_mbps: float = 1000.0
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def load_score(self) -> float:
        """Compute a composite load score (lower is better).

        The score is a weighted combination of CPU usage, memory usage and
        inverse bandwidth availability.  Values are clamped to ``[0, 1]``.
        """
        cpu_w, mem_w, bw_w = 0.4, 0.3, 0.3
        bw_norm = 1.0 - min(self.bandwidth_mbps / 1000.0, 1.0)
        score = cpu_w * self.cpu_usage + mem_w * self.memory_usage + bw_w * bw_norm
        return max(0.0, min(score, 1.0))

    @property
    def is_available(self) -> bool:
        """Return ``True`` if the node can accept work."""
        return self.status == NodeStatus.ONLINE


@dataclass
class InterSatelliteLink:
    """A link between two satellite nodes.

    Attributes:
        link_id: Unique identifier for the link.
        source_id: Source satellite node id.
        target_id: Target satellite node id.
        latency_ms: One-way latency in milliseconds.
        bandwidth_mbps: Available bandwidth in Mbps.
        status: Current link status.
    """

    link_id: str
    source_id: str
    target_id: str
    latency_ms: float = 10.0
    bandwidth_mbps: float = 1000.0
    status: LinkStatus = LinkStatus.UP

    @property
    def cost(self) -> float:
        """Link cost metric used for routing (latency-weighted)."""
        if self.status == LinkStatus.DOWN:
            return float("inf")
        return self.latency_ms


@dataclass
class FlowRule:
    """An SDN flow rule installed on a satellite node.

    Attributes:
        rule_id: Unique rule identifier.
        node_id: Node on which the rule is installed.
        source: Source address / prefix.
        destination: Destination address / prefix.
        next_hop: Next-hop node id.
        priority: Rule priority (higher wins).
        bandwidth_mbps: Reserved bandwidth.
    """

    rule_id: str
    node_id: str
    source: str
    destination: str
    next_hop: str
    priority: int = 100
    bandwidth_mbps: float = 0.0


@dataclass
class BroadcastTask:
    """A broadcast distribution task to be scheduled.

    Attributes:
        task_id: Unique task identifier.
        source_node_id: Originating node.
        target_node_ids: Set of destination nodes.
        bandwidth_required_mbps: Required bandwidth in Mbps.
        priority: Task priority (higher values are scheduled first).
        created_at: Creation epoch timestamp.
    """

    task_id: str
    source_node_id: str
    target_node_ids: list[str] = field(default_factory=list)
    bandwidth_required_mbps: float = 100.0
    priority: int = 1
    created_at: float = field(default_factory=time.time)
