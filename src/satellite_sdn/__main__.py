"""Entry point for running the SDN controller as a standalone service."""

import logging
import os
import signal
import sys

from .controller import SDNController, run_controller_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _controller_kwargs_from_env() -> dict[str, float]:
    """Build SDNController keyword arguments from environment variables."""
    kwargs: dict[str, float] = {}
    if "HEARTBEAT_TIMEOUT_S" in os.environ:
        kwargs["heartbeat_timeout_s"] = float(os.environ["HEARTBEAT_TIMEOUT_S"])
    if "LOAD_THRESHOLD" in os.environ:
        kwargs["load_threshold"] = float(os.environ["LOAD_THRESHOLD"])
    if "RECONCILE_INTERVAL_S" in os.environ:
        kwargs["reconcile_interval_s"] = float(os.environ["RECONCILE_INTERVAL_S"])
    return kwargs


def main() -> None:
    controller = SDNController(**_controller_kwargs_from_env())
    controller.start()

    def _shutdown(signum, frame):  # type: ignore[no-untyped-def]
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run_controller_server(controller)


if __name__ == "__main__":
    main()
