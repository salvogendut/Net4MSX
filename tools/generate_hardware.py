#!/usr/bin/env python3
"""Generate the editable, UNROUTED Net4MSX interface/placement concept.

Requires Debian KiCad 6 pcbnew. Module geometry/pin mapping adapted from
Net4CPC f7e94b6; see hardware/NOTICE.md and LICENSES/Net4CPC-GPL-3.0.txt.
The external EAGLE checkout is needed only to regenerate the module footprint.
"""
import argparse
import csv
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
import pcbnew as pcb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--net4cpc', type=Path, default=Path('/home/sbognann/Development/Net4CPC'))
args = parser.parse_args()
for folder in ['Net4MSX.pretty', 'models', 'renders']:
    (OUT / folder).mkdir(exist_ok=True, parents=True)

def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'net4msx/concept/' + name))

def point(x, y):
    return pcb.wxPointMM(x, y)

board = pcb.BOARD()
board.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6))
nets = {}
def net(name):
    if name not in nets:
        n = pcb.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    return nets[name]

def line(container, x1, y1, x2, y2, layer, width=.15):
    item = pcb.FP_SHAPE(container) if isinstance(container, pcb.FOOTPRINT) else pcb.PCB_SHAPE()
    item.SetShape(pcb.SHAPE_T_SEGMENT)
    item.SetStart(point(x1, y1)); item.SetEnd(point(x2, y2))
    if isinstance(container, pcb.FOOTPRINT):
        item.SetStart0(point(x1,y1));item.SetEnd0(point(x2,y2))
    item.SetLayer(layer); item.SetWidth(pcb.FromMM(width)); container.Add(item)

def rect(container, x1, y1, x2, y2, layer):
    for a,b,c,d in [(x1,y1,x2,y1),(x2,y1,x2,y2),(x2,y2,x1,y2),(x1,y2,x1,y1)]:
        line(container,a,b,c,d,layer)

def pad(fp, num, x, y, w=1.8, h=1.8, drill=1, layer=None):
    p = pcb.PAD(fp); p.SetNumber(str(num)); p.SetPosition(point(x,y))
    p.SetPos0(point(x,y))
    p.SetSize(pcb.wxSizeMM(w,h))
    p.SetShape(pcb.PAD_SHAPE_RECT if str(num) in ['1','16','17','21'] else pcb.PAD_SHAPE_OVAL)
    if layer is None:
        p.SetAttribute(pcb.PAD_ATTRIB_PTH); p.SetDrillSize(pcb.wxSizeMM(drill,drill))
        layers=pcb.LSET.AllCuMask(); layers.AddLayer(pcb.F_Mask); layers.AddLayer(pcb.B_Mask)
        p.SetLayerSet(layers)
    else:
        p.SetAttribute(pcb.PAD_ATTRIB_SMD)
        p.SetShape(pcb.PAD_SHAPE_RECT)
        layers=pcb.LSET(); layers.AddLayer(layer); layers.AddLayer(pcb.F_Mask if layer==pcb.F_Cu else pcb.B_Mask)
        p.SetLayerSet(layers)
    fp.Add(p)

def footprint(name, ref, value):
    fp=pcb.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
    fp.SetFPID(pcb.LIB_ID('Net4MSX', name))
    fp.Reference().SetPosition(point(0,-28)); fp.Value().SetVisible(False)
    return fp

def place(fp, name, x, y, rotation, pin_nets):
    pcb.FootprintSave(str(OUT/'Net4MSX.pretty'),fp)
    path=pcb.KIID_PATH();path.push_back(pcb.KIID(uid('sheet')));path.push_back(pcb.KIID(uid(fp.GetReference())))
    fp.SetPath(path)
    fp.SetPosition(point(x,y)); fp.SetOrientationDegrees(rotation)
    for p in fp.Pads():
        if p.GetNumber() in pin_nets: p.SetNet(net(pin_nets[p.GetNumber()]))
    fp.Reference().SetPosition(point(x,y-28))
    board.Add(fp)

msx_names=['nCS1','nCS2','nCS12','nSLTSL','RESERVED5','nRFSH','nWAIT','nINT','nM1','nBUSDIR','nIORQ','nMERQ','nWR','nRD','nRESET','RESERVED16','A9','A15','A11','A10','A7','A6','A12','A8','A14','A13','A1','A0','A3','A2','A5','A4','D1','D0','D3','D2','D5','D4','D7','D6','GND','CLOCK','GND','SW1','5V_SLOT','SW2','5V_SLOT','12V_SLOT','SOUNDIN','NEG12V_SLOT']
msx_nets={str(i+1):('GND' if n=='GND' else n if 'V_SLOT' in n else 'MSX_'+n) for i,n in enumerate(msx_names)}
edge=footprint('MSX_Edge_50_Concept','J1','MSX cartridge edge - orientation review required')
for i in range(25):
    x=-30.48+i*2.54
    # F.Cu: even contacts right-to-left; B.Cu odd contacts, same physical x.
    pad(edge,50-2*i,x,0,1.7,9,layer=pcb.F_Cu)
    pad(edge,49-2*i,x,0,1.7,9,layer=pcb.B_Cu)
