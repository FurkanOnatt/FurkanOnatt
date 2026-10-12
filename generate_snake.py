import os, json, random, datetime, urllib.request, html
from pathlib import Path

USER = os.getenv('GITHUB_USER', 'FurkanOnatt')
TOKEN = os.getenv('GITHUB_TOKEN', '')
STEP_SECONDS = 0.13  # Increase to 0.17 for slower movement
PITCH, CELL, MARGIN = 17, 12, 18
START_LENGTH = 3
RANDOM_TURNS = 3500


def fetch_contributions():
    if os.getenv('SNAKE_TEST') == '1':
        return {(x, y): (1 if (x * 11 + y * 7) % 13 == 0 else 0)
                for x in range(1, 54) for y in range(7)}
    if not TOKEN:
        raise RuntimeError('GITHUB_TOKEN is missing. Set it in the workflow environment.')
    query = '''query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}'''
    req = urllib.request.Request('https://api.github.com/graphql',
        data=json.dumps({'query':query,'variables':{'login':USER}}).encode(),
        headers={'Authorization':f'Bearer {TOKEN}', 'Content-Type':'application/json',
                 'User-Agent':'custom-snake'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if result.get('errors') or not result.get('data', {}).get('user'):
        raise RuntimeError(f'GitHub GraphQL error: {result.get("errors")}')
    weeks = result['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
    values = {}
    for x, week in enumerate(weeks, start=1):
        for day in week['contributionDays']:
            weekday = (datetime.date.fromisoformat(day['date']).weekday() + 1) % 7
            values[(x, weekday)] = day['contributionCount']
    return values


def initial_path(w, h):
    # Full coverage path, beginning at the left-top starting square.
    path = []
    for y in range(h):
        xs = range(w) if y % 2 == 0 else range(w-1, -1, -1)
        path.extend((x,y) for x in xs)
    return path


def randomized_hamiltonian_path(w, h, rng):
    # Backbite moves randomize a Hamiltonian path without losing any squares.
    # Keep its first endpoint fixed at (0,0); modify only the far endpoint.
    path = initial_path(w,h)
    for _ in range(RANDOM_TURNS):
        end = path[-1]
        x,y = end
        neighbors = [(x+dx,y+dy) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))
                     if 0 <= x+dx < w and 0 <= y+dy < h]
        rng.shuffle(neighbors)
        index = {p:i for i,p in enumerate(path)}
        for neighbor in neighbors:
            j = index[neighbor]
            if j < len(path)-2:
                path[j+1:] = reversed(path[j+1:])
                break
    assert path[0] == (0,0) and len(path) == w*h and len(set(path)) == w*h
    assert all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a,b in zip(path,path[1:]))
    return path


def n(v):
    return f'{v:.6f}'.rstrip('0').rstrip('.')


def make_svg(values):
    cols = max((x for x,y in values), default=53)
    width_cells = cols+1  # x=0 is a visibly empty spawn column
    height_cells = 7
    foods = {p for p,c in values.items() if c > 0}
    rng = random.Random()
    route = randomized_hamiltonian_path(width_cells,height_cells,rng)
    food_steps = {p:i for i,p in enumerate(route) if p in foods}
    last = max(food_steps.values(), default=len(route)-1)
    route = route[:last+1]
    # Start with head at (0,0); tail appears outside the board, not on food.
    bodies = []
    consumed = set()
    for i, head in enumerate(route):
        if head in foods:
            consumed.add(head)
        length = START_LENGTH + len(consumed)
        body = [route[j] if j >= 0 else (j,0)
                for j in range(i,i-length,-1)]
        if len(set(body)) != len(body):
            raise RuntimeError(f'Snake collision at frame {i}')
        bodies.append(body)
    assert consumed == foods
    # A short pause, then the whole map resets at the loop boundary.
    pause_frames = 8
    bodies.extend([bodies[-1]] * pause_frames)
    count = len(bodies)
    duration = count * STEP_SECONDS
    max_segments = max(map(len,bodies))
    canvas_w = MARGIN*2 + (width_cells-1)*PITCH + CELL
    canvas_h = MARGIN*2 + (height_cells-1)*PITCH + CELL
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_w} {canvas_h}" '
           f'width="{canvas_w}" height="{canvas_h}" role="img" '
           f'aria-label="{html.escape(USER,quote=True)} contribution snake">']
    out.append('<rect width="100%" height="100%" fill="#0d1117"/>')
    out.append('<style>')
    # One compact CSS keyframe timeline per food. All reset only at 100%.
    for (x,y),step in food_steps.items():
        pct = 100*step/count
        out.append(f'@keyframes f{x}_{y}{{0%,{n(max(0,pct-0.0001))}%{{opacity:1}}'
                   f'{n(pct)}%,100%{{opacity:0}}}}')
    out.append('</style>')
    for y in range(height_cells):
        for x in range(1,cols+1):
            count_val = values.get((x,y),0)
            color = ('#161b22' if count_val == 0 else '#312e81' if count_val == 1
                     else '#4338ca' if count_val < 4 else '#7c3aed' if count_val < 8
                     else '#a855f7')
            animation = (f' style="animation:f{x}_{y} {n(duration)}s steps(1,end) infinite"'
                         if (x,y) in foods else '')
            out.append(f'<rect x="{MARGIN+x*PITCH}" y="{MARGIN+y*PITCH}" '
                       f'width="{CELL}" height="{CELL}" rx="3" fill="{color}"{animation}/>')
    # Each segment follows exactly the same legal route, delayed by one move.
    # Linear interpolation between adjacent squares is smooth and never diagonal.
    # Values at the end pause; the reset is instantaneous at the loop boundary.
    times = ';'.join(n(i/count) for i in range(count+1))
    for segment in range(max_segments-1,-1,-1):
        transforms, opacities = [], []
        for body in bodies:
            visible = segment < len(body)
            x,y = body[segment] if visible else (-5,-5)
            transforms.append(f'{MARGIN+x*PITCH} {MARGIN+y*PITCH}')
            opacities.append('1' if visible else '0')
        transforms.append(transforms[-1]); opacities.append(opacities[-1])
        x0,y0 = bodies[0][segment] if segment < len(bodies[0]) else (-5,-5)
        color = '#22d3ee' if segment == 0 else '#8b5cf6'
        out.append(f'<rect width="{CELL}" height="{CELL}" rx="4" fill="{color}" '
                   f'transform="translate({MARGIN+x0*PITCH} {MARGIN+y0*PITCH})" '
                   f'opacity="{int(segment<len(bodies[0]))}">')
        out.append(f'<animateTransform attributeName="transform" type="translate" '
                   f'values="{";".join(transforms)}" keyTimes="{times}" '
                   f'calcMode="linear" dur="{n(duration)}s" repeatCount="indefinite"/>')
        out.append(f'<animate attributeName="opacity" values="{";".join(opacities)}" '
                   f'keyTimes="{times}" calcMode="discrete" '
                   f'dur="{n(duration)}s" repeatCount="indefinite"/>')
        out.append('</rect>')
    out.append('</svg>')
    return '\n'.join(out),len(foods),len(route),duration


def main():
    svg, foods, steps, duration = make_svg(fetch_contributions())
    Path('dist').mkdir(exist_ok=True)
    Path('dist/custom-snake.svg').write_text(svg,encoding='utf-8')
    print(f'Food squares: {foods}; route steps: {steps}; duration: {duration:.1f}s')
    print('No self-intersections in generated route; all food consumed.')

if __name__ == '__main__':
    main()
