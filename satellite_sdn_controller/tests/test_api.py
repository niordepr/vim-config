"""Tests for the REST API."""

import json

import pytest

from satellite_sdn_controller.api import create_app
from satellite_sdn_controller.controller import SatelliteSDNController
from satellite_sdn_controller.models import Link, Node, NodeType


@pytest.fixture
def client():
    ctrl = SatelliteSDNController()
    app = create_app(ctrl)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, ctrl


def _seed(ctrl):
    """Add a few nodes and links to the controller."""
    ctrl.add_node(Node(node_id="gw", name="Gateway", node_type=NodeType.GATEWAY))
    ctrl.add_node(Node(node_id="sat1", name="SAT-1", node_type=NodeType.SATELLITE))
    ctrl.add_node(Node(node_id="gs1", name="GS-1", node_type=NodeType.GROUND_STATION))
    ctrl.add_link(Link(link_id="gw-sat1", source_id="gw", target_id="sat1"))
    ctrl.add_link(Link(link_id="sat1-gs1", source_id="sat1", target_id="gs1"))


class TestStatusEndpoint:
    def test_get_status(self, client):
        c, _ = client
        resp = c.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "default_strategy" in data


class TestNodeEndpoints:
    def test_add_and_list_nodes(self, client):
        c, _ = client
        resp = c.post(
            "/api/nodes",
            data=json.dumps({"node_id": "n1", "name": "Test", "node_type": "satellite"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        resp = c.get("/api/nodes")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_get_node_404(self, client):
        c, _ = client
        resp = c.get("/api/nodes/nonexistent")
        assert resp.status_code == 404

    def test_delete_node(self, client):
        c, ctrl = client
        ctrl.add_node(Node(node_id="d1"))
        resp = c.delete("/api/nodes/d1")
        assert resp.status_code == 200


class TestLinkEndpoints:
    def test_add_and_list_links(self, client):
        c, ctrl = client
        ctrl.add_node(Node(node_id="a"))
        ctrl.add_node(Node(node_id="b"))
        resp = c.post(
            "/api/links",
            data=json.dumps({"link_id": "l1", "source_id": "a", "target_id": "b"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        resp = c.get("/api/links")
        assert len(resp.get_json()) == 1

    def test_add_link_invalid_node(self, client):
        c, _ = client
        resp = c.post(
            "/api/links",
            data=json.dumps({"source_id": "x", "target_id": "y"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_update_link_state(self, client):
        c, ctrl = client
        _seed(ctrl)
        resp = c.put(
            "/api/links/gw-sat1/state",
            data=json.dumps({"state": "down"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["state"] == "down"

    def test_update_link_state_invalid(self, client):
        c, ctrl = client
        _seed(ctrl)
        resp = c.put(
            "/api/links/gw-sat1/state",
            data=json.dumps({"state": "invalid"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestSessionEndpoints:
    def test_create_activate_deactivate(self, client):
        c, ctrl = client
        _seed(ctrl)
        # Create session
        resp = c.post(
            "/api/sessions",
            data=json.dumps({
                "name": "TV",
                "source_node_id": "gw",
                "multicast_group": "239.1.1.1",
                "destination_node_ids": ["gs1"],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        sid = resp.get_json()["session_id"]

        # Activate
        resp = c.post(f"/api/sessions/{sid}/activate")
        assert resp.status_code == 200
        assert resp.get_json()["active"] is True

        # Deactivate
        resp = c.post(f"/api/sessions/{sid}/deactivate")
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False

    def test_get_session_404(self, client):
        c, _ = client
        resp = c.get("/api/sessions/nonexistent")
        assert resp.status_code == 404

    def test_delete_session(self, client):
        c, ctrl = client
        _seed(ctrl)
        resp = c.post(
            "/api/sessions",
            data=json.dumps({
                "name": "TV",
                "source_node_id": "gw",
                "multicast_group": "239.1.1.1",
                "destination_node_ids": ["gs1"],
            }),
            content_type="application/json",
        )
        sid = resp.get_json()["session_id"]
        resp = c.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200

    def test_create_session_with_qos(self, client):
        c, ctrl = client
        _seed(ctrl)
        resp = c.post(
            "/api/sessions",
            data=json.dumps({
                "name": "Critical-TV",
                "source_node_id": "gw",
                "multicast_group": "239.2.2.2",
                "destination_node_ids": ["gs1"],
                "qos_priority": "critical",
                "routing_strategy": "min_latency",
                "max_latency_ms": 200.0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["qos_priority"] == "critical"
        assert data["routing_strategy"] == "min_latency"
        assert data["max_latency_ms"] == 200.0


class TestFlowEndpoints:
    def test_list_flows(self, client):
        c, ctrl = client
        _seed(ctrl)
        session = ctrl.create_broadcast_session(
            name="TV",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
        )
        ctrl.activate_session(session.session_id)
        resp = c.get("/api/flows")
        assert resp.status_code == 200
        assert len(resp.get_json()) > 0

    def test_flows_for_node(self, client):
        c, ctrl = client
        _seed(ctrl)
        session = ctrl.create_broadcast_session(
            name="TV",
            source_node_id="gw",
            multicast_group="239.1.1.1",
            destination_node_ids={"gs1"},
        )
        ctrl.activate_session(session.session_id)
        resp = c.get("/api/flows/gw")
        assert resp.status_code == 200


class TestConstellationEndpoints:
    def test_list_presets(self, client):
        c, _ = client
        resp = c.get("/api/constellation/presets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "iridium" in data
        assert "small_leo" in data

    def test_generate_from_preset(self, client):
        c, _ = client
        resp = c.post(
            "/api/constellation/generate",
            data=json.dumps({"preset": "small_leo"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["total_satellites"] == 24
        assert data["nodes"] >= 24

    def test_generate_unknown_preset(self, client):
        c, _ = client
        resp = c.post(
            "/api/constellation/generate",
            data=json.dumps({"preset": "unknown"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_generate_custom(self, client):
        c, _ = client
        resp = c.post(
            "/api/constellation/generate",
            data=json.dumps({
                "name": "custom",
                "num_planes": 2,
                "sats_per_plane": 3,
                "altitude_km": 500.0,
                "inclination_deg": 45.0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["total_satellites"] == 6

    def test_add_ground_station(self, client):
        c, ctrl = client
        ctrl.load_constellation("small_leo")
        resp = c.post(
            "/api/constellation/ground_stations",
            data=json.dumps({
                "station_id": "gs-test",
                "name": "Test GS",
                "latitude": 0.0,
                "longitude": 0.0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["node_id"] == "gs-test"


class TestStrategyEndpoints:
    def test_get_strategy(self, client):
        c, _ = client
        resp = c.get("/api/strategy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["default_strategy"] == "shortest_path"
        assert "available" in data

    def test_set_strategy(self, client):
        c, _ = client
        resp = c.put(
            "/api/strategy",
            data=json.dumps({"strategy": "min_latency"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["default_strategy"] == "min_latency"

    def test_set_invalid_strategy(self, client):
        c, _ = client
        resp = c.put(
            "/api/strategy",
            data=json.dumps({"strategy": "bogus"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestHandoverEndpoint:
    def test_trigger_handover(self, client):
        c, ctrl = client
        ctrl.load_constellation("small_leo")
        ctrl.add_ground_station("gs1", "GS-1", 0.0, 0.0, min_elevation_deg=10.0)
        resp = c.post("/api/handover")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), dict)
