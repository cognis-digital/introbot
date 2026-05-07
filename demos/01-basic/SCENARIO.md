# Demo 01 — Basic warm-intro path

## What this shows

A small bizdev scenario. Your team is **Alice** and **Bob**. You want a warm
introduction to **Dana Reyes**, a VP you have no direct line to.

The manifest (`contacts.json`) records who-knows-whom across the whole team's
combined network, with relationship `strength` in `(0, 1]` (1.0 = very warm)
and an optional `via` channel.

INTROBOT models this as an undirected weighted graph where stronger
relationships are cheaper to traverse (cost = `-log(strength)`), then runs a
multi-source Dijkstra from the whole team to find the **warmest** chain.

## Run it

```bash
python -m introbot path -m demos/01-basic/contacts.json -t "Dana Reyes"
```

JSON (for piping / CI):

```bash
python -m introbot path -m demos/01-basic/contacts.json -t "Dana Reyes" --format json
```

Rank the network's super-connectors:

```bash
python -m introbot connectors -m demos/01-basic/contacts.json --top 5
```

## Expected result

There are two routes to Dana:

- `Bob -> Frank -> Dana Reyes` via weak ties (strengths 0.3, 0.35).
- `Alice -> Carol -> Erin -> Dana Reyes` via strong ties (0.9, 0.85, 0.8).

Even though Bob's route is fewer hops, INTROBOT prefers the **warmer**
Alice route because its combined strength (`0.9 * 0.85 * 0.8 = 0.612`) beats
Bob's (`0.3 * 0.35 = 0.105`). The tool reports:

```
Warm path to Dana Reyes: 3 hop(s), warmth 0.61
  Alice  ->  Carol  ->  Erin  ->  Dana Reyes
```

The top connector is **Carol** (the hub linking several people).

Asking for a nonexistent target (e.g. `--target "Nobody"`) exits with status
`1`, which CI can gate on.
