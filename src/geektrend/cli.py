"""Command-line interface for collecting GitHub Trending snapshots."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from geektrend.collector import CollectionError, collect


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect a GitHub Trending snapshot.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("."),
        help="directory under which the data path is created (default: current directory)",
    )
    return parser


def _failure_detail(error: CollectionError) -> str:
    cause = error.__cause__
    if cause is None or not str(cause):
        return str(error)
    return f"{error}: {cause}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run one collection, returning a process-compatible exit status."""
    arguments = _parser().parse_args(argv)
    try:
        relative_path = collect(arguments.output_root)
    except CollectionError as error:
        print(f"collection failed: {_failure_detail(error)}", file=sys.stderr)
        return 1

    print(relative_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
