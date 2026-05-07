"""Smoke tests for INTROBOT. Pure stdlib, no network."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from introbot import (
    TOOL_NAME,
    TOOL_VERSION,
    build_graph,
    find_intro_path,
    load_manifest,
    rank_connectors,
)
from introbot.cli import main

DEMO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demos", "01-basic", "contacts.json",
)


def _load_demo_graph():
    with open(DEMO, "r", encoding="utf-8") as fh:
        team, edges = load_manifest(fh.read())
    return build_graph(team, edges)


def test_metadata():
    assert TOOL_NAME == "introbot"
    assert TOOL_VERSION.count(".") == 2


def test_prefers_warmer_path_over_fewer_hops():
    g = _load_demo_graph()
    path = find_intro_path(g, "Dana Reyes")
    assert path is not None
    # The warm 3-hop route via Alice/Carol/Erin should win over the
    # 2-hop weak route via Bob/Frank.
    assert path.nodes == ["Alice", "Carol", "Erin", "Dana Reyes"]
    assert path.hops == 3
    assert path.warmth == pytest.approx(0.9 * 0.85 * 0.8, abs=1e-3)
    # via labels preserved
    assert path.steps[0].via == "coworker"


def test_no_path_returns_none():
    g = _load_demo_graph()
    assert find_intro_path(g, "Someone Unknown") is None


def test_target_on_team_is_zero_hops():
    g = _load_demo_graph()
    path = find_intro_path(g, "Alice")
    assert path is not None
    assert path.hops == 0
    assert path.warmth == pytest.approx(1.0)


def test_source_override_changes_route():
    g = _load_demo_graph()
    # Forcing Bob as the only source: best warm route is still through
    # Carol (Bob->Carol->Erin->Dana = 0.4*0.85*0.8=0.272) which beats
    # Bob->Frank->Dana (0.105).
    path = find_intro_path(g, "Dana Reyes", sources=["Bob"])
    assert path is not None
    assert path.source == "Bob"
    assert path.nodes[0] == "Bob"
    assert path.nodes[-1] == "Dana Reyes"


def test_rank_connectors_excludes_team():
    g = _load_demo_graph()
    rows = rank_connectors(g, top=5)
    names = [n for n, _ in rows]
    assert "Alice" not in names and "Bob" not in names
    # Carol is the hub (connects Alice, Erin, Greg, Frank, Bob)
    assert rows[0][0] == "Carol"
    assert rows[0][1] >= 4


def test_csv_manifest_parsing():
    csv_text = (
        "#team: Alice\n"
        "from,to,strength,via\n"
        "Alice,Carol,0.9,coworker\n"
        "Carol,Dana,0.5,linkedin\n"
    )
    team, edges = load_manifest(csv_text)
    assert team == ["Alice"]
    g = build_graph(team, edges)
    path = find_intro_path(g, "Dana")
    assert path is not None
    assert path.nodes == ["Alice", "Carol", "Dana"]


def test_strength_scale_normalization():
    # a 0-10 style strength should be normalized into (0,1]
    team, edges = load_manifest(
        '{"team":["A"],"contacts":[{"from":"A","to":"B","strength":8}]}'
    )
    assert 0 < edges[0].strength <= 1


def test_malformed_manifest_raises():
    with pytest.raises(ValueError):
        load_manifest('{"no_contacts": true}')


def test_cli_json_found_exit_zero(capsys):
    rc = main(["path", "-m", DEMO, "-t", "Dana Reyes", "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["found"] is True
    assert out["target"] == "Dana Reyes"
    assert out["nodes"][0] == "Alice"


def test_cli_no_path_exit_one():
    rc = main(["path", "-m", DEMO, "-t", "Ghost", "--format", "json"])
    assert rc == 1


def test_cli_table_output(capsys):
    rc = main(["path", "-m", DEMO, "-t", "Dana Reyes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Warm path to Dana Reyes" in out
    assert "Alice" in out and "Carol" in out


def test_cli_connectors(capsys):
    rc = main(["connectors", "-m", DEMO, "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["connectors"][0]["name"] == "Carol"


def test_cli_no_command_returns_two():
    assert main([]) == 2
