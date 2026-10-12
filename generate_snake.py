
import os
import json
import html
import datetime
import urllib.request
from pathlib import Path

# ==========================================
# CONFIGURATION
# ==========================================

USER = os.getenv("GITHUB_USER", "FurkanOnatt")
TOKEN = os.getenv("GITHUB_TOKEN", "")

CELL = 12
PITCH = 17
MARGIN = 15

START_LENGTH = 3
SECONDS_PER_MOVE = 0.16

BACKGROUND = "#0d1117"
EMPTY_COLOR = "#161b22"
HEAD_COLOR = "#22d3ee"
BODY_COLOR = "#8b5cf6"

FOOD_COLORS = [
    "#161b22",
    "#312e81",
    "#4338ca",
    "#7c3aed",
    "#a855f7"
]

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is missing")


# ==========================================
# FETCH GITHUB CONTRIBUTIONS
# ==========================================

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
    }).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "FurkanOnatt-Custom-Snake"
    }
)

with urllib.request.urlopen(
    request, timeout=30
) as response:
    result = json.load(response)

if result.get("errors"):
    raise RuntimeError(str(result["errors"]))

user_data = result.get("data", {}).get("user")

if not user_data:
    raise RuntimeError("GitHub user not found")

weeks = user_data[
    "contributionsCollection"
]["contributionCalendar"]["weeks"]

COLS = len(weeks)
ROWS = 7

values = {}

for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        date = datetime.date.fromisoformat(day["date"])
        y = (date.weekday() + 1) % 7

        values[(x + 1, y)] = day[
            "contributionCount"
        ]

foods = {
    pos for pos, count in values.items()
    if count > 0
}


# ==========================================
# SAFE BOARD
# ==========================================

# Extra column on the left for spawning.
# Extra row below for a safe return path.
#
# The width is kept even to construct a
# Hamiltonian cycle.

WIDTH = COLS + 1

if WIDTH % 2:
    WIDTH += 1

HEIGHT = 8

START = (0, 0)


# ==========================================
# COLLISION-FREE HAMILTONIAN CYCLE
# ==========================================

def build_safe_cycle(width, height):
    """
    Visit every board cell exactly once
    before returning to the starting cell.

    This prevents body collisions while
    allowing the snake to keep growing.
    """

    if width % 2 != 0:
        raise ValueError("Board width must be even")

    route = []

    # First row: left to right
    for x in range(width):
        route.append((x, 0))

    # Interior rows: alternating directions
    for y in range(1, height):
        if y % 2 == 1:
            xs = range(width - 1, 0, -1)
        else:
            xs = range(1, width)

        for x in xs:
            route.append((x, y))

    # Return using the reserved left column
    for y in range(height - 1, 0, -1):
        route.append((0, y))

    if len(route) != width * height:
        raise RuntimeError("Incomplete safe cycle")

    if len(set(route)) != len(route):
        raise RuntimeError("Cycle contains duplicates")

    for a, b in zip(
        route,
        route[1:] + route[:1]
    ):
        distance = (
            abs(a[0] - b[0]) +
            abs(a[1] - b[1])
        )

        if distance != 1:
            raise RuntimeError(
                "Non-adjacent cycle movement"
            )

    return route


cycle = build_safe_cycle(WIDTH, HEIGHT)

assert cycle[0] == START

cycle_index = {
    position: i
    for i, position in enumerate(cycle)
}

# Stop when the final contribution is eaten.
if foods:
    last_food_step = max(
        cycle_index[pos] for pos in foods
    )
else:
    last_food_step = 0

# Include a short pause at the end.
PAUSE_STEPS = 8

path = cycle[:last_food_step + 1]

# If no food exists, animate one full lap.
if not foods:
    path = cycle

if len(path) < 2:
    path = cycle[:2]


# ==========================================
# SNAKE SIMULATION
# ==========================================

def simulate():
    """
    A body segment follows its predecessor.

    Growth happens only when a new food
    cell is consumed.

    The Hamiltonian cycle ensures that
    the head never crosses the body.
    """

    eaten = set()
    frames = []
    food_eaten_at = {}

    cycle_size = len(cycle)

    for step, head in enumerate(path):

        if head in foods and head not in eaten:
            eaten.add(head)
            food_eaten_at[head] = step

        length = START_LENGTH + len(eaten)

        # Segment positions follow the cycle.
        body = [
            cycle[(step - j) % cycle_size]
            for j in range(length)
        ]

        # Validate collisions.
        if len(body) != len(set(body)):
            raise RuntimeError(
                f"Self collision at step {step}"
            )

        # Validate head movement.
        if step > 0:
            previous = path[step - 1]

            distance = (
                abs(previous[0] - head[0]) +
                abs(previous[1] - head[1])
            )

            if distance != 1:
                raise RuntimeError(
                    "Invalid head movement"
                )

        frames.append(body)

    if eaten != foods:
        raise RuntimeError(
            "Not all contributions were eaten"
        )

    return frames, food_eaten_at


frames, food_eaten_at = simulate()

# Hold the last frame briefly.
frames.extend([frames[-1]] * PAUSE_STEPS)

