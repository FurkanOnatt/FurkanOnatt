import datetime
import heapq
import html
import json
import os
import random
import urllib.request
from collections import deque
from pathlib import Path

# --- Settings ---
USER = os.getenv('GITHUB_USER', 'FurkanOnatt')
TOKEN = os.getenv('GITHUB_TOKEN', '')
MOVE_SECONDS = 0.18
CELL, GAP, PAD = 12, 17, 20
MAX_ATTEMPTS = 20
SEARCH_LIMIT = 30000
HEAD = '#22d3ee'
BODY = '#8b5cf6'
DOTS = ['#161b22', '#312e81', '#4338ca', '#7c3aed', '#a855f7']
DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


def load_contributions():
    if not TOKEN:
        raise RuntimeError('GITHUB_TOKEN missing in custom-snake.yml')
    query = '''query($login:String!){user(login:$login){
      contributionsCollection{contributionCalendar{weeks{
        contributionDays{date contributionCount}
      }}}}}'''
    payload = json.dumps({'query': query, 'variables': {'login': USER}}).encode()
    req = urllib.request.Request(
        'https://api.github.com/graphql', data=payload,
        headers={'Authorization': 'Bearer ' + TOKEN,
                 'Content-Type': 'application/json',
                 'User-Agent': 'FurkanOnatt-README-Snake'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError(str(result['errors']))
    user = (result.get('data') or {}).get('user')
    if not user:
        raise RuntimeError('GitHub user was not found')
    weeks = user['contributionsCollection']['contributionCalendar']['weeks']
    counts = {}
    for x, week in enumerate(weeks, 1):
        for d in week['contributionDays']:
            weekday = (datetime.date.fromisoformat(d['date']).weekday() + 1) % 7
            counts[(x, weekday)] = d['contributionCount']
    return len(weeks) + 1, 7, counts


def make_route(width, height, counts, seed):
    rng = random.Random(seed)
    food = {p for p, n in counts.items() if n > 0}
    snake = [(0, 0), (0, 1), (0, 2)]  # Visible empty top-left spawn
    frames = [tuple(snake)]
    eaten_at = {}
    total_food = len(food)
    all_cells = width * height

    def neighbors(p):
        x, y = p
        for dx, dy in DIRECTIONS:
            n = (x + dx, y + dy)
            if 0 <= n[0] < width and 0 <= n[1] < height:
                yield n

    def future_escape(body):
        """After eating, check that the head can still reach its tail."""
        occupied = set(body[1:-1])
        tail = body[-1]
        seen = {body[0]}
        queue = deque([body[0]])
        while queue:
            p = queue.popleft()
            if p == tail:
                return True
            for nxt in neighbors(p):
                if nxt not in seen and nxt not in occupied:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    def route_to_next_food():
        """A* searches exact moving-snake states, not static obstacles.

        The search stops at the first safely reachable food, so it finds
        short, natural routes instead of scanning rows/columns.
        """
        start = tuple(snake)
        prior_direction = ((start[0][0] - start[1][0]),
                           (start[0][1] - start[1][1]))
        rng_directions = DIRECTIONS[:]
        rng.shuffle(rng_directions)

        def heuristic(p):
            return min(abs(p[0]-f[0]) + abs(p[1]-f[1]) for f in food)

        frontier = [(heuristic(start[0]), 0, 0, start)]
        best = {start: 0.0}
        parent = {}
        heading = {start: prior_direction}
        serial = 0
        explored = 0
        while frontier and explored < SEARCH_LIMIT:
            _, _, _, state = heapq.heappop(frontier)
            explored += 1
            current = state[0]
            prev_direction = heading[state]
            directions = rng_directions[:]
            rng.shuffle(directions)
            for dx, dy in directions:
                nxt = (current[0] + dx, current[1] + dy)
                if not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                    continue
                growing = nxt in food
                # A normal step may move into the tail's departing square.
                blocked = state if growing else state[:-1]
                if nxt in blocked:
                    continue
                next_state = ((nxt,) + state if growing
                              else (nxt,) + state[:-1])

                if growing:
                    # On the very last food, an exit is no longer needed.
                    if len(food) > 1 and not future_escape(next_state):
                        continue
                    path = [nxt]
                    cursor = state
                    while cursor != start:
                        path.append(cursor[0])
                        cursor = parent[cursor]
                    return list(reversed(path))

                turn_cost = 0.30 if (dx, dy) != prev_direction else 0
                new_cost = best[state] + 1 + turn_cost
                if new_cost >= best.get(next_state, float('inf')) - 1e-8:
                    continue
                best[next_state] = new_cost
                parent[next_state] = state
                heading[next_state] = (dx, dy)
                serial += 1
                score = new_cost + 1.02 * heuristic(nxt)
                heapq.heappush(frontier, (score, new_cost, serial, next_state))
        return None

    while food:
        if len(frames) > all_cells * 6:
            return None
        route = route_to_next_food()
        if not route:
            return None  # Retry offline, never export an unfinished animation.
        for nxt in route:
            eating = nxt in food
            blocked = snake if eating else snake[:-1]
            if nxt in blocked:
                raise RuntimeError('Self-collision in generated route')
            if abs(nxt[0]-snake[0][0]) + abs(nxt[1]-snake[0][1]) != 1:
                raise RuntimeError('Invalid non-adjacent movement')
            snake.insert(0, nxt)
            if eating:
                food.remove(nxt)
                eaten_at[nxt] = len(frames)
            else:
                snake.pop()
            if len(set(snake)) != len(snake):
                raise RuntimeError('Overlapping snake body')
            frames.append(tuple(snake))

    assert len(eaten_at) == total_food
    return frames, eaten_at


def build_animation(width, height, counts):
    """Plan the entire game BEFORE generating the SVG.

    Try different nearby-food choices; keep the shortest complete,
    collision-free run. Incomplete runs never enter the profile.
    """
    best = None
    successes = 0
    random_source = random.SystemRandom()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        plan = make_route(width, height, counts, random_source.randrange(2**48))
        if plan is not None:
            successes += 1
            if best is None or len(plan[0]) < len(best[0]):
                best = plan
            if successes == 3:
                break
    if best is None:
        raise RuntimeError(
            'No complete collision-free route found in 20 attempts. '
            'Old SVG is kept unchanged. Please report the workflow log.'
        )
    print(f'Complete safe routes found: {successes}; moves: {len(best[0]) - 1}')
    return best


def render_svg(width, height, counts, frames, eaten_at):
    # Generate SMIL animations with smoothly interpolated movement.
    hold = max(2, round(1.2 / MOVE_SECONDS))
    frames = list(frames) + [frames[-1]] * hold
    n = len(frames)
    duration = (n - 1) * MOVE_SECONDS
    duration_text = f'{duration:.3f}s'
    times = ';'.join(f'{i / (n - 1):.7f}' for i in range(n))
    max_length = max(map(len, frames))
    pixel = lambda p: (PAD + p[0]*GAP, PAD + p[1]*GAP)
    svg_width = PAD*2 + (width-1)*GAP + CELL
    svg_height = PAD*2 + (height-1)*GAP + CELL
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" '
        f'height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" '
        f'role="img" aria-label="{html.escape(USER, quote=True)} growing snake">',
        '<rect width="100%" height="100%" fill="#0d1117"/>'
    ]
    for p, count in sorted(counts.items()):
        x, y = pixel(p)
        level = 0 if count == 0 else 1 if count == 1 else 2 if count < 4 else 3 if count < 8 else 4
        parts.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                     f'rx="3" fill="{DOTS[level]}">')
        if p in eaten_at:
            at = eaten_at[p] / (n - 1)
            parts.append(
                f'<animate attributeName="opacity" values="1;0;0" '
                f'keyTimes="0;{at:.7f};1" calcMode="discrete" '
                f'dur="{duration_text}" repeatCount="indefinite"/>')
        parts.append('</rect>')

    for segment in range(max_length - 1, -1, -1):
        positions = []
        visible = []
        last = frames[0][-1]
        for body in frames:
            if segment < len(body):
                last = body[segment]
                visible.append('1')
            else:
                visible.append('0')
            x, y = pixel(last)
            positions.append(f'{x} {y}')
        first_x, first_y = positions[0].split()
        color = HEAD if segment == 0 else BODY
        parts.append(
            f'<rect width="{CELL}" height="{CELL}" rx="4" fill="{color}" '
            f'opacity="{visible[0]}" transform="translate({first_x} {first_y})">')
        parts.append(
            '<animateTransform attributeName="transform" type="translate" '
            f'values="{";".join(positions)}" keyTimes="{times}" '
            f'calcMode="linear" dur="{duration_text}" repeatCount="indefinite"/>')
        if '0' in visible:
            birth = visible.index('1') / (n - 1)
            parts.append(
                f'<animate attributeName="opacity" values="0;1;1" '
                f'keyTimes="0;{birth:.7f};1" calcMode="discrete" '
                f'dur="{duration_text}" repeatCount="indefinite"/>')
        parts.append('</rect>')
    parts.append('</svg>')
    return '\n'.join(parts), duration


def main():
    width, height, counts = load_contributions()
    frames, eaten_at = build_animation(width, height, counts)
    svg, duration = render_svg(width, height, counts, frames, eaten_at)
    Path('dist').mkdir(exist_ok=True)
    output = Path('dist/custom-snake.svg')
    output.write_text(svg, encoding='utf-8')
    print(f'Foods: {len(eaten_at)} / {sum(c > 0 for c in counts.values())}')
    print(f'Duration: {duration:.1f}s; SVG size: {len(svg)//1024} KB')
    print(f'Collision check passed; saved: {output}')


if __name__ == '__main__':
    main()
