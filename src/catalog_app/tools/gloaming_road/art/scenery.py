"""The Gloaming Road — original environment art, deterministic editable source.

Run: python art/scenery.py   (Pillow; no network, source images or asset downloads.)
All plants are pixel-painted from stem / leaflet / petal primitives here, NOT
extracted from the visual references. The GLB contains individually named,
textured authored mesh prototypes for runtime batching, not a scene of primitives.
"""
from __future__ import annotations
import io
import json
import math
import random
import struct
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / 'frontend' / 'assets' / 'scenery'
OUT.mkdir(parents=True, exist_ok=True)
R = random.Random(0x61_04_2026)
T = 256


def colour(c, d):
    return tuple(max(0, min(255, int(v+d))) for v in c)


def leaf(draw, x, y, length, width, angle, fill, vein=True):
    vx, vy = math.cos(angle), math.sin(angle)
    nx, ny = -vy, vx
    points = [(x, y), (x+vx*length*.33+nx*width, y+vy*length*.33+ny*width),
              (x+vx*length*.78+nx*width*.58, y+vy*length*.78+ny*width*.58),
              (x+vx*length, y+vy*length),
              (x+vx*length*.57-nx*width*.66, y+vy*length*.57-ny*width*.66)]
    draw.polygon(points, fill=fill)
    if vein:
        draw.line([(x, y), (x+vx*length*.91, y+vy*length*.91)], fill=colour(fill[:3], 20)+(255,), width=1)


def lupines(tile, variant):
    d = ImageDraw.Draw(tile)
    pinks = [(190, 74, 137), (216, 103, 167), (205, 122, 189)]
    col = pinks[variant]
    # Three unequal stems per cutout, curved axis and alternating veined leaves.
    for stem, (bx, top, bend) in enumerate([(53, 72, -9), (181, 52, 13), (125, 10, 4)]):
        base = 249
        for sy in range(base, top+17, -1):
            t = (base-sy)/(base-top)
            sx = bx+bend*t*t+math.sin(t*3.1+stem)*2
            d.line([(sx, sy), (sx+2, sy-2)], fill=(71, 112+int(t*17), 41, 255), width=3)
            if sy < base-8 and sy > top+88 and sy % 15 == stem*3:
                for side in [-1, 1]:
                    ln = (30+(base-sy)*.10)*(1-t*.45)
                    a = -math.pi/2+side*(1.06+R.random()*.24)
                    leaf(d, sx, sy, ln, 5.8, a, (86+R.randrange(39), 128+R.randrange(39), 43+R.randrange(22), 255))
        flower_bottom = min(base-71, top+125)
        for sy in range(flower_bottom, top+2, -4):
            t = (sy-top)/(flower_bottom-top)
            radius = 2+t*16.3
            center = bx+bend*((base-sy)/(base-top))**2
            for k in range(6):
                px = center+(k/5*2-1)*radius+R.uniform(-2, 2)
                py = sy+R.uniform(-2, 2)
                shade = R.randint(-30, 27)+(7 if k<3 else -8)
                c = colour(col, shade)+(255,)
                d.polygon([(px-3, py), (px-1, py-3), (px+3, py-1), (px+4, py+2), (px, py+3)], fill=c)
                d.line([(px-2, py), (px+2, py-1)], fill=colour(col, 52)+(255,), width=1)
                d.point((px+1, py+2), fill=(105, 48, 83, 255))
        d.ellipse((bx+bend-2, top-1, bx+bend+2, top+5), fill=colour(col, 43)+(255,))
    # Basal rosette gives the spires a substantial green understory.
    for j in range(32):
        bx = R.randint(21, 235)
        leaf(d, bx, 252, R.randint(37, 78), R.randint(5, 10), -math.pi/2+R.uniform(-1.3, 1.3), (57+R.randrange(46), 108+R.randrange(54), 30+R.randrange(32), 255))


