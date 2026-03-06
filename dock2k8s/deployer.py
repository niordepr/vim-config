"""Deploy generated Kubernetes manifests to a cluster via kubectl."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def check_kubectl() -> bool:
    """Check if kubectl is available on the system."""
    return shutil.which("kubectl") is not None


def apply_manifests(yaml_content: str, namespace: str = "default") -> str:
    """Apply YAML manifests to the Kubernetes cluster using kubectl."""
    if not check_kubectl():
        raise RuntimeError(
            "kubectl is not installed or not in PATH. "
            "Please install kubectl first: https://kubernetes.io/docs/tasks/tools/"
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_content)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["kubectl", "apply", "-f", tmp_path, "-n", namespace],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"kubectl apply failed (exit code {result.returncode}):\n{result.stderr}"
            )

        return result.stdout
    finally:
        Path(tmp_path).unlink(missing_ok=True)
