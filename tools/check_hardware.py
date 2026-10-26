#!/usr/bin/env python3
"""Check CAD structure and schematic/PCB/CSV agreement, not ERC/DRC qualification."""
from pathlib import Path
import csv
import json
import re
import pcbnew

root=Path(__file__).resolve().parents[1]/'hardware'
def parse(text):
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
    stack=[];result=[]
    for t in tokens:
        if t=='(':
            node=[]
            (stack[-1] if stack else result).append(node);stack.append(node)
        elif t==')':
            assert stack,'Unexpected close parenthesis'
            stack.pop()
        else:
            assert stack,'Token outside expression'
            stack[-1].append(json.loads(t) if t.startswith('"') else t)
    assert not stack and len(result)==1,'Unbalanced or multiple root expressions'
    return result[0]

def children(n,key):return [v for v in n if isinstance(v,list) and v and v[0]==key]
def child(n,key):return children(n,key)[0]
def xy(n):return tuple(round(float(v),5) for v in n[1:3])

s=parse((root/'Net4MSX.kicad_sch').read_text())
assert s[0]=='kicad_sch'
libs={v[1]:v for v in children(child(s,'lib_symbols'),'symbol')}
labels={xy(child(v,'at')):v[1] for v in children(s,'label')}
wire_nets={}
for wire in children(s,'wire'):
    a,b=[xy(v) for v in children(child(wire,'pts'),'xy')]
    label=labels.get(a,labels.get(b))
    assert label is not None,'Wire has no net label'
    wire_nets[a]=wire_nets[b]=label

csv_map={(r['reference'],r['pad']):r['net'] for r in csv.DictReader((root/'pin-map.csv').open())}
sch_map={};symbol_ids={}
for symbol in children(s,'symbol'):
    props={v[1]:v[2] for v in children(symbol,'property')}
    ref=props['Reference'];symbol_ids[ref]=child(symbol,'uuid')[1]
    sx,sy=xy(child(symbol,'at'))
    lib=libs[child(symbol,'lib_id')[1]]
    for part in children(lib,'symbol'):
        for pin in children(part,'pin'):
            px,py=xy(child(pin,'at'));num=child(pin,'number')[1]
            sch_map[ref,num]=wire_nets.get((round(sx+px,5),round(sy-py,5)),'')
assert sch_map==csv_map,'Schematic and pin-map.csv differ'

b=pcbnew.LoadBoard(str(root/'Net4MSX.kicad_pcb'))
pcb_map={}
for fp in b.GetFootprints():
    ref=fp.GetReference()
    assert fp.GetPath().AsString().endswith(symbol_ids[ref]),'Unlinked PCB component'
    positions=[(p.GetPosition().x,p.GetPosition().y) for p in fp.Pads()]
    expected_positions=25 if ref=='J1' else len(positions)
    assert len(set(positions))==expected_positions,'Overlapping pad centers'
    xs=[pcbnew.ToMM(p.GetPosition().x) for p in fp.Pads()]
    ys=[pcbnew.ToMM(p.GetPosition().y) for p in fp.Pads()]
    expected_width={'J1':60.96,'U1':17.78,'U2':25.4}[ref]
    expected_height={'J1':0,'U1':48.26,'U2':38.10}[ref]
    assert abs(max(xs)-min(xs)-expected_width)<1e-5,'Incorrect header/contact spacing'
    assert abs(max(ys)-min(ys)-expected_height)<1e-5,'Incorrect row length'
    for p in fp.Pads():pcb_map[ref,p.GetNumber()]=p.GetNetname()
assert pcb_map==sch_map,'PCB and schematic nets differ'
assert len(pcb_map)==122
assert len(list(b.GetTracks()))==0,'Concept unexpectedly contains routes'
layout=json.loads((root/'placement.json').read_text())
render_pads={(p['ref'],p['pad']):p for p in layout['pads']}
for fp in b.GetFootprints():
    for p in fp.Pads():
        q=render_pads[fp.GetReference(),p.GetNumber()]
        assert abs(pcbnew.ToMM(p.GetPosition().x)-q['x'])<1e-5
        assert abs(pcbnew.ToMM(p.GetPosition().y)-q['y'])<1e-5

for name in ['Net4MSX.kicad_pro','placement.json']:
    json.loads((root/name).read_text())
for footprint in (root/'Net4MSX.pretty').glob('*.kicad_mod'):
    assert pcbnew.FootprintLoad(str(footprint.parent),footprint.stem)
print('PASS: 3 linked components, 122 pads; schematic, PCB and CSV nets agree.')
print('PASS: PCB and local footprints reload; rendering placement agrees with PCB.')
print('PASS: distinct pad centers and expected MSX/Pico/module header extents.')
print('Concept is unrouted. This check is not electrical or mechanical qualification.')
