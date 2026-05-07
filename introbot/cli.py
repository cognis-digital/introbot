"""Command-line interface for INTROBOT.

Examples:
  # Warmest intro path to a target
  introbot path --manifest contacts.json --target "Dana Reyes"

  # Same, as JSON for piping/CI
  introbot path -m contacts.json -t "Dana Reyes" --format json

  # Restrict sources to specific teammates
  introbot path -m contacts.csv -t "Dana Reyes" --source Alice --source Bob

  # List the network's super-connectors
  introbot connectors -m contacts.json --top 10

Exit status:
  0  a path (or connectors) was found
  1  no warm path to the target exists  (useful as a CI gate)
  2  bad usage / malformed manifest
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import build_graph, find_intro_path, load_manifest, rank_connectors


def _read_manifest(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _format_path_table(path) -> str:
    lines = []
    lines.append(
        f"Warm path to {path.target}: {path.hops} hop(s), "
        f"warmth {path.warmth:.2f}"
    )
    if not path.steps:
        lines.append(f"  {path.target} is already on your team.")
        return "\n".join(lines)
    lines.append("  " + "  ->  ".join(path.nodes))
    lines.append("")
    lines.append(f"  {'STEP':<5}{'INTRODUCER':<20}{'INTRODUCEE':<20}"
                 f"{'STRENGTH':<10}VIA")
    for i, step in enumerate(path.steps, 1):
        via = step.via or "-"
        lines.append(
            f"  {i:<5}{step.introducer:<20}{step.introducee:<20}"
            f"{step.strength:<10.2f}{via}"
        )
    return "\n".join(lines)


def _format_connectors_table(rows) -> str:
    if not rows:
        return "No connectors found."
    lines = [f"  {'CONNECTOR':<24}DEGREE"]
    for name, deg in rows:
        lines.append(f"  {name:<24}{deg}")
    return "\n".join(lines)


def _cmd_path(args) -> int:
    try:
        text = _read_manifest(args.manifest)
        team, edges = load_manifest(text)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    graph = build_graph(team, edges)
    sources = args.source if args.source else None
    if sources is None and not graph.team:
        print(
            "error: manifest has no 'team' — specify --source NAME",
            file=sys.stderr,
        )
        return 2
    try:
        path = find_intro_path(graph, args.target, sources)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if path is None:
        if args.format == "json":
            print(json.dumps({"target": args.target, "path": None,
                              "found": False}))
        else:
            print(f"No warm path to {args.target!r} found.", file=sys.stderr)
        return 1

    if args.format == "json":
        out = path.to_dict()
        out["found"] = True
        print(json.dumps(out, indent=2))
    else:
        print(_format_path_table(path))
    return 0


def _cmd_connectors(args) -> int:
    try:
        text = _read_manifest(args.manifest)
        team, edges = load_manifest(text)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    graph = build_graph(team, edges)
    rows = rank_connectors(graph, top=args.top)
    if args.format == "json":
        print(json.dumps(
            {"connectors": [{"name": n, "degree": d} for n, d in rows]},
            indent=2,
        ))
    else:
        print(_format_connectors_table(rows))
    return 0 if rows else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=(
            "Find the warmest intro path through your team's combined "
            "network graph."
        ),
        epilog=(
            "examples:\n"
            "  introbot path -m contacts.json -t 'Dana Reyes'\n"
            "  introbot path -m contacts.csv -t 'Dana Reyes' --format json\n"
            "  introbot connectors -m contacts.json --top 10\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version",
        version=f"{TOOL_NAME} {TOOL_VERSION}",
    )
    sub = parser.add_subparsers(dest="command")

    p_path = sub.add_parser(
        "path",
        help="find the warmest intro path to a target person",
        description="Compute the shortest warm-intro path from your team "
                    "to a target.",
    )
    p_path.add_argument(
        "-m", "--manifest", required=True,
        help="path to contacts manifest (JSON or CSV); '-' for stdin",
    )
    p_path.add_argument(
        "-t", "--target", required=True,
        help="name of the person you want a warm intro to",
    )
    p_path.add_argument(
        "-s", "--source", action="append", default=[],
        help="override team source(s); repeatable. Defaults to manifest team",
    )
    p_path.add_argument(
        "--format", choices=("table", "json"), default="table",
        help="output format (default: table)",
    )
    p_path.set_defaults(func=_cmd_path)

    p_conn = sub.add_parser(
        "connectors",
        help="rank the network's super-connectors by degree",
        description="List the most-connected non-team people — useful hubs.",
    )
    p_conn.add_argument(
        "-m", "--manifest", required=True,
        help="path to contacts manifest (JSON or CSV); '-' for stdin",
    )
    p_conn.add_argument(
        "--top", type=int, default=5,
        help="how many connectors to show (default: 5)",
    )
    p_conn.add_argument(
        "--format", choices=("table", "json"), default="table",
        help="output format (default: table)",
    )
    p_conn.set_defaults(func=_cmd_connectors)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
