"""Entry point for running the SDN controller as a standalone service."""

import logging
import signal
import sys
import threading

from .controller import SDNController, run_controller_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    controller = SDNController()
    controller.start()

    def _shutdown(signum, frame):  # type: ignore[no-untyped-def]
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run_controller_server(controller)


if __name__ == "__main__":
    main()