rect(edge,-32.72,-5,32.72,4.7,pcb.F_Fab)
place(edge,'MSX_Edge_50_Concept',90,135.3,0,msx_nets)

source=ET.parse(args.net4cpc/'Net4CPC.sch')
pkg=next(p for p in source.findall('.//package') if p.get('name')=='W5100S-NETWORK-MODULE')
mod=footprint('W5100S_Net4CPC','U2','W5100S SPI/parallel module - Net4CPC')
for p in pkg.findall('pad'):
    pad(mod,p.get('name'),float(p.get('x')),-float(p.get('y')),drill=float(p.get('drill')))
for w in pkg.findall('wire'):
    line(mod,float(w.get('x1')),-float(w.get('y1')),float(w.get('x2')),-float(w.get('y2')),pcb.F_SilkS)
mod_nets={'1':'MOD_3V3','2':'MOD_3V3',**{str(i+3):f'MOD_D{i}_UNUSED' for i in range(8)},'11':'WIZ_nINT','12':'WIZ_nRESET','21':'MOD_5V_INPUT','22':'MOD_5V_INPUT','23':'MOD_3V3','24':'MOD_3V3','25':'GND','26':'GND','27':'GND','28':'GND','29':'SPI_nCS','30':'SPI_SCK','31':'SPI_MOSI','32':'SPI_MISO'}
mod_labels={'1':'nRD','2':'nWR',**{str(i+3):f'D{i}' for i in range(8)},'11':'nINT','12':'nRST',**{str(i):'UNASSIGNED' for i in range(13,21)},'21':'5V','22':'5V','23':'3V3','24':'3V3','25':'GND','26':'GND','27':'GND','28':'MODE','29':'nCS','30':'SCLK','31':'MOSI/A0','32':'MISO/A1'}
place(mod,'W5100S_Net4CPC',108,77,180,mod_nets)

pico_labels=['GP0','GP1','GND','GP2','GP3','GP4','GP5','GND','GP6','GP7','GP8','GP9','GND','GP10','GP11','GP12','GP13','GND','GP14','GP15','GP16','GP17','GND','GP18','GP19','GP20','GP21','GND','GP22','RUN','GP26','GP27','AGND','GP28','ADC_VREF','3V3_OUT','3V3_EN','GND','VSYS','VBUS']
pico_nets={str(i+1):'GND' if n in ['GND','AGND'] else 'PICO_'+n for i,n in enumerate(pico_labels)}
pico_nets.update({'21':'SPI_MISO','22':'SPI_nCS','24':'SPI_SCK','25':'SPI_MOSI','26':'WIZ_nRESET','27':'WIZ_nINT'})
pico=footprint('Pico_ThroughHole_Concept','U1','Raspberry Pi Pico - optional coprocessor')
for i in range(20):
    pad(pico,i+1,-8.89,-24.13+i*2.54)
    pad(pico,40-i,8.89,-24.13+i*2.54)
rect(pico,-10.5,-25.5,10.5,25.5,pcb.F_SilkS)
place(pico,'Pico_ThroughHole_Concept',70,79,0,pico_nets)

outline=[(50,50),(130,50),(130,130),(122.72,130),(122.72,140),(57.28,140),(57.28,130),(50,130)]
for (x,y),(u,v) in zip(outline,outline[1:]+outline[:1]):line(board,x,y,u,v,pcb.Edge_Cuts,.05)

def text(s,x,y,size=1,layer=pcb.F_SilkS):
    t=pcb.PCB_TEXT(board);t.SetText(s);t.SetPosition(point(x,y));t.SetTextSize(pcb.wxSizeMM(size,size));t.SetTextThickness(pcb.FromMM(.15));t.SetLayer(layer);board.Add(t)

text('Net4MSX',90,107,2.3)
text('W5100S + optional Pico',90,111,1.1)
for bounds,label in [((55,115,87,126),'BUS / LEVEL SHIFT / FIFO'),((92,115,125,126),'ROM / POWER - TBD')]:
    rect(board,*bounds,pcb.Dwgs_User);text(label,(bounds[0]+bounds[2])/2,120,.8,pcb.Dwgs_User)
