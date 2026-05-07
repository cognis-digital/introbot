"""Core engine for INTROBOT.

The manifest describes a network of people and the relationships between them.
We model it as an undirected, weighted graph. Edge *weight* is the "cost" of
traversing a relationship: stronger relationships are cheaper, so a Dijkstra
shortest-path search naturally prefers warm, high-strength chains.

Manifest format (JSON):
{
  "team":     ["Alice", "Bob"],            # your side — path sources
  "contacts": [
    {"from": "Alice", "to": "Carol", "strength": 0.9, "via": "linkedin"},
    {"from": "Carol", "to": "Dave",  "strength": 0.4}
  ]
}

"strength" is in (0, 1]; higher = warmer. Cost of an edge = -log(strength),
so multiplying strengths along a path == minimizing summed cost. Missing
strength defaults to 0.5. "via" is an optional channel label.

A CSV manifest is also accepted: columns from,to,strength,via with an optional
first data section. (See load_manifest.)
"""

from __future__ import annotations

import csv
import heapq
import io
import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


MIN_STRENGTH = 1e-6
DEFAULT_STRENGTH = 0.5


@dataclass(frozen=True)
class Edge:
    """An undirected relationship between two people."""

    a: str
    b: str
    strength: float
    via: Optional[str] = None

    @property
    def cost(self) -> float:
        s = max(MIN_STRENGTH, min(1.0, self.strength))
        return -math.log(s)


@dataclass
class Graph:
    """Undirected weighted contact graph."""

    team: List[str] = field(default_factory=list)
    # adjacency: person -> list of (neighbor, edge)
    adj: Dict[str, List[Tuple[str, Edge]]] = field(default_factory=dict)
    people: set = field(default_factory=set)

    def add_edge(self, edge: Edge) -> None:
        if edge.a == edge.b:
            return
        self.people.add(edge.a)
        self.people.add(edge.b)
        self.adj.setdefault(edge.a, []).append((edge.b, edge))
        self.adj.setdefault(edge.b, []).append((edge.a, edge))

    def neighbors(self, person: str) -> List[Tuple[str, Edge]]:
        return self.adj.get(person, [])

    def degree(self, person: str) -> int:
        return len(self.adj.get(person, []))


@dataclass
class PathStep:
    """One hop along an intro path."""

    introducer: str
    introducee: str
    strength: float
    via: Optional[str]

    def to_dict(self) -> dict:
        return {
            "introducer": self.introducer,
            "introducee": self.introducee,
            "strength": round(self.strength, 4),
            "via": self.via,
        }


@dataclass
class IntroPath:
    """A full warm-intro path from a team member to a target."""

    source: str
    target: str
    nodes: List[str]
    steps: List[PathStep]
    cost: float

    @property
    def hops(self) -> int:
        return len(self.steps)

    @property
    def warmth(self) -> float:
        """Product of strengths along the path == exp(-cost). 1.0 best."""
        return math.exp(-self.cost)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "hops": self.hops,
            "warmth": round(self.warmth, 4),
            "cost": round(self.cost, 4),
            "nodes": self.nodes,
            "steps": [s.to_dict() for s in self.steps],
        }


def _coerce_strength(value) -> float:
    if value is None or value == "":
        return DEFAULT_STRENGTH
    try:
        s = float(value)
    except (TypeError, ValueError):
        return DEFAULT_STRENGTH
    if s <= 0:
        return MIN_STRENGTH
    if s > 1:
        # tolerate 1-10 or 0-100 scales by normalizing common cases
        if s <= 10:
            return s / 10.0
        if s <= 100:
            return s / 100.0
        return 1.0
    return s


def load_manifest(text: str) -> Tuple[List[str], List[Edge]]:
    """Parse a manifest from JSON or CSV text. Returns (team, edges).

    Raises ValueError on malformed input.
    """
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return _load_json(text)
    return _load_csv(text)


