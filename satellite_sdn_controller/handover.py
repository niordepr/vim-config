"""Handover manager for LEO satellite ground-station link management.

In LEO constellations, satellites move rapidly relative to the ground,
causing ground-station links to change as satellites enter and leave the
visible footprint.  This module provides proactive handover by
periodically evaluating link visibility and updating the topology and
any active broadcast sessions accordingly.

References:

* Bhattacherjee, D. & Singla, A. "Network topology design at 27,000 km/h,"
  *CoNEXT*, 2019.
* Papa, A. et al. "Dynamic SDN-based Radio Access Network Slicing for
  LEO Satellite Networks," *IEEE Trans. on Network and Service Management*,
  2022.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Set, Tuple

from .models import ISLType, Link, LinkState, Node, NodeType
from .topology import TopologyManager

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


class HandoverManager:
    """Manages ground-station ↔ satellite link handovers.

    The manager tracks which ground stations have active satellite links
    and provides a :meth:`evaluate_handovers` method that should be
    called whenever satellite positions are updated.
    """

    def __init__(
        self,
        topology: TopologyManager,
        min_elevation_deg: float = 25.0,
        max_gs_links: int = 4,
        hysteresis_deg: float = 5.0,
    ) -> None:
        """
        Parameters
        ----------
        topology:
            The network topology managed by the SDN controller.
        min_elevation_deg:
            Minimum elevation angle for a satellite to be considered visible.
        max_gs_links:
            Maximum number of satellite links per ground station.
        hysteresis_deg:
            Hysteresis margin to prevent rapid link flapping.  A link is
            only torn down when the satellite drops below
            ``min_elevation_deg - hysteresis_deg``.
        """
        self._topology = topology
        self._min_elevation = min_elevation_deg
        self._max_gs_links = max_gs_links
        self._hysteresis = hysteresis_deg
        # ground_station_id -> set of link_ids currently managed by handover
        self._managed_links: Dict[str, Set[str]] = {}

    def evaluate_handovers(
        self,
        ground_link_bandwidth_mbps: float = 1_000.0,
    ) -> Dict[str, Dict[str, List[str]]]:
        """Re-evaluate all ground-station links and perform handovers.

        Returns a dict keyed by ground-station ID with ``"added"`` and
        ``"removed"`` lists of satellite node IDs.
        """
        results: Dict[str, Dict[str, List[str]]] = {}

        for gs in self._topology.get_nodes_by_type(NodeType.GROUND_STATION):
            added, removed = self._handover_for_station(
                gs, ground_link_bandwidth_mbps
            )
            if added or removed:
                results[gs.node_id] = {"added": added, "removed": removed}

        return results

    def get_managed_links(self, gs_id: str) -> Set[str]:
        """Return set of link IDs managed by handover for a ground station."""
        return set(self._managed_links.get(gs_id, set()))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handover_for_station(
        self,
        gs: Node,
        bw_mbps: float,
    ) -> Tuple[List[str], List[str]]:
        """Perform handover evaluation for a single ground station."""
        managed = self._managed_links.setdefault(gs.node_id, set())
        added_sats: List[str] = []
        removed_sats: List[str] = []

        # 1) Evaluate existing managed links – tear down if below threshold
        to_remove: List[str] = []
        current_sats: Set[str] = set()
        for lid in list(managed):
            link = self._topology.get_link(lid)
            if link is None:
                managed.discard(lid)
                continue
            sat_id = (
                link.target_id
                if link.source_id == gs.node_id
                else link.source_id
            )
            sat = self._topology.get_node(sat_id)
            if sat is None:
                to_remove.append(lid)
                continue
            elev = _elevation_angle_deg(
                gs.latitude, gs.longitude,
                sat.latitude, sat.longitude,
                sat.altitude_km,
            )
            teardown_threshold = self._min_elevation - self._hysteresis
            if elev < teardown_threshold:
                to_remove.append(lid)
                removed_sats.append(sat_id)
            else:
                current_sats.add(sat_id)

        for lid in to_remove:
            self._topology.remove_link(lid)
            managed.discard(lid)

        # 2) Find candidate satellites above min elevation
        candidates: List[Tuple[float, Node]] = []
        for sat in self._topology.get_nodes_by_type(NodeType.SATELLITE):
            if sat.node_id in current_sats:
                continue
            elev = _elevation_angle_deg(
                gs.latitude, gs.longitude,
                sat.latitude, sat.longitude,
                sat.altitude_km,
            )
            if elev >= self._min_elevation:
                sr = _approx_slant_range_km(
                    gs.latitude, gs.longitude,
                    sat.latitude, sat.longitude,
                    sat.altitude_km,
                )
                candidates.append((sr, sat))

        candidates.sort(key=lambda t: t[0])

        # Count existing uplinks and downlinks separately
        up_count = sum(
            1 for lid in managed
            if self._topology.get_link(lid) is not None
            and self._topology.get_link(lid).source_id == gs.node_id
        )

        slots = self._max_gs_links - up_count
        for sr, sat in candidates[:max(0, slots)]:
            latency = sr / 299_792.458 * 1000.0
            # Uplink gs -> sat
            ul = Link(
                link_id=f"ho-{gs.node_id}-{sat.node_id}",
                source_id=gs.node_id,
                target_id=sat.node_id,
                bandwidth_mbps=bw_mbps,
                latency_ms=latency,
                isl_type=ISLType.GROUND_LINK,
                cost=2.0,
            )
            # Downlink sat -> gs
            dl = Link(
                link_id=f"ho-{sat.node_id}-{gs.node_id}",
                source_id=sat.node_id,
                target_id=gs.node_id,
                bandwidth_mbps=bw_mbps,
                latency_ms=latency,
                isl_type=ISLType.GROUND_LINK,
                cost=2.0,
            )
            self._topology.add_link(ul)
            self._topology.add_link(dl)
            managed.add(ul.link_id)
            managed.add(dl.link_id)
            added_sats.append(sat.node_id)

        return added_sats, removed_sats


# ------------------------------------------------------------------
# Geometry helpers (duplicated from constellation.py to keep modules
# independent; could be refactored into a shared _geo module)
# ------------------------------------------------------------------


def _elevation_angle_deg(
    gs_lat: float,
    gs_lon: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_km: float,
) -> float:
    central = _central_angle_rad(gs_lat, gs_lon, sat_lat, sat_lon)
    if central == 0:
        return 90.0
    r_e = EARTH_RADIUS_KM
    r_s = r_e + sat_alt_km
    cos_el = math.sin(central) / math.sqrt(
        1 + (r_e / r_s) ** 2 - 2 * (r_e / r_s) * math.cos(central)
    )
    cos_el = max(-1.0, min(1.0, cos_el))
    return 90.0 - math.degrees(math.acos(cos_el))


def _central_angle_rad(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _approx_slant_range_km(
    gs_lat: float,
    gs_lon: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_km: float,
) -> float:
    central = _central_angle_rad(gs_lat, gs_lon, sat_lat, sat_lon)
    r_e = EARTH_RADIUS_KM
    r_s = r_e + sat_alt_km
    return math.sqrt(r_e**2 + r_s**2 - 2 * r_e * r_s * math.cos(central))
