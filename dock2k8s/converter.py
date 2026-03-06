"""Parse docker-compose.yml and convert services to internal representation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_compose_file(path: str | Path) -> dict[str, Any]:
    """Load and validate a docker-compose.yml file."""
    filepath = Path(path)
    if not filepath.is_file():
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Invalid docker-compose file: expected a YAML mapping")

    if "services" not in data:
        raise ValueError("Invalid docker-compose file: missing 'services' key")

    return data


def parse_service(name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Parse a single Docker Compose service into a normalized dict."""
    service: dict[str, Any] = {
        "name": name,
        "image": config.get("image", ""),
        "ports": [],
        "env": {},
        "replicas": 1,
        "command": None,
    }

    if not service["image"]:
        raise ValueError(f"Service '{name}' is missing required 'image' field")

    # Parse ports: "host:container" or just "container"
    for port_entry in config.get("ports", []):
        port_str = str(port_entry)
        if ":" in port_str:
            parts = port_str.split(":")
            host_port = int(parts[0])
            container_port = int(parts[1].split("/")[0])
        else:
            container_port = int(port_str.split("/")[0])
            host_port = container_port
        service["ports"].append({
            "host_port": host_port,
            "container_port": container_port,
        })

    # Parse environment variables
    env_config = config.get("environment", [])
    if isinstance(env_config, list):
        for item in env_config:
            key_val = str(item).split("=", 1)
            if len(key_val) == 2:
                service["env"][key_val[0]] = key_val[1]
            else:
                service["env"][key_val[0]] = ""
    elif isinstance(env_config, dict):
        service["env"] = {k: str(v) for k, v in env_config.items()}

    # Parse replicas from deploy config
    deploy = config.get("deploy", {})
    if isinstance(deploy, dict):
        service["replicas"] = deploy.get("replicas", 1)

    # Parse command
    cmd = config.get("command")
    if cmd is not None:
        if isinstance(cmd, list):
            service["command"] = cmd
        else:
            service["command"] = str(cmd).split()

    return service


def parse_compose(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse all services from a docker-compose data dict."""
    services = []
    for name, config in data.get("services", {}).items():
        if not isinstance(config, dict):
            raise ValueError(f"Service '{name}' has invalid configuration")
        services.append(parse_service(name, config))
    return services
