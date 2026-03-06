"""Tests for dock2k8s.converter module."""

import pytest

from dock2k8s.converter import load_compose_file, parse_compose, parse_service


class TestParseService:
    def test_basic_service(self):
        config = {"image": "nginx:latest"}
        result = parse_service("web", config)

        assert result["name"] == "web"
        assert result["image"] == "nginx:latest"
        assert result["ports"] == []
        assert result["env"] == {}
        assert result["replicas"] == 1
        assert result["command"] is None

    def test_service_with_ports(self):
        config = {
            "image": "nginx:latest",
            "ports": ["80:80", "443:443"],
        }
        result = parse_service("web", config)

        assert len(result["ports"]) == 2
        assert result["ports"][0] == {"host_port": 80, "container_port": 80}
        assert result["ports"][1] == {"host_port": 443, "container_port": 443}

    def test_service_with_different_host_container_ports(self):
        config = {
            "image": "nginx:latest",
            "ports": ["8080:80"],
        }
        result = parse_service("web", config)

        assert result["ports"][0] == {"host_port": 8080, "container_port": 80}

    def test_service_with_env_list(self):
        config = {
            "image": "app:latest",
            "environment": ["DB_HOST=localhost", "DB_PORT=5432"],
        }
        result = parse_service("api", config)

        assert result["env"] == {"DB_HOST": "localhost", "DB_PORT": "5432"}

    def test_service_with_env_dict(self):
        config = {
            "image": "app:latest",
            "environment": {"DB_HOST": "localhost", "DB_PORT": 5432},
        }
        result = parse_service("api", config)

        assert result["env"] == {"DB_HOST": "localhost", "DB_PORT": "5432"}

    def test_service_with_replicas(self):
        config = {
            "image": "app:latest",
            "deploy": {"replicas": 3},
        }
        result = parse_service("api", config)

        assert result["replicas"] == 3

    def test_service_with_command_list(self):
        config = {
            "image": "app:latest",
            "command": ["python", "app.py"],
        }
        result = parse_service("api", config)

        assert result["command"] == ["python", "app.py"]

    def test_service_with_command_string(self):
        config = {
            "image": "app:latest",
            "command": "python app.py",
        }
        result = parse_service("api", config)

        assert result["command"] == ["python", "app.py"]

    def test_service_missing_image_raises(self):
        config = {"ports": ["80:80"]}
        with pytest.raises(ValueError, match="missing required 'image' field"):
            parse_service("web", config)

    def test_env_without_value(self):
        config = {
            "image": "app:latest",
            "environment": ["MY_VAR"],
        }
        result = parse_service("api", config)

        assert result["env"] == {"MY_VAR": ""}


class TestParseCompose:
    def test_parse_multiple_services(self):
        data = {
            "services": {
                "web": {"image": "nginx:latest", "ports": ["80:80"]},
                "api": {"image": "app:v1", "ports": ["8080:8080"]},
            }
        }
        services = parse_compose(data)

        assert len(services) == 2
        assert services[0]["name"] == "web"
        assert services[1]["name"] == "api"

    def test_empty_services(self):
        data = {"services": {}}
        services = parse_compose(data)
        assert services == []

    def test_invalid_service_config(self):
        data = {"services": {"web": "invalid"}}
        with pytest.raises(ValueError, match="invalid configuration"):
            parse_compose(data)


class TestLoadComposeFile:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_compose_file("/nonexistent/docker-compose.yml")

    def test_load_valid_file(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("services:\n  web:\n    image: nginx\n")
        data = load_compose_file(compose)
        assert "services" in data

    def test_missing_services_key(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        with pytest.raises(ValueError, match="missing 'services' key"):
            load_compose_file(compose)
