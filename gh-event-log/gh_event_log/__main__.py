from __future__ import annotations

import argparse
import logging
import sys
import threading

from . import config
from .collector import Collector
from .server import serve_forever


def main() -> int:
    ap = argparse.ArgumentParser(prog="gh-event-log", description="Log GitHub PR activity via gh and serve it read-only on the tailnet.")
    ap.add_argument("--config", help=f"config JSON (default {config.DEFAULT_PATH})")
    ap.add_argument("--once", action="store_true", help="run one poll and exit (no HTTP server)")
    ap.add_argument("--no-collector", action="store_true", help="serve only, do not poll GitHub")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    cfg = config.load(args.config)

    if args.once:
        Collector(cfg).run_forever(once=True)
        return 0

    stop = threading.Event()
    t = threading.Thread(target=serve_forever, args=(cfg, stop), name="http", daemon=True)
    t.start()
    if args.no_collector:
        t.join()
        return 0
    Collector(cfg).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
