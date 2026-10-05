"""Original tileable cloud, cratered moon and masonry paintings; no source images used."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
rng=np.random.default_rng(90521)
out=Path(__file__).parent.parent/'frontend/assets/atmosphere';out.mkdir(parents=True,exist_ok=True)
n=np.zeros((512,1024))
for sigma,amp in [(62,1.0),(25,.47),(10,.22),(3,.055)]:
    layer=gaussian_filter(rng.normal(size=n.shape),sigma,mode='wrap');n+=layer/(layer.std()+1e-6)*amp
n=np.clip((n-n.min())/(n.max()-n.min()),0,1)
Image.fromarray(np.uint8(n*255)).save(out/'clouds.png')
s=256;im=Image.new('RGBA',(s,s));d=ImageDraw.Draw(im)
for y in range(s):
    for x in range(s):
        dx=(x-127.5)/127.5;dy=(y-127.5)/127.5;r=dx*dx+dy*dy
        if r<1:
            shade=.28+.7*np.sqrt(1-r);noise=rng.uniform(-.055,.055);v=int(255*np.clip(shade+noise,0,1));im.putpixel((x,y),(v,int(v*.96),int(v*.83),255))
for _ in range(95):
    x,y=rng.integers(18,238,2);r=int(rng.integers(4,18))
    if (x-128)**2+(y-128)**2<(119-r)**2:
        d.ellipse((x-r,y-r,x+r,y+r),fill=(135,130,113,255),outline=(222,211,178,255),width=1);d.arc((x-r+2,y-r+3,x+r-2,y+r-2),30,210,fill=(109,105,96,255),width=2)
im.save(out/'moon.png')
for name,base,bs in [('stone',(174,176,152),32),('floor',(139,143,129),48),('wood',(86,65,43),32),('roof',(158,93,44),16)]:
    a=np.zeros((256,256,3),dtype=np.uint8)
    noise=rng.normal(0,7,(256,256));waves=gaussian_filter(rng.normal(size=(256,256)),9,mode='wrap');waves/=waves.std()
    for c,b in enumerate(base):a[:,:,c]=np.clip(b+noise+waves*6,0,255)
    tile=Image.fromarray(a);dr=ImageDraw.Draw(tile)
    if name=='wood':
        for x in range(0,256,32):
            dr.line((x,0,x,256),fill=(43,34,28),width=2)
            for _ in range(10):
                xx=x+int(rng.integers(3,30));y=int(rng.integers(0,240));dr.line((xx,y,xx+int(rng.integers(-2,3)),y+50),fill=(64,47,34),width=1)
    else:
        for y in range(0,256,bs):
            dr.line((0,y,256,y),fill=tuple(int(b*.62) for b in base),width=2)
            offset=(y//bs%2)*bs
            for x in range(-bs*2+offset,256,bs*2):
                dr.line((x,y,x,y+bs),fill=tuple(int(b*.61) for b in base),width=2)
                dr.line((x+3,y+3,x+bs*2-4,y+3),fill=tuple(min(255,int(b*1.10)) for b in base))
    tile.save(out/(name+'.png'))
print('Original atmosphere and architectural textures exported.')