def carpet(tile, palette):
    d = ImageDraw.Draw(tile)
    for j in range(34):
        x, y = R.randint(13, 241), R.randint(67, 232)
        d.line([(x+R.randint(-9, 9), 253), (x, y)], fill=(63, 104+R.randrange(28), 39, 255), width=2)
        for s in [-1, 1]:
            leaf(d, x, y+20, R.randint(11, 26), 3.3, -math.pi/2+s*1.1, (78, 133+R.randrange(29), 43, 255))
        c = palette[j % len(palette)]
        radius = R.randint(4, 7)
        for petal in range(5):
            a=petal*math.tau/5
            px, py=x+math.cos(a)*radius*.82, y+math.sin(a)*radius*.62
            d.ellipse((px-3, py-2, px+3, py+3), fill=colour(c, R.randint(-18, 12))+(255,))
        d.ellipse((x-2, y-2, x+2, y+2), fill=(232, 184, 73, 255))


def grasses(tile):
    d=ImageDraw.Draw(tile)
    for j in range(76):
        x=R.randint(14, 242); h=R.randint(47, 211); lean=R.randint(-45, 45)
        c=(53+R.randrange(47), 89+R.randrange(63), 30+R.randrange(30), 255)
        d.polygon([(x-2, 253), (x+3, 253), (x+lean*.35+2, 253-h*.6), (x+lean, 253-h), (x+lean*.29-1, 253-h*.48)], fill=c)
        if j%8==0:
            for k in range(7):
                y=253-h+k*4
                d.line([(x+lean-1, y+7), (x+lean+(-1 if k%2 else 1)*5, y)], fill=(159, 159, 83, 255), width=2)


def ferns(tile, autumn=False):
    d=ImageDraw.Draw(tile)
    for f in range(9):
        a=-math.pi/2+(f-4)*.265
        ln=R.randint(128, 211); bx=125+R.randint(-12, 12); by=253
        for k in range(1, 19):
            t=k/19
            x=bx+math.cos(a)*ln*t; y=by+math.sin(a)*ln*t+math.sin(t*math.pi)*12
            d.line([(bx+math.cos(a)*ln*(t-.06), by+math.sin(a)*ln*(t-.06)), (x,y)], fill=(87, 115, 48, 255), width=2)
            length=29*math.sin(t*math.pi)**.65*(1.12-t*.35)
            for side in [-1, 1]:
                c=(68+R.randrange(37), 112+R.randrange(54), 41+R.randrange(30), 255) if not autumn else (174+R.randrange(50), 111+R.randrange(38), 32+R.randrange(23), 255)
                leaf(d,x,y,length,3.2,a+side*1.09,c)


def shrub(tile):
    d=ImageDraw.Draw(tile)
    for j in range(13):
        x=128+R.randint(-76,76); y=R.randint(60,192)
        d.line([(128,253),(x,y)],fill=(105,80,45,255),width=3)
    for j in range(230):
        x=128+R.gauss(0,47); y=149+R.gauss(0,37)
        if not(10<x<246 and 29<y<242):continue
        c=R.choice([(193,140,39,255),(169,100,32,255),(216,162,45,255),(134,130,40,255),(111,117,36,255)])
        leaf(d,x,y,R.randint(11,24),R.randint(3,6),R.random()*math.tau,c)
    for j in range(19):
        x,y=R.randint(68,188),R.randint(91,195)
        d.ellipse((x-2,y-2,x+3,y+2),fill=(170,57,42,255))


def leaf_cloud(tile, gold=False):
    d=ImageDraw.Draw(tile)
    for j in range(650):
        a=R.random()*math.tau; rad=math.sqrt(R.random())
        x=128+math.cos(a)*rad*105; y=127+math.sin(a)*rad*108
        shade=int((1-y/256)*26)+R.randint(-25,25)
        base=(136,133,41) if gold else (63,103,48)
        c=colour(base,shade)+(255,)
        leaf(d,x,y,R.randint(10,25),R.randint(3,7),-2.5+R.random()*4.5,c)


