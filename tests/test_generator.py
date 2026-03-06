"""Tests for dock2k8s.generator module."""

from dock2k8s.generator import (
    generate_configmap,
    generate_deployment,
    generate_manifests,
    generate_service,
    manifests_to_yaml,
)


class TestGenerateConfigMap:
    def test_with_env_vars(self):
        service = {
            "name": "api",
            "env": {"DB_HOST": "localhost", "DB_PORT": "5432"},
        }
        result = generate_configmap(service, "default")

        assert result["kind"] == "ConfigMap"
        assert result["metadata"]["name"] == "api-config"
        assert result["metadata"]["namespace"] == "default"
        assert result["data"] == {"DB_HOST": "localhost", "DB_PORT": "5432"}

    def test_without_env_vars(self):
        service = {"name": "web", "env": {}}
        result = generate_configmap(service, "default")
        assert result is None


class TestGenerateDeployment:
    def test_basic_deployment(self):
        service = {
            "name": "web",
            "image": "nginx:latest",
            "ports": [{"container_port": 80}],
            "env": {},
            "replicas": 1,
            "command": None,
        }
        result = generate_deployment(service, "default")

        assert result["kind"] == "Deployment"
        assert result["metadata"]["name"] == "web"
        assert result["spec"]["replicas"] == 1
        container = result["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == "nginx:latest"
        assert container["ports"] == [{"containerPort": 80}]
        assert "envFrom" not in container
        assert "command" not in container

    def test_deployment_with_env(self):
        service = {
            "name": "api",
            "image": "app:v1",
            "ports": [],
            "env": {"KEY": "val"},
            "replicas": 3,
            "command": None,
        }
        result = generate_deployment(service, "prod")

        assert result["metadata"]["namespace"] == "prod"
        assert result["spec"]["replicas"] == 3
        container = result["spec"]["template"]["spec"]["containers"][0]
        assert container["envFrom"] == [{"configMapRef": {"name": "api-config"}}]

    def test_deployment_with_command(self):
        service = {
            "name": "worker",
            "image": "app:v1",
            "ports": [],
            "env": {},
            "replicas": 1,
            "command": ["python", "worker.py"],
        }
        result = generate_deployment(service, "default")

        container = result["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "worker.py"]


class TestGenerateService:
    def test_with_ports(self):
        service = {
            "name": "web",
            "ports": [{"host_port": 8080, "container_port": 80}],
        }
        result = generate_service(service, "default")

        assert result["kind"] == "Service"
        assert result["spec"]["type"] == "ClusterIP"
        assert result["spec"]["ports"] == [
            {"port": 8080, "targetPort": 80, "protocol": "TCP"}
        ]

    def test_without_ports(self):
        service = {"name": "worker", "ports": []}
        result = generate_service(service, "default")
        assert result is None


class TestGenerateManifests:
    def test_full_service(self):
        services = [
            {
                "name": "web",
                "image": "nginx:latest",
                "ports": [{"host_port": 80, "container_port": 80}],
                "env": {"APP_ENV": "prod"},
                "replicas": 2,
                "command": None,
            }
        ]
        manifests = generate_manifests(services, namespace="test")

        assert len(manifests) == 3  # ConfigMap + Deployment + Service
        kinds = [m["kind"] for m in manifests]
        assert kinds == ["ConfigMap", "Deployment", "Service"]

    def test_service_without_ports_or_env(self):
        services = [
            {
                "name": "worker",
                "image": "app:v1",
                "ports": [],
                "env": {},
                "replicas": 1,
                "command": None,
            }
        ]
        manifests = generate_manifests(services)

        assert len(manifests) == 1  # Only Deployment
        assert manifests[0]["kind"] == "Deployment"


class TestManifestsToYaml:
    def test_yaml_output(self):
        manifests = [
            {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "test"}},
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}},
        ]
        output = manifests_to_yaml(manifests)

        assert "---" in output
        assert "kind: ConfigMap" in output
        assert "kind: Deployment" in output
