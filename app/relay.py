"""Outbox relay process: python -m app.relay"""

import signal
import threading

from .config import Config, ConfigError
from .extensions import db
from .logging_setup import setup_logging
from .services.outbox_service import KaryaClient, OutboxRelay


def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    if not config.karya_url:
        raise ConfigError("Missing required environment variable: KARYA_URL")
    db.init_app(config.database_url)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    OutboxRelay(KaryaClient(config.karya_url)).run(stop)


if __name__ == "__main__":
    main()
