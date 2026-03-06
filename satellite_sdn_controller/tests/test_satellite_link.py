"""Tests for satellite link modelling utilities."""

import math

import pytest

from satellite_sdn_controller.models import Link
from satellite_sdn_controller.satellite_link import (
    adaptive_link_bandwidth,
    carrier_to_noise_db,
    estimate_max_bitrate_mbps,
    free_space_path_loss_db,
    link_budget_db,
    slant_range_km,
)


class TestFreeSpacePathLoss:
    def test_known_value(self):
        # 1 km, 1 GHz -> FSPL ~ 92.45 dB (well-known approximation)
        fspl = free_space_path_loss_db(1.0, 1.0)
        assert fspl == pytest.approx(92.45, abs=0.1)

    def test_increases_with_distance(self):
        fspl1 = free_space_path_loss_db(100, 12.0)
        fspl2 = free_space_path_loss_db(200, 12.0)
        assert fspl2 > fspl1

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            free_space_path_loss_db(0, 1)
        with pytest.raises(ValueError):
            free_space_path_loss_db(1, -1)


class TestLinkBudget:
    def test_simple_budget(self):
        result = link_budget_db(
            tx_power_dbw=10,
            tx_gain_db=40,
            rx_gain_db=30,
            fspl_db=200,
        )
        # EIRP = 50, C = 50 + 30 - 200 = -120
        assert result == pytest.approx(-120.0)

    def test_with_losses(self):
        result = link_budget_db(
            tx_power_dbw=10,
            tx_gain_db=40,
            rx_gain_db=30,
            fspl_db=200,
            atmospheric_loss_db=2,
            rain_loss_db=3,
        )
        assert result == pytest.approx(-125.0)


class TestCarrierToNoise:
    def test_positive_cn(self):
        cn = carrier_to_noise_db(-120, 300, 36e6)
        assert isinstance(cn, float)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            carrier_to_noise_db(-120, 0, 36e6)
        with pytest.raises(ValueError):
            carrier_to_noise_db(-120, 300, 0)


class TestMaxBitrate:
    def test_high_snr(self):
        rate = estimate_max_bitrate_mbps(30, 36)
        assert rate > 100  # 36 MHz at 30 dB SNR -> several hundred Mbps

    def test_zero_snr(self):
        rate = estimate_max_bitrate_mbps(0, 36)
        # SNR = 1 -> log2(2) = 1 -> 36 Mbps
        assert rate == pytest.approx(36.0, rel=0.01)


class TestAdaptiveBandwidth:
    def test_good_conditions(self):
        link = Link(bandwidth_mbps=100)
        bw = adaptive_link_bandwidth(link, cn_db=20, bandwidth_mhz=36)
        assert bw == 100  # link cap is the bottleneck

    def test_poor_conditions_halves(self):
        link = Link(bandwidth_mbps=100)
        bw_good = adaptive_link_bandwidth(link, cn_db=20, bandwidth_mhz=36, margin_db=3)
        bw_poor = adaptive_link_bandwidth(link, cn_db=1, bandwidth_mhz=36, margin_db=3)
        # Under poor C/N the bandwidth should be reduced
        assert bw_poor < bw_good


class TestSlantRange:
    def test_directly_below(self):
        # Ground station directly below a GEO satellite
        sr = slant_range_km(0, 0, 0, 0, 35786)
        assert sr == pytest.approx(35786, rel=0.01)

    def test_off_nadir(self):
        sr = slant_range_km(45, 0, 0, 0, 35786)
        assert sr > 35786  # must be farther than directly below
