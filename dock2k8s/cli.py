"""Command-line interface for dock2k8s."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dock2k8s.converter import load_compose_file, parse_compose
from dock2k8s.deployer import apply_manifests
from dock2k8s.generator import generate_manifests, manifests_to_yaml


def cmd_generate(args: argparse.Namespace) -> int:
    """Handle the 'generate' subcommand."""
    try:
        data = load_compose_file(args.compose_file)
        services = parse_compose(data)
        manifests = generate_manifests(services, namespace=args.namespace)
        yaml_output = manifests_to_yaml(manifests)

        if args.output:
            Path(args.output).write_text(yaml_output, encoding="utf-8")
            print(f"Manifests written to {args.output}")
        else:
            print(yaml_output)

        return 0
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_deploy(args: argparse.Namespace) -> int:
    """Handle the 'deploy' subcommand."""
    try:
        data = load_compose_file(args.compose_file)
        services = parse_compose(data)
        manifests = generate_manifests(services, namespace=args.namespace)
        yaml_output = manifests_to_yaml(manifests)

        print(f"Deploying to namespace '{args.namespace}'...")
        output = apply_manifests(yaml_output, namespace=args.namespace)
        print(output)
        print("Deployment complete.")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="dock2k8s",
        description="Convert Docker Compose projects to Kubernetes manifests and deploy to K8S clusters",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate subcommand
    gen_parser = subparsers.add_parser(
        "generate", help="Generate Kubernetes manifests from a docker-compose file"
    )
    gen_parser.add_argument(
        "compose_file", help="Path to docker-compose.yml"
    )
    gen_parser.add_argument(
        "-o", "--output", help="Output file path (default: stdout)"
    )
    gen_parser.add_argument(
        "-n", "--namespace", default="default", help="Kubernetes namespace (default: default)"
    )

    # deploy subcommand
    dep_parser = subparsers.add_parser(
        "deploy", help="Deploy docker-compose services to a Kubernetes cluster"
    )
    dep_parser.add_argument(
        "compose_file", help="Path to docker-compose.yml"
    )
    dep_parser.add_argument(
        "-n", "--namespace", default="default", help="Kubernetes namespace (default: default)"
    )

    return parser


def main() -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        sys.exit(cmd_generate(args))
    elif args.command == "deploy":
        sys.exit(cmd_deploy(args))
