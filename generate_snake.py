"""A collision-free, organically winding GitHub contribution snake.

Only Python's standard library is needed. GitHub Actions must supply
GITHUB_TOKEN; output is dist/custom-snake.svg.
"""
import datetime
import html
import json
import os
import random
import urllib.request
from pathlib import Path

USER = os.getenv("GITHUB_USER", "FurkanOnatt")
TOKEN = os.getenv("GITHUB_TOKEN", "")
SEED = os.getenv("SNAKE_SEED")  # Optional: repeatable testing
RNG = random.Random(int(SEED)) if SEED is not None else random.Random()

CELL = 12
PITCH = 17
PAD = 20
SECONDS_PER_CELL = 0.13   # Smooth, continuous travel between cells
START_LENGTH = 3
HEAD_COLOR = "#22d3ee"
BODY_COLOR = "#8b5cf6"
DOT_COLORS = ["#161b22", "#312e81", "#4338ca", "#7c3aed", "#a855f7"]


def get_contributions():
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing from custom-snake.yml")
    query = """query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": USER}}).encode(),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
            "User-Agent": "FurkanOnatt-Readme-Snake",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(str(result["errors"]))
    user = (result.get("data") or {}).get("user")
    if not user:
        raise RuntimeError("GitHub user not found")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    counts = {}
    for x, week in enumerate(weeks, 1):
        for day in week["contributionDays"]:
            date = datetime.date.fromisoformat(day["date"])
            weekday = (date.weekday() + 1) % 7  # Sun = 0
            counts[(x, weekday)] = day["contributionCount"]
    return len(weeks), counts


def make_random_cycle(width, height, rng):
    """Produce a randomized Hamiltonian cycle, *not* a row-sweep.

    Build a random spanning tree on the half-resolution grid. Every
    coarse square has a 2x2 mini-cycle. Merge neighboring mini-cycles
    along spanning-tree edges. This creates one loop that visits every
    fine cell once, irrespective of snake length. No dead ends.
    """
    if width % 2 or height % 2:
        raise ValueError("Board dimensions must both be even")
    coarse_w, coarse_h = width // 2, height // 2
    graph = { (x, y): set() for y in range(height) for x in range(width) }

    def edge(a, b, add=True):
        if add:
            graph[a].add(b)
            graph[b].add(a)
        else:
            graph[a].remove(b)
            graph[b].remove(a)

    for cy in range(coarse_h):
        for cx in range(coarse_w):
            x, y = cx * 2, cy * 2
            a, b = (x, y), (x + 1, y)
            c, d = (x + 1, y + 1), (x, y + 1)
            for p, q in [(a, b), (b, c), (c, d), (d, a)]:
                edge(p, q)

    # Randomized depth-first spanning tree (nonuniform organic bends).
    origin = (0, 0)
    visited = {origin}
    stack = [origin]
    tree_edges = []
    while stack:
        cx, cy = stack[-1]
        options = [
            (cx + dx, cy + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= cx + dx < coarse_w
            and 0 <= cy + dy < coarse_h
            and (cx + dx, cy + dy) not in visited
        ]
        if not options:
            stack.pop()
            continue
        nxt = rng.choice(options)
        tree_edges.append(((cx, cy), nxt))
        visited.add(nxt)
        stack.append(nxt)

    for (ax, ay), (bx, by) in tree_edges:
        if ax != bx:  # Horizontally adjacent 2x2 blocks
            left = min(ax, bx) * 2
            y = ay * 2
            ltop = (left + 1, y)
            lbottom = (left + 1, y + 1)
            rtop = (left + 2, y)
            rbottom = (left + 2, y + 1)
            edge(ltop, lbottom, False)
            edge(rtop, rbottom, False)
            edge(ltop, rtop)
            edge(lbottom, rbottom)
        else:  # Vertically adjacent 2x2 blocks
            x = ax * 2
            top = min(ay, by) * 2
            tl = (x, top + 1)
            tr = (x + 1, top + 1)
            bl = (x, top + 2)
            br = (x + 1, top + 2)
            edge(tl, tr, False)
            edge(bl, br, False)
            edge(tl, bl)
            edge(tr, br)

    assert all(len(neighbors) == 2 for neighbors in graph.values())

    # Start in the visible empty cell at the top left, facing right.
    start = (0, 0)
    previous = start
    current = (1, 0)
    route = [start]
    while current != start:
        if current in route:
            raise RuntimeError("Generated route contains a premature loop")
        route.append(current)
        a, b = tuple(graph[current])
        following = b if a == previous else a
        previous, current = current, following

    if len(route) != width * height or len(set(route)) != len(route):
        raise RuntimeError("Route did not cover every grid cell")
    for a, b in zip(route, route[1:] + route[:1]):
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise RuntimeError("Route contains a non-adjacent move")
    return route


def format_number(number):
    return ("%.6f" % number).rstrip("0").rstrip(".")


def create_svg(week_count, counts):
    # Extra column is the spawn zone; extra bottom row is safe space.
    width = week_count + 1
    if width % 2:
        width += 1
    height = 8
    route = make_random_cycle(width, height, RNG)
    N = len(route)
    food = {pos for pos, count in counts.items() if count > 0}
    if (0, 0) in food or not food.issubset(route):
        raise RuntimeError("Contribution cells are outside the board")
    if START_LENGTH + len(food) > N:
        raise RuntimeError("The snake would be longer than its safe route")
    positions = {p: i for i, p in enumerate(route)}
    # All foods are visited before the *complete* SVG animation resets.
    assert len(set(positions)) == N
    assert all(0 < positions[p] < N for p in food)

    duration = N * SECONDS_PER_CELL
    distance = N * PITCH
    color_levels = DOT_COLORS
    svg_width = PAD * 2 + (width - 1) * PITCH + CELL
    svg_height = PAD * 2 + (height - 1) * PITCH + CELL
    center = lambda p: (PAD + p[0] * PITCH + CELL / 2,
                        PAD + p[1] * PITCH + CELL / 2)
    coords = [center(p) for p in route]
    # Explicit return to the starting cell to close the animation.
    path = "M " + " L ".join(
        f"{format_number(x)} {format_number(y)}" for x, y in coords
    ) + " Z"
    # N+1 timeline positions, one per cell transition.
    key_times = ";".join(format_number(i / N) for i in range(N + 1))
    eaten_count = 0
    body_lengths = []
    offsets = []
    for i in range(N + 1):
        if i and route[i % N] in food:
            eaten_count += 1
        # At N the position is the spawn point; do not recount it.
        length_px = (START_LENGTH - 1 + eaten_count) * PITCH
        body_lengths.append(length_px)
        offsets.append(length_px - i * PITCH)
    assert eaten_count == len(food)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" '
        f'height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" '
        f'role="img" aria-label="{html.escape(USER, quote=True)} contribution snake">',
        '<rect width="100%" height="100%" fill="#0d1117"/>',
    ]
    for y in range(7):
        for x in range(1, week_count + 1):
            pos = (x, y)
            count = counts.get(pos, 0)
            level = 0 if count == 0 else 1 if count == 1 else 2 if count < 4 else 3 if count < 8 else 4
            px = PAD + x * PITCH
            py = PAD + y * PITCH
            svg.append(
                f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" '
                f'rx="3" fill="{color_levels[level]}">'
            )
            if count > 0:
                at = positions[pos] / N
                svg.append(
                    f'<animate attributeName="opacity" values="1;0;0" '
                    f'keyTimes="0;{format_number(at)};1" '
                    f'calcMode="discrete" dur="{format_number(duration)}s" '
                    f'repeatCount="indefinite"/>'
                )
            svg.append('</rect>')

    # Just ONE moving snake body rather than hundreds of animated squares.
    svg.append(
        f'<path d="{path}" fill="none" stroke="{BODY_COLOR}" '
        f'stroke-width="{CELL - 2}" stroke-linecap="round" '
        f'stroke-linejoin="round" '
        f'stroke-dasharray="{body_lengths[0]} {distance - body_lengths[0]}" '
        f'stroke-dashoffset="{offsets[0]}">'
    )
    dasharrays = [f"{value} {distance - value}" for value in body_lengths]
    svg.append(
        f'<animate attributeName="stroke-dasharray" '
        f'values="{";".join(dasharrays)}" keyTimes="{key_times}" '
        f'calcMode="linear" dur="{format_number(duration)}s" '
        f'repeatCount="indefinite"/>'
    )
    svg.append(
        f'<animate attributeName="stroke-dashoffset" '
        f'values="{";".join(str(v) for v in offsets)}" '
        f'keyTimes="{key_times}" calcMode="linear" '
        f'dur="{format_number(duration)}s" repeatCount="indefinite"/>'
    )
    svg.append('</path>')

    # Smooth, constant-speed head; no giant per-frame animation lists.
    svg.append(
        f'<circle cx="0" cy="0" r="{(CELL - 1)/2}" fill="{HEAD_COLOR}">'
        f'<animateMotion path="{path}" dur="{format_number(duration)}s" '
        f'calcMode="paced" repeatCount="indefinite"/>'
        '</circle>'
    )
    svg.append('</svg>')
    Path('dist').mkdir(parents=True, exist_ok=True)
    target = Path('dist/custom-snake.svg')
    target.write_text('\n'.join(svg), encoding='utf-8')
    print('Route: randomized collision-free loop')
    print('Start: visible top-left; route covers all cells')
    print(f'Food collected: {len(food)}/{len(food)}')
    print(f'Route: {N} steps; animation: {duration:.1f}s')
    print(f'SVG: {target} ({target.stat().st_size/1024:.1f} KB)')
    return route


def main():
    week_count, counts = get_contributions()
    create_svg(week_count, counts)


if __name__ == '__main__':
    main()