def _load_json(text: str) -> Tuple[List[str], List[Edge]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON manifest must be an object with 'contacts'")
    team = [str(t).strip() for t in data.get("team", []) if str(t).strip()]
    raw_contacts = data.get("contacts")
    if raw_contacts is None:
        raise ValueError("JSON manifest missing 'contacts' list")
    if not isinstance(raw_contacts, list):
        raise ValueError("'contacts' must be a list")
    edges: List[Edge] = []
    for i, c in enumerate(raw_contacts):
        if not isinstance(c, dict):
            raise ValueError(f"contact #{i} is not an object")
        a = str(c.get("from", "")).strip()
        b = str(c.get("to", "")).strip()
        if not a or not b:
            raise ValueError(f"contact #{i} missing 'from'/'to'")
        via = c.get("via")
        via = str(via).strip() if via not in (None, "") else None
        edges.append(Edge(a, b, _coerce_strength(c.get("strength")), via))
    return team, edges


def _load_csv(text: str) -> Tuple[List[str], List[Edge]]:
    """CSV with header row including from,to and optional strength,via.

    Lines beginning with '#team:' (comma-separated names) declare the team.
    """
    team: List[str] = []
    body_lines: List[str] = []
    for line in text.splitlines():
        if line.strip().lower().startswith("#team:"):
            names = line.split(":", 1)[1]
            team = [n.strip() for n in names.split(",") if n.strip()]
            continue
        if line.strip().startswith("#"):
            continue
        body_lines.append(line)
    reader = csv.DictReader(io.StringIO("\n".join(body_lines)))
    if reader.fieldnames is None:
        raise ValueError("CSV manifest is empty")
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    if "from" not in cols or "to" not in cols:
        raise ValueError("CSV manifest must have 'from' and 'to' columns")
    edges: List[Edge] = []
    for i, row in enumerate(reader):
        a = str(row.get(cols["from"], "")).strip()
        b = str(row.get(cols["to"], "")).strip()
        if not a or not b:
            continue
        strength = row.get(cols["strength"]) if "strength" in cols else None
        via = row.get(cols["via"]) if "via" in cols else None
        via = via.strip() if via else None
        edges.append(Edge(a, b, _coerce_strength(strength), via or None))
    if not edges:
        raise ValueError("CSV manifest contained no valid contacts")
    return team, edges


def build_graph(team: List[str], edges: List[Edge]) -> Graph:
    g = Graph(team=list(team))
    for e in edges:
        g.add_edge(e)
    for member in team:
        g.people.add(member)
        g.adj.setdefault(member, [])
    return g


def _dijkstra(
    graph: Graph, sources: List[str], target: str
) -> Optional[Tuple[str, List[str], List[Edge], float]]:
    """Multi-source Dijkstra. Returns (chosen_source, nodes, edges, cost)."""
    if target not in graph.people:
        return None
    dist: Dict[str, float] = {}
    prev: Dict[str, Tuple[str, Edge]] = {}
    origin: Dict[str, str] = {}
    heap: List[Tuple[float, str]] = []
    for s in sources:
        if s in graph.people:
            dist[s] = 0.0
            origin[s] = s
            heapq.heappush(heap, (0.0, s))
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, math.inf):
            continue
        if node == target:
            break
        for neighbor, edge in graph.neighbors(node):
            nd = d + edge.cost
            if nd < dist.get(neighbor, math.inf):
                dist[neighbor] = nd
                prev[neighbor] = (node, edge)
                origin[neighbor] = origin[node]
                heapq.heappush(heap, (nd, neighbor))
    if target not in dist:
        return None
    nodes: List[str] = []
    used_edges: List[Edge] = []
    cur = target
    while cur in prev:
        nodes.append(cur)
        parent, edge = prev[cur]
        used_edges.append(edge)
        cur = parent
    nodes.append(cur)
    nodes.reverse()
    used_edges.reverse()
    return origin[target], nodes, used_edges, dist[target]


def find_intro_path(
    graph: Graph, target: str, sources: Optional[List[str]] = None
) -> Optional[IntroPath]:
    """Find the warmest (shortest-cost) path from the team to `target`.

    If `sources` is None, the graph's team is used. Returns None if no path
    exists or the target is unknown.
    """
    if sources is None:
        sources = graph.team
    sources = [s for s in sources if s]
    if not sources:
        raise ValueError("no team/source members specified")
    if target in sources:
        # Already on the team — trivial zero-hop path.
        return IntroPath(target, target, [target], [], 0.0)
    result = _dijkstra(graph, sources, target)
    if result is None:
        return None
    source, nodes, edges, cost = result
    steps: List[PathStep] = []
    for idx, edge in enumerate(edges):
        introducer = nodes[idx]
        introducee = nodes[idx + 1]
        steps.append(PathStep(introducer, introducee, edge.strength, edge.via))
    return IntroPath(source, target, nodes, steps, cost)


def rank_connectors(graph: Graph, top: int = 5) -> List[Tuple[str, int]]:
    """Return the most-connected non-team people (degree centrality).

    These are the network's super-connectors — useful intro hubs.
    """
    team_set = set(graph.team)
    scored = [
        (p, graph.degree(p))
        for p in graph.people
        if p not in team_set
    ]
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return scored[: max(0, top)]