FRAME_COUNT = len(frames)
DURATION = FRAME_COUNT * SECONDS_PER_MOVE

MAX_SEGMENTS = max(
    len(body) for body in frames
)


# ==========================================
# SVG HELPERS
# ==========================================

def number(value):
    return f"{value:.6f}".rstrip("0").rstrip(".")


def pixel_position(position):
    x, y = position

    return (
        MARGIN + x * PITCH,
        MARGIN + y * PITCH
    )


def animate_values(values, attribute):
    """
    Discrete animation avoids visual
    diagonal interpolation through
    occupied body cells.
    """

    times = [
        number(i / FRAME_COUNT)
        for i in range(FRAME_COUNT + 1)
    ]

    values = list(values) + [values[-1]]

    return (
        f'<animate attributeName="{attribute}" '
        f'values="{";".join(map(str, values))}" '
        f'keyTimes="{";".join(times)}" '
        f'calcMode="discrete" '
        f'dur="{number(DURATION)}s" '
        f'repeatCount="indefinite"/>'
    )


# ==========================================
# SVG GENERATION
# ==========================================

SVG_WIDTH = (
    MARGIN * 2 +
    (WIDTH - 1) * PITCH +
    CELL
)

SVG_HEIGHT = (
    MARGIN * 2 +
    (HEIGHT - 1) * PITCH +
    CELL
)

svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{SVG_WIDTH}" '
    f'height="{SVG_HEIGHT}" '
    f'viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
    'role="img" '
    f'aria-label="{html.escape(USER, quote=True)} '
    'growing contribution snake">',
]

svg.append(
    f'<rect width="100%" height="100%" '
    f'fill="{BACKGROUND}"/>'
)


# ==========================================
# DRAW CONTRIBUTION GRID
# ==========================================

for y in range(ROWS):
    for x in range(1, COLS + 1):

        position = (x, y)
        count = values.get(position, 0)

        if count == 0:
            level = 0
        elif count == 1:
            level = 1
        elif count < 4:
            level = 2
        elif count < 8:
            level = 3
        else:
            level = 4

        color = FOOD_COLORS[level]
        px, py = pixel_position(position)

        svg.append(
            f'<rect x="{px}" y="{py}" '
            f'width="{CELL}" height="{CELL}" '
            f'rx="3" fill="{color}">'
        )

        if position in foods:
            eat_step = food_eaten_at[position]

            opacity_values = [
                "1" if i < eat_step else "0"
                for i in range(FRAME_COUNT)
            ]

            svg.append(
                animate_values(
                    opacity_values,
                    "opacity"
                )
            )

        svg.append("</rect>")


# ==========================================
# DRAW ANIMATED SNAKE
# ==========================================

for segment in range(
    MAX_SEGMENTS - 1, -1, -1
):

    is_head = segment == 0

    color = (
        HEAD_COLOR if is_head
        else BODY_COLOR
    )

    initial_visible = (
        segment < len(frames[0])
    )

    initial_position = (
        frames[0][segment]
        if initial_visible
        else (-10, -10)
    )

    px, py = pixel_position(initial_position)

    svg.append(
        f'<rect width="{CELL}" '
        f'height="{CELL}" '
        f'rx="4" fill="{color}" '
        f'transform="translate({px} {py})" '
        f'opacity="{int(initial_visible)}">'
    )

    positions = []
    opacity_values = []

    for body in frames:

        if segment < len(body):
            pos = body[segment]
            opacity_values.append("1")
        else:
            pos = (-10, -10)
            opacity_values.append("0")

        x, y = pixel_position(pos)
        positions.append(f"{x} {y}")

    times = [
        number(i / FRAME_COUNT)
        for i in range(FRAME_COUNT + 1)
    ]

    position_values = positions + [
        positions[-1]
    ]

    svg.append(
        '<animateTransform '
        'attributeName="transform" '
        'type="translate" '
        f'values="{";".join(position_values)}" '
        f'keyTimes="{";".join(times)}" '
        'calcMode="discrete" '
        f'dur="{number(DURATION)}s" '
        'repeatCount="indefinite"/>'
    )

    svg.append(
        animate_values(
            opacity_values,
            "opacity"
        )
    )

    svg.append("</rect>")


svg.append("</svg>")


# ==========================================
# SAVE SVG
# ==========================================

output_dir = Path("dist")
output_dir.mkdir(
    parents=True,
    exist_ok=True
)

output_file = (
    output_dir / "custom-snake.svg"
)

output_file.write_text(
    "\n".join(svg),
    encoding="utf-8"
)

print("=================================")
print("CUSTOM CONTRIBUTION SNAKE")
print("=================================")
print(f"User: {USER}")
print(f"Board: {WIDTH}x{HEIGHT}")
print(f"Contributions: {len(foods)}")
print(f"Consumed: {len(food_eaten_at)}")
print(f"Frames: {FRAME_COUNT}")
print(f"Max snake length: {MAX_SEGMENTS}")
print(f"Duration: {DURATION:.2f}s")
print("Collision check: PASSED")
print("All contributions eaten: YES")
print(f"Output: {output_file}")
