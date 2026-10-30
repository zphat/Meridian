"""Generate Meridian's globe/compass Windows and desktop icons."""
from pathlib import Path
from PIL import Image, ImageDraw

path=Path("assets")
path.mkdir(parents=True,exist_ok=True)
scale=4
n=256*scale
lime=(209,255,74,255)
muted=(209,255,74,90)
im=Image.new("RGBA",(n,n),(0,0,0,0))
d=ImageDraw.Draw(im)
d.rounded_rectangle((0,0,n-1,n-1),radius=56*scale,fill=(18,24,19,255))
d.ellipse((36*scale,36*scale,220*scale,220*scale),outline=lime,width=10*scale)
for line in ((128,24,128,232),(24,128,232,128),(60,60,196,196),(196,60,60,196)):
    d.line(tuple(v*scale for v in line),fill=muted,width=5*scale)
d.ellipse((111*scale,111*scale,145*scale,145*scale),fill=lime)
im=im.resize((256,256),Image.Resampling.LANCZOS)
im.save(path/"meridian.png",format="PNG",optimize=True)
im.save(path/"meridian.ico",format="ICO",sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