def needles(tile):
    d=ImageDraw.Draw(tile)
    d.line([(128,249),(125,19)],fill=(92,81,47,255),width=4)
    for level in range(20):
        y=31+level*10; width=12+level*4.5
        for side in [-1,1]:
            endx=128+side*width; endy=y+28
            d.line([(128,y),(endx,endy)],fill=(65,91,57,255),width=2)
            for k in range(12):
                t=k/12; x=128+side*width*t; yy=y+28*t
                c=R.choice([(56,93,63,255),(71,113,77,255),(83,125,78,255),(40,76,56,255)])
                d.line([(x,yy),(x+side*12,yy-14)],fill=c,width=2)
                d.line([(x,yy),(x+side*14,yy+9)],fill=colour(c[:3],-6)+(255,),width=2)


foliage=Image.new('RGBA',(1024,1024),(0,0,0,0))
for i in range(16):
    tile=Image.new('RGBA',(256,256),(0,0,0,0))
    if i<3:lupines(tile,i)
    elif i==3:carpet(tile,[(221,225,203),(243,231,212),(202,220,195)])
    elif i==4:carpet(tile,[(177,157,214),(199,174,229),(159,153,212)])
    elif i==5:carpet(tile,[(231,183,53),(242,208,79),(213,154,37)])
    elif i==6:grasses(tile)
    elif i==7:ferns(tile)
    elif i==8:shrub(tile)
    elif i==9:leaf_cloud(tile)
    elif i==10:needles(tile)
    elif i==11:leaf_cloud(tile,True)
    elif i==12:ferns(tile,True)
    elif i==13:carpet(tile,[(137,171,112),(168,187,117)])
    elif i==14:carpet(tile,[(115,131,212),(154,146,231)])
    else:
        d=ImageDraw.Draw(tile)
        d.polygon([(128,9),(95,86),(103,151),(116,199),(151,220),(166,180),(158,112),(142,74)],fill=(238,129,42,255))
        d.polygon([(128,54),(112,128),(121,185),(139,205),(149,169),(135,119)],fill=(255,205,86,255))
        d.polygon([(128,119),(121,159),(132,192),(140,166)],fill=(255,244,188,255))
    # Two transparent texel gutters per cell protect mipmapped atlas borders.
    tile.paste((0,0,0,0),(0,0,2,256));tile.paste((0,0,0,0),(254,0,256,256))
    tile.paste((0,0,0,0),(0,0,256,2));tile.paste((0,0,0,0),(0,254,256,256))
    foliage.paste(tile,((i%4)*256,(i//4)*256))
foliage.save(OUT/'foliage-atlas.png',optimize=True)


def ground_tile(kind):
    bases={'meadow':(87,119,52),'earth':(120,97,68),'stone':(124,128,120),'granite':(164,166,158),'forest':(72,83,51),
           'bark':(104,89,62),'masonry':(149,144,118),'cutwood':(161,128,78)}
    base=bases[kind]; im=Image.new('RGB',(256,256)); p=im.load()
    for y in range(256):
        for x in range(256):
            wave=7*math.sin(x*math.tau/128)*math.sin(y*math.tau/256)+5*math.cos((x+y)*math.tau/64)
            if kind=='bark':wave+=14*math.sin(x*.31+math.sin(y*.057))*math.sin(x*.073)
            if kind=='cutwood':wave+=13*math.sin(math.hypot(x-128,y-128)*.46)
            p[x,y]=colour(base,wave+R.gauss(0,8))
    d=ImageDraw.Draw(im)
    for j in range(9500):
        x,y=R.randrange(256),R.randrange(256)
        c=colour(base,R.randint(-30,26))
        if kind in ('meadow','forest'):
            if kind=='forest' and j%7==0:c=R.choice([(137,112,57),(108,84,43),(137,128,68)])
            d.line([(x,y),(x+R.randint(-2,3),y-R.randint(1,6))],fill=c,width=1)
        else:d.point((x,y),fill=c)
    if kind in ('stone','masonry','granite'):
        for j in range(48):
            x,y=R.randrange(256),R.randrange(256)
            points=[(x,y)]
            for k in range(R.randint(2,5)):
                x+=R.randint(-12,17);y+=R.randint(3,14);points.append((x,y))
            d.line(points,fill=colour(base,-28),width=1)
        for j in range(190):
            x,y=R.randrange(256),R.randrange(256)
            d.ellipse((x,y,x+R.randint(1,5),y+R.randint(1,4)),fill=R.choice([(143,153,103),(106,126,81),(158,159,130)]))
    if kind=='bark':
        for j in range(65):
            x=R.randrange(256);y=R.randrange(256)
            d.line([(x,y),(x-2,y+17),(x+3,y+45),(x+1,y+71)],fill=colour(base,R.randint(-37,-13)),width=R.choice([1,1,2]))
            d.line([(x+3,y+1),(x+2,y+14),(x+6,y+42)],fill=colour(base,24),width=1)
    if kind=='cutwood':
        for rad in range(9,166,11):d.arc((128-rad,128-rad,128+rad,128+rad),0,360,fill=(112,86,51),width=1)
        d.line([(128,128),(181,140),(232,166)],fill=(101,78,51),width=2)
    # Extend the inner edge into a gutter, so bilinear samples cannot touch the neighbouring tile.
    im.paste(im.crop((2,0,3,256)).resize((2,256)),(0,0));im.paste(im.crop((253,0,254,256)).resize((2,256)),(254,0))
    im.paste(im.crop((0,2,256,3)).resize((256,2)),(0,0));im.paste(im.crop((0,253,256,254)).resize((256,2)),(0,254))
    return im

terrain_atlas=Image.new('RGB',(512,512))
for i,kind in enumerate(['meadow','earth','granite','forest']):terrain_atlas.paste(ground_tile(kind),((i%2)*256,(i//2)*256))
terrain_atlas.save(OUT/'ground-atlas.png',optimize=True)
solid_atlas=Image.new('RGB',(512,512))
for i,kind in enumerate(['bark','stone','masonry','cutwood']):solid_atlas.paste(ground_tile(kind),((i%2)*256,(i//2)*256))
solid_atlas.save(OUT/'scenery-atlas.png',optimize=True)

# ---- Original geometry authoring: tapered forked trees, irregular rocks, fronds. ----
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def cross(a,b):return(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a):
    l=math.sqrt(sum(x*x for x in a)) or 1
    return tuple(x/l for x in a)


def atlas_uv(tile,u,v,tiles=2):
    # glTF image coordinates use top-left; v here is a conventional bottom-up authoring UV.
    return ((tile%tiles+.009+u*.982)/tiles,(tile//tiles+.009+(1-v)*.982)/tiles)


class Mesh:
    def __init__(self,name,material=0):
        self.name=name;self.material=material;self.p=[];self.n=[];self.uv=[];self.c=[];self.idx=[]
    def face(self,points,tile=0,colour=(1,1,1),uv=None,tiles=2):
        normal=norm(cross(sub(points[1],points[0]),sub(points[2],points[0])))
        start=len(self.p)//3
        if uv is None:uv=[(0,0),(1,0),(1,1),(0,1)] if len(points)==4 else [(0,0),(1,0),(.5,1)]
        for point,tex in zip(points,uv):
            self.p.extend(point);self.n.extend(normal);self.uv.extend(atlas_uv(tile,*tex,tiles));self.c.extend(colour)
        self.idx.extend([start,start+1,start+2])
        if len(points)==4:self.idx.extend([start,start+2,start+3])
    def tube(self,a,b,r0,r1,tile=0,sides=6,colour=(1,1,1),caps=True):
        axis=norm(sub(b,a));right=norm(cross(axis,(1,0,0) if abs(axis[1])>.93 else (0,1,0)));forward=cross(axis,right)
        rings=[]
        for center,rad in [(a,r0),(b,r1)]:
            rings.append([add(center,add(mul(right,math.cos(i*math.tau/sides)*rad),mul(forward,math.sin(i*math.tau/sides)*rad))) for i in range(sides)])
        for i in range(sides):
            j=(i+1)%sides
            self.face([rings[0][i],rings[0][j],rings[1][j],rings[1][i]],tile,colour)
            if caps:
                ui=(.5+math.cos(i*math.tau/sides)*.48,.5+math.sin(i*math.tau/sides)*.48)
                uj=(.5+math.cos(j*math.tau/sides)*.48,.5+math.sin(j*math.tau/sides)*.48)
                self.face([a,rings[0][j],rings[0][i]],3,colour,uv=[(.5,.5),uj,ui])
                self.face([b,rings[1][i],rings[1][j]],3,colour,uv=[(.5,.5),ui,uj])
    def cloud(self,center,radii,tile,phase=0):
        # Three bent, intersecting leaf shells, each a volume-filling textured canopy lobe.
        for k in range(3):
            a=phase+k*math.pi/3;right=(math.cos(a),0,math.sin(a));up=(0,1,0);bend=(math.sin(a)*.32,0,-math.cos(a)*.32)
            pts=[add(center,add(mul(right,-radii[0]),mul(up,-radii[1]))),add(center,add(mul(right,radii[0]),mul(up,-radii[1]))),
                 add(center,add(mul(right,radii[0]),mul(up,radii[1]))),add(center,add(mul(right,-radii[0]),mul(up,radii[1])))]
            mid=add(center,mul(bend,radii[2]))
            for j in range(4):
                self.face([pts[j],pts[(j+1)%4],mid],tile,(1,1,1),uv=[[(0,0),(1,0),(1,1),(0,1)][j],[(0,0),(1,0),(1,1),(0,1)][(j+1)%4],(.5,.5)],tiles=4)


meshes=[]
for kind in ['oak','rowan']:
    trunk=Mesh(kind+'_solid');crown=Mesh(kind+'_crown',1)
    factor=1 if kind=='oak' else .86
    def scaled(p):return mul(p,factor)
    trunk.tube(scaled((0,0,0)),scaled((.10,3.8,-.09)),.43*factor,.29*factor,caps=False)
    trunk.tube(scaled((.10,3.8,-.09)),scaled((-.15,7.45,.22)),.29*factor,.10*factor,caps=False)
    for j in range(4):
        a=j*math.tau/4+.43
        trunk.tube(scaled((0,.52,0)),scaled((math.cos(a)*.95,.02,math.sin(a)*.95)),.27*factor,.08*factor,sides=5,caps=False)
    lobes=[(-1.65,5.5,.40,2.15,1.75),(1.65,6.0,.3,2.0,1.8),(.2,6.9,-1.62,2.10,1.65),(-1.2,7.7,-.55,1.85,1.75),(1.0,8.3,.25,1.9,1.7),(-.25,9.1,-.4,1.65,1.50)]
    for j,(x,y,z,rx,ry) in enumerate(lobes):
        if j<3:trunk.tube(scaled((.08,3.8+j*.52,0)),scaled((x,y-.55,z)),.19*factor,.08*factor,caps=False)
        crown.cloud(scaled((x,y,z)),(rx*factor,ry*factor,1.6*factor),11 if kind=='rowan' else 9,phase=j*.71)
    meshes += [trunk,crown]
fir=Mesh('fir_solid');fronds=Mesh('fir_crown',1)
fir.tube((0,0,0),(.1,10.85,-.11),.40,.045,caps=False)
for tier in range(6):
    y=3.0+tier*1.27; radius=3.0-tier*.39
    for j in range(6):
        a=j*math.tau/6+tier*.58;ux,uz=math.cos(a),math.sin(a);nx,nz=-uz,ux
        p0=(ux*.08,y+.65,uz*.08);p1=(ux*radius+nx*.65,y-.65,uz*radius+nz*.65)
        p2=(ux*(radius+.17),y-1.0,uz*(radius+.17));p3=(ux*radius-nx*.65,y-.65,uz*radius-nz*.65)
        fronds.face([p0,p1,p2,p3],10,colour=(.92,1,.91),uv=[(.5,1),(0,.15),(.5,0),(1,.15)],tiles=4)
        # A second raised needle fan makes each whorl read as fronds instead of a polygon cone.
        fronds.face([p0,(ux*radius+nx*.5,y-.15,uz*radius+nz*.5),p2,(ux*radius-nx*.5,y-.15,uz*radius-nz*.5)],10,tiles=4)
fronds.cloud((.02,10.35,-.08),(.55,1.0,.4),10)
meshes += [fir,fronds]


def rock_mesh(mesh,center=(0,0,0),scale=(1,1,1),seed=32,tile=1):
    r=random.Random(seed);rings=[];sides=8
    for level,(y,radius) in enumerate([(0,.88),(.36,1.18),(.96,.82),(1.30,.36)]):
        ring=[]
        for j in range(sides):
            a=j*math.tau/sides+level*.13;rad=radius*r.uniform(.82,1.14)
            ring.append(add(center,(math.cos(a)*rad*scale[0],(y+r.uniform(-.06,.06))*scale[1],math.sin(a)*rad*scale[2])))
        rings.append(ring)
    for k in range(3):
        for j in range(sides):
            c=(.77,.91,.62) if k==2 and j%3!=0 else (.95,.98,.94)
            mesh.face([rings[k][j],rings[k+1][j],rings[k+1][(j+1)%sides],rings[k][(j+1)%sides]],tile,c)
    for j in range(sides):mesh.face([rings[-1][j],add(center,(0,1.34*scale[1],0)),rings[-1][(j+1)%sides]],tile,(.71,.86,.52))

rock=Mesh('rock_solid');rock_mesh(rock);meshes.append(rock)
log=Mesh('log_solid')
log.tube((-1.73,.33,-.1),(1.73,.37,.12),.39,.31,sides=8,colour=(.80,.94,.66))
log.tube((.38,.52,.04),(.72,1.08,.50),.16,.035,sides=5,colour=(.91,.97,.77))
meshes.append(log)
ruin=Mesh('ruin_solid')
rock_mesh(ruin,(0,0,0),(.62,.63,.63),82,2)
rock_mesh(ruin,(.07,.58,-.04),(.53,.54,.55),47,2)
rock_mesh(ruin,(-.05,1.08,.03),(.44,.49,.49),5,2)
meshes.append(ruin)
rest=Mesh('rest_solid');flames=Mesh('rest_crown',1)
for j in range(10):
    a=j*math.tau/11+.34
    # Leave a broad entry notch toward +Z.
    if abs(a-math.pi/2)<.45:continue
    rock_mesh(rest,(math.cos(a)*2.30,-.055,math.sin(a)*2.30),(.33,.31,.31),j*27+8,1)
rock_mesh(rest,(1.27,0,.11),(.65,.44,.59),412,2)
for j in range(3):
    x=1.06+j*.21;z=.10+(j%2)*.19;h=.33+j*.075
    rest.tube((x,.52,z),(x,.52+h,z),.067,.060,tile=2,sides=7,colour=(1,.92,.63))
    flames.cloud((x,.52+h+.095,z),(.055,.105,.03),15,phase=j*.8)
meshes += [rest,flames]

# Minimal glTF 2.0 writer: flat diffuse textures, named meshes, embedded PNGs.
blob=bytearray();views=[];accessors=[]

def append_bytes(data,target=None):
    while len(blob)%4:blob.append(0)
    index=len(views);view={'buffer':0,'byteOffset':len(blob),'byteLength':len(data)}
    if target:view['target']=target
    blob.extend(data);views.append(view);return index


def accessor(values,components,component_type=5126):
    code='f' if component_type==5126 else 'I'
    view=append_bytes(struct.pack('<'+code*len(values),*values),34962 if component_type==5126 else 34963)
    entry={'bufferView':view,'componentType':component_type,'count':len(values)//components,'type':{1:'SCALAR',2:'VEC2',3:'VEC3',4:'VEC4'}[components]}
    if components==3:
        entry['min']=[min(values[i::3]) for i in range(3)];entry['max']=[max(values[i::3]) for i in range(3)]
    index=len(accessors);accessors.append(entry);return index

images=[]
for name in ['scenery-atlas.png','foliage-atlas.png']:
    images.append({'name':name,'bufferView':append_bytes((OUT/name).read_bytes()),'mimeType':'image/png'})
gltf_meshes=[];nodes=[]
for mesh in meshes:
    attrs={'POSITION':accessor(mesh.p,3),'NORMAL':accessor(mesh.n,3),'TEXCOORD_0':accessor(mesh.uv,2),'COLOR_0':accessor(mesh.c,3)}
    primitive={'attributes':attrs,'indices':accessor(mesh.idx,1,5125),'material':mesh.material,'mode':4}
    gltf_meshes.append({'name':mesh.name,'primitives':[primitive]})
    nodes.append({'name':mesh.name,'mesh':len(gltf_meshes)-1})
materials=[{'name':'weathered-scenery','pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':1},'doubleSided':False},
            {'name':'leaf-cutout','pbrMetallicRoughness':{'baseColorTexture':{'index':1},'metallicFactor':0,'roughnessFactor':1},'alphaMode':'MASK','alphaCutoff':.37,'doubleSided':True}]
gltf={'asset':{'version':'2.0','generator':'The Gloaming Road original scenery.py — deterministic bespoke meshes and pixel painting'},
      'scene':0,'scenes':[{'name':'Original scenery prototypes — not world placement','nodes':list(range(len(nodes)))}],
      'nodes':nodes,'meshes':gltf_meshes,'materials':materials,'textures':[{'sampler':0,'source':0},{'sampler':0,'source':1}],
      'samplers':[{'magFilter':9728,'minFilter':9986,'wrapS':33071,'wrapT':33071}],
      'images':images,'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors,
      'extras':{'license':'Original art authored for The Gloaming Road. No third-party imagery.','units':'metres','up':'+Y','atlasTilePixels':256}}
encoded=json.dumps(gltf,separators=(',',':')).encode()
encoded+=b' '*((-len(encoded))%4);blob+=b'\x00'*((-len(blob))%4)
header=struct.pack('<4sII',b'glTF',2,12+8+len(encoded)+8+len(blob))
glb=header+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+bytes(blob)
(OUT/'gloaming-scenery.glb').write_bytes(glb)
manifest={'generator':'art/scenery.py','seed':'0x61042026','textures':{'foliage-atlas.png':[1024,1024],'ground-atlas.png':[512,512],'scenery-atlas.png':[512,512]},
          'meshTriangles':{m.name:len(m.idx)//3 for m in meshes},'prototypes':['oak','rowan','fir','rock','log','ruin','rest'],
          'foliageTiles':['rose spires','magenta spires','lilac spires','white stitchwort','lilac carpet','gold buttercups','grasses','fern','amber shrub','oak foliage','fir needles','rowan foliage','bracken','clover','blue flowers','candle flame']}
(OUT/'scenery-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'Authored {len(meshes)} named mesh parts; {sum(len(m.idx)//3 for m in meshes):,} source triangles; GLB {len(glb):,} bytes.')
for path in sorted(OUT.iterdir()):print(path.name, path.stat().st_size)
