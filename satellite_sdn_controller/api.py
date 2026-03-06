"""REST API for the satellite broadcast distribution SDN controller.

Exposes the controller's functionality over HTTP using Flask, including
constellation management, routing strategy selection, handover control,
and QoS-aware session management.
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from .constellation import PRESETS, ConstellationConfig
from .controller import SatelliteSDNController
from .models import (
    Link,
    LinkState,
    Node,
    NodeType,
    QosPriority,
    RoutingStrategy,
)


def create_app(controller: SatelliteSDNController | None = None) -> Flask:
    """Create and configure the Flask application.

    Parameters
    ----------
    controller:
        An existing controller instance.  If *None* a fresh one is created.
    """
    app = Flask(__name__)
    ctrl = controller or SatelliteSDNController()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify(ctrl.get_status())

    # ------------------------------------------------------------------
    # Constellation
    # ------------------------------------------------------------------

    @app.route("/api/constellation/presets", methods=["GET"])
    def list_presets():
        result = {}
        for name, cfg in PRESETS.items():
            result[name] = {
                "num_planes": cfg.num_planes,
                "sats_per_plane": cfg.sats_per_plane,
                "total_sats": cfg.num_planes * cfg.sats_per_plane,
                "altitude_km": cfg.altitude_km,
                "inclination_deg": cfg.inclination_deg,
            }
        return jsonify(result)

    @app.route("/api/constellation/generate", methods=["POST"])
    def generate_constellation():
        data = request.get_json(force=True)
        preset = data.get("preset")
        if preset:
            try:
                config = ctrl.load_constellation(preset)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        else:
            config = ConstellationConfig(
                name=data.get("name", "custom"),
                num_planes=data.get("num_planes", 6),
                sats_per_plane=data.get("sats_per_plane", 11),
                altitude_km=data.get("altitude_km", 780.0),
                inclination_deg=data.get("inclination_deg", 86.4),
                phase_offset=data.get("phase_offset", 1),
                isl_intra_plane=data.get("isl_intra_plane", True),
                isl_inter_plane=data.get("isl_inter_plane", True),
                isl_bandwidth_mbps=data.get("isl_bandwidth_mbps", 10_000.0),
            )
            ctrl.generate_constellation(config)
        return jsonify({
            "name": config.name,
            "total_satellites": config.num_planes * config.sats_per_plane,
            "nodes": ctrl.topology.node_count,
            "links": ctrl.topology.link_count,
        }), 201

    @app.route("/api/constellation/ground_stations", methods=["POST"])
    def add_ground_station():
        data = request.get_json(force=True)
        try:
            gs = ctrl.add_ground_station(
                station_id=data["station_id"],
                name=data.get("name", ""),
                latitude=data["latitude"],
                longitude=data["longitude"],
                min_elevation_deg=data.get("min_elevation_deg", 25.0),
                bandwidth_mbps=data.get("bandwidth_mbps", 1_000.0),
                max_links=data.get("max_links", 4),
            )
        except (KeyError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(gs.to_dict()), 201

    # ------------------------------------------------------------------
    # Routing strategy
    # ------------------------------------------------------------------

    @app.route("/api/strategy", methods=["GET"])
    def get_strategy():
        return jsonify({
            "default_strategy": ctrl.default_strategy.value,
            "available": [s.value for s in RoutingStrategy],
        })

    @app.route("/api/strategy", methods=["PUT"])
    def set_strategy():
        data = request.get_json(force=True)
        name = data.get("strategy", "")
        try:
            strategy = RoutingStrategy(name)
        except ValueError:
            return jsonify({
                "error": f"unknown strategy: {name}",
                "available": [s.value for s in RoutingStrategy],
            }), 400
        ctrl.default_strategy = strategy
        return jsonify({"default_strategy": strategy.value})

    # ------------------------------------------------------------------
    # Handover
    # ------------------------------------------------------------------

    @app.route("/api/handover", methods=["POST"])
    def trigger_handover():
        results = ctrl.trigger_handover()
        return jsonify(results)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    @app.route("/api/nodes", methods=["GET"])
    def list_nodes():
        return jsonify([n.to_dict() for n in ctrl.topology.get_all_nodes()])

    @app.route("/api/nodes", methods=["POST"])
    def add_node():
        data = request.get_json(force=True)
        node = Node.from_dict(data)
        ctrl.add_node(node)
        return jsonify(node.to_dict()), 201

    @app.route("/api/nodes/<node_id>", methods=["GET"])
    def get_node(node_id: str):
        node = ctrl.topology.get_node(node_id)
        if node is None:
            return jsonify({"error": "node not found"}), 404
        return jsonify(node.to_dict())

    @app.route("/api/nodes/<node_id>", methods=["DELETE"])
    def delete_node(node_id: str):
        node = ctrl.remove_node(node_id)
        if node is None:
            return jsonify({"error": "node not found"}), 404
        return jsonify(node.to_dict())

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------

    @app.route("/api/links", methods=["GET"])
    def list_links():
        return jsonify([l.to_dict() for l in ctrl.topology.get_all_links()])

    @app.route("/api/links", methods=["POST"])
    def add_link():
        data = request.get_json(force=True)
        try:
            link = Link.from_dict(data)
            ctrl.add_link(link)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(link.to_dict()), 201

    @app.route("/api/links/<link_id>", methods=["DELETE"])
    def delete_link(link_id: str):
        link = ctrl.remove_link(link_id)
        if link is None:
            return jsonify({"error": "link not found"}), 404
        return jsonify(link.to_dict())

    @app.route("/api/links/<link_id>/state", methods=["PUT"])
    def update_link_state(link_id: str):
        data = request.get_json(force=True)
        state_str = data.get("state", "")
        try:
            state = LinkState(state_str)
        except ValueError:
            return jsonify({"error": f"invalid state: {state_str}"}), 400
        if not ctrl.set_link_state(link_id, state):
            return jsonify({"error": "link not found"}), 404
        return jsonify({"link_id": link_id, "state": state.value})

    # ------------------------------------------------------------------
    # Broadcast sessions
    # ------------------------------------------------------------------

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        return jsonify([s.to_dict() for s in ctrl.get_all_sessions()])

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        data = request.get_json(force=True)
        qos = QosPriority.MEDIUM
        if "qos_priority" in data:
            try:
                qos = QosPriority(data["qos_priority"])
            except ValueError:
                pass
        strategy = None
        if "routing_strategy" in data and data["routing_strategy"]:
            try:
                strategy = RoutingStrategy(data["routing_strategy"])
            except ValueError:
                pass
        session = ctrl.create_broadcast_session(
            name=data.get("name", ""),
            source_node_id=data["source_node_id"],
            multicast_group=data.get("multicast_group", ""),
            destination_node_ids=set(data.get("destination_node_ids", [])),
            bandwidth_mbps=data.get("bandwidth_mbps", 10.0),
            qos_priority=qos,
            routing_strategy=strategy,
            max_latency_ms=data.get("max_latency_ms", 0.0),
        )
        return jsonify(session.to_dict()), 201

    @app.route("/api/sessions/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        session = ctrl.get_session(session_id)
        if session is None:
            return jsonify({"error": "session not found"}), 404
        return jsonify(session.to_dict())

    @app.route("/api/sessions/<session_id>/activate", methods=["POST"])
    def activate_session(session_id: str):
        if not ctrl.activate_session(session_id):
            return jsonify({"error": "activation failed"}), 400
        session = ctrl.get_session(session_id)
        return jsonify(session.to_dict())  # type: ignore[union-attr]

    @app.route("/api/sessions/<session_id>/deactivate", methods=["POST"])
    def deactivate_session(session_id: str):
        if not ctrl.deactivate_session(session_id):
            return jsonify({"error": "deactivation failed"}), 400
        session = ctrl.get_session(session_id)
        return jsonify(session.to_dict())  # type: ignore[union-attr]

    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def delete_session(session_id: str):
        session = ctrl.remove_session(session_id)
        if session is None:
            return jsonify({"error": "session not found"}), 404
        return jsonify(session.to_dict())

    # ------------------------------------------------------------------
    # Flow rules
    # ------------------------------------------------------------------

    @app.route("/api/flows", methods=["GET"])
    def list_flows():
        return jsonify([r.to_dict() for r in ctrl.flow_manager.get_all_rules()])

    @app.route("/api/flows/<node_id>", methods=["GET"])
    def flows_for_node(node_id: str):
        rules = ctrl.flow_manager.get_rules_for_node(node_id)
        return jsonify([r.to_dict() for r in rules])

    return app


def main() -> None:
    """Run the API server (development mode)."""
    app = create_app()
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
