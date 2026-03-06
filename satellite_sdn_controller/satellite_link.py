"""Satellite link modelling utilities.

Provides helper functions for modelling satellite communication link
characteristics such as free-space path loss, link budget estimation,
and adaptive bandwidth based on link conditions.
"""

from __future__ import annotations

import math
from typing import Optional

from .models import Link, LinkState, Node


# Physical / RF constants
SPEED_OF_LIGHT_M_S = 299_792_458.0
BOLTZMANN_DB = -228.6  # dBW/K/Hz


def free_space_path_loss_db(distance_km: float, frequency_ghz: float) -> float:
    """Calculate free-space path loss (FSPL) in dB.

    Parameters
    ----------
    distance_km:
        Distance between transmitter and receiver in kilometres.
    frequency_ghz:
        Carrier frequency in GHz.
    """
    if distance_km <= 0 or frequency_ghz <= 0:
        raise ValueError("distance and frequency must be positive")
    distance_m = distance_km * 1e3
    frequency_hz = frequency_ghz * 1e9
    return 20 * math.log10(distance_m) + 20 * math.log10(frequency_hz) + 20 * math.log10(4 * math.pi / SPEED_OF_LIGHT_M_S)


def link_budget_db(
    tx_power_dbw: float,
    tx_gain_db: float,
    rx_gain_db: float,
    fspl_db: float,
    atmospheric_loss_db: float = 0.0,
    rain_loss_db: float = 0.0,
) -> float:
    """Compute received signal power (dBW) using a simplified link budget.

    ``C = EIRP + G_rx - FSPL - L_atm - L_rain``
    """
    eirp = tx_power_dbw + tx_gain_db
    return eirp + rx_gain_db - fspl_db - atmospheric_loss_db - rain_loss_db


def carrier_to_noise_db(
    received_power_dbw: float,
    noise_temp_k: float,
    bandwidth_hz: float,
) -> float:
    """Compute carrier-to-noise ratio (C/N) in dB.

    ``C/N = C - 10*log10(k*T*B)``
    """
    if noise_temp_k <= 0 or bandwidth_hz <= 0:
        raise ValueError("noise temperature and bandwidth must be positive")
    noise_power_dbw = (
        BOLTZMANN_DB + 10 * math.log10(noise_temp_k) + 10 * math.log10(bandwidth_hz)
    )
    return received_power_dbw - noise_power_dbw


def estimate_max_bitrate_mbps(cn_db: float, bandwidth_mhz: float) -> float:
    """Estimate maximum achievable bitrate using Shannon capacity.

    ``C = B * log2(1 + SNR)``

    Returns the capacity in Mbps.
    """
    snr_linear = 10 ** (cn_db / 10)
    capacity_hz = bandwidth_mhz * 1e6 * math.log2(1 + snr_linear)
    return capacity_hz / 1e6


def adaptive_link_bandwidth(
    link: Link,
    cn_db: float,
    bandwidth_mhz: float,
    margin_db: float = 3.0,
) -> float:
    """Return an adjusted bandwidth for *link* based on current C/N.

    If the C/N falls below *margin_db*, the link is considered degraded and
    a reduced bandwidth is returned.
    """
    max_rate = estimate_max_bitrate_mbps(cn_db, bandwidth_mhz)
    effective = min(max_rate, link.bandwidth_mbps)
    if cn_db < margin_db:
        effective *= 0.5  # halve throughput under poor conditions
    return effective


def slant_range_km(
    ground_lat: float,
    ground_lon: float,
    sat_lat: float,
    sat_lon: float,
    sat_altitude_km: float,
) -> float:
    """Approximate slant range from a ground station to a satellite (km).

    Uses the law of cosines with Earth radius = 6371 km.
    """
    earth_r = 6371.0
    # Central angle between ground station and sub-satellite point
    phi1 = math.radians(ground_lat)
    phi2 = math.radians(sat_lat)
    dphi = math.radians(sat_lat - ground_lat)
    dlambda = math.radians(sat_lon - ground_lon)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    central_angle = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    r_sat = earth_r + sat_altitude_km
    return math.sqrt(
        earth_r**2 + r_sat**2 - 2 * earth_r * r_sat * math.cos(central_angle)
    )
