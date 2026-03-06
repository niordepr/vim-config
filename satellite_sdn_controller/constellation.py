"""LEO satellite constellation generator.

Generates Walker Delta and Walker Star constellation topologies at various
scales, with realistic orbital parameters and inter-satellite link (ISL)
connectivity.  Includes preset configurations modelled after well-known
commercial constellations.

References:

* Walker, J.G. "Satellite constellations," *J. Br. Interplanet. Soc.*, 1984.
* Bhattacherjee, D. & Singla, A. "Network topology design at 27,000 km/h,"
  *CoNEXT*, 2019 (Starlink ISL analysis).
* del Portillo, I. et al. "A technical comparison of three LEO satellite
  constellation systems to provide global broadband,"
  *ICSSC*, 2018.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import ISLType, Link, LinkState, Node, NodeType, OrbitType
from .topology import TopologyManager

# Earth parameters
EARTH_RADIUS_KM = 6371.0
EARTH_MU_KM3_S2 = 398600.4418  # standard gravitational parameter


def orbital_period_minutes(altitude_km: float) -> float:
    """Kepler orbital period for a circular orbit at *altitude_km* (minutes)."""
    r = EARTH_RADIUS_KM + altitude_km
    return 2 * math.pi * math.sqrt(r**3 / EARTH_MU_KM3_S2) / 60.0


@dataclass
class ConstellationConfig:
    """Parameters for a Walker Delta/Star constellation.

    Notation follows Walker's ``T/P/F`` convention:

    * *T* = ``num_planes * sats_per_plane`` – total number of satellites.
    * *P* = ``num_planes`` – number of equally-spaced orbital planes.
    * *F* = ``phase_offset`` – relative phasing between adjacent planes
      (Walker *F* parameter, integer in ``[0, P-1]``).

    Additional parameters:

    * ``altitude_km`` – orbital altitude.
    * ``inclination_deg`` – orbital inclination (degrees).
    * ``isl_intra_plane`` – whether to create intra-plane ISLs.
    * ``isl_inter_plane`` – whether to create inter-plane ISLs.
    * ``isl_bandwidth_mbps`` – nominal ISL bandwidth.
    * ``ground_link_bandwidth_mbps`` – nominal ground-link bandwidth.
    """

    name: str = "custom"
    num_planes: int = 6
    sats_per_plane: int = 11
    altitude_km: float = 780.0
    inclination_deg: float = 86.4
    phase_offset: int = 1
    isl_intra_plane: bool = True
    isl_inter_plane: bool = True
    isl_bandwidth_mbps: float = 10_000.0
    ground_link_bandwidth_mbps: float = 1_000.0


# ------------------------------------------------------------------
# Preset constellation configurations
# ------------------------------------------------------------------

PRESET_IRIDIUM = ConstellationConfig(
    name="iridium",
    num_planes=6,
    sats_per_plane=11,
    altitude_km=780.0,
    inclination_deg=86.4,
    phase_offset=1,
)

PRESET_ONEWEB = ConstellationConfig(
    name="oneweb",
    num_planes=18,
    sats_per_plane=36,
    altitude_km=1200.0,
    inclination_deg=87.9,
    phase_offset=1,
    isl_inter_plane=False,
)

PRESET_STARLINK_SHELL1 = ConstellationConfig(
    name="starlink_shell1",
    num_planes=72,
    sats_per_plane=22,
    altitude_km=550.0,
    inclination_deg=53.0,
    phase_offset=1,
)

PRESET_SMALL_LEO = ConstellationConfig(
    name="small_leo",
    num_planes=4,
    sats_per_plane=6,
    altitude_km=600.0,
    inclination_deg=55.0,
    phase_offset=0,
)

PRESETS: Dict[str, ConstellationConfig] = {
    "iridium": PRESET_IRIDIUM,
    "oneweb": PRESET_ONEWEB,
    "starlink_shell1": PRESET_STARLINK_SHELL1,
    "small_leo": PRESET_SMALL_LEO,
}


# ------------------------------------------------------------------
# Constellation generation
# ------------------------------------------------------------------


def _sat_id(plane: int, index: int) -> str:
    return f"sat-P{plane}-S{index}"


def _isl_id(src: str, dst: str) -> str:
    return f"isl-{src}-{dst}"


def generate_constellation(
    config: ConstellationConfig,
    topology: Optional[TopologyManager] = None,
) -> TopologyManager:
    """Generate a Walker constellation and populate a :class:`TopologyManager`.

    Each satellite is placed at its sub-satellite point on the initial
    snapshot (ascending node longitude evenly spaced).  Intra-plane ISLs
    connect adjacent satellites within the same plane; inter-plane ISLs
    connect corresponding satellites in neighbouring planes.

    Parameters
    ----------
    config:
        Constellation configuration.
    topology:
        An existing topology to populate.  A new one is created if *None*.

    Returns
    -------
    TopologyManager:
        The populated topology.
    """
    topo = topology or TopologyManager()
    period = orbital_period_minutes(config.altitude_km)
    raan_spacing = 360.0 / config.num_planes
    anomaly_spacing = 360.0 / config.sats_per_plane
    phase_shift = (
        360.0 * config.phase_offset
        / (config.num_planes * config.sats_per_plane)
    )

    # --- Create satellite nodes ---
    for p in range(config.num_planes):
        for s in range(config.sats_per_plane):
            mean_anomaly = (s * anomaly_spacing + p * phase_shift) % 360.0
            # Sub-satellite latitude approximation for near-polar orbits
            lat = config.inclination_deg * math.sin(math.radians(mean_anomaly))
            lon = (p * raan_spacing + mean_anomaly) % 360.0
            if lon > 180.0:
                lon -= 360.0
            node = Node(
                node_id=_sat_id(p, s),
                name=f"{config.name}-P{p}-S{s}",
                node_type=NodeType.SATELLITE,
                latitude=lat,
                longitude=lon,
                altitude_km=config.altitude_km,
                capacity_mbps=config.isl_bandwidth_mbps,
                orbit_type=OrbitType.LEO,
                orbital_plane=p,
                orbital_index=s,
                inclination_deg=config.inclination_deg,
                period_minutes=period,
            )
            topo.add_node(node)

    # --- Intra-plane ISLs (ring within each plane) ---
    if config.isl_intra_plane:
        for p in range(config.num_planes):
            for s in range(config.sats_per_plane):
                src = _sat_id(p, s)
                dst = _sat_id(p, (s + 1) % config.sats_per_plane)
                topo.add_link(Link(
                    link_id=_isl_id(src, dst),
                    source_id=src,
                    target_id=dst,
                    bandwidth_mbps=config.isl_bandwidth_mbps,
                    latency_ms=_intra_plane_latency_ms(config),
                    isl_type=ISLType.INTRA_PLANE,
                    cost=1.0,
                ))
                # Reverse direction
                topo.add_link(Link(
                    link_id=_isl_id(dst, src),
                    source_id=dst,
                    target_id=src,
                    bandwidth_mbps=config.isl_bandwidth_mbps,
                    latency_ms=_intra_plane_latency_ms(config),
                    isl_type=ISLType.INTRA_PLANE,
                    cost=1.0,
                ))

    # --- Inter-plane ISLs (between corresponding sats in adjacent planes) ---
    if config.isl_inter_plane:
        for p in range(config.num_planes):
            next_p = (p + 1) % config.num_planes
            for s in range(config.sats_per_plane):
                src = _sat_id(p, s)
                dst = _sat_id(next_p, s)
                lat_ms = _inter_plane_latency_ms(config)
                topo.add_link(Link(
                    link_id=_isl_id(src, dst),
                    source_id=src,
                    target_id=dst,
                    bandwidth_mbps=config.isl_bandwidth_mbps,
                    latency_ms=lat_ms,
                    isl_type=ISLType.INTER_PLANE,
                    cost=1.5,
                ))
                topo.add_link(Link(
                    link_id=_isl_id(dst, src),
                    source_id=dst,
                    target_id=src,
                    bandwidth_mbps=config.isl_bandwidth_mbps,
                    latency_ms=lat_ms,
                    isl_type=ISLType.INTER_PLANE,
                    cost=1.5,
                ))

    return topo


def add_ground_station(
    topology: TopologyManager,
    station_id: str,
    name: str,
    latitude: float,
    longitude: float,
    min_elevation_deg: float = 25.0,
    bandwidth_mbps: float = 1_000.0,
    max_links: int = 4,
) -> Node:
    """Add a ground station and connect it to visible satellites.

    Satellites are considered visible when the elevation angle from the
    ground station exceeds *min_elevation_deg*.  Up to *max_links* of
    the closest visible satellites are connected.

    Returns the newly created ground-station node.
    """
    gs = Node(
        node_id=station_id,
        name=name,
        node_type=NodeType.GROUND_STATION,
        latitude=latitude,
        longitude=longitude,
        altitude_km=0.0,
        capacity_mbps=bandwidth_mbps,
    )
    topology.add_node(gs)

    # Find visible satellites sorted by slant range (ascending)
    candidates: List[Tuple[float, Node]] = []
    for node in topology.get_nodes_by_type(NodeType.SATELLITE):
        elev = _elevation_angle_deg(
            latitude, longitude, node.latitude, node.longitude, node.altitude_km
        )
        if elev >= min_elevation_deg:
            sr = _approx_slant_range_km(
                latitude, longitude, node.latitude, node.longitude, node.altitude_km
            )
            candidates.append((sr, node))

    candidates.sort(key=lambda t: t[0])

    for sr, sat in candidates[:max_links]:
        latency = sr / 299_792.458 * 1000.0  # ms
        # Bidirectional ground links
        topology.add_link(Link(
            link_id=_isl_id(gs.node_id, sat.node_id),
            source_id=gs.node_id,
            target_id=sat.node_id,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency,
            isl_type=ISLType.GROUND_LINK,
            cost=2.0,
        ))
        topology.add_link(Link(
            link_id=_isl_id(sat.node_id, gs.node_id),
            source_id=sat.node_id,
            target_id=gs.node_id,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency,
            isl_type=ISLType.GROUND_LINK,
            cost=2.0,
        ))

    return gs


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _intra_plane_latency_ms(config: ConstellationConfig) -> float:
    """Approximate intra-plane ISL latency."""
    r = EARTH_RADIUS_KM + config.altitude_km
    arc = 2 * math.pi * r / config.sats_per_plane
    return arc / 299_792.458 * 1000.0


def _inter_plane_latency_ms(config: ConstellationConfig) -> float:
    """Approximate inter-plane ISL latency at the equator."""
    r = EARTH_RADIUS_KM + config.altitude_km
    raan_spacing_rad = 2 * math.pi / config.num_planes
    chord = 2 * r * math.sin(raan_spacing_rad / 2)
    return chord / 299_792.458 * 1000.0


def _elevation_angle_deg(
    gs_lat: float,
    gs_lon: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_km: float,
) -> float:
    """Approximate elevation angle (degrees) from ground station to satellite."""
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
