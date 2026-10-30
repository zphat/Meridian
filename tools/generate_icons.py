"""Generate matching Meridian asterisk logos for Windows, Linux and web."""
from pathlib import Path
from math import cos, sin, pi
from PIL import Image, ImageDraw, ImageFilter

assets=Path("assets")
assets.mkdir(parents=True, exist_ok=True)
size=256
factor=4
n=size*factor
dark=(12,17,14,255)
lime=(195,255,56,255)

def star(draw,width,color):
    cx=cy=n//2
    radius=92*factor
    for i in range(8):
        a=i*pi/4
        x=cx+int(radius*cos(a)); y=cy+int(radius*sin(a))
        draw.line([(cx,cy),(x,y)],fill=color,width=width,joint="curve")
        r=width//2
        draw.ellipse((x-r,y-r,x+r,y+r),fill=color)

background=Image.new("RGBA",(n,n),(0,0,0,0))
d=ImageDraw.Draw(background)
d.rounded_rectangle((0,0,n-1,n-1),radius=40*factor,fill=dark)
# A restrained glow preserves recognition at 16px icon sizes.
glow=Image.new("RGBA",(n,n),(0,0,0,0))
star(ImageDraw.Draw(glow),32*factor,(147,250,25,110))
glow=glow.filter(ImageFilter.GaussianBlur(9*factor))
background=Image.alpha_composite(background,glow)
# Refine the rounded tile edge without enclosing the logo in a globe.
d=ImageDraw.Draw(background)
d.rounded_rectangle((3*factor,3*factor,n-4*factor,n-4*factor),
                    radius=38*factor,outline=(61,103,50,130),width=2*factor)
star(d,25*factor,lime)
background=background.resize((size,size),Image.Resampling.LANCZOS)
background.save(assets/"meridian.png",optimize=True)
background.save(assets/"meridian.ico",format="ICO",
                sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
# Versioned icon filename forces Windows to refresh legacy desktop shortcut cache.
background.save(assets/"meridian-desktop-2026.ico",format="ICO",
                sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect x="0.6" y="0.6" width="62.8" height="62.8" rx="13.5" fill="#0c110e" stroke="#36582c" stroke-width="1.2"/>
<g stroke="#c3ff38" stroke-linecap="round" stroke-width="7.5">
<path d="M32 11v42M11 32h42M17.15 17.15l29.7 29.7M46.85 17.15l-29.7 29.7"/>
</g></svg>'''
Path("static/favicon.svg").write_text(svg+"\n",encoding="utf-8")
print("Generated coordinated Meridian app, installer, taskbar and website logos.")
