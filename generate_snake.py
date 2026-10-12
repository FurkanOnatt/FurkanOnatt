import json, os, urllib.request, datetime, math, html
from collections import deque
USER=os.environ.get('GITHUB_USER','FurkanOnatt')
TOKEN=os.environ.get('GITHUB_TOKEN','')
query='query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}'
req=urllib.request.Request('https://api.github.com/graphql',data=json.dumps({'query':query,'variables':{'login':USER}}).encode(),headers={'Authorization':f'Bearer {TOKEN}','Content-Type':'application/json','User-Agent':'custom-snake'})
with urllib.request.urlopen(req,timeout=25) as r: data=json.load(r)
if 'errors' in data: raise RuntimeError(str(data['errors']))
weeks=data['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
rows=7; cols=len(weeks); cell=15; pitch=19; left=18; top=18
values={(x,datetime.date.fromisoformat(d['date']).weekday()+1 if False else (datetime.date.fromisoformat(d['date']).weekday()+1)%7):d['contributionCount'] for x,w in enumerate(weeks) for d in w['contributionDays']}
# Snake travels a serpentine path through all cells, eating filled contribution days.
path=[]
for x in range(cols):
    ys=range(rows) if x%2==0 else range(rows-1,-1,-1)
    path.extend((x,y) for y in ys)
# Start with 3 segments; each occupied square adds exactly one segment.
length=3; history=deque(maxlen=len(path)+4); frames=[]
for pos in path:
    history.append(pos)
    if values.get(pos,0)>0: length+=1
    frames.append((list(history)[-length:][::-1],pos))
# Generate animated SVG using CSS discrete keyframes, with 1 rectangle per snake segment.
# Each segment follows prior head locations. Positions are held between frames.
# Compress to <= 220 frames to keep SVG reasonably sized, while preserving growth at sampled steps.
indices=list(range(0,len(frames),max(1,math.ceil(len(frames)/180))))
if indices[-1]!=len(frames)-1: indices.append(len(frames)-1)
N=len(indices); duration=22
W=left*2+(cols-1)*pitch+cell; H=top*2+(rows-1)*pitch+cell
out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Animated contribution snake for {html.escape(USER)}">', '<style>']
# Use one CSS animation per segment, each with changing x/y coordinates using transforms.
max_segments=max(len(frames[i][0]) for i in indices)
for s in range(max_segments):
    stops=[]
    for j,i in enumerate(indices):
        snake=frames[i][0]
        if s<len(snake):
            x,y=snake[s]; transform=f'translate({left+x*pitch}px,{top+y*pitch}px)'; opacity='1'
        else: transform='translate(-30px,-30px)'; opacity='0'
        stops.append(f'{j/(N-1)*100:.3f}%{{transform:{transform};opacity:{opacity}}}')
    out.append(f'@keyframes seg{s}{{'+''.join(stops)+'}')
out.append('</style>')
for x in range(cols):
    for y in range(rows):
        count=values.get((x,y),0)
        fill=('#161b22' if count==0 else '#312e81' if count==1 else '#4338ca' if count<4 else '#7c3aed' if count<8 else '#a855f7')
        out.append(f'<rect x="{left+x*pitch}" y="{top+y*pitch}" width="{cell}" height="{cell}" rx="3" fill="{fill}"/>')
for s in range(max_segments-1,-1,-1):
    color='#22d3ee' if s==0 else '#8b5cf6'
    out.append(f'<rect width="{cell}" height="{cell}" rx="4" fill="{color}" style="animation:seg{s} {duration}s steps(1,end) infinite"/>')
out.append('</svg>')
os.makedirs('dist',exist_ok=True)
with open('dist/custom-snake.svg','w',encoding='utf-8') as f:f.write('\n'.join(out))
print(f'Generated {cols} weeks, {max_segments} snake segments, {N} animation frames')
