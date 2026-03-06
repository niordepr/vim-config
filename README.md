# Satellite Broadcast Distribution System – SDN Controller

An SDN (Software-Defined Networking) controller for managing broadcast distribution over satellite networks.

## Features

- **Topology Management** – model satellites, ground stations, and gateways as a directed graph with link-state tracking.
- **Multicast Tree Computation** – shortest-path trees and approximate Steiner trees for efficient broadcast distribution.
- **Flow Rule Management** – install, query, and remove SDN flow rules (FORWARD / REPLICATE / DROP) on network nodes.
- **Satellite Link Modelling** – free-space path loss, link budget, C/N ratio, Shannon capacity, and adaptive bandwidth.
- **Reactive Re-routing** – automatic session re-routing when a link failure is detected.
- **REST API** – manage the entire system via HTTP (nodes, links, sessions, flows).

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run the controller API server
satellite-sdn

# Run tests
pytest satellite_sdn_controller/tests/ -v
```

## Project Structure

```
satellite_sdn_controller/
├── __init__.py          # Package metadata
├── models.py            # Data models (Node, Link, FlowRule, BroadcastSession)
├── topology.py          # Network topology graph & shortest-path routing
├── multicast.py         # Multicast / broadcast tree algorithms
├── flow_manager.py      # SDN flow rule management
├── satellite_link.py    # RF link budget & adaptive bandwidth utilities
├── controller.py        # Central SDN controller orchestration
├── api.py               # Flask REST API
└── tests/               # Unit tests (pytest)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Controller status summary |
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

## License

MIT
