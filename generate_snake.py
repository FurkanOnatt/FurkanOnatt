"""Generate a direct-target, smooth contribution snake for a GitHub profile."""
import datetime
import html
import json
import os
import urllib.request
from collections import deque
from pathlib import Path

USER = os.getenv('GITHUB_USER', 'FurkanOnatt')
TOKEN = os.getenv('GITHUB_TOKEN', '')
if not TOKEN:
    raise RuntimeError('GITHUB_TOKEN is required')
query = '''query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}'''
request = urllib.request.Request(
    'https://api.github.com/graphql',
    data=json.dumps({'query':query,'variables':{'login':USER}}).encode(),
    headers={'Authorization':f'Bearer {TOKEN}','Content-Type':'application/json','User-Agent':'direct-contribution-snake'},
)
with urllib.request.urlopen(request, timeout=30) as response:
    result=json.load(response)
if result.get('errors'):
    raise RuntimeError(str(result['errors']))
weeks=result['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
cols=len(weeks)
rows=7
values={
    (x,(datetime.date.fromisoformat(day['date']).weekday()+1)%7):day['contributionCount']
    for x,week in enumerate(weeks) for day in week['contributionDays']
}
targets={p for p,n in values.items() if n>0}

# Find the shortest orthogonal route to the nearest remaining contribution.
# No sweeping empty columns, so the snake goes directly toward food.
def neighbors(p):
    x,y=p
    for q in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
        if 0<=q[0]<cols and 0<=q[1]<rows:
            yield q

def route_to_nearest(start, remaining):
    queue=deque([start]); previous={start:None}
    found=None
    while queue:
        p=queue.popleft()
        if p in remaining:
            found=p;break
        for q in neighbors(p):
            if q not in previous:
                previous[q]=p;queue.append(q)
    if found is None:
        return []
    route=[]
    while found != start:
        route.append(found);found=previous[found]
    return route[::-1]

start=(0,0)
path=[start]
remaining=set(targets)
if start in remaining:
    remaining.remove(start)
while remaining:
    route=route_to_nearest(path[-1],remaining)
    if not route:
        raise RuntimeError('No route to remaining contributions')
    path.extend(route)
    remaining.remove(path[-1])

# A segment grows exactly once for every occupied day reached.
length=3
history=deque([(0,0)]*3)
frames=[]
consumed={}
for step,p in enumerate(path):
    history.appendleft(p)
    if p in targets and p not in consumed:
        consumed[p]=step
        length+=1
    while len(history)>length:
        history.pop()
    frames.append(list(history))

cell=13; pitch=18; margin=18
width=margin*2+(cols-1)*pitch+cell
height=margin*2+(rows-1)*pitch+cell
n=len(frames)
# Smooth linear interpolation from one cell to the next. More steps => longer total duration.
duration=max(12,min(70,(n-1)*0.17))
max_length=max(map(len,frames))
fmt=lambda n: f'{n:.5f}'.rstrip('0').rstrip('.')
output=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Growing contribution snake for {html.escape(USER,quote=True)}">','<style>']

# CSS transforms animate smoothly (linear) rather than jumping at each grid cell.
# For newly grown segments, hide them until the frame when food is eaten.
for s in range(max_length):
    keys=[]
    for i,body in enumerate(frames):
        if s<len(body):
            x,y=body[s]
            opacity=1
        else:
            x,y=-3,-3
            opacity=0
        pct=100*i/max(1,n-1)
        keys.append(f'{fmt(pct)}%{{transform:translate({margin+x*pitch}px,{margin+y*pitch}px);opacity:{opacity}}}')
    output.append(f'@keyframes snake_{s}{{'+''.join(keys)+'}')

# Food stays invisible after consumption and only reappears on full loop restart.
for (x,y),step in consumed.items():
    pct=100*step/max(1,n-1)
    before=max(0,pct-0.0001)
    output.append(f'@keyframes food_{x}_{y}{{0%,{fmt(before)}%{{opacity:1}}{fmt(pct)}%,100%{{opacity:0}}}}')
output.append('</style>')
for x in range(cols):
    for y in range(rows):
        count=values.get((x,y),0)
        fill='#161b22' if not count else '#312e81' if count==1 else '#4338ca' if count<4 else '#7c3aed' if count<8 else '#a855f7'
        style=f' style="animation:food_{x}_{y} {fmt(duration)}s steps(1,end) infinite"' if count else ''
        output.append(f'<rect x="{margin+x*pitch}" y="{margin+y*pitch}" width="{cell}" height="{cell}" rx="3" fill="{fill}"{style}/>')
for s in range(max_length-1,-1,-1):
    color='#22d3ee' if s==0 else '#8b5cf6'
    output.append(f'<rect width="{cell}" height="{cell}" rx="4" fill="{color}" style="animation:snake_{s} {fmt(duration)}s linear infinite"/>')
output.append('</svg>')
Path('dist').mkdir(exist_ok=True)
Path('dist/custom-snake.svg').write_text('\n'.join(output),encoding='utf-8')
print(f'Generated: {len(targets)} food tiles, {len(path)} moves, {max_length} segments, {duration:.1f}s loop')
