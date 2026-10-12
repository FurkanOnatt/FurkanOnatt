
import os
import json
import random
import html
import datetime
import urllib.request
from pathlib import Path
from collections import deque

USER = os.getenv("GITHUB_USER", "FurkanOnatt")
TOKEN = os.getenv("GITHUB_TOKEN", "")

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is required")

# Visual settings
CELL = 12
PITCH = 17
MARGIN = 55
MOVE_TIME = 0.22
START_LENGTH = 3
MAX_ATTEMPTS = 20

HEAD = "#22d3ee"
BODY = "#8b5cf6"
EMPTY = "#161b22"
COLORS = [
    "#161b22", "#312e81", "#4338ca",
    "#7c3aed", "#a855f7"
]

# GitHub GraphQL
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
        "User-Agent": "CustomSnake"
    }
)

with urllib.request.urlopen(request, timeout=30) as r:
    data = json.load(r)

if data.get("errors"):
    raise RuntimeError(str(data["errors"]))

weeks = data["data"]["user"][
    "contributionsCollection"
]["contributionCalendar"]["weeks"]

COLS = len(weeks) + 1
ROWS = 7

counts = {}

for x, week in enumerate(weeks, start=1):
    for day in week["contributionDays"]:
        d = datetime.date.fromisoformat(day["date"])
        y = (d.weekday() + 1) % 7
        counts[(x, y)] = day["contributionCount"]

foods = {
    p for p, count in counts.items()
    if count > 0
}

rng = random.Random()

DIRECTIONS = [
    (1, 0), (-1, 0),
    (0, 1), (0, -1)
]


def neighbors(pos):
    x, y = pos
    directions = DIRECTIONS[:]
    rng.shuffle(directions)

    for dx, dy in directions:
        p = (x + dx, y + dy)
        if 0 <= p[0] < COLS and 0 <= p[1] < ROWS:
            yield p


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def find_route(body, target):
    """
    Search with the entire moving body as state.
    No movement through occupied body cells.
    """
    start = tuple(body)
    queue = deque([(start, [])])
    seen = {start}

    while queue:
        state, route = queue.popleft()
        head = state[0]

        if head == target:
            return route

        for nxt in neighbors(head):
            grows = nxt in foods and nxt not in eaten_now

            blocked = state if grows else state[:-1]

            if nxt in blocked:
                continue

            new_state = (
                (nxt,) + state
                if grows
                else (nxt,) + state[:-1]
            )

            if new_state in seen:
                continue

            seen.add(new_state)
            queue.append((new_state, route + [nxt]))

            # Prevent excessive memory usage.
            if len(seen) > 15000:
                return None

    return None


def plan():
    global eaten_now

    eaten_now = set()

    # Visible spawn at top-left, before the grid.
    body = [(0, 0), (-1, 0), (-2, 0)]
    frames = [list(body)]
    consumed_at = {}

    remaining = set(foods)

    while remaining:
        head = body[0]

        targets = sorted(
            remaining,
            key=lambda p: distance(head, p)
        )

        # Prefer nearby food, but vary target order.
        nearest = targets[:min(8, len(targets))]
        rng.shuffle(nearest)

        candidates = nearest + [
            p for p in targets if p not in nearest
        ]

        best_route = None

        for target in candidates:
            route = find_route(body, target)

            if route is None:
                continue

            if best_route is None or len(route) < len(best_route):
                best_route = route

            # A reasonably short safe route is enough.
            if len(route) <= distance(head, target) + 2:
                break

        if best_route is None:
            break

        for nxt in best_route:
            grows = nxt in remaining

            occupied = body if grows else body[:-1]

            if nxt in occupied:
                raise RuntimeError("Snake collision detected")

            body.insert(0, nxt)

            if grows:
                remaining.remove(nxt)
                eaten_now.add(nxt)
                consumed_at[nxt] = len(frames)
            else:
                body.pop()

            if len(body) != len(set(body)):
                raise RuntimeError("Body overlap detected")

            frames.append(list(body))

    return frames, consumed_at, len(remaining)


