"""CLI entrypoint: python -m discovery_engine [run]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .report import run


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="discovery_engine", description="OpenEndo Discovery Engine (Stage 4)")
    ap.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run",),
        help="subcommand (default: run)",
    )
    ap.add_argument("--source", choices=("raw", "local"), help="data source (default: env OPENENDO_SOURCE or raw)")
    ap.add_argument("--path", help="local wckdboy/openendo path when --source local")
    ap.add_argument("--outdir", default="output", help="output directory (default: output/)")
    ap.add_argument("--no-tracing", action="store_true", help="disable LangSmith tracing for this run")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="skip LLM (and remote fetch) and write a schema-valid skeleton findings file",
    )
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    s = Settings()
    if args.source:
        s.source = args.source
    if args.path:
        s.local_path = args.path
    if args.no_tracing or args.dry_run:
        s.langsmith_api_key = ""

    run(s, Path(args.outdir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
