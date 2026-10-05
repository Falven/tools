#!/usr/bin/env python3
"""Measure the delivered encodings, not subjective sound quality.

Re-decodes every local Ogg and MP3, checks manifest byte counts/hashes, records
sample peaks, a 4x oversampled peak estimate, boundary discontinuities and material
spectra. This is an offline export-quality report, not a listening/fidelity test.
No audio device is used. Output: audio-source/measurements.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy import signal

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"frontend"/"assets"/"audio"
SR=24000


def main():
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    manifest=json.loads((OUT/"manifest.json").read_text())
    score=json.loads((ROOT/"audio-source"/"score.json").read_text())
    rows=[]; problems=[]; duration_adjustments=[]; material=defaultdict(list); totals=defaultdict(lambda:{"assets":0,"seconds":0,"ogg_bytes":0,"mp3_bytes":0})
    for entry in manifest["assets"]:
        cat=totals[entry["kind"]]; cat["assets"]+=1; cat["seconds"]+=entry["duration"]
        for codec,encoding in entry["encodings"].items():
            path=OUT/encoding["file"]; encoded=path.read_bytes(); cat[codec+"_bytes"]+=len(encoded)
            if len(encoded)!=encoding["bytes"] or hashlib.sha256(encoded).hexdigest()!=encoding["sha256"]:
                problems.append(f"Manifest integrity mismatch: {path.name}")
            channels=encoding.get("channels",entry["channels"])
            result=subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-i",str(path),"-f","f32le","-acodec","pcm_f32le","-ar",str(SR),"-ac",str(channels),"pipe:1"],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            y=np.frombuffer(result.stdout,dtype="<f4").reshape(-1,channels)
            peak=float(np.max(np.abs(y))); rms=float(np.sqrt(np.mean(y.astype(np.float64)**2)))
            oversampled=0.0
            # Overlap avoids artificial internal block edges in the interpolation filter.
            block=SR*2; margin=32
            for start in range(0,len(y),block):
                left=max(0,start-margin); right=min(len(y),start+block+margin)
                expanded=signal.resample_poly(y[left:right],4,1,axis=0,window=("kaiser",8.6))
                skip=(start-left)*4; size=min(block,len(y)-start)*4
                oversampled=max(oversampled,float(np.max(np.abs(expanded[skip:skip+size]))))
            edge=np.concatenate((y[-1200:],y[:1200]),axis=0)
            seam=float(np.max(np.abs(y[-1]-y[0])))
            step_rms=float(np.sqrt(np.mean(np.diff(edge,axis=0).astype(np.float64)**2)))
            row={"id":entry["id"],"codec":codec,"channels":channels,"duration":round(len(y)/SR,6),
                 "sample_peak":round(peak,7),"oversampled_peak_4x":round(oversampled,7),
                 "oversampled_peak_dbfs":round(20*math.log10(max(oversampled,1e-9)),3),
                 "rms":round(rms,7),"clipped_samples":int(np.count_nonzero(np.abs(y)>=1))}
            if entry["loop"]:
                row.update({"seam_step":round(seam,7),"seam_to_local_difference_rms":round(seam/max(step_rms,1e-9),3)})
            if abs(len(y)/SR-encoding["decoded_duration"])>1/SR+.000001:
                problems.append(f"Manifest decoded-duration mismatch: {path.name}")
            delta=len(y)/SR-entry["duration"]
            if abs(delta)>1/SR+.000001:
                # Vorbis's variable-size final packet can pad/trim short one-shots.
                # Source and actual decoded durations are both explicitly in the manifest.
                duration_adjustments.append({"file":path.name,"seconds":round(delta,6)})
                if entry["kind"] in ("music","ambience") or abs(delta)>.08:
                    problems.append(f"Unexpected long-file/large duration change: {path.name}")
            if row["clipped_samples"] or oversampled>=1:
                problems.append(f"Full-scale peak: {path.name}")
            rows.append(row)
            if codec=="ogg" and entry["group"] in ("step_dirt","step_grass","step_stone","step_wood","parry","block","shield","armor","flesh"):
                mono=y.mean(axis=1); power=np.abs(np.fft.rfft(mono))**2; hz=np.fft.rfftfreq(len(mono),1/SR); total=float(np.sum(power))+1e-20
                material[entry["group"]].append({"centroid_hz":float(np.sum(power*hz)/total),
                    "low_under_250":float(np.sum(power[hz<250])/total),"body_250_1200":float(np.sum(power[(hz>=250)&(hz<1200)])/total),
                    "grit_1200_4500":float(np.sum(power[(hz>=1200)&(hz<4500)])/total),"air_over_4500":float(np.sum(power[hz>=4500])/total)})
        print(f"Measured {entry['id']}",flush=True)
    materials={key:{metric:round(float(np.mean([v[metric] for v in values])),4) for metric in values[0]} for key,values in material.items()}
    report={"method":"Local ffmpeg re-decode; NumPy RMS/sample peak; SciPy 4x Kaiser oversampling (estimate, not certified ITU true-peak meter). No auditory evaluation.",
            "ffmpeg":imageio_ffmpeg.get_ffmpeg_version(),"total_compressed_bytes":manifest["total_compressed_bytes"],
            "assets":len(manifest["assets"]),"encoded_files":len(rows),"categories":dict(totals),
            "highest_sample_peak":max(rows,key=lambda r:r["sample_peak"]),
            "highest_4x_peak":max(rows,key=lambda r:r["oversampled_peak_4x"]),
            "total_clipped_samples":sum(r["clipped_samples"] for r in rows),"integrity_or_peak_issues":problems,
            "short_codec_duration_adjustments":duration_adjustments,
            "maximum_short_duration_adjustment_seconds":max([abs(a["seconds"]) for a in duration_adjustments],default=0),
            "composition":{name:{"duration":track["duration"],"events":len(track["events"]),"instruments":sorted(set(e["instrument"] for e in track["events"]))} for name,track in score["tracks"].items()},
            "material_spectral_means":materials,"encodings":rows}
    (ROOT/"audio-source"/"measurements.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({key:report[key] for key in ("total_compressed_bytes","assets","encoded_files","total_clipped_samples","highest_4x_peak","integrity_or_peak_issues","material_spectral_means")},indent=2),flush=True)


if __name__=="__main__":
    main()
