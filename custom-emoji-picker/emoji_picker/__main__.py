"""Command-line entry point."""

import sys

from . import __version__
from .app import run


def main() -> int:
    if "--version" in sys.argv[1:]:
        print("custom-emoji-picker {}".format(__version__))
        return 0
    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())

