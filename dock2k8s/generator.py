"""Generate Kubernetes manifests from parsed service definitions."""

from __future__ import annotations

from typing import Any

import yaml


def generate_configmap(service: dict[str, Any], namespace: str) -> dict[str, Any] | None:
    """Generate a ConfigMap for a service's environment variables."""
    if not service["env"]:
        return None

    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"{service['name']}-config",
            "namespace": namespace,
        },
        "data": service["env"],
    }


def generate_deployment(service: dict[str, Any], namespace: str) -> dict[str, Any]:
    """Generate a Deployment manifest for a service."""
    container: dict[str, Any] = {
        "name": service["name"],
        "image": service["image"],
        "ports": [
            {"containerPort": p["container_port"]}
            for p in service["ports"]
        ],
    }

    if service["command"]:
        container["command"] = service["command"]

    if service["env"]:
        container["envFrom"] = [
            {"configMapRef": {"name": f"{service['name']}-config"}}
        ]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": service["name"],
            "namespace": namespace,
        },
        "spec": {
            "replicas": service["replicas"],
            "selector": {
                "matchLabels": {"app": service["name"]},
            },
            "template": {
                "metadata": {
                    "labels": {"app": service["name"]},
                },
                "spec": {
                    "containers": [container],
                },
            },
        },
    }


def generate_service(service: dict[str, Any], namespace: str) -> dict[str, Any] | None:
    """Generate a Service manifest for a service (only if ports are defined)."""
    if not service["ports"]:
        return None

    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service["name"],
            "namespace": namespace,
        },
        "spec": {
            "selector": {"app": service["name"]},
            "ports": [
                {
                    "port": p["host_port"],
                    "targetPort": p["container_port"],
                    "protocol": "TCP",
                }
                for p in service["ports"]
            ],
            "type": "ClusterIP",
        },
    }


def generate_manifests(
    services: list[dict[str, Any]],
    namespace: str = "default",
) -> list[dict[str, Any]]:
    """Generate all Kubernetes manifests for a list of parsed services."""
    manifests: list[dict[str, Any]] = []

    for service in services:
        configmap = generate_configmap(service, namespace)
        if configmap:
            manifests.append(configmap)

        manifests.append(generate_deployment(service, namespace))

        k8s_service = generate_service(service, namespace)
        if k8s_service:
            manifests.append(k8s_service)

    return manifests


def manifests_to_yaml(manifests: list[dict[str, Any]]) -> str:
    """Serialize a list of manifests to a multi-document YAML string."""
    docs = []
    for manifest in manifests:
        docs.append(yaml.dump(manifest, default_flow_style=False, sort_keys=False))
    return "---\n".join(docs)
