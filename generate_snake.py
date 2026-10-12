import os, json, random, datetime, urllib.request, html
from pathlib import Path

USER = os.getenv('GITHUB_USER', 'FurkanOnatt')
TOKEN = os.getenv('GITHUB_TOKEN', '')
if not TOKEN:
    raise RuntimeError('GITHUB_TOKEN is required. Set it in the GitHub Actions workflow.')

CELL, PITCH, MARGIN = 12, 17, 18
START_LENGTH = 3
SECONDS_PER_MOVE = 0.20  # Increase to 0.25 for slower motion
ROUTE_VARIATIONS = 2

query = '''query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}'''
req = urllib.request.Request('https://api.github.com/graphql', data=json.dumps({'query':query,'variables':{'login':USER}}).encode(), headers={'Authorization':f'Bearer {TOKEN}','Content-Type':'application/json','User-Agent':'readme-custom-snake'})
with urllib.request.urlopen(req, timeout=30) as response:
    result=json.load(response)
if result.get('errors') or not result.get('data',{}).get('user'):
    raise RuntimeError(f'GitHub API error: {result.get("errors", result)}')
weeks=result['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
COLS=len(weeks)
ROWS=7
values={}
for x,week in enumerate(weeks):
    for day in week['contributionDays']:
        y=(datetime.date.fromisoformat(day['date']).weekday()+1)%7
        values[(x,y)]=day['contributionCount']
foods={pos for pos,count in values.items() if count>0}

# The snake always starts at the upper-left EMPTY margin, not on a contribution.
START=(-1,0)
rng=random.Random()

from collections import deque

# Head starts at (-1, 0); the two initial tail cells are outside the grid.
# A move into the current tail is safe only when the tail moves away.
def legal_next(body, nxt, remaining):
    x, y = nxt
    if not (-1 <= x < COLS and 0 <= y < ROWS):
        return False
    growing = nxt in remaining
    blocked = body if growing else body[:-1]
    return nxt not in blocked

def neighbors(pos):
    x, y = pos
    opts = [(x+1,y),(x-1,y),(x,y+1),(x,y-1)]
    rng.shuffle(opts)
    return opts

def safe_route(body, target, remaining):
    # Search with a simulated moving body, not just a static obstacle map.
    start = tuple(body)
    queue = deque([(start, [])])
    seen = {start}
    limit = 35000
    while queue and len(seen) < limit:
        state, path = queue.popleft()
        for nxt in neighbors(state[0]):
            if not legal_next(state, nxt, remaining):
                continue
            grows = nxt in remaining
            updated = (nxt,) + (state if grows else state[:-1])
            if nxt == target:
                return path + [nxt]
            if updated not in seen:
                seen.add(updated)
                queue.append((updated, path + [nxt]))
    return None

def make_cycle():
    remaining = set(foods)
    body = [START, (-2,0), (-3,0)]
    positions = [START]
    bodies = [body.copy()]
    eaten = {}
    while remaining:
        # Try nearby random targets, then farther targets if needed.
        ordered = sorted(remaining, key=lambda p: abs(p[0]-body[0][0])+abs(p[1]-body[0][1]))
        choices = ordered[:min(8,len(ordered))]
        rng.shuffle(choices)
        route = None
        for target in choices:
            route = safe_route(body,target,remaining)
            if route:
                break
        if not route:
            for target in ordered[8:]:
                route = safe_route(body,target,remaining)
                if route:
                    break
        if not route:
            print(f'No collision-free route; {len(remaining)} squares remain. Ending cycle safely.')
            break
        blocked_route = False
        for nxt in route:
            if not legal_next(body, nxt, remaining):
                blocked_route = True
                break
            grows = nxt in remaining
            body.insert(0,nxt)
            if grows:
                remaining.remove(nxt)
                eaten[nxt] = len(positions)
            else:
                body.pop()
            positions.append(nxt)
            bodies.append(body.copy())
        if blocked_route:
            continue  # Replan using the updated body and remaining food.
    for _ in range(6):
        positions.append(positions[-1])
        bodies.append(body.copy())
    return positions, eaten, bodies

cycles=[make_cycle() for _ in range(ROUTE_VARIATIONS)]
frames=[]
states=[]
for ci,(path,eaten,bodies) in enumerate(cycles):
    for step,pos in enumerate(path):
        frames.append((ci,step,pos))
        states.append(bodies[step])
N=len(frames)
duration=max(1,(N-1)*SECONDS_PER_MOVE)
width=MARGIN*2+(COLS-1)*PITCH+CELL
height=MARGIN*2+(ROWS-1)*PITCH+CELL

def fmt(x):
    return f'{x:.6f}'.rstrip('0').rstrip('.')

def pct(i):
    return fmt(100*i/max(1,N-1))

def translate(pos):
    x,y=pos
    return f'translate({MARGIN+x*PITCH}px,{MARGIN+y*PITCH}px)'

max_segments=max(map(len,states))

parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Growing contribution snake for {html.escape(USER,quote=True)}">','<style>']
# The food layer is only restored when the entire board has been eaten.
# SVG keyframes use discrete opacity changes and smooth position transitions.
for pos in sorted(foods):
    x,y=pos
    changes=[]
    start=0
    for path,eaten,_bodies in cycles:
        changes.append((start,1))
        eat_index=start+eaten.get(pos, len(path)-1)
        changes.append((eat_index,0))
        start+=len(path)
    # steps(1,end) makes each square disappear only upon arrival.
    keys=[]
    for index,opacity in changes:
        keys.append(f'{pct(index)}%{{opacity:{opacity}}}')
    keys.append('100%{opacity:0}')
    parts.append(f'@keyframes food_{x}_{y}{{{"".join(keys)}}}')

# Keyframe every move, with a very short hold at the beginning of each cycle.
# Note: body may overlap itself on very long runs; avoiding that requires pathfinding.
for segment in range(max_segments):
    keys=[]
    for i,state in enumerate(states):
        visible=segment<len(state)
        pos=state[segment] if visible else START
        keys.append(f'{pct(i)}%{{transform:{translate(pos)};opacity:{1 if visible else 0}}}')
    parts.append(f'@keyframes seg_{segment}{{{"".join(keys)}}}')
parts.append('</style>')

for x in range(COLS):
    for y in range(ROWS):
        count=values.get((x,y),0)
        color=('#161b22' if count==0 else '#312e81' if count==1 else '#4338ca' if count<4 else '#7c3aed' if count<8 else '#a855f7')
        style=(f' style="animation:food_{x}_{y} {fmt(duration)}s steps(1,end) infinite"' if count else '')
        parts.append(f'<rect x="{MARGIN+x*PITCH}" y="{MARGIN+y*PITCH}" width="{CELL}" height="{CELL}" rx="3" fill="{color}"{style}/>')
for segment in range(max_segments-1,-1,-1):
    color='#22d3ee' if segment==0 else '#8b5cf6'
    parts.append(f'<rect width="{CELL}" height="{CELL}" rx="4" fill="{color}" style="animation:seg_{segment} {fmt(duration)}s linear infinite"/>')
parts.append('</svg>')
Path('dist').mkdir(exist_ok=True)
Path('dist/custom-snake.svg').write_text('\n'.join(parts),encoding='utf-8')
print(f'Generated {len(foods)} food squares, {N} frames, {duration:.1f}s animation')
