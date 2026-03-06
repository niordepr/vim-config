# Satellite Broadcast Distribution System – SDN Controller

An SDN (Software-Defined Networking) controller for managing broadcast distribution over satellite networks. Supports various scales of LEO constellations (from small 24-satellite networks to large 1584-satellite Starlink-scale deployments), multiple routing strategies, QoS-aware session management, and proactive handover for LEO dynamics.

## Features

- **LEO Constellation Generation** – Walker Delta/Star constellations with configurable planes, satellites per plane, altitude, and inclination. Preset configurations for Iridium (66 sats), OneWeb (648 sats), Starlink Shell-1 (1584 sats), and small LEO (24 sats).
- **Inter-Satellite Links (ISL)** – automatic intra-plane and inter-plane ISL generation with realistic propagation delay estimation.
- **Multiple Routing Strategies** – shortest path, minimum cost (Steiner tree), minimum latency, maximum bandwidth, load-balanced, and delay-bounded multicast.
- **QoS Priority Levels** – critical, high, medium, low, best-effort with corresponding flow rule priorities.
- **Handover Management** – proactive ground-station ↔ satellite link handover based on elevation angle with hysteresis.
- **Reactive Re-routing** – automatic session re-routing when a link failure or handover event is detected.
- **Topology Management** – directed graph with Dijkstra routing, link-state tracking, and propagation delay estimation.
- **Satellite Link Modelling** – free-space path loss, link budget, C/N ratio, Shannon capacity, and adaptive bandwidth.
- **REST API** – manage the entire system via HTTP (constellation, nodes, links, sessions, flows, strategy, handover).

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run the controller API server
satellite-sdn

# Run tests
pytest satellite_sdn_controller/tests/ -v
```

## Example: LEO Constellation Broadcast

```python
from satellite_sdn_controller.controller import SatelliteSDNController
from satellite_sdn_controller.models import RoutingStrategy, QosPriority

# Create controller with min-latency routing
ctrl = SatelliteSDNController(
    default_strategy=RoutingStrategy.MIN_LATENCY,
)

# Generate an Iridium-like constellation (66 satellites)
ctrl.load_constellation("iridium")

# Add ground stations
ctrl.add_ground_station("gs-tokyo", "GS-Tokyo", 35.68, 139.69)
ctrl.add_ground_station("gs-london", "GS-London", 51.51, -0.13)
ctrl.add_ground_station("gs-nyc", "GS-NewYork", 40.71, -74.01)

# Create a critical broadcast session
session = ctrl.create_broadcast_session(
    name="Breaking-News",
    source_node_id="gs-tokyo",
    multicast_group="239.1.1.1",
    destination_node_ids={"gs-london", "gs-nyc"},
    bandwidth_mbps=50.0,
    qos_priority=QosPriority.CRITICAL,
    routing_strategy=RoutingStrategy.DELAY_BOUNDED,
    max_latency_ms=200.0,
)

# Activate – computes distribution tree and installs flow rules
ctrl.activate_session(session.session_id)

# Trigger handover when satellite positions change
ctrl.trigger_handover()
```

## Constellation Presets

| Preset | Planes × Sats | Total | Altitude | Inclination | ISL |
|--------|--------------|-------|----------|-------------|-----|
| `small_leo` | 4 × 6 | 24 | 600 km | 55° | intra + inter |
| `iridium` | 6 × 11 | 66 | 780 km | 86.4° | intra + inter |
| `oneweb` | 18 × 36 | 648 | 1200 km | 87.9° | intra only |
| `starlink_shell1` | 72 × 22 | 1584 | 550 km | 53° | intra + inter |

## Routing Strategies

| Strategy | Optimises For | Use Case |
|----------|--------------|----------|
| `shortest_path` | Link cost | General purpose |
| `minimum_cost_tree` | Total tree cost (Steiner) | Bandwidth-efficient multicast |
| `min_latency` | End-to-end delay | Live broadcast, real-time |
| `max_bandwidth` | Bottleneck bandwidth | High-throughput streams |
| `load_balanced` | Even traffic distribution | Congestion avoidance |
| `delay_bounded` | Cost under latency constraint | QoS-guaranteed broadcast |

## Project Structure

```
satellite_sdn_controller/
├── __init__.py            # Package metadata
├── models.py              # Data models (Node, Link, FlowRule, BroadcastSession, enums)
├── topology.py            # Network topology graph & shortest-path routing
├── constellation.py       # Walker Delta/Star LEO constellation generator
├── multicast.py           # Legacy multicast / broadcast tree algorithms
├── routing_strategy.py    # Pluggable routing strategies (6 algorithms)
├── flow_manager.py        # SDN flow rule management
├── satellite_link.py      # RF link budget & adaptive bandwidth utilities
├── handover.py            # LEO ground-station handover manager
├── controller.py          # Central SDN controller orchestration
├── api.py                 # Flask REST API
└── tests/                 # Unit tests (pytest, 119 tests)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Controller status summary |
| GET | `/api/constellation/presets` | List available constellation presets |
| POST | `/api/constellation/generate` | Generate constellation (preset or custom) |
| POST | `/api/constellation/ground_stations` | Add a ground station |
| GET / PUT | `/api/strategy` | Get / set default routing strategy |
| POST | `/api/handover` | Trigger ground-station handover evaluation |
| GET / POST | `/api/nodes` | List / add nodes |
| GET / DELETE | `/api/nodes/<id>` | Get / remove a node |
| GET / POST | `/api/links` | List / add links |
| DELETE | `/api/links/<id>` | Remove a link |
| PUT | `/api/links/<id>/state` | Update link state (up/down/degraded) |
| GET / POST | `/api/sessions` | List / create broadcast sessions |
| GET / DELETE | `/api/sessions/<id>` | Get / remove a session |
| POST | `/api/sessions/<id>/activate` | Activate (compute tree & install flows) |
| POST | `/api/sessions/<id>/deactivate` | Deactivate (remove flows) |
| GET | `/api/flows` | List all installed flow rules |
| GET | `/api/flows/<node_id>` | List flow rules for a specific node |

## References

* Walker, J.G. "Satellite constellations," *J. Br. Interplanet. Soc.*, 1984.
* Handley, M. "Delay is Not an Option: Low Latency Routing in Space," *HotNets*, 2018.
* Bhattacherjee, D. & Singla, A. "Network topology design at 27,000 km/h," *CoNEXT*, 2019.
* del Portillo, I. et al. "A technical comparison of three LEO satellite constellation systems to provide global broadband," *ICSSC*, 2018.
* Papa, A. et al. "Dynamic SDN-based Radio Access Network Slicing for LEO Satellite Networks," *IEEE Trans. on Network and Service Management*, 2022.

## License

MIT
