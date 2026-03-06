# Satellite Broadcast Distribution SDN Controller

An SDN controller for LEO (Low Earth Orbit) satellite broadcast distribution systems with dynamic resource scheduling, designed for Kubernetes deployment.

## Features

- **Dynamic topology management** – tracks LEO satellite constellation changes including orbital plane shifts, link state transitions, and node heartbeats.
- **Resource-aware scheduling** – assigns broadcast distribution tasks based on node load (CPU, memory, bandwidth) and network path quality.
- **SDN flow rule generation** – computes shortest-path broadcast trees and installs per-hop forwarding rules on satellite nodes.
- **K8s-native health endpoints** – exposes `/healthz` and `/readyz` probes for liveness and readiness checks.

## Project Structure

```
src/satellite_sdn/
├── models.py       # Data models (SatelliteNode, InterSatelliteLink, FlowRule, BroadcastTask)
├── topology.py     # LEO topology manager with Dijkstra shortest-path routing
├── scheduler.py    # Priority-aware resource scheduler with bandwidth reservation
├── controller.py   # SDN controller with HTTP health/API server
└── __main__.py     # Entry point for standalone execution
k8s/
├── configmap.yaml  # Controller configuration
├── deployment.yaml # K8s Deployment with health probes
└── service.yaml    # ClusterIP Service
```

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run the controller
python -m satellite_sdn
```

## Kubernetes Deployment

```bash
# Build container image
docker build -t satellite-sdn-controller:latest .

# Deploy to K8s
kubectl apply -f k8s/
```

## License

MIT
