# Satellite Broadcast Distribution SDN Controller

English | [中文](README.zh-CN.md)

An SDN controller for LEO (Low Earth Orbit) satellite broadcast distribution systems with dynamic resource scheduling, designed for Kubernetes deployment.

## Features

- **Dynamic topology management** – tracks LEO satellite constellation changes including orbital plane shifts, link state transitions, and node heartbeats.
- **Resource-aware scheduling** – assigns broadcast distribution tasks based on node load (CPU, memory, bandwidth) and network path quality.
- **SDN flow rule generation** – computes shortest-path broadcast trees and installs per-hop forwarding rules on satellite nodes.
- **K8s-native health endpoints** – exposes `/healthz` and `/readyz` probes for liveness and readiness checks.

## Prerequisites

- Python 3.10 or later
- pip (Python package manager)
- Docker (optional, for container deployment)
- kubectl + a Kubernetes cluster (optional, for K8s deployment)

## Project Structure

```
src/satellite_sdn/
├── __init__.py     # Package marker and version
├── __main__.py     # Entry point for standalone execution
├── models.py       # Data models (SatelliteNode, InterSatelliteLink, FlowRule, BroadcastTask)
├── topology.py     # LEO topology manager with Dijkstra shortest-path routing
├── scheduler.py    # Priority-aware resource scheduler with bandwidth reservation
└── controller.py   # SDN controller with HTTP health/API server
k8s/
├── configmap.yaml  # Controller configuration (tunable parameters)
├── deployment.yaml # K8s Deployment with liveness/readiness probes
└── service.yaml    # ClusterIP Service on port 8081
tests/
├── test_models.py
├── test_topology.py
├── test_scheduler.py
└── test_controller.py
```

## Installation

```bash
# Clone the repository
git clone https://github.com/niordepr/vim-config.git
cd vim-config

# Install in development mode (includes pytest for running tests)
pip install -e ".[dev]"
```

## Quick Start

### Running the Controller as a Standalone Service

```bash
python -m satellite_sdn
```

This starts the SDN controller with an HTTP server on port 8081 that exposes health and management endpoints:

| Endpoint    | Description                                       |
| ----------- | ------------------------------------------------- |
| `/healthz`  | Liveness probe – always returns `{"status":"ok"}` |
| `/readyz`   | Readiness probe – `ready` when the controller is running |
| `/topology` | JSON snapshot of the current constellation topology |
| `/rules`    | Currently installed SDN flow rules                |

### Using the Library in Your Own Code

The core classes can be imported and used directly in Python:

```python
from satellite_sdn.controller import SDNController
from satellite_sdn.models import (
    SatelliteNode,
    InterSatelliteLink,
    BroadcastTask,
)

# 1. Create a controller
ctrl = SDNController(load_threshold=0.8)

# 2. Register satellite nodes
ctrl.register_node(SatelliteNode(node_id="sat-0", orbit_id=0, position_index=0))
ctrl.register_node(SatelliteNode(node_id="sat-1", orbit_id=0, position_index=1))
ctrl.register_node(SatelliteNode(node_id="sat-2", orbit_id=1, position_index=0))

# 3. Register inter-satellite links
ctrl.register_link(InterSatelliteLink(
    link_id="link-01", source_id="sat-0", target_id="sat-1", latency_ms=5.0,
))
ctrl.register_link(InterSatelliteLink(
    link_id="link-12", source_id="sat-1", target_id="sat-2", latency_ms=8.0,
))

# 4. Submit a broadcast distribution task
results = ctrl.submit_tasks([
    BroadcastTask(
        task_id="task-1",
        source_node_id="sat-0",
        target_node_ids=["sat-1", "sat-2"],
        bandwidth_required_mbps=100.0,
        priority=5,
    )
])

# 5. Inspect results
for r in results:
    print(f"Task {r.task_id}: success={r.success}")
    for target, path in r.assigned_paths.items():
        print(f"  -> {target}: {' -> '.join(path)}")
    for rule in r.flow_rules:
        print(f"  Rule {rule.rule_id}: {rule.node_id} -> {rule.next_hop}")
```

### Updating Node Metrics

Node metrics can be updated at runtime to reflect real-time resource usage:

```python
from satellite_sdn.models import NodeStatus, LinkStatus

# Update CPU / memory / bandwidth metrics
ctrl.update_node_metrics("sat-0", cpu_usage=0.6, memory_usage=0.4)
ctrl.update_node_metrics("sat-1", bandwidth_mbps=500.0)

# Change node or link status
ctrl.update_node_status("sat-2", NodeStatus.OFFLINE)
ctrl.update_link_status("link-12", LinkStatus.DOWN)
```

### Querying Topology

```python
# Get a full topology snapshot (JSON-serialisable dict)
snapshot = ctrl.topology_snapshot()

# Access the topology manager directly
online = ctrl.topology.online_nodes
print(f"{len(online)} nodes online")

# Compute shortest path between two nodes
path, cost = ctrl.topology.shortest_path("sat-0", "sat-2")
print(f"Path: {' -> '.join(path)}, cost: {cost}")
```

## Configuration

The controller accepts the following parameters:

| Parameter              | Default | Description                                        |
| ---------------------- | ------- | -------------------------------------------------- |
| `heartbeat_timeout_s`  | `30.0`  | Seconds before an unresponsive node is marked OFFLINE |
| `load_threshold`       | `0.8`   | Maximum load score (0–1) a node may have to accept tasks |
| `reconcile_interval_s` | `10.0`  | Seconds between periodic reconciliation sweeps     |

These can be set when creating the controller:

```python
ctrl = SDNController(
    heartbeat_timeout_s=60.0,
    load_threshold=0.9,
    reconcile_interval_s=5.0,
)
```

They can also be set via environment variables (used by the standalone entry point and Kubernetes deployments):

```bash
HEARTBEAT_TIMEOUT_S=60 LOAD_THRESHOLD=0.9 RECONCILE_INTERVAL_S=5 python -m satellite_sdn
```

When deployed to Kubernetes, they are configured via the ConfigMap in `k8s/configmap.yaml`, which injects the values as environment variables into the container.

## Running Tests

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific test file
pytest tests/test_scheduler.py

# Run a specific test class or method
pytest tests/test_topology.py::TestShortestPath::test_simple_path
```

## Kubernetes Deployment

### Build and Deploy

```bash
# Build the container image
docker build -t satellite-sdn-controller:latest .

# Apply all K8s manifests (ConfigMap, Deployment, Service)
kubectl apply -f k8s/

# Verify the deployment
kubectl get pods -l app=satellite-sdn-controller
kubectl logs -l app=satellite-sdn-controller
```

### Accessing the Service

Inside the cluster the controller is reachable at `satellite-sdn-controller:8081`.

```bash
# Port-forward for local access
kubectl port-forward svc/satellite-sdn-controller 8081:8081

# Health check
curl http://localhost:8081/healthz

# Topology snapshot
curl http://localhost:8081/topology
```

### Customising Configuration

Edit `k8s/configmap.yaml` and re-apply:

```yaml
data:
  HEARTBEAT_TIMEOUT_S: "60"
  LOAD_THRESHOLD: "0.9"
  RECONCILE_INTERVAL_S: "5"
```

```bash
kubectl apply -f k8s/configmap.yaml
kubectl rollout restart deployment/satellite-sdn-controller
```

## License

MIT
