
import os
import json
import html
import random
import datetime
import urllib.request
from pathlib import Path

USER = os.getenv("GITHUB_USER", "FurkanOnatt")
TOKEN = os.getenv("GITHUB_TOKEN", "")

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is required")

# Animation settings
CELL = 12
PITCH = 17
MARGIN = 18
START_LENGTH = 3
ROUTE_VARIATIONS = 3
SECONDS_PER_MOVE = 0.075

# Get GitHub contribution data
query = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps({
        "query": query,
        "variables": {"login": USER}
    }).encode(),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "custom-growing-snake"
    }
)

with urllib.request.urlopen(request, timeout=30) as response:
    result = json.load(response)

if result.get("errors"):
    raise RuntimeError(str(result["errors"]))

weeks = result["data"]["user"]["contributionsCollection"][
    "contributionCalendar"
]["weeks"]

COLS = len(weeks)
ROWS = 7

values = {}

for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        date = datetime.date.fromisoformat(day["date"])
        y = (date.weekday() + 1) % 7
        values[(x, y)] = day["contributionCount"]

foods = {pos for pos, count in values.items() if count > 0}

rng = random.Random()

def direct_route(start, target):
    """Move toward the target without sweeping the whole grid."""
    x, y = start
    tx, ty = target
    route = []

    # Randomly choose horizontal-first or vertical-first.
    axes = ["x", "y"]
    rng.shuffle(axes)

    for axis in axes:
        if axis == "x":
            while x != tx:
                x += 1 if tx > x else -1
                route.append((x, y))
        else:
            while y != ty:
                y += 1 if ty > y else -1
                route.append((x, y))

    return route

def create_cycle():
    if not foods:
        return [(0, 0)], {}, (0, 0)

    # Start from a random occupied contribution square.
    start = rng.choice(tuple(sorted(foods)))
    remaining = set(foods)
    remaining.remove(start)

    path = [start]
    eaten = {start: 0}

    while remaining:
        current = path[-1]

        # Choose randomly among nearby remaining targets.
        ranked = sorted(
            remaining,
            key=lambda p: (
                abs(p[0] - current[0]) +
                abs(p[1] - current[1])
            )
        )

        candidates = ranked[:min(6, len(ranked))]
        target = rng.choice(candidates)

        route = direct_route(current, target)

        for position in route:
            path.append(position)

            # Any food crossed is eaten immediately.
            if position in remaining:
                remaining.remove(position)
                eaten[position] = len(path) - 1

    return path, eaten, start

def fmt(value):
    return f"{value:.5f}".rstrip("0").rstrip(".")

# Generate several different animation cycles.
cycles = [create_cycle() for _ in range(ROUTE_VARIATIONS)]

total_moves = sum(max(1, len(c[0]) - 1) for c in cycles)
duration = max(12, total_moves * SECONDS_PER_MOVE)

width = MARGIN * 2 + (COLS - 1) * PITCH + CELL
height = MARGIN * 2 + (ROWS - 1) * PITCH + CELL

output = [
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}" '
    f'role="img" aria-label="Growing snake for '
    f'{html.escape(USER, quote=True)}">',
    "<style>"
]

# Timeline positions for all cycles.
timeline = []
food_events = {}
offset = 0

for cycle_index, (path, eaten, start) in enumerate(cycles):
    for step, position in enumerate(path):
        timeline.append((cycle_index, step, position))

    food_events[cycle_index] = eaten
    offset += len(path)

total_frames = len(timeline)
denominator = max(1, total_frames)

# Build growing snake bodies.
bodies = []
current_body = []
current_cycle = -1
consumed = set()

for cycle_index, step, position in timeline:
    if cycle_index != current_cycle:
        current_cycle = cycle_index
        consumed = set()
        current_body = [position] * START_LENGTH

    else:
        current_body.insert(0, position)

        if position in foods and position not in consumed:
            consumed.add(position)
        else:
            current_body.pop()

    if step == 0 and position in foods:
        consumed.add(position)

    bodies.append(list(current_body))

max_segments = max(len(body) for body in bodies)

# Animate each segment smoothly.
for segment in range(max_segments):
    keyframes = []

    for i, body in enumerate(bodies):
        pct = 100 * i / denominator

        if segment < len(body):
            x, y = body[segment]
            opacity = 1
        else:
            x, y = -3, -3
            opacity = 0

        keyframes.append(
            f'{fmt(pct)}%{{'
            f'transform:translate('
            f'{MARGIN + x * PITCH}px,'
            f'{MARGIN + y * PITCH}px);'
            f'opacity:{opacity}}}'
        )

    # Hold the final frame until the loop restarts.
    keyframes.append(
        f'100%{{'
        f'transform:translate('
        f'{MARGIN + bodies[-1][min(segment, len(bodies[-1])-1)][0] * PITCH}px,'
        f'{MARGIN + bodies[-1][min(segment, len(bodies[-1])-1)][1] * PITCH}px);'
        f'opacity:{int(segment < len(bodies[-1]))}}}'
    )

    output.append(
        f'@keyframes snake_{segment}{{'
        + "".join(keyframes)
        + "}"
    )

# Food visibility: disappear when eaten, reset only
# at the beginning of the next complete cycle.
for pos in sorted(foods):
    x, y = pos
    keyframes = []

    offset = 0
    for cycle_index, (path, eaten, start) in enumerate(cycles):
        start_pct = 100 * offset / denominator
        eat_step = eaten.get(pos)
        eat_pct = 100 * (offset + eat_step) / denominator

        keyframes.append(
            f'{fmt(start_pct)}%{{opacity:1}}'
        )
        keyframes.append(
            f'{fmt(max(start_pct, eat_pct - 0.00001))}%'
            '{opacity:1}'
        )
        keyframes.append(
            f'{fmt(eat_pct)}%{{opacity:0}}'
        )

        offset += len(path)

    keyframes.append("100%{opacity:0}")

    output.append(
        f'@keyframes food_{x}_{y}{{'
        + "".join(keyframes)
        + "}"
    )

output.append("</style>")

# Draw contribution grid.
for x in range(COLS):
    for y in range(ROWS):
        count = values.get((x, y), 0)

        if count == 0:
            color = "#161b22"
        elif count == 1:
            color = "#312e81"
        elif count < 4:
            color = "#4338ca"
        elif count < 8:
            color = "#7c3aed"
        else:
            color = "#a855f7"

        style = ""

        if count:
            style = (
                f' style="animation:food_{x}_{y} '
                f'{fmt(duration)}s steps(1,end) infinite"'
            )

        output.append(
            f'<rect x="{MARGIN + x * PITCH}" '
            f'y="{MARGIN + y * PITCH}" '
            f'width="{CELL}" height="{CELL}" '
            f'rx="3" fill="{color}"{style}/>'
        )

# Draw snake body, then head.
for segment in range(max_segments - 1, -1, -1):
    color = "#22d3ee" if segment == 0 else "#8b5cf6"

    output.append(
        f'<rect width="{CELL}" height="{CELL}" '
        f'rx="4" fill="{color}" '
        f'style="animation:snake_{segment} '
        f'{fmt(duration)}s linear infinite"/>'
    )

output.append("</svg>")

Path("dist").mkdir(exist_ok=True)

Path("dist/custom-snake.svg").write_text(
    "\n".join(output),
    encoding="utf-8"
)

print(f"Generated {len(foods)} contribution squares")
print(f"Random cycles: {ROUTE_VARIATIONS}")
print(f"Total frames: {total_frames}")
print(f"Duration: {duration:.1f}s")
print("Output: dist/custom-snake.svg")
