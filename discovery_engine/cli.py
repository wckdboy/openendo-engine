"""CLI entrypoint: python -m discovery_engine"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .report import run


def main() -> None:
    ap = argparse.ArgumentParser(prog="discovery_engine", description="OpenEndo Discovery Engine (Stage 4)")
    ap.add_argument("--source", choices=("raw", "local"), help="data source (default: env OPENENDO_SOURCE or raw)")
    ap.add_argument("--path", help="local wckdboy/openendo path when --source local")
    ap.add_argument("--outdir", default="output", help="output directory (default: output/)")
    ap.add_argument("--no-tracing", action="store_true", help="disable LangSmith tracing for this run")
    args = ap.parse_args()

    s = Settings()
    if args.source:
        s.source = args.source
    if args.path:
        s.local_path = args.path
    if args.no_tracing:
        s.langsmith_api_key = ""

    run(s, Path(args.outdir))


if __name__ == "__main__":
    main()
