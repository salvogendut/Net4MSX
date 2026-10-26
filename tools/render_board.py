"""Run with: blender -b --python tools/render_board.py

Geometric concept rendering from the generated KiCad placement data.
No invented copper tracks: the PCB is intentionally unrouted.
"""
from pathlib import Path
import json
import math
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware'
data=json.loads((OUT/'placement.json').read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)

def material(name,color,metal=0,rough=.4):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=rough
    return m
green=material('Carrier solder mask',(.015,.13,.10),.15)
gold=material('Gold edge contacts',(.78,.51,.16),.8,.23)
silver=material('Metal',(.5,.55,.61),.85,.27)
black=material('Black polymer',(.014,.019,.025),.05)
white=material('Silkscreen',(.82,.91,.88))
blue=material('W5100S module',(.02,.12,.27),.1)
picogreen=material('Pico PCB',(.025,.27,.17),.1)
amber=material('Amber markers',(.95,.42,.06),.15)
ground=material('Backdrop',(.045,.059,.078),.15,.55)

def box(name,loc,dims,mat,bevel=.25):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);obj=bpy.context.object;obj.name=name
    obj.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    obj.data.use_auto_smooth=True
    if bevel:
        mod=obj.modifiers.new('Edge radii','BEVEL');mod.width=bevel;mod.segments=3
        obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def text(body,x,y,z,size=2,mat=white,angle=0):
    c=bpy.data.curves.new('Text','FONT');c.body=body;c.size=size;c.align_x='CENTER';c.extrude=.008
    o=bpy.data.objects.new(body,c);bpy.context.collection.objects.link(o);o.location=(x,y,z);o.rotation_euler[2]=angle;o.data.materials.append(mat)
    return o

xy=[(x-90,95-y) for x,y in data['outline']]
n=len(xy);verts=[(x,y,z) for z in [0,1.6] for x,y in xy]
faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
mesh=bpy.data.meshes.new('Carrier outline');mesh.from_pydata(verts,[],faces);mesh.update()
carrier=bpy.data.objects.new('Net4MSX carrier - no routing',mesh);bpy.context.collection.objects.link(carrier);carrier.data.materials.append(green)

for p in data['pads']:
    x=p['x']-90;y=95-p['y']
    if p['ref']=='J1':
        for side,z in [('front',1.62),('back',-.02)]:
            if p[side]:box('Edge '+p['pad'],(x,y,z),(p['w'],p['h'],.035),gold,.08)
    else:
        box('Socket housing',(x,y,4.6),(2.2,2.3,6),black,.12)
        box('Socket contact',(x,y,7.65),(1.4,1.4,.1),gold,.12)
        box('Socket opening',(x,y,7.74),(.7,.7,.12),black,.06)

for c in data['components']:
    if c['ref']=='J1':continue
    cx,cy=c['x']-90,95-c['y'];angle=math.radians(c['angle'])
    def local(x,y,z):return (cx+x*math.cos(angle)-y*math.sin(angle),cy+x*math.sin(angle)+y*math.cos(angle),z+1.6)
    key='pico' if c['ref']=='U1' else 'module'
    for i,(center,dims,_) in enumerate(data['models'][key]):
        mat=picogreen if key=='pico' else blue
        if i==1:mat=silver
        if i==2:mat=black
        o=box(key+str(i),local(*center),dims,mat,.2);o.rotation_euler[2]=angle
    if key=='module':
        # RJ45 mouth is a recessed dark face in an approximate connector body.
        o=box('RJ45 opening',local(.635,-23.3,15),(12,.25,8.8),black,.25);o.rotation_euler[2]=angle
        for i in range(8):
            o=box('RJ45 contact',local(-3.3+i*1.12,-23.5,16),(.45,.2,3.4),gold,.03);o.rotation_euler[2]=angle
        text('W5100S',*local(-1,3.8,10.25),1.35,white,angle)
        for x,y in [(-9,14),(8,12),(-8,5),(9,0),(-9,-2)]:
            o=box('Illustrative passives',local(x,y,9.4),(1.2,2.3,1),black,.1);o.rotation_euler[2]=angle
        text('SPI / PARALLEL',*local(0,16,9),1.15,white,angle)
    else:
        text('RP2040',*local(0,0,9.6),1.3)
        text('PICO',*local(0,-15,8.6),2)
        box('Boot button',local(0,14,9.5),(4,3,1.6),white,.3)
        box('USB opening',local(0,25.1,10),(6,.2,1.5),black,.15)

text('Net4MSX',0,-12,1.66,4)
text('W5100S  /  UNAPI  /  PICO OPTION',0,-17,1.66,1.55)
for x,w,label in [(-19,32,'BUS INTERFACE'),(18.5,33,'ROM / POWER')]:
    for dx,dy,sx,sy in [(0,5.5,w,.2),(0,-5.5,w,.2),(-w/2,0,.2,11),(w/2,0,.2,11)]:
        box('Reserved area outline',(x+dx,-25.5+dy,1.65),(sx,sy,.025),white,0)
    text(label,x,-25,1.68,1.7)
    text('RESERVED',x,-28,1.68,1.25,amber)
text('CONCEPT A0  -  UNROUTED',0,-33,1.66,1.5,amber)
text('50',-30.48,-36,1.66,1);text('2',30.48,-36,1.66,1)

box('Floor',(0,0,-1),(700,700,1),ground,.1)
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.cycles.use_denoising=False
scene.world.color=(.22,.22,.22)
for loc,power,size in [((30,25,150),210000,100),((-100,30,90),140000,80),((50,-100,70),110000,70)]:
    bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size
    o.rotation_euler=(Vector((0,0,0))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(110,-145,170));camera=bpy.context.object
camera.rotation_euler=(Vector((0,0,4))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=145;scene.camera=camera
scene.render.resolution_x=1280;scene.render.resolution_y=1120;scene.render.resolution_percentage=100
scene.view_settings.view_transform='Filmic';scene.view_settings.look='Medium High Contrast'
scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(OUT/'renders'/'Net4MSX-concept-3d.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Net4MSX-concept.blend'))
bpy.ops.render.render(write_still=True)
camera.location=(0,0,180);camera.rotation_euler=(0,0,0);camera.data.ortho_scale=110
scene.cycles.samples=16
scene.render.filepath=str(OUT/'renders'/'Net4MSX-concept-top.png')
bpy.ops.render.render(write_still=True)
