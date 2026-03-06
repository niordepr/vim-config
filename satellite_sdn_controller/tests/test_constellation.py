"""Tests for the constellation generator."""

import pytest

from satellite_sdn_controller.constellation import (
    PRESETS,
    ConstellationConfig,
    add_ground_station,
    generate_constellation,
    orbital_period_minutes,
)
from satellite_sdn_controller.models import ISLType, NodeType, OrbitType
from satellite_sdn_controller.topology import TopologyManager


class TestOrbitalPeriod:
    def test_leo_period(self):
        # ISS-like altitude (~400 km) => ~92 minutes
        period = orbital_period_minutes(400.0)
        assert 90 < period < 95

    def test_geo_period(self):
        # GEO altitude => ~1436 minutes (≈ 23h56m)
        period = orbital_period_minutes(35786.0)
        assert 1430 < period < 1440


class TestGenerateConstellation:
    def test_small_leo(self):
        config = PRESETS["small_leo"]
        topo = generate_constellation(config)
        expected_sats = config.num_planes * config.sats_per_plane
        sats = topo.get_nodes_by_type(NodeType.SATELLITE)
        assert len(sats) == expected_sats
        assert topo.node_count == expected_sats

    def test_iridium_scale(self):
        config = PRESETS["iridium"]
        topo = generate_constellation(config)
        sats = topo.get_nodes_by_type(NodeType.SATELLITE)
        assert len(sats) == 66  # 6 planes × 11 sats

    def test_satellite_orbital_params(self):
        config = PRESETS["small_leo"]
        topo = generate_constellation(config)
        sat = topo.get_node("sat-P0-S0")
        assert sat is not None
        assert sat.orbit_type == OrbitType.LEO
        assert sat.orbital_plane == 0
        assert sat.orbital_index == 0
        assert sat.inclination_deg == config.inclination_deg
        assert sat.period_minutes is not None
        assert sat.period_minutes > 0

    def test_intra_plane_isls(self):
        config = ConstellationConfig(
            name="test",
            num_planes=2,
            sats_per_plane=3,
            altitude_km=600.0,
            inclination_deg=55.0,
            isl_intra_plane=True,
            isl_inter_plane=False,
        )
        topo = generate_constellation(config)
        # 2 planes × 3 sats × 2 intra-plane links (bidirectional ring)
        # Each plane: 3 sats in ring = 3 forward + 3 backward = 6 links
        # Total: 2 × 6 = 12
        links = topo.get_all_links()
        intra = [l for l in links if l.isl_type == ISLType.INTRA_PLANE]
        assert len(intra) == 12

    def test_inter_plane_isls(self):
        config = ConstellationConfig(
            name="test",
            num_planes=3,
            sats_per_plane=2,
            altitude_km=600.0,
            inclination_deg=55.0,
            isl_intra_plane=False,
            isl_inter_plane=True,
        )
        topo = generate_constellation(config)
        links = topo.get_all_links()
        inter = [l for l in links if l.isl_type == ISLType.INTER_PLANE]
        # 3 planes × 2 sats × 2 (bidirectional) = 12
        assert len(inter) == 12

    def test_no_isls(self):
        config = ConstellationConfig(
            name="test",
            num_planes=2,
            sats_per_plane=3,
            isl_intra_plane=False,
            isl_inter_plane=False,
        )
        topo = generate_constellation(config)
        assert topo.link_count == 0

    def test_custom_constellation(self):
        config = ConstellationConfig(
            name="custom",
            num_planes=3,
            sats_per_plane=4,
            altitude_km=500.0,
            inclination_deg=45.0,
        )
        topo = generate_constellation(config)
        assert topo.node_count == 12


class TestAddGroundStation:
    def test_ground_station_connects_to_visible_sats(self):
        config = ConstellationConfig(
            name="test",
            num_planes=4,
            sats_per_plane=6,
            altitude_km=600.0,
            inclination_deg=55.0,
        )
        topo = generate_constellation(config)
        gs = add_ground_station(
            topo,
            station_id="gs-test",
            name="Test GS",
            latitude=0.0,
            longitude=0.0,
            min_elevation_deg=10.0,
            max_links=4,
        )
        assert gs.node_type == NodeType.GROUND_STATION
        assert topo.get_node("gs-test") is gs

        # Should have some ground links
        links = topo.get_all_links()
        ground_links = [l for l in links if l.isl_type == ISLType.GROUND_LINK]
        assert len(ground_links) > 0
        # Should be bidirectional
        assert len(ground_links) % 2 == 0

    def test_ground_station_max_links_respected(self):
        config = ConstellationConfig(
            name="test",
            num_planes=4,
            sats_per_plane=6,
            altitude_km=600.0,
            inclination_deg=55.0,
        )
        topo = generate_constellation(config)
        add_ground_station(
            topo,
            station_id="gs1",
            name="GS-1",
            latitude=0.0,
            longitude=0.0,
            min_elevation_deg=10.0,
            max_links=2,
        )
        links = topo.get_all_links()
        gs_uplinks = [
            l for l in links
            if l.source_id == "gs1" and l.isl_type == ISLType.GROUND_LINK
        ]
        assert len(gs_uplinks) <= 2


class TestPresets:
    def test_all_presets_exist(self):
        assert "iridium" in PRESETS
        assert "oneweb" in PRESETS
        assert "starlink_shell1" in PRESETS
        assert "small_leo" in PRESETS

    def test_oneweb_no_inter_plane(self):
        config = PRESETS["oneweb"]
        assert config.isl_inter_plane is False

    def test_starlink_scale(self):
        config = PRESETS["starlink_shell1"]
        total = config.num_planes * config.sats_per_plane
        assert total == 1584
