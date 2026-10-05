#!/usr/bin/env python3
"""The Gloaming Road: deterministic original composition and offline sound design.

Run from the workspace: .venv/bin/python src/catalog_app/tools/gloaming_road/audio-source/render.py
No recordings, soundfonts, reference audio, external downloads or runtime oscillators.
The first run writes an editable event score; later runs read that score unchanged.
Use --rewrite-score to regenerate the compositional event list; --only music|ambience|effects
renders a subset and rebuilds the catalog using the other existing manifest entries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "audio-source"
OUT = ROOT / "frontend" / "assets" / "audio"
SR = 24_000
TAU = math.tau
SEED = 20261005
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# This five-note cell is original to this project: D4, F4, E4, A4, C5.
# The larger D-Dorian palette is D E F G A B C; not a transcription.
MOTIF = [62, 65, 64, 69, 72]
CHORDS = {
    "d": [38, 50, 57, 62, 64, 65], "c": [36, 48, 55, 60, 62, 64],
    "g": [43, 50, 55, 57, 59, 62], "a": [33, 45, 52, 57, 60, 64],
    "f": [41, 48, 53, 57, 60, 64], "ds": [38, 45, 50, 57, 62, 67],
}
# Explicitly composed four-bar phrases, in quarter-note beats. Gaps are intentional.
PHRASES = [
    [(0,62,1.25), (1.5,65,.5), (2.25,64,.55), (3.25,69,1.3), (5,72,.75),
     (6,69,.75), (7,64,.8), (8.25,62,1.15), (10.5,60,.5), (11.25,62,.6)],
    [(0,62,1.8), (2.25,65,.5), (3.5,64,1.25), (5.25,69,.5), (6,72,1.6),
     (8,74,.7), (9.5,72,.7), (10.5,69,1.1)],
    [(0.5,74,1.15), (2,72,.65), (3,69,1.3), (5,67,.65), (6.25,65,.55),
     (7.25,64,1.2), (9.5,62,1.7)],
    [(0,65,1.25), (1.75,64,.7), (3,62,1.25), (5.25,57,.5), (6,60,1.6),
     (8.5,64,.75), (10,62,1.5)],
    [(0,62,.65), (.85,65,.65), (2,64,.55), (3,69,1.25), (4.6,72,.6),
     (6.25,76,.9), (7.5,74,.65), (9,72,1), (10.5,69,.9)],
    [(0.5,60,.7), (1.5,62,1.1), (3.25,65,.6), (4.25,64,1.1),
     (6.5,57,1.5), (9,62,2.25)],
]


def rng_for(name: str) -> np.random.Generator:
    return np.random.default_rng(SEED + int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little"))


def compose_score() -> dict:
    tracks = {}
    progression = ["d", "d", "c", "g", "d", "f", "a", "d", "c", "g", "f", "a", "d", "c", "ds", "d"]
    for name, bars, beat, order in [
        ("title",16,1.25,[0,1,2,5]),
        ("meadow",32,1.25,[0,1,3,2,4,1,3,5]),
        ("forest",32,1.25,[5,0,3,2,1,3,2,5]),
    ]:
        events = []
        def note(at, pitch, dur, instrument, level, pan=0):
            events.append({"t":round(at*beat,5), "midi":pitch, "duration":round(dur*beat,5),
                           "instrument":instrument, "level":round(level,4), "pan":round(pan,3)})
        for bar in range(bars):
            chord = CHORDS[progression[(bar + (4 if name == "forest" else 0)) % 16]]
            # Broken consort voicing, not a continuous unchanging drone. Cadential gaps
            # in bars 7/15 leave space for the melodic line and the field ambience.
            if bar % 8 != 7:
                register = -12 if name == "forest" else 0
                for j, pitch in enumerate(chord[1:5]):
                    note(bar*3 + j*.035, pitch+register, 2.55 if bar%4!=3 else 1.9,
                         "organ", .072 if name=="forest" else .055, (j-1.5)*.21)
                if bar % 2 == 0:
                    note(bar*3+.05, chord[0], 2.2, "viol", .09, -.1)
            # Irregular plucked replies: phrase-dependent patterns, rests and voicings.
            slots = [(.15,2), (1.65,3)] if bar%4 in (0,2) else [(.75,4)]
            if name == "forest":
                slots = [(1.75,3)] if bar%3==0 else []
            if name == "title" and bar < 4:
                slots = []
            for off,j in slots:
                note(bar*3+off, chord[j]+(12 if bar%8==5 else 0), 1.2, "lute", .11, -.35 if j%2 else .38)
            if name == "meadow" and bar%4 in (1,3):
                note(bar*3+1.1, chord[4]+12, .8, "glass", .035, .48)
            if name != "title" and bar%4==0:
                note(bar*3, 0, .6, "drum", .045 if name=="meadow" else .055, -.22)
            if name=="meadow" and 8<=bar<24 and bar%2==1:
                note(bar*3+2.1, 0, .22, "seed", .028, .3)
        for phrase_index, variant in enumerate(order):
            for k, (at,pitch,dur) in enumerate(PHRASES[variant]):
                offset = phrase_index*12 + at
                if name=="forest":
                    pitch -= 12
                    instrument = "reed"
                    level = .19 if phrase_index%2==0 else .155
                elif name=="title":
                    instrument = "reed" if phrase_index in (1,2) else "lute"
                    level = .19 if instrument=="reed" else .26
                else:
                    instrument = "lute" if phrase_index%3!=2 else "reed"
                    level = .235 if instrument=="lute" else .155
                note(offset, pitch, dur, instrument, level, -.10 if instrument=="reed" else .16)
                # Countervoice arrives only in the second half, never a pitch-locked echo.
                if name=="meadow" and phrase_index in (4,6) and k in (0,3,6):
                    note(offset+.7, pitch-12+(7 if k==3 else 0), dur*1.3, "reed", .075, -.38)
                if name=="forest" and phrase_index in (3,6) and k in (1,5):
                    note(offset+.9, pitch+19, dur*.7, "glass", .032, .44)
        tracks[name] = {"duration":bars*3*beat,"loop":True,"meter":"3/4","quarter_bpm":48,
                        "description":{"title":"A lamp in the eastern window: invitation, answering reed, open fifth return.",
                        "meadow":"Roadside consort: eight varied phrases, plucked walking figures, middle countervoice, long rests.",
                        "forest":"Under the black leaves: lowered reed, separated organ breaths, distant high harmonics."}[name],
                        "events":events}
    # Two distinct 32-bar battle forms in measured duple metre, not sped-up exploration.
    battle_lines = [
        [(0,62,.75),(1.5,65,.5),(2.5,64,.7),(4,69,1),(6,72,1.2)],
        [(0,69,.7),(1,67,.7),(2.5,65,.8),(4.5,64,.7),(6,62,1.4)],
        [(0,62,.65),(1,65,.6),(2,64,.65),(3,69,.6),(4.5,72,.7),(6,74,1)],
        [(0.5,72,1),(2.5,69,1.1),(4.5,64,.7),(6,62,1.7)],
        [(0,74,.6),(1,72,.6),(2.5,69,.8),(4,65,.8),(6,64,1.3)],
        [(0,60,1.25),(2,62,.7),(3.5,65,.6),(5,64,.75),(6.5,62,1)],
        [(0,69,.5),(1,72,.5),(2,74,.6),(3.5,76,.7),(5,74,.65),(6.5,72,.8)],
        [(0,69,1.2),(2,65,.8),(3.5,64,.7),(5.5,62,2)],
    ]
    for name in ("duel", "royal"):
        events=[]
        def note(at,pitch,dur,instrument,level,pan=0):
            events.append({"t":round(at*.5,5),"midi":pitch,"duration":round(dur*.5,5),"instrument":instrument,"level":level,"pan":pan})
        for bar in range(32):
            ch=CHORDS[progression[(bar//2+(2 if name=="royal" else 0))%16]]
            energy = .65 if bar in (7,15,23,31) else (1 if bar<24 else 1.16)
            # Low drum, paired wooden knocks and intentionally omitted turnaround beats.
            for off,level in ([(0,.14),(2.5,.07)] if name=="duel" else [(0,.16),(1.75,.065),(3,.095)]):
                if bar%8==7 and off>0: continue
                note(bar*4+off,0,.8,"drum",level*energy,-.16)
            if bar%4 not in (2,3):
                note(bar*4+1.5,0,.35,"knock",.063,.27)
                note(bar*4+3.25,0,.25,"seed",.026,-.4)
            if bar%8!=7:
                for j,pitch in enumerate(ch[1:5]):
                    note(bar*4+j*.025,pitch+(0 if name=="royal" else -12),3.45,"organ",.07*energy,(j-1.5)*.22)
                for k,off in enumerate([0,1.5,2.75] if bar%2==0 else [.5,2]):
                    note(bar*4+off,ch[1+k%3],.85,"lute",.145*energy,(-1 if k%2 else 1)*.3)
            if name=="royal" and bar%4==0:
                note(bar*4,ch[0],3.7,"viol",.12,-.08)
        for pair in range(16):
            line=battle_lines[(pair+(2 if name=="royal" else 0))%8]
            for k,(off,pitch,dur) in enumerate(line):
                if pair in (3,11) and k%2: continue
                octave = 0 if name=="royal" or pair%4==2 else -12
                note(pair*8+off,pitch+octave,dur,"reed",.195 if name=="royal" else .175,-.12)
                if name=="royal" and pair>=8 and k in (0,3):
                    note(pair*8+off+.4,pitch-12,dur*1.6,"lute",.15,.35)
        tracks[name]={"duration":64,"loop":True,"meter":"4/4","quarter_bpm":120,
                      "description":"The crown's oath: antiphonal reeds, ceremonial organ, final rising answer." if name=="royal" else "Iron at the ford: fractured five-note calls, measured frame drum, retreating half-phrases.","events":events}
    # A through-composed seven-breath rescue cadence, 35 seconds; no automatic repeat.
    events=[]
    rescue_chords=["d","f","c","g","a","ds","d"]
    rescue_line=[(0,62,1.8),(2,65,1.4),(4,64,1.1),(6,69,2.1),(9,72,2.5),
                 (12.5,74,1.5),(15,76,2),(18,74,1.4),(20,72,1.6),(23,69,2.2),
                 (26,65,1.3),(28,64,1.2),(30,62,3.8)]
    for bar,key in enumerate(rescue_chords):
        for j,pitch in enumerate(CHORDS[key][1:]):
            events.append({"t":bar*5+j*.06,"midi":pitch,"duration":4.6,"instrument":"organ","level":.064,"pan":(j-2)*.17})
        if bar<6:
            events.append({"t":bar*5+.6,"midi":CHORDS[key][3]+12,"duration":2.8,"instrument":"glass","level":.06,"pan":.3})
    for k,(at,pitch,dur) in enumerate(rescue_line):
        events.append({"t":at,"midi":pitch,"duration":dur,"instrument":"reed" if k>2 else "lute","level":.19 if k>2 else .26,"pan":-.08})
        if k in (5,7,9): events.append({"t":at+1,"midi":pitch-12,"duration":dur*.8,"instrument":"lute","level":.11,"pan":.36})
    tracks["rescue"]={"duration":35,"loop":False,"meter":"seven freely phrased 5-second breaths","description":"A hand in the dawn: one rising answer, a suspended second, then a quiet D–A resolution.","events":events}
    return {"title":"The Gloaming Road — original miniature consort", "seed":SEED, "sample_rate":SR,
            "motif_midi":MOTIF,"motif_names":["D4","F4","E4","A4","C5"],
            "palette":"D Dorian; minor pentachord motif; open fifths and added seconds; no soundtrack transcription",
            "tracks":tracks}


def env(n: int, attack: float, release: float, power=1.0) -> np.ndarray:
    a=np.ones(n,dtype=np.float32)
    na=min(n,max(1,int(attack*SR))); nr=min(n,max(1,int(release*SR)))
    a[:na]*=np.sin(np.linspace(0,math.pi/2,na,dtype=np.float32))**2
    a[-nr:]*=np.cos(np.linspace(0,math.pi/2,nr,dtype=np.float32))**2
    return a**power


def filtered_noise(n: int, rng, low=80, high=5000) -> np.ndarray:
    x=rng.normal(0,1,n).astype(np.float32)
    if low and high:
        sos=signal.butter(2,[low, min(high,SR*.46)],btype="bandpass",fs=SR,output="sos")
    elif low:
        sos=signal.butter(2,low,btype="highpass",fs=SR,output="sos")
    else:
        sos=signal.butter(2,min(high,SR*.46),btype="lowpass",fs=SR,output="sos")
    return signal.sosfilt(sos,x).astype(np.float32)


def instrument(name: str, midi: float, duration: float, rng) -> np.ndarray:
    tail={"lute":1.2,"glass":2.2,"organ":.65,"reed":.35,"viol":.5,"drum":.25,"knock":.15,"seed":.1}.get(name,.2)
    n=max(2,int((duration+tail)*SR)); t=np.arange(n,dtype=np.float32)/SR
    f=440*2**((midi-69)/12)
    if name=="lute":
        y=np.zeros(n,dtype=np.float32)
        for h,level in [(1,1),(2,.34),(3,.17),(4,.07),(5,.035),(7,.016)]:
            y+=level*np.sin(TAU*f*h*(1+.00012*h*h)*t)*np.exp(-t*(1.4+h*.57)/(duration+.55))
        y+=filtered_noise(n,rng,900,6500)*.022*np.exp(-t*50)
        y*=env(n,.006,.18)
    elif name=="glass":
        y=sum(a*np.sin(TAU*f*r*t)*np.exp(-t*(.85+r*.24)) for r,a in [(1,1),(2.008,.22),(3.013,.09),(4.17,.025)])
        y*=env(n,.018,.55)
    elif name in ("organ","reed","viol"):
        vib=(.0013 if name=="reed" else .00055)*np.sin(TAU*(4.1+rng.random()*.4)*t)*np.minimum(t/.65,1)
        phase=TAU*f*np.cumsum((1+vib)/SR)
        if name=="organ":
            y=.75*np.sin(phase)+.2*np.sin(phase*2)+.085*np.sin(phase*3)+.028*np.sin(phase*4.0009)
            y+=.07*np.sin(phase*1.0012+.3)
            y*=env(n,.21,.65)
        elif name=="reed":
            y=.68*np.sin(phase)+.18*np.sin(phase*2)+.12*np.sin(phase*3)+.052*np.sin(phase*5)+.018*np.sin(phase*7)
            y+=filtered_noise(n,rng,650,3800)*.025
            y*=env(n,.105,.34)*(1-.065*np.sin(TAU*.85*t)**2)
        else:
            y=.76*np.sin(phase)+.2*np.sin(phase*2)+.10*np.sin(phase*3)+.035*np.sin(phase*4)
            y*=env(n,.26,.5)
    elif name=="drum":
        phase=TAU*(62*t+18*(1-np.exp(-t*28))/28)
        y=np.sin(phase)*np.exp(-t*10)+.27*np.sin(TAU*131*t)*np.exp(-t*20)
        y+=filtered_noise(n,rng,180,2400)*.13*np.exp(-t*35)
        y*=env(n,.002,.06)
    elif name=="knock":
        y=.5*np.sin(TAU*490*t)*np.exp(-t*42)+.32*np.sin(TAU*1173*t)*np.exp(-t*67)
        y+=filtered_noise(n,rng,400,4500)*.12*np.exp(-t*95)
        y*=env(n,.001,.025)
    elif name=="seed":
        y=filtered_noise(n,rng,3200,8800)*np.exp(-t*22)*env(n,.008,.035)
    else:
        raise ValueError(name)
    return np.asarray(y,dtype=np.float32)


def add_stereo(dst, mono, at, level, pan=0, loop=False):
    pan=float(np.clip(pan,-1,1)); g=np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],np.float32)*level
    start=round(at*SR); block=mono[:,None]*g[None,:]
    if loop:
        index=start%len(dst)
        while len(block):
            size=min(len(block),len(dst)-index)
            dst[index:index+size]+=block[:size]; block=block[size:]; index=0
    elif start<len(dst):
        skip=max(0,-start); start=max(0,start); size=min(len(block)-skip,len(dst)-start)
        if size>0: dst[start:start+size]+=block[skip:skip+size]


def room_ir(seconds=1.55, seed="room"):
    rng=rng_for(seed); n=int(seconds*SR); t=np.arange(n)/SR
    ir=np.zeros((n,2),np.float32)
    for ch in range(2):
        tail=filtered_noise(n,rng,180,5600)*np.exp(-t*6.7/seconds)
        tail[:int(.03*SR)]=0
        ir[:,ch]=tail*.024
        for delay,amp in [(.037,.32),(.067,.22),(.109,.15),(.157,.10),(.229,.055)]:
            ix=int((delay+ch*.007)*SR)
            if ix<n: ir[ix,ch]+=amp*(1 if ch==0 else -.9)
        ir[:,ch]*=env(n,.006,.15)
    return ir


def reverberate(y, wet=.18, loop=False, seconds=1.8):
    ir=room_ir(seconds)
    out=np.zeros_like(y)
    for ch in range(2):
        if loop:
            kernel=np.zeros(len(y),np.float32); kernel[:len(ir)]=ir[:,ch]
            out[:,ch]=np.fft.irfft(np.fft.rfft(y[:,ch]) * np.fft.rfft(kernel),n=len(y)).astype(np.float32)
        else:
            out[:,ch]=signal.fftconvolve(y[:,ch],ir[:,ch],mode="full")[:len(y)]
    return y+out*wet


def master(y, kind, loop=False):
    y=np.asarray(y,np.float32)
    if y.ndim==1: y=y[:,None]
    # Remove DC and infrasonic build-up before setting headroom, not brickwall clipping.
    y=signal.sosfilt(signal.butter(2,28,btype="highpass",fs=SR,output="sos"),y,axis=0).astype(np.float32)
    if loop:
        # Match 24ms of endpoint slope gently; no fade-to-silence pulse at every cycle.
        width=min(int(.024*SR),len(y)//20)
        delta=y[-1]-y[0]
        taper=(.5-.5*np.cos(np.linspace(0,math.pi,width)))[:,None]
        y[-width:]-=taper*delta
    else:
        y*=env(len(y),.004,.035)[:,None]
    target_rms={"music":.092,"ambience":.064,"effect":.115,"ir":.018,"silence":0}[kind]
    peak_limit={"music":.47,"ambience":.36,"effect":.56,"ir":.42,"silence":0}[kind]
    rms=float(np.sqrt(np.mean(y.astype(np.float64)**2))); peak=float(np.max(np.abs(y)))
    if peak>0:
        y*=min(target_rms/max(rms,1e-8),peak_limit/peak)
    return np.asarray(y,np.float32)


def render_music(name, track):
    out=np.zeros((round(track["duration"]*SR),2),np.float32); rng=rng_for(name)
    for event in sorted(track["events"],key=lambda e:e["t"]):
        voice=instrument(event["instrument"],event["midi"],event["duration"],rng)
        # Rendered humanisation is deterministic; it is not a runtime note sequencer.
        level=event["level"]*(.955+rng.random()*.09)
        add_stereo(out,voice,event["t"],level,event.get("pan",0),track["loop"])
    out=reverberate(out,.38 if name=="forest" else .27,track["loop"],2.15 if name in ("forest","royal") else 1.65)
    if not track["loop"]:
        out*=env(len(out),.03,2.8)[:,None]
    return master(out,"music",track["loop"])


def periodic_noise(n,rng,low,high):
    # FFT colouring gives a periodic stochastic bed: its wrap is a normal sample step.
    freq=np.fft.rfftfreq(n,1/SR)
    spectrum=rng.normal(size=len(freq))+1j*rng.normal(size=len(freq))
    weighting=(1-np.exp(-(freq/max(low,1))**2))*np.exp(-(freq/high)**2)/np.sqrt(np.maximum(freq,low))
    weighting[0]=0
    x=np.fft.irfft(spectrum*weighting,n=n)
    return (x/(np.std(x)+1e-8)).astype(np.float32)


def bird(rng,kind="day",variation=0):
    length=1.1+variation*.11; n=int(length*SR); y=np.zeros(n,np.float32)
    calls=[(.08,.15,1900,2800),(.33,.10,2250,3550),(.53,.21,2650,1950)]
    if kind=="night": calls=[(.10,.34,460,430),(.61,.43,380,410)]
    for at,dur,f0,f1 in calls:
        size=int(dur*SR); t=np.arange(size)/SR
        p=TAU*(f0*t+(f1-f0)*t*t/(2*dur)+12*np.sin(TAU*19*t)/(TAU*19))*(.95+.035*variation)
        chirp=(np.sin(p)+.13*np.sin(2*p))*np.sin(np.linspace(0,math.pi,size))**2
        ix=int(at*SR); y[ix:ix+size]+=chirp*.44
    return y*env(n,.005,.08)


def ambience(name,seconds=24):
    rng=rng_for("amb_"+name); n=seconds*SR; t=np.arange(n)/SR
    out=np.zeros((n,2),np.float32)
    for ch in range(2):
        base=periodic_noise(n,rng,45 if name=="castle" else 90,950 if name=="castle" else 3500)
        gust=.38+.16*np.sin(TAU*t/24+ch*.23)+.095*np.sin(TAU*3*t/24+.7)+.075*np.sin(TAU*5*t/24)
        out[:,ch]=base*gust*.075
        if name in ("meadow","forest","wind"):
            grass=periodic_noise(n,rng,850,5800)
            out[:,ch]+=grass*(.016+.013*np.sin(TAU*2*t/24+.5+ch*.12)**2)
        if name=="forest":
            canopy=periodic_noise(n,rng,260,1300)
            out[:,ch]+=canopy*(.045+.02*np.cos(TAU*t/12))
        if name=="night":
            # Groups of tiny insect stridulations with pockets of silence, not a sine drone.
            for k in range(8):
                at=(k*2.93+ch*.31+.4)%24; dur=.35+rng.random()*.65; size=int(dur*SR)
                u=np.arange(size)/SR
                trill=(np.sin(TAU*(3700+k*91)*u)+.22*np.sin(TAU*(4300+k*33)*u))
                trill*=np.maximum(0,np.sin(TAU*(18+k%3)*u))**3*env(size,.045,.12)*.014
                add_stereo(out,trill,at,1,-.65 if ch==0 else .65,True)
        if name=="castle":
            room=periodic_noise(n,rng,35,300)
            out[:,ch]+=room*.035
    if name=="meadow":
        for i,at in enumerate([3.7,10.2,18.45]): add_stereo(out,bird(rng,variation=i),at,.036,[-.65,.5,.2][i],True)
    if name=="forest":
        for i,at in enumerate([6.2,16.75]): add_stereo(out,bird(rng,variation=i+2),at,.023,[.65,-.4][i],True)
        for i,at in enumerate([2.7,8.9,14.8,21.3]):
            clip=effect("leaves",i)[0]; add_stereo(out,clip,at,.024,(-1 if i%2 else 1)*.6,True)
    if name=="night": add_stereo(out,bird(rng,"night"),13.2,.04,-.55,True)
    if name=="castle":
        for i,at in enumerate([4.1,13.7,21.9]):
            drop=instrument("glass",86-i*2,.15,rng)
            add_stereo(out,drop,at,.015,[-.65,.7,-.2][i],True)
        out=reverberate(out,.8,True,2.8)
    return master(out,"ambience",True)


def burst(n,rng,low,high,at,dur,amp=1):
    y=np.zeros(n,np.float32); ix=int(at*SR); size=min(n-ix,max(2,int(dur*SR)))
    if size>0:
        clip=filtered_noise(size,rng,low,high)*env(size,.003,min(.09,dur*.75))
        y[ix:ix+size]=clip*amp
    return y


def effect(name,variation=0):
    rng=rng_for(name+str(variation)); jitter=.94+variation*.04
    duration={"step_dirt":.37,"step_grass":.42,"step_stone":.33,"step_wood":.4,
              "cloth":.47,"leaves":.85,"whoosh_light":.39,"whoosh_heavy":.68,"miss":.5,
              "parry":1.1,"block":.57,"shield":.69,"armor":.53,"flesh":.37,"enemy_death":1.08,
              "bow_draw":.8,"bow_release":.44,"arrow_pass":.43,"arrow_impact":.57,
              "arrow_wood":.55,"arrow_stone":.65,"arrow_flesh":.39,
              "fire_charge":1.18,"fire_release":.66,"fire_travel":1.25,"fire_impact":1.05,"fire_linger":2.8,
              "door":1.45,"latch":.39,"rest":2.5,"ui":.14,"ui_confirm":.37,"ui_cancel":.3,
              "death":3.1,"respawn":2.8,"shield_break":1.0}.get(name,.5)
    if name=="bird": return bird(rng,variation=variation), False
    if name=="bird_night": return bird(rng,"night",variation), False
    n=int(duration*SR); t=np.arange(n,dtype=np.float32)/SR; y=np.zeros(n,np.float32)
    if name.startswith("step_"):
        material=name[5:]
        weight=np.sin(TAU*(74 if material in ("dirt","grass") else 112)*jitter*t)*np.exp(-t*33)*.32
        y+=weight*env(n,.006,.04)
        if material=="dirt":
            y+=burst(n,rng,350,2900,.006,.095,.7)+burst(n,rng,900,4600,.12,.12,.28)
            for _ in range(9): y+=burst(n,rng,1100,6700,float(rng.uniform(.015,.19)),.009,float(rng.uniform(.1,.3)))
        elif material=="grass":
            y+=burst(n,rng,950,6200,.018,.14,.54)+burst(n,rng,1800,7700,.16,.2,.33)
            y+=filtered_noise(n,rng,260,1550)*np.exp(-t*19)*.26
        elif material=="stone":
            y+=burst(n,rng,900,7000,.004,.035,.65)+burst(n,rng,600,2400,.135,.06,.20)
            y+=.18*np.sin(TAU*918*jitter*t)*np.exp(-t*52)+.13*np.sin(TAU*1613*jitter*t)*np.exp(-t*76)
        else:
            y+=burst(n,rng,450,4000,.003,.047,.42)
            for hz,amp,decay in [(165,.34,24),(327,.20,31),(711,.11,42)]: y+=amp*np.sin(TAU*hz*jitter*t)*np.exp(-t*decay)
            y+=burst(n,rng,650,2800,.145,.12,.09)
    elif name in ("cloth","leaves"):
        high=4200 if name=="cloth" else 8200; low=500 if name=="cloth" else 1800
        for k in range(3 if name=="cloth" else 7):
            y+=burst(n,rng,low,high,float(rng.uniform(.005,duration*.63)),float(rng.uniform(.055,.19)),float(rng.uniform(.2,.6)))
    elif name in ("whoosh_light","whoosh_heavy","miss","arrow_pass"):
        low=110 if name=="whoosh_heavy" else 380
        y=filtered_noise(n,rng,low,3800 if name=="whoosh_heavy" else 7500)
        shape=np.sin(np.linspace(0,math.pi,n))**(3 if name=="whoosh_heavy" else 5)
        y*=shape*(.52 if name=="arrow_pass" else .9)
        if name=="whoosh_heavy": y+=.18*np.sin(TAU*(150*t-75*t*t))*shape
        if name=="arrow_pass": y+=.12*np.sin(TAU*(2200*t-1200*t*t/duration))*shape
    elif name in ("parry","block","shield","armor","shield_break","arrow_stone"):
        # Different physical resonators distinguish contact, not merely different pitches.
        modes={"parry":[(1830,.35,7),(2843,.28,10),(4211,.20,16),(5717,.11,25)],
               "block":[(440,.35,20),(813,.21,27),(1631,.16,40)],
               "shield":[(173,.36,10),(383,.30,16),(697,.15,29),(1381,.08,48)],
               "armor":[(682,.27,23),(1139,.20,29),(2211,.18,42),(3689,.12,55)],
               "shield_break":[(137,.4,11),(263,.25,15),(583,.2,23),(1347,.11,40)],
               "arrow_stone":[(1204,.22,29),(2969,.17,41),(4777,.10,61)]}[name]
        for hz,amp,decay in modes: y+=amp*np.sin(TAU*hz*jitter*t)*np.exp(-t*decay)*env(n,.001,.045)
        y+=burst(n,rng,1200,9200,.001,.033,.85 if name=="parry" else .55)
        if name in ("armor","shield_break"):
            for k in range(4): y+=burst(n,rng,1400,5900,.038+k*.044,.025,.24/(k+1))
        if name=="shield_break": y+=burst(n,rng,240,5400,.06,.23,.62)
    elif name in ("flesh","arrow_flesh","enemy_death"):
        y+=np.sin(TAU*(93*t-15*t*t))*np.exp(-t*24)*.48
        y+=burst(n,rng,180,1300,.005,.11,.8)+burst(n,rng,550,2100,.03,.08,.30)
        if name=="enemy_death":
            # Breath and falling body/cloth, deliberately no sampled human vocalisation.
            y+=burst(n,rng,260,1550,.13,.47,.48)+burst(n,rng,350,3200,.58,.3,.38)
            y+=.27*np.sin(TAU*58*t)*np.exp(-((t-.64)/.10)**2)
    elif name=="bow_draw":
        y=filtered_noise(n,rng,280,1900)*np.sin(np.linspace(0,math.pi,n))*.24
        y+=.08*np.sin(TAU*(128*t+93*t*t))*np.maximum(0,np.sin(TAU*13*t))**2*env(n,.13,.09)
        for at in (.12,.37,.60): y+=burst(n,rng,700,3500,at,.08,.18)
    elif name=="bow_release":
        for hz,amp in [(126,.46),(254,.20),(387,.11)]: y+=amp*np.sin(TAU*hz*jitter*t)*np.exp(-t*21)
        y+=burst(n,rng,1500,7800,.005,.09,.38)
    elif name in ("arrow_impact","arrow_wood"):
        for hz,amp,decay in [(212,.44,18),(491,.22,26),(1237,.09,53)]: y+=amp*np.sin(TAU*hz*jitter*t)*np.exp(-t*decay)
        y+=burst(n,rng,800,5700,.003,.055,.60)
        y+=burst(n,rng,1300,3600,.09,.12,.14)
    elif name.startswith("fire_"):
        noise=filtered_noise(n,rng,90,4900)
        low=filtered_noise(n,rng,40,480)
        if name=="fire_charge":
            shape=np.sin(np.linspace(0,math.pi/2,n))**1.6*env(n,.05,.16)
            y=(noise*.28+low*.48+np.sin(TAU*(87*t+45*t*t))*.12)*shape
        elif name=="fire_release":
            y=(noise*.7+low*.75)*np.exp(-t*5)*env(n,.012,.07)
            y+=.15*np.sin(TAU*(121*t-65*t*t))*np.exp(-t*9)
        elif name=="fire_travel":
            y=(noise*.45+low*.45)*env(n,.13,.28)*(1+.17*np.sin(TAU*8*t))
        elif name=="fire_impact":
            y=(noise*.8+low*.85)*np.exp(-t*5.8)*env(n,.006,.13)
            y+=.45*np.sin(TAU*(58*t+16*(1-np.exp(-t*30))/30))*np.exp(-t*9)
            for k in range(7): y+=burst(n,rng,1600,8400,.08+k*.071,.018,.23)
        else:
            y=(noise*.25+low*.25)*env(n,.04,.60)
            for k in range(18): y+=burst(n,rng,1400,6500,float(rng.uniform(.03,2.5)),.019,float(rng.uniform(.13,.35)))
    elif name=="door":
        y+=burst(n,rng,130,1200,.07,.85,.37)
        strain=np.sin(TAU*(119*t+8*np.sin(TAU*1.4*t)))*.13+np.sin(TAU*261*t)*.055
        y+=strain*np.exp(-((t-.49)/.35)**2)
        q=np.maximum(0,t-1.05)
        y+=(np.sin(TAU*88*q)*.4+np.sin(TAU*249*q)*.2)*np.exp(-q*20)*(t>=1.05)
        y+=burst(n,rng,180,2600,1.05,.17,.42)
    elif name=="latch":
        y+=burst(n,rng,1000,7100,.004,.027,.70)+burst(n,rng,750,3400,.11,.05,.40)
        y+=.18*np.sin(TAU*1373*t)*np.exp(-t*42)
    elif name in ("ui","ui_confirm","ui_cancel","rest","respawn","death"):
        lines={"ui":[(0,74,.07,.25)],"ui_confirm":[(0,62,.13,.32),(.10,69,.2,.25)],
               "ui_cancel":[(0,64,.12,.26),(.10,62,.12,.2)],
               "rest":[(0,62,.7,.28),(.3,65,.7,.22),(.7,69,1,.20)],
               "respawn":[(0,50,.6,.25),(.30,62,.6,.26),(.63,65,.7,.23),(1.05,69,1,.18)],
               "death":[(0,62,.8,.27),(.42,60,.8,.25),(.95,57,1.2,.21),(1.5,50,1,.20)]}[name]
        for at,pitch,dur,level in lines:
            clip=instrument("lute" if name.startswith("ui") else "glass",pitch,dur,rng)
            ix=int(at*SR); count=min(len(clip),n-ix); y[ix:ix+count]+=clip[:count]*level
        if name=="death": y+=burst(n,rng,80,800,.05,2.4,.055)
    else:
        raise ValueError(name)
    return np.asarray(y*env(n,.002,.025),np.float32), False


EFFECT_VARIATIONS = {
    "step_dirt":4,"step_grass":4,"step_stone":4,"step_wood":4,
    "cloth":3,"leaves":3,"bird":4,"bird_night":2,
    "whoosh_light":3,"whoosh_heavy":3,"miss":2,
    "parry":3,"block":3,"shield":3,"armor":3,"flesh":3,"enemy_death":3,"shield_break":1,
    "bow_draw":2,"bow_release":3,"arrow_pass":3,"arrow_impact":3,"arrow_wood":2,"arrow_stone":2,"arrow_flesh":2,
    "fire_charge":2,"fire_release":2,"fire_travel":2,"fire_impact":3,"fire_linger":1,
    "door":2,"latch":2,"rest":1,"ui":2,"ui_confirm":1,"ui_cancel":1,"death":1,"respawn":1,
}


def stats(data):
    data=np.asarray(data,np.float32)
    peak=float(np.max(np.abs(data)))
    rms=float(np.sqrt(np.mean(data.astype(np.float64)**2)))
    return {"peak":round(peak,7),"peak_dbfs":round(20*math.log10(max(peak,1e-9)),3),
            "rms":round(rms,7),"rms_dbfs":round(20*math.log10(max(rms,1e-9)),3),
            "dc":round(float(np.mean(data)),8),"clipped_samples":int(np.count_nonzero(np.abs(data)>=1)),
            "seam_step":round(float(np.max(np.abs(data[-1]-data[0]))),7)}


def encode(name,y,kind,loop=False,group=None):
    y=np.asarray(y,np.float32)
    if y.ndim==1: y=y[:,None]
    channels=y.shape[1]; raw=y.astype("<f4").tobytes()
    variants={}
    for codec in ("ogg","mp3"):
        path=OUT/f"{name}.{codec}"
        # The primary Ogg keeps stereo spatial detail. MP3 is a conservative local
        # fallback for browsers lacking Vorbis; 32kHz+ would waste the small payload.
        enc_channels=1 if codec=="mp3" and kind in ("music","ambience") else channels
        opts=["-c:a","libvorbis","-q:a","-1"] if codec=="ogg" else ["-c:a","libmp3lame","-ac",str(enc_channels),"-b:a", "24k" if kind in ("music","ambience") else "40k"]
        command=[FFMPEG,"-hide_banner","-loglevel","error","-y","-f","f32le","-ar",str(SR),"-ac",str(channels),"-i","pipe:0",
                 "-map_metadata","-1","-fflags","+bitexact","-flags:a","+bitexact",*opts,"-metadata","artist=The Gloaming Road — original procedural composition",
                 "-metadata",f"title={name}",str(path)]
        subprocess.run(command,input=raw,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
        result=subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-i",str(path),"-f","f32le","-acodec","pcm_f32le","-ar",str(SR),"-ac",str(enc_channels),"pipe:1"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        decoded=np.frombuffer(result.stdout,dtype="<f4").reshape(-1,enc_channels)
        measured=stats(decoded)
        if measured["clipped_samples"]: raise RuntimeError(f"Clipping after {codec} encoding: {name}")
        variants[codec]={"file":path.name,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                         "channels":enc_channels,"sample_rate":SR,"decoded_duration":round(len(decoded)/SR,6),"measured":measured}
    return {"id":name,"group":group or name,"kind":kind,"loop":loop,"duration":round(len(y)/SR,6),
            "sample_rate":SR,"channels":channels,"pcm_bytes":int(y.size*4),"source_measured":stats(y),"encodings":variants}


def export_catalog(manifest):
    lines=["// Generated by audio-source/render.py; local assets are embedded by the production bundler."]
    for i,entry in enumerate(manifest["assets"]):
        for codec in ("ogg","mp3"): lines.append(f"import a{i}_{codec} from './{entry['id']}.{codec}';")
    lines += ["", "export type AudioAsset = { id: string; group: string; kind: 'music' | 'ambience' | 'effect' | 'ir' | 'silence'; duration: number; channels: number; sampleRate: number; pcmBytes: number; loop: boolean; peak: number; rms: number; ogg: string; mp3: string };", "export const AUDIO_ASSETS: readonly AudioAsset[] = ["]
    for i,e in enumerate(manifest["assets"]):
        values=json.dumps({"id":e["id"],"group":e["group"],"kind":e["kind"],"duration":e["duration"],"channels":e["channels"],
                           "sampleRate":e["sample_rate"],"pcmBytes":e["pcm_bytes"],"loop":e["loop"],"peak":e["source_measured"]["peak"],"rms":e["source_measured"]["rms"]},separators=(",",":"))
        lines.append(f"  {{...{values}, ogg: a{i}_ogg, mp3: a{i}_mp3}},")
    lines += ["] as const;",f"export const AUDIO_COMPRESSED_BYTES = {manifest['total_compressed_bytes']};", ""]
    (OUT/"catalog.ts").write_text("\n".join(lines),encoding="utf-8")


def main():
    p=argparse.ArgumentParser(); p.add_argument("--rewrite-score",action="store_true"); p.add_argument("--only",choices=["music","ambience","effects"])
    args=p.parse_args(); OUT.mkdir(parents=True,exist_ok=True); SOURCE.mkdir(parents=True,exist_ok=True)
    score_path=SOURCE/"score.json"
    if not score_path.exists() or args.rewrite_score:
        score_path.write_text(json.dumps(compose_score(),indent=2)+"\n",encoding="utf-8")
    score=json.loads(score_path.read_text())
    entries=[]; manifest_path=OUT/"manifest.json"
    if args.only and manifest_path.exists():
        kind="effect" if args.only=="effects" else args.only
        entries=[e for e in json.loads(manifest_path.read_text())["assets"] if e["kind"]!=kind and not(args.only=="effects" and e["kind"] in ("ir","silence"))]
    if args.only in (None,"music"):
        for name,track in score["tracks"].items():
            print(f"Rendering music {name}: {track['duration']} seconds, {len(track['events'])} composed events",flush=True)
            entries.append(encode("music_"+name,render_music(name,track),"music",track["loop"],name))
    if args.only in (None,"ambience"):
        for name in ("wind","meadow","forest","night","castle"):
            print(f"Rendering ambience {name}",flush=True)
            entries.append(encode("ambient_"+name,ambience(name),"ambience",True,name))
    if args.only in (None,"effects"):
        for name,count in EFFECT_VARIATIONS.items():
            print(f"Rendering {name}: {count} variations",flush=True)
            for variation in range(count):
                y,loop=effect(name,variation)
                entries.append(encode(f"{name}_{variation+1}",master(y,"effect",loop),"effect",loop,name))
        entries.append(encode("room_ir",master(room_ir(1.35,"runtime_room"),"ir"),"ir",False,"room_ir"))
        entries.append(encode("silence",np.zeros((int(.25*SR),2),np.float32),"silence",True,"silence"))
    entries.sort(key=lambda e:(e["kind"],e["id"]))
    total=sum(c["bytes"] for e in entries for c in e["encodings"].values())
    manifest={"schema":1,"project":"The Gloaming Road","original":True,"seed":SEED,"sample_rate":SR,
              "composition":"Original D4–F4–E4–A4–C5 motif; not an auditory match to or transcription of any source soundtrack.",
              "render":"NumPy/SciPy offline synthesis; local ffmpeg libvorbis and libmp3lame; no third-party audio input",
              "total_compressed_bytes":total,"total_uncompressed_float32_bytes":sum(e["pcm_bytes"] for e in entries),
              "assets":entries}
    manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8"); export_catalog(manifest)
    print(f"DONE: {len(entries)} assets, Ogg+MP3 {total:,} bytes ({total/1_000_000:.3f} MB).",flush=True)
    print(f"All decoded PCM would be {manifest['total_uncompressed_float32_bytes']/1_000_000:.2f} MB; runtime streams score and ambience instead.",flush=True)
    if total>6_000_000: print("NOTE: Payload exceeds the approximate 6 MB target; review encodings.",flush=True)


if __name__=="__main__":
    main()