text('CONCEPT A0 - UNROUTED',90,128,.95)
text('50',59.52,129.6,.75);text('2',120.48,129.6,.75)
text('MODULE PINOUT: Net4CPC REFERENCE',150,65,1,pcb.Dwgs_User)
text('No bus glue, boot ROM or power circuit yet',150,70,1,pcb.Dwgs_User)

# These simple models are original geometric placeholders, not vendor STEP files.
def wrl_box(center, dims, color):
    c=' '.join(str(v/2.54) for v in center);d=' '.join(str(v/2.54) for v in dims)
    return f'Transform {{ translation {c} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {d} }} }} ] }}\n'

models={
 'pico':[((0,0,8),(21,51,1),'0.02 0.28 0.16'),((0,22,10),(8,6,3),'0.65 0.66 0.68'),((0,0,9),(7,7,1),'0.04 0.04 0.05')],
 'module':[((0,-1.27,8),(27.616,42.856,1.6),'0.03 0.22 0.37'),((.635,-15.24,15),(16,16,12),'0.65 0.67 0.69'),((-1.27,3.81,9.5),(8,8,1.4),'0.04 0.04 0.05')]
}
for name,boxes in models.items():
    (OUT/'models'/f'{name}.wrl').write_text('#VRML V2.0 utf8\n'+''.join(wrl_box(*b) for b in boxes))
for fp,name in [(pico,'pico'),(mod,'module')]:
    model=pcb.FP_3DMODEL();model.m_Filename='${KIPRJMOD}/models/'+name+'.wrl';fp.Add3DModel(model)
pcb.SaveBoard(str(OUT/'Net4MSX.kicad_pcb'),board)
(OUT/'Net4MSX.kicad_pro').write_text(json.dumps({'meta':{'filename':'Net4MSX.kicad_pro','version':1},'board':{},'boards':[],'cvpcb':{},'erc':{},'libraries':{},'net_settings':{'classes':[{'name':'Default','clearance':.25,'track_width':.25,'via_diameter':.8,'via_drill':.4}],'meta':{'version':2}},'pcbnew':{},'schematic':{}},indent=2)+'\n')
(OUT/'fp-lib-table').write_text('(fp_lib_table\n (lib (name "Net4MSX")(type "KiCad")(uri "${KIPRJMOD}/Net4MSX.pretty")(options "")(descr "Net4MSX concept footprints"))\n)\n')

# Self-contained native KiCad 6 schematic: exact module pin labels plus proposed
# Pico SPI nets; disconnected host, power and boot interfaces remain visible.
components=[('J1','MSX_Edge_50_Concept','MSX connector',msx_names,msx_nets,50,90),('U1','Pico_ThroughHole_Concept','Optional Pico',pico_labels,pico_nets,135,90),('U2','W5100S_Net4CPC','W5100S / Net4CPC',list(mod_labels.values()),mod_nets,225,90)]
libs=[]; instances=[]; wires=[]; labels=[]; symbol_paths=[]
for ref,foot,value,names,mapping,x,y in components:
    half=(len(names)+1)//2; height=(half+1)*2.54
    symid='Net4MSX:'+foot
    pins=[]
    for i,name in enumerate(names):
        left=i<half;row=i if left else i-half
        px=-22.86 if left else 22.86;py=height/2-2.54-row*2.54
        pins.append(f'(pin passive line (at {px} {py} {0 if left else 180}) (length 5.08) (name "{name}" (effects (font (size 1 1)))) (number "{i+1}" (effects (font (size 1 1)))))')
        # Library coordinates point upward, sheet coordinates downward.
        sx=x+px;sy=y-py;ex=sx+(-7.62 if left else 7.62)
        if str(i+1) in mapping:
            n=mapping[str(i+1)]
            wires.append(f'(wire (pts (xy {sx} {sy}) (xy {ex} {sy})) (stroke (width 0) (type default)) (uuid {uid(ref+str(i)+"wire")}))')
            labels.append(f'(label "{n}" (at {ex} {sy} {0 if left else 180}) (effects (font (size .9 .9)) (justify left bottom)) (uuid {uid(ref+str(i)+"label")}))')
    libs.append(f'''(symbol "{symid}" (pin_names (offset .8)) (in_bom yes) (on_board yes)
      (property "Reference" "{ref}" (id 0) (at 0 {height/2+5} 0) (effects (font (size 1.27 1.27))))
      (property "Value" "{value}" (id 1) (at 0 {height/2+2.5} 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Net4MSX:{foot}" (id 2) (at 0 0 0) (effects (font (size 1 1)) hide))
      (symbol "{foot}_0_1" (rectangle (start -17.78 {height/2}) (end 17.78 {-height/2}) (stroke (width .254) (type default)) (fill (type background))))
      (symbol "{foot}_1_1" {''.join(pins)}))''')
    sid=uid(ref)
    instances.append(f'''(symbol (lib_id "{symid}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (uuid {sid})
      (property "Reference" "{ref}" (id 0) (at {x} {y-height/2-5} 0) (effects (font (size 1.27 1.27))))
      (property "Value" "{value}" (id 1) (at {x} {y-height/2-2.5} 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Net4MSX:{foot}" (id 2) (at {x} {y} 0) (effects (font (size 1 1)) hide))
      {''.join(f'(pin "{i+1}" (uuid {uid(ref+str(i)+"pin")}))' for i in range(len(names)))})''')
    symbol_paths.append(f'(path "/{sid}" (reference "{ref}") (unit 1) (value "{value}") (footprint "Net4MSX:{foot}"))')
