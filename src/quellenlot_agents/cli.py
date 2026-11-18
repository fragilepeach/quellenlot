"""Command-line entry point for a local Quellenlot model review."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError

from quellenlot_agents.config import load_config
from quellenlot_agents.models import CaseInput
from quellenlot_agents.workflow import run_review


def _parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""
    parser = argparse.ArgumentParser(description="Run an evidence-first Quellenlot model review.")
    parser.add_argument("--config", required=True, type=Path, help="TOML file with five models.")
    parser.add_argument("--input", required=True, type=Path, help="JSON case with source snapshots.")
    parser.add_argument("--output", required=True, type=Path, help="Path for the JSON report.")
    return parser


def main() -> None:
    """Validate inputs, run the review, and write the report JSON."""
    args = _parser().parse_args()
    try:
        config = load_config(args.config)
        case = CaseInput.model_validate_json(args.input.read_bytes())
        report = asyncio.run(run_review(case, config))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    except (OSError, ValueError, ValidationError) as exc:
        _parser().error(str(exc))
    if report.status == "failed":
        sys.exit(2)


if __name__ == "__main__":
    main()