# Try several random routes and keep the best one.
best = None

for attempt in range(MAX_ATTEMPTS):
    result = plan()

    if best is None or result[2] < best[2]:
        best = result

    if result[2] == 0:
        break

frames, consumed_at, remaining_count = best

print(f"Total food: {len(foods)}")
print(f"Eaten: {len(consumed_at)}")
print(f"Remaining: {remaining_count}")

# Hold the completed frame briefly.
frames += [frames[-1]] * 6

N = len(frames)
DURATION = N * MOVE_TIME
MAX_BODY = max(len(f) for f in frames)

W = MARGIN * 2 + COLS * PITCH
H = MARGIN * 2 + ROWS * PITCH


def fmt(n):
    return f"{n:.6f}".rstrip("0").rstrip(".")


def point(p):
    return (
        MARGIN + p[0] * PITCH,
        MARGIN + p[1] * PITCH
    )


def animation_times():
    return ";".join(
        fmt(i / N) for i in range(N + 1)
    )


TIMES = animation_times()
DUR = fmt(DURATION) + "s"


def animate(attribute, values, mode="discrete"):
    values = list(values)
    values.append(values[-1])

    return (
        f'<animate attributeName="{attribute}" '
        f'values="{";".join(map(str, values))}" '
        f'keyTimes="{TIMES}" '
        f'calcMode="{mode}" '
        f'dur="{DUR}" '
        f'repeatCount="indefinite"/>'
    )


svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" '
    f'aria-label="{html.escape(USER, quote=True)} Snake">',
    '<rect width="100%" height="100%" fill="#0d1117"/>'
]

# Contribution cells
for x in range(1, COLS):
    for y in range(ROWS):
        p = (x, y)
        count = counts.get(p, 0)

        level = (
            0 if count == 0 else
            1 if count == 1 else
            2 if count < 4 else
            3 if count < 8 else 4
        )

        px, py = point(p)

        svg.append(
            f'<rect x="{px}" y="{py}" '
            f'width="{CELL}" height="{CELL}" '
            f'rx="3" fill="{COLORS[level]}">'
        )

        if p in consumed_at:
            step = consumed_at[p]
            opacity = [
                "1" if i < step else "0"
                for i in range(N)
            ]
            svg.append(animate("opacity", opacity))

        svg.append("</rect>")


# Snake segments
for segment in reversed(range(MAX_BODY)):
    color = HEAD if segment == 0 else BODY

    positions = []
    visibility = []

    last_position = frames[0][-1]

    for frame in frames:
        if segment < len(frame):
            pos = frame[segment]
            last_position = pos
            visibility.append("1")
        else:
            pos = last_position
            visibility.append("0")

        positions.append(point(pos))

    initial = positions[0]

    svg.append(
        f'<rect width="{CELL}" height="{CELL}" '
        f'rx="4" fill="{color}" '
        f'opacity="{visibility[0]}" '
        f'transform="translate({initial[0]} {initial[1]})">'
    )

    # Interpolate between adjacent positions.
    values = [
        f"{x} {y}" for x, y in positions
    ]
    values.append(values[-1])

    svg.append(
        '<animateTransform '
        'attributeName="transform" '
        'type="translate" '
        f'values="{";".join(values)}" '
        f'keyTimes="{TIMES}" '
        'calcMode="linear" '
        f'dur="{DUR}" '
        'repeatCount="indefinite"/>'
    )

    svg.append(animate("opacity", visibility))
    svg.append("</rect>")


svg.append("</svg>")

Path("dist").mkdir(exist_ok=True)

Path("dist/custom-snake.svg").write_text(
    "\n".join(svg),
    encoding="utf-8"
)

print(f"Frames: {N}")
print(f"Duration: {DURATION:.1f}s")
print("Generated: dist/custom-snake.svg")

if remaining_count:
    print(
        "WARNING: No safe route found for all food. "
        "Animation will restart after the last safe frame."
    )