notes=['INTERFACE CONCEPT A0 - NOT A COMPLETE CIRCUIT - DO NOT FABRICATE',
 'MSX bus decode, translation, FIFO/mailbox and boot ROM are not implemented.',
 '5V_SLOT, MOD_5V_INPUT and PICO_VSYS are intentionally separate: power protection / sequencing TBD.',
 'Pico SPI: GP16 MISO / GP17 CS / GP18 SCK / GP19 MOSI; GP20 reset / GP21 interrupt.',
 'Module MODE = GND (SPI); RD/WR = MOD_3V3. Module 3V3 and Pico 3V3 are separate.',
 'Module pads 13-20 are unassigned in the Net4CPC device; do not infer electrical functions.',
 'All nets are UNROUTED. Pull-ups, bypass, protection and boot-safe outputs still require design.']
texts=[f'(text "{s}" (at 18 {155+i*5} 0) (effects (font (size {1.5 if i==0 else 1.1} {1.5 if i==0 else 1.1})) (justify left)) (uuid {uid("note"+str(i))}))' for i,s in enumerate(notes)]
sch=f'''(kicad_sch (version 20211123) (generator eeschema)
 (uuid {uid('sheet')}) (paper "A4")
 (title_block (title "Net4MSX interface concept") (rev "A0 - UNROUTED") (comment 1 "No completed MSX bus / ROM / power circuit"))
 (lib_symbols {''.join(libs)})
 {''.join(wires+labels+texts+instances)}
 (sheet_instances (path "/" (page "1")))
 (symbol_instances {''.join(symbol_paths)}))\n'''
(OUT/'Net4MSX.kicad_sch').write_text(sch)
(OUT/'Net4MSX.kicad_sym').write_text('(kicad_symbol_lib (version 20211014) (generator kicad_symbol_editor)\n'+''.join(v.replace('(symbol "Net4MSX:', '(symbol "',1) for v in libs)+')\n')
(OUT/'sym-lib-table').write_text('(sym_lib_table\n (lib (name "Net4MSX")(type "KiCad")(uri "${KIPRJMOD}/Net4MSX.kicad_sym")(options "")(descr "Net4MSX interface concept symbols"))\n)\n')

with (OUT/'pin-map.csv').open('w',newline='') as f:
    writer=csv.writer(f,lineterminator='\n');writer.writerow(['reference','pad','signal','net','status'])
    for ref,foot,value,names,mapping,*_ in components:
        for i,n in enumerate(names):writer.writerow([ref,i+1,n,mapping.get(str(i+1),''),'concept / unrouted'])

layout={'outline':outline,'thickness':1.6,'components':[],'pads':[],'models':models,'status':'CONCEPT A0 / UNROUTED'}
for fp in board.GetFootprints():
    pos=fp.GetPosition()
    layout['components'].append({'ref':fp.GetReference(),'x':pcb.ToMM(pos.x),'y':pcb.ToMM(pos.y),'angle':fp.GetOrientationDegrees()})
    for p in fp.Pads():
        pos=p.GetPosition();size=p.GetSize()
        layout['pads'].append({'ref':fp.GetReference(),'pad':p.GetNumber(),'x':pcb.ToMM(pos.x),'y':pcb.ToMM(pos.y),'w':pcb.ToMM(size.x),'h':pcb.ToMM(size.y),'hole':pcb.ToMM(p.GetDrillSize().x),'front':p.IsOnLayer(pcb.F_Cu),'back':p.IsOnLayer(pcb.B_Cu)})
(OUT/'placement.json').write_text(json.dumps(layout,indent=2)+'\n')
print('Generated schematic, PCB, project, footprints, models, pin map and placement data.')
