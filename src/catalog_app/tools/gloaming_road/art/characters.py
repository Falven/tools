#!/usr/bin/env python3
"""The Gloaming Road / original character workshop.

Deterministically authors contoured, rigid-articulated glTF 2.0 characters,
hand-painted-style atlas textures and timed, in-place animation clips.
No downloaded models, source-game assets, Blender or runtime primitives.
Run from the repository: .venv/bin/python src/catalog_app/tools/gloaming_road/art/characters.py
"""
from __future__ import annotations

import io
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "frontend" / "assets" / "characters"
TAU = math.tau
PI = math.pi
TILES = {
    "steel": 0, "edge": 1, "mail": 2, "leather": 3,
    "red": 4, "mustard": 5, "gilt": 6, "skin": 7,
    "hair": 8, "ivory": 9, "rose": 10, "wood": 11,
    "black": 12, "robe": 13, "gem": 14, "thread": 15,
}
def atomic_binary(path: Path, data: bytes):
    staging = path.with_suffix(path.suffix+".tmp")
    staging.write_bytes(data)
    staging.replace(path)


COLORS = [
    (155, 167, 171), (202, 210, 209), (45, 48, 47), (65, 45, 32),
    (106, 42, 39), (148, 119, 56), (165, 140, 82), (197, 176, 150),
    (71, 45, 29), (197, 189, 166), (139, 92, 88), (103, 69, 42),
    (18, 23, 23), (54, 63, 68), (69, 126, 117), (164, 152, 116),
]


def texture_atlas() -> tuple[bytes, bytes, bytes]:
    rng = np.random.default_rng(730021)
    atlas = Image.new("RGB", (512, 512))
    orm = Image.new("RGB", (512, 512))
    emission = Image.new("RGB", (512, 512))
    for name, k in TILES.items():
        yy, xx = np.mgrid[0:128, 0:128]
        noise = rng.normal(0, 2.9, (128, 128))
        grain = np.sin(xx * .15 + np.sin(yy * .09) * 2) * 1.7
        broad = np.sin(xx * .051 + yy * .034) * 3 + np.cos(yy * .065) * 2
        metal = name in ("steel", "edge", "gilt")
        cloth = name in ("red", "mustard", "ivory", "rose", "robe", "thread")
        wood = name in ("wood", "hair")
        if metal:
            broad += np.sin(xx * .083) * 5 + np.cos(yy * .025) * 5
            grain += (xx % 3 == 0) * 1.6
        elif cloth:
            grain += (xx % 3 == 0) * 3.0 - (yy % 3 == 0) * 2.4
            broad += np.cos(xx * .20) * 2.7
        elif wood:
            grain += np.sin(xx * .45 + np.sin(yy * .031) * 2.4) * 7
        pixels = np.clip(np.array(COLORS[k]) + (noise + grain + broad)[..., None], 0, 255).astype(np.uint8)
        tile = Image.fromarray(pixels)
        d = ImageDraw.Draw(tile)
        if metal:
            for _ in range(51):
                x, y = (int(v) for v in rng.integers(7, 121, 2))
                le = int(rng.integers(2, 16))
                c = tuple(int(v) for v in np.clip(np.array(COLORS[k]) + int(rng.integers(-27, 28)), 0, 255))
                d.line((x, y, x + int(rng.integers(-1, 2)), min(123, y + le)), fill=c)
            # Fine rubbed edges, not photographic metal pasted onto a primitive.
            d.line((5, 5, 5, 122), fill=tuple(min(255, c + 19) for c in COLORS[k]))
            d.line((121, 6, 121, 121), fill=tuple(max(0, c - 15) for c in COLORS[k]))
        elif name == "mail":
            for y in range(3, 128, 9):
                for x in range((y // 9 % 2) * 4 - 4, 128, 8):
                    d.arc((x, y, x + 7, y + 8), 5, 285, fill=(86, 87, 79), width=1)
                    d.arc((x + 1, y + 2, x + 6, y + 7), 15, 265, fill=(20, 25, 25), width=1)
        elif name == "leather":
            for x in (8, 118):
                d.line((x, 5, x, 123), fill=(32, 27, 21))
                for y in range(8, 123, 7):
                    d.line((x + 2, y, x + 2, y + 2), fill=(139, 119, 82))
            for _ in range(22):
                x, y = (int(v) for v in rng.integers(12, 116, 2))
                d.line((x, y, x + 2, y + 5), fill=(81, 59, 39))
        elif cloth:
            for y in (6, 121):
                d.line((6, y, 121, y), fill=tuple(max(0, c - 19) for c in COLORS[k]))
                for x in range(8, 122, 6):
                    d.line((x, y + 2, x + 2, y + 2), fill=tuple(min(255, c + 15) for c in COLORS[k]))
        elif wood:
            for _ in range(12):
                x = int(rng.integers(4, 124))
                path = [(x + math.sin(y * .065 + x) * 2, y) for y in range(0, 128, 8)]
                d.line(path, fill=tuple(max(0, c - 16) for c in COLORS[k]))
        if name == "gem":
            d.polygon([(21, 92), (39, 18), (80, 12), (111, 44), (93, 109)], outline=(144, 183, 151), width=2)
        x0, y0 = (k % 4) * 128, (k // 4) * 128
        atlas.paste(tile, (x0, y0))
        rough = .56 if name == "steel" else .43 if name == "edge" else .5 if name == "gilt" else .92 if cloth else .84
        metallic = .57 if name == "steel" else .67 if name == "edge" else .65 if name == "gilt" else .09 if name == "mail" else 0
        if name == "gem":
            rough = .34
        orm_array = np.empty((128, 128, 3), np.uint8)
        orm_array[:, :, 0] = np.clip(246 + broad, 224, 255)
        orm_array[:, :, 1] = np.clip(rough * 255 + noise * 2 + grain, 0, 255)
        orm_array[:, :, 2] = int(metallic * 255)
        orm.paste(Image.fromarray(orm_array), (x0, y0))
        if name == "gem":
            emission.paste(Image.new("RGB", (128, 128), (25, 57, 43)), (x0, y0))
    OUT.mkdir(parents=True, exist_ok=True)
    answer = []
    for image, name in ((atlas, "characters-atlas.png"), (orm, "characters-surface.png"), (emission, "characters-emission.png")):
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        atomic_binary(OUT / name, data)
        answer.append(data)
    return tuple(answer)


def normalize(v):
    a = np.asarray(v, dtype=float)
    le = np.linalg.norm(a)
    return a / le if le > 1e-10 else np.array([0., 1., 0.])


def quat_mul(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return np.array([w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z])


def quat_inv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def euler(x=0., y=0., z=0.):
    # XYZ, matching THREE.Euler's default order.
    x, y, z = np.radians([x, y, z]) / 2
    a, b, c = math.sin(x), math.sin(y), math.sin(z)
    A, B, C = math.cos(x), math.cos(y), math.cos(z)
    return np.array([a*B*C+A*b*c, A*b*C-a*B*c, A*B*c+a*b*C, A*B*C-a*b*c])


def q_from_to(a, b):
    a, b = normalize(a), normalize(b)
    dot = float(np.dot(a, b))
    if dot < -.999999:
        axis = normalize(np.cross(a, [1, 0, 0]) if abs(a[0]) < .9 else np.cross(a, [0, 0, 1]))
        return np.array([*axis, 0.])
    return normalize_quat(np.array([*np.cross(a, b), 1 + dot]))


def normalize_quat(q):
    return np.asarray(q) / np.linalg.norm(q)


def q_rotate(q, v):
    return quat_mul(quat_mul(q, [*v, 0]), quat_inv(q))[:3]


def axis_quat(direction, roll=0.):
    return quat_mul(q_from_to([0, 1, 0], direction), euler(0, roll, 0))


def blend_q(a, b, t):
    if np.dot(a, b) < 0:
        b = -b
    return normalize_quat(np.asarray(a) * (1-t) + np.asarray(b) * t)


class Mesh:
    def __init__(self):
        self.p = []
        self.n = []
        self.uv = []
        self.indices = []

    def mirror_x(self):
        for p, n in zip(self.p, self.n):
            p[0] = -p[0]
            n[0] = -n[0]
        for i in range(0, len(self.indices), 3):
            self.indices[i+1], self.indices[i+2] = self.indices[i+2], self.indices[i+1]

    def face(self, points, tile="steel", uv=None, reverse=False):
        points = np.asarray(points, dtype=float)
        if reverse:
            points = points[::-1]
            if uv is not None:
                uv = uv[::-1]
        cross = np.zeros(3)
        for i in range(1, len(points)-1):
            cross += np.cross(points[i]-points[0], points[i+1]-points[0])
        if np.linalg.norm(cross) < 1e-12:
            return
        n = normalize(cross)
        start = len(self.p)
        if uv is None:
            # Stable planar mapping, with UVs padded away from atlas tile edges.
            drop = int(np.argmax(np.abs(n)))
            axes = [j for j in range(3) if j != drop]
            xy = points[:, axes]
            lo, hi = xy.min(axis=0), xy.max(axis=0)
            uv = (xy-lo) / np.maximum(hi-lo, 1e-6)
        k = TILES[tile]
        for point, tex in zip(points, uv):
            self.p.append(point.tolist())
            self.n.append(n.tolist())
            self.uv.append([((k % 4)*128 + 7 + float(tex[0])*114)/512, ((k // 4)*128 + 7 + (1-float(tex[1]))*114)/512])
        for i in range(1, len(points)-1):
            self.indices.extend([start, start+i, start+i+1])

    def loft(self, rings, tile="steel", sides=12, ridge=0., flutes=0., caps=True, phase=0., tiles=None, omit=None):
        # Each cross section: y, half-width, front-depth, back-depth, optional x/z offset.
        rows = []
        for ri, ring in enumerate(rings):
            y, width, front, back = ring[:4]
            cx, cz = ring[4:6] if len(ring) >= 6 else (0., 0.)
            row = []
            for j in range(sides):
                a = TAU*j/sides + phase
                c, s = math.cos(a), math.sin(a)
                fold = 1 + flutes*math.cos(a*12 + .16*ri)
                row.append([cx+s*width*fold, y, cz+c*(front if c >= 0 else back)*fold + ridge*max(c, 0)**8])
            rows.append(row)
        for i in range(len(rows)-1):
            for j in range(sides):
                if omit and omit(i, j):
                    continue
                k = (j+1) % sides
                mat = tiles(i, j) if tiles else tile
                self.face([rows[i][j], rows[i][k], rows[i+1][k], rows[i+1][j]], mat,
                          None if mat=="mail" else [(j/sides, i/(len(rows)-1)), ((j+1)/sides, i/(len(rows)-1)), ((j+1)/sides, (i+1)/(len(rows)-1)), (j/sides, (i+1)/(len(rows)-1))])
        if caps:
            self.face(rows[0], tile, reverse=True)
            self.face(rows[-1], tile)

    def plate(self, xy, z=.0, depth=.012, tile="steel", edge="edge", bulge=.0):
        # Bevelled polygon with a raised central facet and a solid reverse.
        points = np.asarray([[p[0], p[1], p[2] if len(p)>2 else z] for p in xy], float)
        if np.cross(points[1]-points[0], points[2]-points[0])[2] < 0:
            points = points[::-1]
        center = points.mean(axis=0)
        inner = center + (points-center)*.89
        inner[:, 2] += depth
        apex = center + [0, 0, depth+bulge]
        back = points - [0, 0, depth*.35]
        for i in range(len(points)):
            j = (i+1) % len(points)
            self.face([points[i], points[j], inner[j], inner[i]], edge)
            self.face([inner[i], inner[j], apex], tile)
            self.face([back[i], back[j], points[j], points[i]], edge)
        self.face(back, tile, reverse=True)

    def path(self, points, radius, tile="edge", sides=6, taper=None):
        points = np.asarray(points, float)
        rows = []
        for i, p in enumerate(points):
            direction = normalize(points[min(i+1, len(points)-1)] - points[max(0, i-1)])
            ref = [0, 1, 0] if abs(direction[1]) < .9 else [0, 0, 1]
            a = normalize(np.cross(direction, ref))
            b = normalize(np.cross(direction, a))
            r = (taper[i] if taper else radius)
            rows.append([p + r*(math.cos(TAU*j/sides)*a+math.sin(TAU*j/sides)*b) for j in range(sides)])
        for i in range(len(rows)-1):
            for j in range(sides):
                k = (j+1) % sides
                self.face([rows[i][j], rows[i][k], rows[i+1][k], rows[i+1][j]], tile,
                          [(j/sides, i/(len(rows)-1)), ((j+1)/sides, i/(len(rows)-1)), ((j+1)/sides, (i+1)/(len(rows)-1)), (j/sides, (i+1)/(len(rows)-1))])
        self.face(rows[0], tile, reverse=True)
        self.face(rows[-1], tile)

    def rivet(self, center, radius=.0055, tile="edge", normal=(0, 0, 1)):
        center = np.asarray(center)
        q = q_from_to([0, 0, 1], normal)
        pts = [center+q_rotate(q, [math.cos(j*TAU/8)*radius, math.sin(j*TAU/8)*radius, 0]) for j in range(8)]
        peak = center+np.asarray(normal)*radius*.52
        for j in range(8):
            self.face([pts[j], pts[(j+1)%8], peak], tile)

    def cloth(self, rows, tile="red", folds=10, band=False):
        # Transverse vertices for a shaped, fully backed hanging cloth panel.
        strips = []
        for i, (y, width, z, taper) in enumerate(rows):
            row = []
            for j in range(folds+1):
                u = j/folds
                x = (u*2-1)*width
                zz = z + math.cos(u*TAU*3+.17*i)*taper + .01*(abs(u-.5)*2)
                row.append([x, y+(math.cos(u*TAU*2)*.009 if i == len(rows)-1 else 0), zz])
            strips.append(row)
        for i in range(len(rows)-1):
            for j in range(folds):
                points = [strips[i][j], strips[i+1][j], strips[i+1][j+1], strips[i][j+1]]
                self.face(points, tile)
                self.face([np.array(p)-[0, 0, .005] for p in points], tile, reverse=True)
        if band:
            # Actual narrow sewn edging: do not recolour a whole cloth segment as a hem.
            for side in (0, folds):
                self.path([np.array(row[side])+[0, 0, .004] for row in strips], .0034, "thread", sides=5)
            self.path([np.array(point)+[0, .006, .004] for point in strips[-1]], .0042, "thread", sides=5)


class GLB:
    def __init__(self, name, images):
        self.name = name
        self.doc = {"asset": {"version": "2.0", "generator": "The Gloaming Road / original deterministic character workshop 1.0", "copyright": "Original art authored for The Gloaming Road"},
                    "scene": 0, "scenes": [{"name": name, "nodes": [0]}], "nodes": [], "meshes": [],
                    "materials": [{"name": "Roadworn / painted steel, woven cloth and leather", "doubleSided": True,
                                   "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicRoughnessTexture": {"index": 1}, "metallicFactor": 1, "roughnessFactor": 1},
                                   "emissiveTexture": {"index": 2}, "emissiveFactor": [.38, .38, .38]}],
                    "textures": [{"source": j, "sampler": 0} for j in range(3)],
                    "samplers": [{"magFilter": 9728, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
                    "images": [], "bufferViews": [], "accessors": [], "animations": []}
        self.bin = bytearray()
        self.ids = {}
        self.meshes = defaultdict(Mesh)
        self.rest = {}
        self.trans = {}
        self.scal = {}
        for j, data in enumerate(images):
            view = self.blob(data)
            self.doc["images"].append({"name": ["512px original color atlas", "512px material surface atlas", "512px muted gem emission"][j], "mimeType": "image/png", "bufferView": view})
        self.node("character-root", None)

    def blob(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target:
            view["target"] = target
        self.doc["bufferViews"].append(view)
        return len(self.doc["bufferViews"])-1

    def accessor(self, data, kind, indices=False, target=None, bounds=False):
        a = np.asarray(data, dtype="<u4" if indices else "<f4")
        view = self.blob(a.tobytes(), target)
        acc = {"bufferView": view, "componentType": 5125 if indices else 5126, "count": len(a), "type": kind}
        if bounds:
            acc["min"] = np.atleast_1d(a.min(axis=0)).tolist()
            acc["max"] = np.atleast_1d(a.max(axis=0)).tolist()
        self.doc["accessors"].append(acc)
        return len(self.doc["accessors"])-1

    def node(self, name, parent="character-root", position=(0, 0, 0), rotation=None, scale=(1, 1, 1)):
        ix = len(self.doc["nodes"])
        rotation = np.array(rotation if rotation is not None else [0, 0, 0, 1], float)
        self.ids[name] = ix
        self.rest[name] = rotation
        self.trans[name] = np.array(position, float)
        self.scal[name] = np.array(scale, float)
        self.doc["nodes"].append({"name": name, "translation": list(position), "rotation": rotation.tolist(), "scale": list(scale)})
        if parent is not None:
            self.doc["nodes"][self.ids[parent]].setdefault("children", []).append(ix)
        return self.meshes[name]

    def channel(self, anim, name, path, times, values):
        # Quaternion signs must remain continuous when interpolating rotations.
        values = [np.asarray(x, float) for x in values]
        if path == "rotation":
            for i in range(1, len(values)):
                if np.dot(values[i-1], values[i]) < 0:
                    values[i] = -values[i]
        input_ix = self.accessor(times, "SCALAR", bounds=True)
        output_ix = self.accessor(values, "VEC4" if path=="rotation" else "VEC3")
        sampler = len(anim["samplers"])
        anim["samplers"].append({"input": input_ix, "output": output_ix, "interpolation": "LINEAR"})
        anim["channels"].append({"sampler": sampler, "target": {"node": self.ids[name], "path": path}})

    def export(self):
        triangles = 0
        vertex_count = 0
        for name, mesh in self.meshes.items():
            if not mesh.indices:
                continue
            positions = self.accessor(mesh.p, "VEC3", target=34962, bounds=True)
            normals = self.accessor(mesh.n, "VEC3", target=34962)
            uv = self.accessor(mesh.uv, "VEC2", target=34962)
            indices = self.accessor(mesh.indices, "SCALAR", indices=True, target=34963)
            mix = len(self.doc["meshes"])
            self.doc["meshes"].append({"name": name+" / contoured mesh", "primitives": [{"attributes": {"POSITION": positions, "NORMAL": normals, "TEXCOORD_0": uv}, "indices": indices, "material": 0}]})
            self.doc["nodes"][self.ids[name]]["mesh"] = mix
            triangles += len(mesh.indices)//3
            vertex_count += len(mesh.p)
        self.doc["buffers"] = [{"byteLength": len(self.bin)}]
        self.doc["extras"] = {"kind": self.name, "units": "metres", "forward": "+Z", "feetY": 0, "original": True,
                              "rig": "Named rigid articulation; no external skin dependency; root motion is gameplay-owned",
                              "triangles": triangles, "contactWindows": {"light": [.24, .38], "heavy": [.52, .70]}}
        data = json.dumps(self.doc, separators=(",", ":"), ensure_ascii=True).encode()
        data += b" " * ((-len(data)) % 4)
        self.bin += b"\0" * ((-len(self.bin)) % 4)
        result = struct.pack("<4sII", b"glTF", 2, 12+8+len(data)+8+len(self.bin)) + struct.pack("<I4s", len(data), b"JSON") + data + struct.pack("<I4s", len(self.bin), b"BIN\0") + self.bin
        path = OUT / (self.name+".glb")
        atomic_binary(path, result)
        info = {"kind": self.name, "file": path.name, "triangles": triangles, "vertices": vertex_count,
                "rigidMeshes": len(self.doc["meshes"]), "nodes": len(self.ids), "bytes": len(result),
                "clips": {a["name"]: float(max(self.doc["accessors"][s["input"]]["max"][0] for s in a["samplers"])) for a in self.doc["animations"]}}
        print(f"{self.name:10} {triangles:5} triangles / {len(self.doc['meshes']):2} articulated meshes / {len(self.doc['animations']):2} clips / {len(result):,} bytes")
        return info


def armor_rim(mesh, y, width, front, back, tile="edge", cx=0):
    mesh.loft([(y-.008, width, front, back, cx, 0), (y, width+.001, front+.002, back+.002, cx, 0), (y+.006, width-.002, front, back, cx, 0)], tile, sides=12, caps=False)


def hand(mesh, armored=True, small=False):
    # A real closed grip: metacarpal shell, four separately curled fingers, thumb.
    material = "mail" if armored else "skin"
    scale = .88 if small else 1.
    mesh.loft([(-.098*scale, .029*scale, .021, .024), (-.082*scale, .038*scale, .025, .031), (-.028*scale, .039*scale, .024, .030), (.009, .027*scale, .021, .023)], material, sides=10)
    if armored:
        mesh.plate([(-.038, -.085), (-.037, -.015), (-.027, .015), (.027, .015), (.038, -.016), (.036, -.084)], z=-.029, depth=.006, tile="steel", edge="edge", bulge=.004)
        armor_rim(mesh, .013, .033, .028, .029, "steel")
    for finger in range(4):
        y = (-.021-finger*.021)*scale
        path = np.array([[-.030, y, -.006], [-.043, y-.002, .014], [-.028, y-.003, .039], [-.004, y-.003, .045], [.019, y-.001, .032], [.020, y+.002, .012]])
        path[:, 0] *= scale
        mesh.path(path, .0086*scale, material, sides=6)
        if armored:
            for k in (1, 2, 3):
                mesh.path([path[k]*[1, 1, 1]+[0, .001, .002], path[k+1]*[1, 1, 1]+[0, .001, .002]], .0092*scale, "steel" if k<3 else "edge", sides=6)
            mesh.rivet([-.027*scale, y, .045], .006*scale)
    mesh.path([[.032*scale, -.018, -.011], [.045*scale, -.036, .010], [.034*scale, -.055, .029], [.012*scale, -.068, .034]], .011*scale, "steel" if armored else "skin", sides=7, taper=[.012*scale, .0115*scale, .010*scale, .008*scale])


def shoe(mesh, armored=True, dainty=False):
    # Long, pointed sabatons with six separate overlapping toe lames.
    width_scale = .83 if dainty else 1.
    rows = []
    for z, width, h in [(-.086, .048, .100), (-.037, .061, .126), (.038, .072, .105), (.115, .064, .073), (.182, .048, .050), (.242, .023, .028), (.256, .004, .018)]:
        w = width*width_scale
        rows.append([[-w, -.096, z], [-w, -.074+h*.24, z], [-w*.70, -.096+h*.88, z], [0, -.096+h, z], [w*.70, -.096+h*.88, z], [w, -.074+h*.24, z], [w, -.096, z]])
    mat = "steel" if armored else "rose" if dainty else "leather"
    for i in range(len(rows)-1):
        for j in range(6):
            mesh.face([rows[i][j], rows[i][j+1], rows[i+1][j+1], rows[i+1][j]], mat)
        mesh.face([rows[i][0], rows[i+1][0], rows[i+1][-1], rows[i][-1]], "leather")
        if armored and i>0:
            mesh.path(np.array(rows[i]) + [0, .004, .004], .0035, "edge", sides=4)
    mesh.face(rows[0], mat)
    mesh.face(rows[-1], mat, reverse=True)
    if armored:
        armor_rim(mesh, .020, .057, .062, .055, "edge")
        for x in (-.036, .036):
            mesh.rivet([x, .023, .009], .0045, normal=[0, 1, .1])


def sword(g, parent, elite=False, viewmodel=False):
    m = g.node("weapon", parent, (0, -.031, .023))
    # Diamond-section tapered blade; edges, fuller and bevels are actual geometry.
    y0, tip = .083, 1.104 if viewmodel else 1.062
    rows = [(y0, .027, .0070), (.17, .026, .0075), (.63, .023, .0065), (.93 if not viewmodel else .97, .017, .0055), (tip, 0., .0000)]
    for face_sign in (-1, 1):
        strips = []
        for y, w, depth in rows:
            strips.append([[-w, y, 0], [-w*.75, y, face_sign*depth*.73], [-w*.16, y, face_sign*depth], [w*.16, y, face_sign*depth], [w*.75, y, face_sign*depth*.73], [w, y, 0]])
        for i in range(len(rows)-1):
            for j in range(5):
                material = "edge" if j in (0, 4) else "steel" if j != 2 else "mail"
                m.face([strips[i][j], strips[i][j+1], strips[i+1][j+1], strips[i+1][j]], material, reverse=face_sign<0)
    guard = "gilt" if elite else "steel"
    m.plate([(-.155, .036), (-.148, .071), (-.063, .086), (-.033, .100), (.033, .100), (.063, .086), (.148, .071), (.155, .036), (.130, .036), (.047, .060), (-.047, .060), (-.130, .036)], z=.008, depth=.012, tile=guard, edge="edge", bulge=.001)
    m.loft([(-.133, .0155, .018, .018), (-.10, .017, .018, .018), (.045, .014, .015, .015), (.063, .021, .021, .021)], "leather", sides=10)
    for y in np.linspace(-.127, .051, 12):
        m.loft([(y, .0162, .0186, .0186), (y+.003, .0168, .019, .019)], "gilt" if elite else "mail", sides=10, caps=False)
    m.loft([(-.177, .008, .009, .009), (-.158, .025, .017, .017), (-.145, .028, .018, .018), (-.130, .018, .015, .015)], guard, sides=10)
    m.rivet([0, -.150, .019], .010, "gilt" if elite else "edge")
    # Markers are along the blade, not hilt, in metres.
    g.node("weapon-base", "weapon", (0, y0, 0))
    g.node("weapon-tip", "weapon", (0, tip, 0))


def face_head(m, female=False, aged=False):
    w = .92 if female else 1.
    m.loft([(-.033, .043*w, .054, .064), (-.009, .066*w, .074, .078), (.040, .086*w, .089, .089), (.090, .094*w, .098, .098), (.145, .092*w, .097, .100), (.193, .078*w, .083, .088), (.218, .051*w, .055, .063), (.229, .004, .006, .008)], "skin", sides=16, ridge=.004)
    for side in (-1, 1):
        m.loft([(.042, .009, .018, .013, side*.09*w, -.006), (.075, .014, .019, .017, side*.09*w, -.006), (.105, .008, .011, .009, side*.09*w, -.006)], "skin", sides=8)
        ex = side*.038*w
        # Recessed small eyes, upper eyelid and separate brow; deliberately not cartoon eyes.
        m.plate([(ex-.019, .108), (ex-.010, .113), (ex+.012, .111), (ex+.020, .106), (ex+.008, .102), (ex-.009, .102)], z=.099, depth=.0013, tile="black", edge="skin")
        m.rivet([ex+side*.001, .107, .102], .0028, "ivory")
        m.path([[ex-.021, .123, .103], [ex, .128, .107], [ex+.020, .124, .103]], .004 if female else .005, "hair" if not aged else "mail", sides=4)
        if aged:
            m.path([[ex-.016, .090, .101], [ex, .086, .106], [ex+.014, .091, .101]], .0019, "rose", sides=4)
    # Angular nose with a real bridge and nostrils, mouth with shaped lower lip.
    nose_w = .013 if female else .016
    m.face([[-nose_w, .064, .105], [0, .066, .131], [0, .134, .105]], "skin")
    m.face([[0, .066, .131], [nose_w, .064, .105], [0, .134, .105]], "skin")
    m.face([[-nose_w, .064, .105], [nose_w, .064, .105], [0, .066, .131]], "rose")
    m.path([[-.019, .043, .092], [0, .041, .098], [.019, .043, .092]], .0022, "rose", sides=4)
    m.path([[-.014, .036, .093], [0, .034, .096], [.014, .036, .093]], .0018, "skin", sides=4)
    if aged:
        m.plate([(-.051, .032), (-.046, -.012), (-.018, -.072), (0, -.098), (.018, -.072), (.046, -.012), (.051, .032), (.024, .014), (0, .006), (-.024, .014)], z=.080, depth=.009, tile="ivory", edge="thread", bulge=.013)
        for x in (-.021, -.010, .009, .019):
            m.path([[x, -.008, .098], [x*.55, -.054, .100]], .0016, "thread", sides=4)


def helmet(m, elite=False):
    m.loft([(-.045, .078, .083, .089), (-.012, .109, .113, .108), (.068, .113, .119, .112), (.142, .110, .112, .108), (.198, .081, .079, .090), (.234, .032, .030, .055), (.248, .006, .009, .019)], "steel", sides=16, ridge=.016)
    # Dark visor aperture with a sculpted heavy brow and central nose ridge.
    slit = [(-.094, .088, .095), (-.073, .101, .127), (-.010, .106, .145), (0, .102, .147), (.010, .106, .145), (.073, .101, .127), (.094, .088, .095), (.070, .084, .129), (0, .088, .150), (-.070, .084, .129)]
    m.face(slit, "black")
    m.path([[-.098, .103, .096], [-.071, .113, .128], [0, .119, .147], [.071, .113, .128], [.098, .103, .096]], .006, "edge", sides=5)
    m.plate([(-.013, .113), (-.008, .031), (0, .010), (.008, .031), (.013, .113)], z=.139, depth=.006, tile="steel", edge="edge", bulge=.003)
    m.path([[-.099, -.008, .064], [-.065, -.035, .094], [0, -.057, .121], [.065, -.035, .094], [.099, -.008, .064]], .0045, "gilt" if elite else "edge", sides=5)
    for s in (-1, 1):
        for j in range(3):
            x = s*(.035+j*.016)
            z = .143-abs(x)*.36
            m.plate([(x-.003, .024), (x-.003, .052), (x+.003, .055), (x+.003, .027)], z=z, depth=.001, tile="black", edge="steel")
        m.rivet([s*.110, .088, .024], .010, "gilt" if elite else "edge", normal=[s, 0, .1])
        m.rivet([s*.091, .068, .093], .0065, "gilt" if elite else "edge")
    # Fine ridge and construction seam from brow to the elongated, angular crown.
    m.path([[0, .132, .135], [0, .199, .098], [0, .248, .023], [0, .226, -.059], [0, .151, -.112]], .0035, "gilt" if elite else "edge", sides=5)
    if elite:
        for s in (-1, 1):
            m.path([[s*.033, .136, .127], [s*.046, .174, .108], [s*.029, .216, .071]], .0022, "gilt", sides=4)


def shield(g):
    m = g.node("shield", "hand-l", (0, -.035, .084))
    xy = [(-.285, -.405), (.285, -.405), (.310, -.350), (.306, .344), (.253, .415), (-.253, .415), (-.306, .344), (-.310, -.350)]
    m.plate(xy, z=.005, depth=.026, tile="red", edge="leather", bulge=.025)
    # Broad red-painted boards, visible grain, worn wood seams; closed backing and metal edge.
    for j in range(5):
        x0, x1 = -.274+j*.110, -.168+j*.110
        z0 = .048 + (1-abs((x0+x1)/2)/.30)*.028
        m.plate([(x0, -.378), (x1, -.378), (x1, .362), (x0, .362)], z=z0, depth=.0015, tile="red", edge="wood")
        m.path([[x0+.010, -.350, z0+.002], [x0+.013, -.17, z0+.004], [x0+.009, .04, z0+.004], [x0+.015, .29, z0+.003]], .0018, "wood", sides=4)
    m.path([[x, y, .038] for x, y in xy]+[[xy[0][0], xy[0][1], .038]], .013, "steel", sides=6)
    # Center boss and restrained original forked-road heraldry.
    m.plate([(-.073, -.074), (0, -.102), (.073, -.074), (.093, 0), (.073, .074), (0, .098), (-.073, .074), (-.093, 0)], z=.078, depth=.014, tile="steel", edge="edge", bulge=.037)
    for s in (-1, 1):
        m.path([[s*.072, .112, .073], [s*.150, .246, .064], [s*.135, .269, .064]], .011, "thread", sides=5)
    for x in (-.274, .274):
        for y in (-.335, -.20, 0, .20, .338):
            m.rivet([x, y, .051], .008, "edge")
    for y in (-.235, .235):
        m.plate([(-.28, y-.014), (.28, y-.014), (.28, y+.014), (-.28, y+.014)], z=-.008, depth=.007, tile="wood", edge="leather")
        m.path([[-.105, y, -.020], [-.106, y, -.070], [.103, y, -.071], [.105, y, -.020]], .014, "leather", sides=6)


def bow_and_quiver(g):
    m = g.node("weapon", "hand-l", (0, -.036, .036))
    curve = [[0, -.652, -.175], [0, -.590, -.106], [0, -.482, .025], [0, -.280, .074], [0, -.10, .022], [0, 0, 0], [0, .10, .022], [0, .280, .074], [0, .482, .025], [0, .590, -.106], [0, .652, -.175]]
    m.path(curve, .016, "wood", sides=8, taper=[.006, .010, .015, .019, .019, .017, .019, .019, .015, .010, .006])
    m.path([[.015, y, z] for _, y, z in curve[1:-1]], .0033, "mustard", sides=5)
    for y in np.linspace(-.082, .082, 11):
        m.loft([(y, .020, .022, .022), (y+.006, .020, .022, .022)], "leather", sides=8, caps=False)
    for s in (-1, 1):
        name = "bow-string-upper" if s==1 else "bow-string-lower"
        endpoint = np.array([0., s*.652, -.175])
        vec = np.array([0., 0., -.230])-endpoint
        string = g.node(name, "weapon", endpoint, q_from_to([0, 1, 0], vec), (1, float(np.linalg.norm(vec)), 1))
        string.path([[0, 0, 0], [0, 1, 0]], .0014, "thread", sides=4)
    arrow = g.node("arrow", "weapon", (0, 0, 0))
    arrow.path([[0, 0, -.26], [0, 0, .450]], .0032, "wood", sides=6)
    arrow.plate([(-.013, .003, .449), (0, .003, .510), (.013, .003, .449)], z=0, depth=.001, tile="steel", edge="edge")
    for a in (0, TAU/3, 2*TAU/3):
        v = np.array([math.cos(a), math.sin(a), 0])
        points = [np.array([0, 0, -.255])+v*.002, np.array([0, 0, -.234])+v*.027, np.array([0, 0, -.140])+v*.022, np.array([0, 0, -.119])+v*.003]
        arrow.face(points, "ivory")
        arrow.face(points, "ivory", reverse=True)
    g.node("weapon-base", "weapon", (0, 0, -.260))
    g.node("weapon-tip", "weapon", (0, 0, .510))
    quiver = g.node("quiver", "chest", (-.140, -.030, -.174), euler(0, 0, 18))
    quiver.loft([(-.270, .046, .047, .047), (-.228, .062, .063, .063), (.178, .068, .069, .069), (.223, .074, .075, .075)], "leather", sides=12, caps=False)
    quiver.loft([(.203, .076, .077, .077), (.226, .076, .077, .077), (.232, .064, .065, .065), (.208, .061, .062, .062)], "mustard", sides=12, caps=False)
    quiver.loft([(-.273, .047, .048, .048), (-.25, .054, .055, .055)], "wood", sides=12)
    for i in range(7):
        a = i*TAU/7
        x, z = math.sin(a)*.039, math.cos(a)*.039
        y = .40+(i%3)*.023
        quiver.path([[x, -.06, z], [x, y, z]], .0035, "wood", sides=5)
        for axis in ((.018, 0), (0, .018)):
            dx, dz = axis
            quiver.face([[x-dx, y-.065, z-dz], [x+dx, y-.065, z+dz], [x+dx, y-.008, z+dz], [x, y+.014, z]], "ivory" if i%2 else "red")
            quiver.face([[x-dx, y-.065, z-dz], [x+dx, y-.065, z+dz], [x+dx, y-.008, z+dz], [x, y+.014, z]], "ivory", reverse=True)


def staff(g):
    m = g.node("weapon", "hand-r", (0, -.033, .026))
    points = [[.010, -.77, -.010], [0, -.62, 0], [-.012, -.38, .005], [.009, -.12, 0], [0, .17, 0], [.016, .42, -.014], [.006, .67, 0], [-.006, .76, .005]]
    m.path(points, .019, "wood", sides=9, taper=[.012, .019, .018, .016, .017, .021, .024, .023])
    m.loft([(-.788, .015, .016, .016), (-.712, .018, .019, .019)], "steel", sides=8)
    for y in np.linspace(-.12, .10, 11):
        m.loft([(y, .020, .021, .021), (y+.006, .020, .021, .021)], "leather", sides=8, caps=False)
    for y in (.43, .62, .72):
        m.loft([(y, .029, .029, .029), (y+.024, .029, .029, .029)], "gilt", sides=10)
    for s in (-1, 1):
        m.path([[s*.015, .73, 0], [s*.068, .78, .002], [s*.076, .89, .006], [s*.043, .952, 0], [s*.017, .975, 0]], .010, "wood", sides=7, taper=[.018, .015, .011, .008, .004])
        m.path([[0, .749, s*.010], [0, .80, s*.052], [0, .909, s*.052], [0, .949, s*.022]], .0065, "gilt", sides=6)
    m.loft([(.770, .001, .001, .001), (.822, .043, .035, .035), (.902, .034, .028, .028), (.941, .002, .002, .002)], "gem", sides=7)
    # Hanging votive cord, small stone, asymmetric silhouette rather than a stock wizard orb.
    m.path([[-.058, .798, 0], [-.084, .682, .017], [-.059, .591, .033]], .003, "thread", sides=5)
    m.loft([(.555, .004, .006, .006, -.059, .034), (.575, .016, .010, .010, -.059, .034), (.596, .006, .007, .007, -.059, .034)], "gilt", sides=6)
    g.node("weapon-base", "weapon", (0, -.710, 0))
    g.node("weapon-tip", "weapon", (0, .974, 0))


def robe_skirt(g, princess=False):
    # Four separately animated angular/folded panels; the feet and articulated legs remain real.
    for panel, start in (("skirt-front", -PI/4), ("skirt-l", PI/4), ("skirt-back", 3*PI/4), ("skirt-r", 5*PI/4)):
        mesh = g.node(panel, "hips")
        rings = [(-.10, .141, .130), (-.28, .180, .157), (-.53, .245, .199), (-.75, .295, .236), (-.922, .325, .271)]
        rows = []
        n = 10
        for i, (y, w, d) in enumerate(rings):
            row = []
            for j in range(n+1):
                a = start+PI/2*j/n
                fold = .007+(.010*i/4)
                wav = math.cos(a*16+.19*i)*fold
                row.append([math.sin(a)*(w+wav), y + (math.cos(a*8)*.007 if i==4 else 0), math.cos(a)*(d+wav)])
            rows.append(row)
        for i in range(4):
            for j in range(n):
                center = panel=="skirt-front" and 3<=j<=6
                mat = ("rose" if center else "ivory") if princess else ("red" if center else "robe")
                pts = [rows[i][j], rows[i][j+1], rows[i+1][j+1], rows[i+1][j]]
                mesh.face(pts, mat)
                mesh.face([np.array(v)*[.985, 1, .985] for v in pts], mat, reverse=True)
        for j in range(n):
            a, b = np.array(rows[-1][j]), np.array(rows[-1][j+1])
            mesh.face([a, b, b+[0, .035, 0], a+[0, .035, 0]], "thread")
        if panel=="skirt-front":
            for j in (3, 7):
                mesh.path([np.asarray(row[j])+[0, 0, .003] for row in rows], .0035, "thread", sides=5)
            # Small sewn angular leafwork at the gown/robe hem, not a repeated logo texture.
            for j in range(1, n, 2):
                x, y, z = rows[-1][j]
                mesh.path([[x-.012, y+.058, z+.003], [x, y+.088, z+.004], [x+.012, y+.058, z+.003]], .0022, "thread", sides=4)


def hood(mesh):
    rings = [(-.110, .145, .101, .138), (.017, .163, .121, .142), (.131, .160, .124, .147), (.219, .105, .093, .109), (.246, .027, .025, .052)]
    # The front sector is genuinely open: the pale face sits inside the hood, not on its exterior.
    mesh.loft(rings, "robe", sides=20, caps=False, omit=lambda i, j: i<3 and (j<3 or j>=17))
    inner = [(-.093, -.047, .101), (-.108, .083, .132), (-.090, .173, .126), (0, .220, .106), (.090, .173, .126), (.108, .083, .132), (.093, -.047, .101)]
    outer = [(-.148, -.107, .087), (-.164, .081, .105), (-.128, .196, .086), (0, .248, .050), (.128, .196, .086), (.164, .081, .105), (.148, -.107, .087)]
    for i in range(len(inner)-1):
        mesh.face([inner[i], inner[i+1], outer[i+1], outer[i]], "robe")
        mesh.face([np.array(inner[i])-[0, 0, .012], np.array(inner[i+1])-[0, 0, .012], inner[i+1], inner[i]], "black")
    mesh.path(inner, .0055, "thread", sides=5)
    mesh.path(outer, .004, "robe", sides=5)
    mesh.cloth([(-.083, .140, -.005, .016), (-.143, .182, .019, .018), (-.230, .165, .041, .019)], "robe", folds=10, band=True)


def hair_and_crown(mesh):
    mesh.loft([(-.032, .094, .071, .108), (.080, .102, .105, .111), (.164, .096, .100, .105), (.213, .074, .074, .081), (.236, .011, .011, .030)], "hair", sides=20, caps=False, omit=lambda i, j: i<3 and (j<4 or j>=16))
    for s in (-1, 1):
        mesh.path([[s*.008, .214, .075], [s*.051, .200, .099], [s*.082, .164, .096], [s*.096, .088, .080], [s*.091, -.025, .055], [s*.100, -.142, .036]], .021, "hair", sides=8, taper=[.012, .018, .020, .026, .023, .012])
        # Braided locks fall onto the non-armoured shoulders.
        for k in range(10):
            y = .071-k*.025
            x = s*(.098 + math.sin(k*2.2)*.007)
            z = .049+math.cos(k*2.2)*.008
            mesh.loft([(y-.018, .010, .011, .011, x, z), (y-.006, .016, .015, .015, x, z), (y+.010, .012, .012, .012, x, z)], "hair", sides=7)
        mesh.loft([(-.182, .015, .016, .016, s*.098, .050), (-.169, .015, .016, .016, s*.098, .050)], "gilt", sides=8)
    # Thin open circlet with eight fleur-like raised points, not a helmet.
    mesh.loft([(.182, .098, .105, .099), (.202, .098, .105, .099)], "gilt", sides=24, caps=False)
    for j in range(8):
        a = TAU*j/8
        c, s = math.cos(a), math.sin(a)
        center = np.array([s*.099, .202, c*.105])
        tangent = np.array([c, 0, -s])
        outward = np.array([s, 0, c])
        pts = [center+tangent*(-.016), center+tangent*(-.020)+[0, .030, 0], center+tangent*(-.008)+[0, .037, 0], center+[0, .064 if j%2==0 else .048, 0]+outward*.005, center+tangent*.008+[0, .037, 0], center+tangent*.020+[0, .030, 0], center+tangent*.016]
        mesh.face(pts, "gilt")
        mesh.face([p-outward*.003 for p in pts], "gilt", reverse=True)
        mesh.rivet(center+[0, .014, 0]+outward*.003, .0055, "gem" if j==0 else "edge", normal=outward)


def humanoid(kind, images):
    g = GLB(kind, images)
    armored = kind in ("swordsman", "elite", "shield")
    elite = kind=="elite"
    princess = kind=="princess"
    mage = kind=="mage"
    archer = kind=="archer"
    hip = g.node("hips", position=(0, .956, 0))
    hip.loft([(-.133, .138, .111, .114), (-.081, .161, .117, .115), (.018, .158, .111, .111), (.071, .135, .099, .096)], "mail" if armored else "rose" if princess else "red" if archer else "robe", sides=16)
    belly = g.node("spine", "hips", (0, .040, 0))
    belly.loft([(-.025, .146, .116, .103), (.070, .141, .113, .103), (.183, .170, .124, .110)], "mail" if armored else "rose" if princess else "red" if archer else "robe", sides=16)
    chest = g.node("chest", "spine", (0, .209, 0))
    neck = g.node("neck", "chest", (0, .299, 0))
    neck.loft([(-.012, .058, .054, .054), (.065, .053, .050, .051), (.092, .049, .045, .047)], "mail" if armored or archer else "skin", sides=12)
    head = g.node("head", "neck", (0, .074, 0))
    if armored:
        chest.loft([(-.092, .142, .121, .098), (-.035, .158, .158, .107), (.061, .191, .175, .110), (.152, .208, .157, .112), (.228, .185, .119, .104), (.280, .123, .083, .086)], "steel", sides=16, ridge=.024)
        chest.path([[0, -.101, .142], [0, -.031, .187], [0, .061, .201], [0, .155, .183], [0, .228, .143], [0, .278, .102]], .0038, "gilt" if elite else "edge", sides=5)
        for s in (-1, 1):
            chest.path([[s*.126, .282, .041], [s*.095, .270, .086], [0, .252, .112]], .0048, "gilt" if elite else "edge", sides=5)
            chest.path([[s*.027, -.079, .151], [s*.095, -.064, .154], [s*.151, -.028, .137]], .0035, "edge", sides=5)
            # Restrained embossed flutes define the breastplate's tapered volume.
            for k in range(2):
                chest.path([[s*(.044+.033*k), -.057, .162-k*.007], [s*(.079+.033*k), .035, .166-k*.012], [s*(.093+.035*k), .121, .165-k*.014]], .0018, "gilt" if elite else "edge", sides=4)
            for y, x, z in ((.227, .147, .084), (.142, .178, .096), (-.030, .133, .118)):
                chest.rivet([s*x, y, z], .0055, "gilt" if elite else "edge")
        # Three overlapping fauld lames, inset red cloth beneath the hanging tassets.
        for i in range(3):
            y = .086-i*.041
            w = .151+i*.010
            hip.loft([(y-.041, w+.011, .137+i*.007, .119), (y-.011, w+.003, .134+i*.006, .117), (y, w, .129+i*.006, .116)], "steel", sides=16, caps=False)
            armor_rim(hip, y-.036, w+.01, .138+i*.007, .12, "gilt" if elite else "edge")
        cloth = g.node("tabard", "hips", (0, -.055, .043))
        cloth.cloth([(0, .096, .107, .009), (-.180, .111, .096, .016), (-.404, .109, .082, .018), (-.564, .095, .064, .022)], "red", folds=10, band=elite)
        for s in (-1, 1):
            tm = g.node("tasset-"+("r" if s<0 else "l"), "hips", (s*.109, -.045, .135))
            tm.plate([(-.078, -.014), (-.073, -.228), (-.045, -.282), (.068, -.257), (.078, -.079), (.054, .010)], z=.020, depth=.009, tile="steel", edge="gilt" if elite else "edge", bulge=.012)
            for y in (-.068, -.130, -.197):
                tm.path([[-.066, y, .034], [0, y-.010, .051], [.066, y, .034]], .0033, "edge", sides=4)
            for x in (-.048, .048):
                tm.rivet([x, -.015, .036], .0048, "gilt" if elite else "edge")
        helmet(head, elite)
    else:
        chest.loft([(-.101, .127 if princess else .143, .101, .093), (-.020, .140 if princess else .166, .119, .104), (.116, .174 if princess else .188, .133 if princess else .143, .107), (.209, .168 if princess else .184, .104, .105), (.269, .117, .078, .082)], "ivory" if princess else "red" if archer else "robe", sides=20, ridge=.008)
        face_head(head, princess, mage)
        if mage:
            hood(head)
            chest.cloth([(.264, .075, .090, .005), (.129, .079, .151, .005), (-.04, .065, .133, .005), (-.116, .060, .115, .005)], "red", folds=6, band=True)
            for y in (.174, .103):
                chest.rivet([0, y, .167], .008, "gilt")
        elif princess:
            hair_and_crown(head)
            chest.plate([(-.087, .236), (0, .189), (.087, .236), (.043, .266), (-.043, .266)], z=.088, depth=.001, tile="skin", edge="thread")
            for s in (-1, 1):
                chest.path([[s*.124, .218, .092], [s*.115, .089, .130], [s*.093, -.015, .115], [s*.075, -.084, .104]], .0045, "rose", sides=5)
            for y in (.047, .075, .103, .131):
                chest.path([[-.026, y, .144], [.026, y+.018, .144]], .0017, "thread", sides=4)
                chest.path([[.026, y, .145], [-.026, y+.018, .145]], .0017, "thread", sides=4)
            chest.path([[-.064, .227, .113], [0, .147, .151], [.064, .227, .113]], .002, "gilt", sides=5)
            chest.rivet([0, .145, .158], .010, "gem")
        elif archer:
            # Burgundy quilted gambeson, mustard shoulder mantle, open pointed metal cap.
            head.loft([(.121, .113, .119, .114), (.165, .109, .112, .113), (.220, .073, .075, .079), (.276, .017, .020, .026), (.284, .001, .003, .006)], "steel", sides=12, ridge=.006)
            head.loft([(.116, .135, .145, .127), (.130, .117, .124, .118)], "edge", sides=16, caps=False)
            for s in (-1, 1):
                head.path([[s*.10, .119, .043], [s*.088, .006, .062], [s*.042, -.028, .071]], .007, "leather", sides=5)
                chest.path([[s*.146, .178, .094], [s*.123, -.048, .091]], .0026, "mustard", sides=4)
            for y in (-.037, .014, .065, .116, .167):
                chest.path([[-.108, y, .128], [0, y+.016, .155], [.108, y, .128]], .0019, "leather", sides=4)
            # Diagonal quiver baldric, with edge stitching and a proper bronze buckle.
            chest.path([[-.169, .246, .071], [-.08, .139, .147], [.016, .025, .142], [.121, -.100, .108]], .023, "leather", sides=4)
            chest.plate([(-.076, .095), (-.047, .065), (-.012, .099), (-.041, .130)], z=.159, depth=.005, tile="gilt", edge="thread")
    # Belt is a separate encircling shaped band, with buckle, keepers and a hanging tail.
    hip.loft([(-.022, .168 if armored else .150, .128, .123), (.022, .168 if armored else .150, .128, .123)], "thread" if princess else "leather", sides=20, caps=False)
    hip.plate([(-.027, -.025), (.027, -.025), (.027, .027), (-.027, .027)], z=.137, depth=.005, tile="gilt", edge="edge")
    hip.plate([(-.014, -.012), (.014, -.012), (.014, .014), (-.014, .014)], z=.145, depth=.001, tile="leather", edge="gilt")
    if not princess:
        hip.plate([(.043, .014), (.067, .014), (.080, -.134), (.062, -.157), (.045, -.136)], z=.133, depth=.003, tile="leather", edge="leather")
    # Complete articulated limbs, including anatomy beneath robes and plate.
    for s, side in ((-1, "r"), (1, "l")):
        upper = g.node("upper-arm-"+side, "chest", (s*.220, .242, 0))
        fore = g.node("forearm-"+side, "upper-arm-"+side, (0, -.289, 0))
        palm = g.node("hand-"+side, "forearm-"+side, (0, -.251, 0))
        thigh = g.node("thigh-"+side, "hips", (s*.103, -.026, 0))
        shin = g.node("shin-"+side, "thigh-"+side, (0, -.424, 0))
        foot = g.node("foot-"+side, "shin-"+side, (0, -.410, 0))
        if armored:
            upper.loft([(-.281, .054, .057, .056), (-.175, .072, .074, .067), (-.055, .072, .073, .069), (.018, .064, .068, .064)], "mail", sides=12)
            upper.loft([(-.230, .068, .069, .066), (-.155, .077, .082, .072), (-.060, .074, .078, .071)], "steel", sides=12, caps=False)
            # Three genuinely overlapping pauldron shells, asymmetrically flared at the outside.
            for i in range(3):
                y = .041-i*.065
                width = .099-i*.004
                upper.loft([(y-.074, width+.006, .106-i*.002, .090, s*.018, 0), (y-.045, width+.009, .110-i*.002, .095, s*.018, 0), (y+.003, width*.81, .094-i*.003, .084, s*.018, 0), (y+.030, width*.55, .062, .062, s*.018, 0)], "steel", sides=12, caps=False)
                armor_rim(upper, y-.066, width+.009, .109-i*.002, .094, "gilt" if elite and i==0 else "edge", s*.018)
                upper.rivet([s*.073, y-.042, .095], .0045, "gilt" if elite else "edge")
            fore.loft([(-.245, .042, .045, .041), (-.206, .046, .049, .046), (-.105, .061, .066, .055), (-.016, .075, .072, .064), (.022, .065, .067, .061)], "steel", sides=12, ridge=.010)
            fore.plate([(-.064, .040), (-.104*s, -.010), (-.068, -.076), (0, -.099), (.068, -.063), (.092*s, -.010), (.047, .044)], z=.067, depth=.007, tile="steel", edge="gilt" if elite else "edge", bulge=.008)
            for y, w, z in ((-.221, .049, .053), (-.100, .064, .070)):
                armor_rim(fore, y, w, z, z*.87)
            thigh.loft([(-.406, .062, .064, .064), (-.338, .075, .077, .073), (-.166, .087, .091, .084), (-.025, .092, .094, .088), (.015, .082, .083, .081)], "mail", sides=12)
            thigh.loft([(-.330, .073, .083, .074), (-.205, .088, .098, .083), (-.054, .093, .096, .084)], "steel", sides=12, ridge=.008, caps=False)
            armor_rim(thigh, -.322, .075, .086, .076)
            shin.loft([(-.407, .043, .047, .044), (-.329, .048, .052, .047), (-.202, .061, .064, .055), (-.081, .074, .074, .064), (.010, .061, .065, .061)], "steel", sides=12, ridge=.012)
            shin.plate([(-.059, .050), (-.093, .008), (-.070, -.062), (0, -.086), (.070, -.062), (.093, .008), (.059, .050), (0, .073)], z=.068, depth=.009, tile="steel", edge="gilt" if elite else "edge", bulge=.024)
            shin.path([[0, -.366, .062], [0, -.185, .081], [0, -.079, .093]], .0032, "edge", sides=5)
            armor_rim(shin, -.355, .049, .060, .048)
            shin.rivet([0, -.006, .105], .006, "gilt" if elite else "edge")
        else:
            cloth = "ivory" if princess else "red" if archer else "robe"
            upper.loft([(-.280, .052, .054, .053), (-.211, .062, .063, .061), (-.076, .070, .069, .067), (.033, .065, .067, .061)], cloth, sides=14)
            if archer:
                upper.loft([(-.128, .082, .080, .076), (-.081, .091, .085, .081), (.021, .085, .079, .075), (.057, .052, .047, .050)], "mustard", sides=12, caps=False)
                armor_rim(upper, -.119, .084, .081, .077, "thread")
            elif princess:
                upper.loft([(-.142, .056, .057, .054), (-.110, .067, .066, .061), (-.057, .073, .071, .066), (.010, .069, .064, .060), (.042, .053, .051, .049), (.062, .022, .023, .023)], "rose", sides=16, caps=True)
                armor_rim(upper, -.135, .059, .060, .057, "thread")
            fore.loft([(-.251, .036, .039, .037), (-.196, .044, .046, .043), (-.088, .056, .060, .053), (.015, .053, .055, .050)], cloth, sides=14)
            if mage or princess:
                # Shaped bell sleeves remain bound to the forearm, trimmed and folded.
                fore.loft([(-.224, .071 if mage else .056, .069 if mage else .055, .065), (-.187, .068 if mage else .054, .065 if mage else .053, .061), (-.092, .056, .058, .054)], cloth, sides=16, flutes=.06, caps=False)
                armor_rim(fore, -.218, .073 if mage else .058, .071 if mage else .057, .067, "thread")
            else:
                fore.plate([(-.038, -.225), (-.050, -.102), (-.039, -.059), (.039, -.059), (.050, -.102), (.038, -.225)], z=.051, depth=.007, tile="leather", edge="mustard", bulge=.004)
                for y in (-.092, -.204):
                    armor_rim(fore, y, .054 if y>-.1 else .042, .059 if y>-.1 else .048, .050, "leather")
            thigh.loft([(-.416, .059, .062, .061), (-.323, .072, .075, .071), (-.110, .079, .083, .077), (.003, .075, .079, .075)], "rose" if princess else "red" if archer else "robe", sides=12)
            shin.loft([(-.405, .040, .044, .042), (-.287, .046, .051, .046), (-.120, .060, .063, .056), (.015, .058, .060, .055)], "leather", sides=12)
            for y in (-.124, -.189, -.260, -.335):
                armor_rim(shin, y, .061 if y>-.15 else .053 if y>-.3 else .047, .065 if y>-.15 else .056 if y>-.3 else .051, .057, "leather")
        hand(palm, armored, princess)
        if side == "l":
            palm.mirror_x()
        shoe(foot, armored, princess)
    if mage or princess:
        robe_skirt(g, princess)
    if elite:
        cape = g.node("cape", "chest", (0, .231, -.124))
        cape.cloth([(0, .179, -.011, .019), (-.218, .235, -.052, .024), (-.556, .272, -.083, .027), (-.941, .238, -.103, .031)], "red", folds=14, band=True)
        chest.path([[-.125, .217, .084], [0, .201, .134], [.125, .217, .084]], .0034, "gilt", sides=6)
        for s in (-1, 1):
            chest.rivet([s*.125, .219, .090], .012, "gilt")
    if armored:
        sword(g, "hand-r", elite)
        if kind=="shield":
            shield(g)
    elif archer:
        bow_and_quiver(g)
    elif mage:
        staff(g)
    else:
        g.node("weapon", "hand-r")
        g.node("weapon-base", "weapon", (0, -.047, .018))
        g.node("weapon-tip", "weapon", (0, -.047, .018))
    return g


def viewmodel(images):
    g = GLB("viewmodel", images)
    g.node("vm-pivot")
    # Camera mount recommendation rotates this +Z-forward authoring space by PI about Y.
    # Hands sit close together around a long arming-sword grip; arms taper back out of frame.
    g.node("chest", "vm-pivot", (0, 0, 0))
    for s, side in ((-1, "r"), (1, "l")):
        upper = g.node("upper-arm-"+side, "chest", (s*.220, -.300, -.285))
        fore = g.node("forearm-"+side, "upper-arm-"+side, (0, -.289, 0))
        palm = g.node("hand-"+side, "forearm-"+side, (0, -.251, 0))
        upper.loft([(-.290, .051, .055, .051), (-.20, .065, .069, .062), (-.075, .071, .074, .069), (.020, .074, .077, .070)], "mail", sides=14)
        fore.loft([(-.248, .043, .046, .043), (-.211, .049, .054, .049), (-.112, .068, .074, .063), (-.016, .084, .081, .076), (.041, .075, .071, .069)], "steel", sides=16, ridge=.008)
        for i in range(3):
            y = -.052-i*.061
            armor_rim(fore, y, .080-i*.013, .081-i*.012, .074-i*.012, "edge")
        fore.plate([(-.065, .034), (-.093, -.029), (-.062, -.090), (0, -.112), (.065, -.090), (.093, -.029), (.058, .034)], z=.074, depth=.010, tile="steel", edge="edge", bulge=.008)
        for x in (-.04, .04):
            fore.rivet([x, -.066, .087], .0055, "gilt")
        hand(palm, True)
        if side == "l":
            palm.mirror_x()
    sword(g, "hand-r", False, True)
    return g


# ---------------------- Authored articulation and motion ----------------------
ARM_JOINTS = ["upper-arm-r", "forearm-r", "hand-r", "upper-arm-l", "forearm-l", "hand-l"]
BODY_JOINTS = ["hips", "spine", "chest", "neck", "head", "thigh-r", "shin-r", "foot-r", "thigh-l", "shin-l", "foot-l"]
CLOTH_JOINTS = ["tabard", "tasset-r", "tasset-l", "cape", "skirt-front", "skirt-back", "skirt-r", "skirt-l"]


def base_pose(g):
    return {n: q.copy() for n, q in g.rest.items()}


def set_e(p, name, xyz):
    if name in p:
        p[name] = euler(*xyz)


def arm_ik(g, p, side, target, orientation=None, pole=None):
    shoulder = g.trans["upper-arm-"+side]
    L1, L2 = .289, .251
    target = np.asarray(target, float)
    delta = target-shoulder
    dist = np.linalg.norm(delta)
    dist = min(max(dist, .055), L1+L2-.003)
    direction = normalize(delta)
    cosine = (L1*L1 + dist*dist - L2*L2)/(2*L1*dist)
    along = L1*cosine
    s = -1 if side=="r" else 1
    pole = np.asarray(pole if pole is not None else [s*.85, -.38, -.30])
    perpendicular = normalize(pole-direction*np.dot(pole, direction))
    elbow = shoulder+direction*along+perpendicular*math.sqrt(max(0, L1*L1-along*along))
    hand_target = shoulder+direction*dist
    upper_q = q_from_to([0, -1, 0], elbow-shoulder)
    fore_world = q_from_to([0, -1, 0], hand_target-elbow)
    p["upper-arm-"+side] = upper_q
    p["forearm-"+side] = quat_mul(quat_inv(upper_q), fore_world)
    orient = orientation if orientation is not None else euler(10, 0, 0)
    p["hand-"+side] = quat_mul(quat_inv(fore_world), orient)


def idle_pose(g, t=0.):
    p = base_pose(g)
    b = math.sin(t*TAU)
    c = math.cos(t*TAU)
    kind = g.name
    set_e(p, "hips", (0, 1.0*b, 0.5*b))
    set_e(p, "spine", (1.3*b, -1.5*b, 0))
    set_e(p, "chest", (-1.0*b, -3, .6*b))
    set_e(p, "head", (-1+b, 3+2*b, -.7*b))
    if kind=="viewmodel":
        orient = axis_quat([-.245+.005*b, .899, .363], 3)
        hand_r = np.array([-.035, .004+.003*b, .013+.003*c])
        arm_ik(g, p, "r", hand_r, orient, [-1, -1, -.2])
        # Second gauntlet grips below the first hand on the same physical hilt.
        hand_l = hand_r+q_rotate(orient, [0, -.098, 0])
        arm_ik(g, p, "l", hand_l, orient, [1, -1, -.25])
        set_e(p, "chest", (.2*b, .3*b, .2*c))
        return p
    if kind=="archer":
        arm_ik(g, p, "l", [.269, -.045+.007*b, .368], euler(5, -4, -15))
        arm_ik(g, p, "r", [-.214, -.190+.007*b, .188], euler(15, 15, 5))
    elif kind=="mage":
        arm_ik(g, p, "r", [-.260, -.142+.005*b, .228], euler(4, 0, 2), [-1, -.2, -.4])
        arm_ik(g, p, "l", [.244, -.257+.009*b, .109], euler(15, 0, -8))
    elif kind=="princess":
        arm_ik(g, p, "r", [-.025, -.138+.007*b, .192], euler(31, 2, -46), [-1, -.6, -.4])
        arm_ik(g, p, "l", [.021, -.157+.007*b, .187], euler(32, -3, 45), [1, -.6, -.4])
        set_e(p, "head", (-3+b, 2.3*b, -2))
        set_e(p, "hips", (0, 1*b, -.7))
    else:
        arm_ik(g, p, "r", [-.274, -.245+.005*b, .199], axis_quat([-.12, .47, .875], 12), [-1, -.2, -.4])
        if kind=="shield":
            arm_ik(g, p, "l", [.250, -.032+.006*b, .285], euler(-6, -8, -6))
        else:
            arm_ik(g, p, "l", [.226, -.222+.007*b, .163], euler(10, 0, -12))
    for side, sign in (("r", -1), ("l", 1)):
        set_e(p, "thigh-"+side, (-2, 0, sign*2.5))
        set_e(p, "shin-"+side, (3, 0, 0))
        set_e(p, "foot-"+side, (-1, sign*3, -sign*2.5))
    return p


def melee_pose(g, sector, phase, heavy=False):
    p = idle_pose(g)
    power = 1.18 if heavy else 1.
    # Relative to chest. The same forearm rig drives a held weapon, never a floating sword.
    samples = {
        "high": [([-.18, .398, .158], [-.10, -.58, -.81], [-8, -12, -4]),
                 ([-.100, .093, .484], [0, .50, .866], [8, 0, 0]),
                 ([-.074, -.199, .395], [.12, -.68, .73], [17, 9, 3])],
        "left": [([-.398, .089, .092], [-.97, .16, -.17], [-2, -28, -6]),
                 ([-.093, .022, .487], [-.04, .07, .997], [5, 0, 0]),
                 ([.167, -.081, .320], [.94, -.13, .31], [8, 28, 5])],
        "right": [([.152, .125, .212], [.97, .17, -.15], [-1, 26, 6]),
                  ([-.043, .027, .484], [.02, .08, .997], [5, 0, 0]),
                  ([-.389, -.059, .291], [-.96, -.08, .27], [8, -29, -6])],
        "low": [([-.296, -.290, .192], [-.12, -.73, .67], [13, -17, -4]),
                ([-.105, -.044, .491], [0, .10, .995], [2, -3, 0]),
                ([-.12, .322, .249], [.08, .88, .47], [-8, 12, 5])],
    }
    target, direction, torso = samples[sector][phase]
    if heavy and phase==0:
        target = np.asarray(target)+([0, .035, -.035] if sector=="high" else [0, -.025, -.045])
    if g.name=="viewmodel":
        # Dedicated first-person choreography, lower amplitude than body swings.
        # All directions remain in +Z authoring space; the camera mount rotates Y by PI.
        vms = {
            "high": [([-.015, .100, .015], [.08, .946, .313]), ([-.015, -.038, .126], [.30, .40, .866]), ([.045, -.060, .065], [.35, -.28, .894])],
            "left": [([.135, -.006, .013], [.72, .57, .40]), ([.005, -.038, .133], [.34, .20, .92]), ([-.040, -.055, .015], [-.84, .43, .30])],
            "right": [([-.153, .018, .015], [-.77, .54, .34]), ([-.012, -.035, .126], [.28, .28, .918]), ([.110, -.080, .025], [.83, .38, .41])],
            "low": [([.040, -.115, -.015], [.23, -.26, .938]), ([.013, -.068, .134], [.29, .11, .95]), ([.040, .070, .035], [.16, .90, .40])],
        }
        target, direction = vms[sector][phase]
        orient = axis_quat(direction, -10 if sector=="left" else 10)
        arm_ik(g, p, "r", target, orient, [-1, -1, -.3])
        arm_ik(g, p, "l", np.asarray(target)+q_rotate(orient, [0, -.098, 0]), orient, [1, -1, -.3])
        set_e(p, "chest", (0, torso[1]*.09, torso[2]*.2))
        return p
    arm_ik(g, p, "r", target, axis_quat(direction, 12 if sector in ("high", "low") else 0), [-1, -.35, -.25])
    if g.name=="shield":
        arm_ik(g, p, "l", [.18 if phase==0 else .26, .075 if phase==0 else -.07, .28], euler(-6, -12 if phase==0 else 5, -5))
    else:
        arm_ik(g, p, "l", [.237, -.018 if phase==0 else -.151, .177 if phase==0 else .097], euler(18, 0, -16))
    set_e(p, "hips", (-torso[0]*.12, torso[1]*.37, -torso[2]*.2))
    set_e(p, "spine", (torso[0]*.35*power, torso[1]*.20, torso[2]*.3))
    set_e(p, "chest", (torso[0]*.65*power, torso[1]*.43, torso[2]*.55))
    set_e(p, "head", (-torso[0]*.4, -torso[1]*.72, -torso[2]*.3))
    set_e(p, "thigh-r", (-13 if phase==0 else -21, 0, -5))
    set_e(p, "shin-r", (24 if phase==0 else 32, 0, 0))
    set_e(p, "foot-r", (-11, -4, 5))
    set_e(p, "thigh-l", (9 if phase==0 else 14, 0, 5))
    set_e(p, "shin-l", (8 if phase==0 else 10, 0, 0))
    set_e(p, "foot-l", (-16, 4, -5))
    for n in CLOTH_JOINTS:
        set_e(p, n, (4 if phase==0 else -8, torso[1]*.25, torso[2]*.35))
    return p


def guard_pose(g, sector, t=0):
    p = idle_pose(g, t*.14)
    specs = {
        "high": ([-.130, .324, .232], [-.13, .69, -.71], [-4, -10, -3]),
        "left": ([-.337, .032, .274], [-.60, .76, .26], [1, -17, -5]),
        "right": ([.092, .054, .335], [.59, .77, .25], [1, 16, 5]),
        "low": ([-.204, -.214, .350], [.23, -.29, .93], [8, -8, -2]),
    }
    target, direction, torso = specs[sector]
    if g.name=="viewmodel":
        vm = {
            "high": ([.006, .060, .048], [-.36, .83, .42]),
            "left": ([.119, -.032, .077], [.69, .66, .30]),
            "right": ([-.123, -.025, .069], [-.69, .68, .23]),
            "low": ([-.023, -.095, .100], [.69, .10, .72]),
        }
        target, direction = vm[sector]
        orient = axis_quat(direction)
        arm_ik(g, p, "r", target, orient, [-1, -1, -.3])
        arm_ik(g, p, "l", np.asarray(target)+q_rotate(orient, [0, -.098, 0]), orient, [1, -1, -.3])
    else:
        arm_ik(g, p, "r", target, axis_quat(direction), [-1, 0, -.35])
        arm_ik(g, p, "l", [.12 if sector=="right" else .23, .16 if sector=="high" else -.02, .31], euler(-8, -7, -8))
        set_e(p, "spine", (torso[0]*.4, torso[1]*.4, torso[2]*.4))
        set_e(p, "chest", (torso[0]*.6, torso[1]*.6, torso[2]*.6))
        set_e(p, "head", (-torso[0]*.5, -torso[1]*.8, 0))
        for s, side in ((-1, "r"), (1, "l")):
            set_e(p, "thigh-"+side, (-8, 0, s*4))
            set_e(p, "shin-"+side, (13, 0, 0))
            set_e(p, "foot-"+side, (-5, s*4, -s*4))
    return p


def interpolate_pose(a, b, t):
    return {n: blend_q(a[n], b[n], t) for n in a}


def animation(g, name, times, poses, hip_y=None, extra=None):
    anim = {"name": name, "samplers": [], "channels": []}
    targets = ARM_JOINTS+["chest", "vm-pivot"] if g.name=="viewmodel" else BODY_JOINTS+ARM_JOINTS+CLOTH_JOINTS
    for node in targets:
        if node in g.ids:
            g.channel(anim, node, "rotation", times, [p.get(node, g.rest[node]) for p in poses])
    if "hips" in g.ids:
        ys = hip_y if hip_y is not None else [float(g.trans["hips"][1])]*len(times)
        g.channel(anim, "hips", "translation", times, [[0, y, 0] for y in ys])
    if extra:
        for node, path, values in extra:
            g.channel(anim, node, path, times, values)
    g.doc["animations"].append(anim)


def authored_animations(g):
    kind = g.name
    idle = idle_pose(g)
    # Set the GLB's unactioned bind display to the exact idle, not a T-pose.
    for node, q in idle.items():
        g.doc["nodes"][g.ids[node]]["rotation"] = q.tolist()
    # All tracks are absolute relative to the named parent, and root is never animated.
    times = [0, .8, 1.6, 2.4, 3.2]
    animation(g, "idle", times, [idle_pose(g, t/3.2) for t in times])
    times = [0, .1125, .225, .3375, .45, .5625, .675, .7875, .90]
    poses, ys = [], []
    for t in times:
        a = t/.9*TAU
        p = idle_pose(g, t/.9)
        if kind=="viewmodel":
            set_e(p, "chest", (math.sin(a*2)*1.3, math.sin(a)*1.4, math.sin(a)*1.1))
        else:
            amplitude = 17 if kind=="princess" else 20 if kind=="mage" else 28
            for sign, side in ((-1, "r"), (1, "l")):
                swing = math.cos(a)*sign
                set_e(p, "thigh-"+side, (swing*amplitude, 0, sign*2))
                set_e(p, "shin-"+side, (max(0, swing)*31+max(0, math.sin(a)*sign)*18+3, 0, 0))
                set_e(p, "foot-"+side, (-max(0, swing)*18-2, sign*3, -sign*2))
                if kind not in ("mage", "princess", "shield", "archer") or side=="r":
                    p["upper-arm-"+side] = quat_mul(euler(-swing*6, 0, 0), p["upper-arm-"+side])
            set_e(p, "hips", (0, math.cos(a)*3.6, math.sin(a)*1.9))
            set_e(p, "spine", (2, -math.cos(a)*2.6, -math.sin(a)*1.4))
            set_e(p, "head", (-1, math.cos(a)*1.1, 0))
            for n in CLOTH_JOINTS:
                set_e(p, n, (math.sin(a+(0 if n.endswith("r") else PI))*(6 if n.startswith("skirt") else 9), math.cos(a)*3, math.sin(a)*2))
        poses.append(p)
        ys.append(.949+abs(math.sin(a))*.012)
    animation(g, "walk", times, poses, ys)
    for sector in ("high", "left", "right", "low"):
        animation(g, "guard-"+sector, [0, .65, 1.3], [guard_pose(g, sector, t) for t in (0, .5, 0)])
        for heavy in (False, True):
            dur = 1.25 if heavy else .70
            contact0, contact1 = (.52, .70) if heavy else (.24, .38)
            wind = melee_pose(g, sector, 0, heavy)
            hit = melee_pose(g, sector, 1, heavy)
            follow = melee_pose(g, sector, 2, heavy)
            ts = [0, contact0*.54, contact0, (contact0+contact1)/2, contact1, contact1+(dur-contact1)*.42, dur]
            ps = [idle, interpolate_pose(idle, wind, .86), wind, hit, follow, interpolate_pose(follow, idle, .35), idle]
            animation(g, ("heavy-" if heavy else "light-")+sector, ts, ps, [.950, .926 if heavy else .941, .916 if heavy else .935, .930, .932, .945, .956])
    wind = melee_pose(g, "high", 0)
    guard = guard_pose(g, "right")
    animation(g, "feint", [0, .12, .235, .33, .50], [idle, interpolate_pose(idle, wind, .6), wind, interpolate_pose(wind, guard, .7), idle], [.956, .946, .940, .946, .956])
    for name, duration in (("block", .56), ("parry", .45)):
        ready = guard_pose(g, "high" if name=="block" else "left")
        recoil = interpolate_pose(ready, melee_pose(g, "right", 0), .22)
        set_e(recoil, "chest", (-9, -4, 6))
        set_e(recoil, "head", (6, 6, -3))
        if kind=="viewmodel":
            set_e(recoil, "chest", (-5, 1, 5))
        animation(g, name, [0, duration*.22, duration*.42, duration*.65, duration], [idle, ready, recoil, ready, idle], [.956, .938, .930, .941, .956])
    for name, amplitude, duration in (("hit", 1., .45), ("stagger", 1.9, .88)):
        p = idle_pose(g)
        set_e(p, "hips", (-5*amplitude, -5, 3*amplitude))
        set_e(p, "chest", (-11*amplitude, 4, 7*amplitude))
        set_e(p, "head", (16*amplitude, -8, -3))
        for side in ("r", "l"):
            p["upper-arm-"+side] = quat_mul(euler(13*amplitude, 0, 0), p["upper-arm-"+side])
            set_e(p, "thigh-"+side, (-8*amplitude, 0, -4 if side=="r" else 4))
            set_e(p, "shin-"+side, (15*amplitude, 0, 0))
        animation(g, name, [0, duration*.20, duration*.42, duration], [idle, p, interpolate_pose(p, idle, .25), idle], [.956, .956-.04*amplitude, .936, .956])
    duck = idle_pose(g)
    set_e(duck, "hips", (4, -12, 10))
    set_e(duck, "spine", (16, 8, -6))
    set_e(duck, "chest", (15, 5, -5))
    set_e(duck, "head", (-18, -4, 0))
    for s, side in ((-1, "r"), (1, "l")):
        set_e(duck, "thigh-"+side, (-48 if s<0 else -32, 0, s*9))
        set_e(duck, "shin-"+side, (76 if s<0 else 63, 0, 0))
        set_e(duck, "foot-"+side, (-28 if s<0 else -31, s*4, -s*9))
    if kind=="viewmodel":
        set_e(duck, "chest", (-11, -9, -12))
    animation(g, "dodge", [0, .11, .28, .45, .64], [idle, interpolate_pose(idle, duck, .7), duck, interpolate_pose(duck, idle, .40), idle], [.956, .79, .727, .818, .956])
    tuck = idle_pose(g)
    set_e(tuck, "hips", (0, 0, 0))
    set_e(tuck, "spine", (33, 0, 0))
    set_e(tuck, "chest", (33, 0, 0))
    set_e(tuck, "head", (28, 0, 0))
    for s, side in ((-1, "r"), (1, "l")):
        set_e(tuck, "thigh-"+side, (-93, 0, s*5))
        set_e(tuck, "shin-"+side, (125, 0, 0))
        set_e(tuck, "foot-"+side, (-22, 0, 0))
    ps = [idle, duck]
    for angle in (80, 185, 295):
        roll = {n:q.copy() for n,q in tuck.items()}
        set_e(roll, "hips", (angle, 0, 0))
        if kind=="viewmodel":
            set_e(roll, "chest", (-13, 2, -16 if angle<185 else 9))
        ps.append(roll)
    ps += [duck, idle]
    # Quaternion keys explicitly follow a full turn through 80/185/295 degrees.
    animation(g, "roll", [0, .12, .24, .39, .54, .66, .84], ps, [.956, .60, .35, .32, .40, .69, .956])
    # Stationary death: pelvis lowers vertically while the body tips back; X/Z root stays zero.
    collapse = idle_pose(g)
    set_e(collapse, "hips", (-18, 5, -4))
    set_e(collapse, "chest", (-15, -8, 6))
    set_e(collapse, "head", (28, 14, 4))
    for side in ("r", "l"):
        set_e(collapse, "thigh-"+side, (-24, 0, -7 if side=="r" else 7))
        set_e(collapse, "shin-"+side, (45, 0, 0))
    dead = idle_pose(g)
    set_e(dead, "hips", (-87, 5, -5))
    set_e(dead, "spine", (3, 0, 1))
    set_e(dead, "chest", (2, -4, -2))
    set_e(dead, "head", (8, 20, 3))
    for s, side in ((-1, "r"), (1, "l")):
        set_e(dead, "thigh-"+side, (-3 if s<0 else 8, 0, s*9))
        set_e(dead, "shin-"+side, (7 if s<0 else 19, 0, 0))
        set_e(dead, "foot-"+side, (-5, s*16, 0))
        set_e(dead, "upper-arm-"+side, (15, 0, s*37))
        set_e(dead, "forearm-"+side, (-13, 0, 0))
        set_e(dead, "hand-"+side, (20, 0, 0))
    if kind=="viewmodel":
        set_e(collapse, "chest", (-24, 8, -18))
        set_e(dead, "chest", (48, 22, -38))
    animation(g, "death", [0, .18, .47, .84, 1.32, 1.60], [idle, collapse, interpolate_pose(collapse, dead, .58), dead, dead, dead], [.956, .80, .41, .139, .134, .134])
    if kind=="archer":
        ready, drawn = idle_pose(g), idle_pose(g)
        for p, pull in ((ready, False), (drawn, True)):
            set_e(p, "chest", (0, -12, -2))
            set_e(p, "head", (-2, 12, 2))
            arm_ik(g, p, "l", [-.030, .390, .440], euler(0, 12, -2), [1, -.4, 0])
            # Finger pads meet the nock at the cheek; the elbow draws back, not over the helmet.
            arm_ik(g, p, "r", [-.116 if pull else -.070, .404, .015 if pull else .230], euler(5, 0, -12), [-1, -.15, -1])
            set_e(p, "spine", (0, 2 if pull else 0, 0))
        def bow_extras(ts, pulls, visible=None):
            channels=[]
            for s, n in ((1, "bow-string-upper"), (-1, "bow-string-lower")):
                vectors = [np.array([0., -s*.652, -.055-.22*x]) for x in pulls]
                channels.append((n, "rotation", [q_from_to([0,1,0], v) for v in vectors]))
                channels.append((n, "scale", [[1, float(np.linalg.norm(v)), 1] for v in vectors]))
            channels.append(("arrow", "translation", [[0, 0, -.22*x] for x in pulls]))
            channels.append(("arrow", "scale", [[v, v, v] for v in (visible if visible is not None else [1]*len(ts))]))
            return channels
        ts=[0, .22, .50, .83, 1.10]
        animation(g, "draw", ts, [idle, ready, interpolate_pose(ready, drawn, .5), drawn, drawn], [.956]*5, bow_extras(ts, [0, 0, .5, 1, 1]))
        recoil = {n:q.copy() for n,q in drawn.items()}
        arm_ik(g, recoil, "r", [-.110, .440, -.060], euler(8, 0, -12), [-1, .2, -.3])
        set_e(recoil, "chest", (-2, -10, -2))
        ts=[0, .08, .135, .23, .42, .65]
        animation(g, "release", ts, [drawn, drawn, recoil, interpolate_pose(recoil, ready, .3), ready, idle], [.956]*6, bow_extras(ts, [1, 1, 0, .08, 0, 0], [1, 1, .001, .001, .001, 1]))
        # Reset bow extras explicitly in all non-ranged actions, to avoid a hidden arrow after interruption.
        for anim in g.doc["animations"]:
            if anim["name"] in ("draw", "release"):
                continue
            duration = max(g.doc["accessors"][s["input"]]["max"][0] for s in anim["samplers"])
            for node, path, values in bow_extras([0, duration], [0, 0]):
                g.channel(anim, node, path, [0, duration], values)
    if kind=="mage":
        charge = idle_pose(g)
        arm_ik(g, charge, "r", [-.269, -.037, .276], euler(-7, 0, 7), [-1, -.1, -.3])
        arm_ik(g, charge, "l", [.186, .185, .258], euler(-65, 10, -25), [1, .1, -.3])
        set_e(charge, "chest", (-4, -8, 0))
        set_e(charge, "head", (-5, 8, -3))
        pulse = {n:q.copy() for n,q in charge.items()}
        arm_ik(g, pulse, "l", [.175, .223, .279], euler(-78, 12, -28), [1, .1, -.3])
        set_e(pulse, "chest", (-6, -10, 0))
        set_e(pulse, "head", (-8, 10, -3))
        animation(g, "charge", [0, .25, .55, .83, 1.15, 1.45], [idle, interpolate_pose(idle, charge, .65), charge, pulse, charge, pulse], [.956, .947, .939, .938, .939, .938])
        cast = idle_pose(g)
        arm_ik(g, cast, "l", [.093, .167, .497], euler(-85, 0, -12), [1, -.2, -.2])
        arm_ik(g, cast, "r", [-.276, -.135, .252], euler(16, 0, 4), [-1, -.2, -.3])
        set_e(cast, "hips", (0, 7, 0))
        set_e(cast, "chest", (9, 4, 0))
        set_e(cast, "head", (-8, -7, 0))
        animation(g, "cast", [0, .12, .24, .38, .65, .90], [charge, pulse, cast, cast, interpolate_pose(cast, idle, .55), idle], [.938, .935, .934, .94, .95, .956])
    if kind=="princess":
        explain = idle_pose(g)
        arm_ik(g, explain, "r", [-.259, -.068, .324], euler(-36, 0, 28), [-1, -.1, -.3])
        set_e(explain, "head", (-5, -8, -3))
        set_e(explain, "chest", (1, -4, -1))
        listen = idle_pose(g)
        set_e(listen, "head", (3, 6, 3))
        arm_ik(g, listen, "l", [.075, -.119, .205], euler(19, 4, 38), [1, -.5, -.4])
        emphasize = {n:q.copy() for n,q in explain.items()}
        arm_ik(g, emphasize, "r", [-.182, .023, .287], euler(-45, 0, 26), [-1, -.1, -.2])
        set_e(emphasize, "head", (-2, -4, -1))
        animation(g, "talk", [0, .28, .64, .93, 1.18, 1.55, 1.94, 2.30, 2.65, 3.10], [idle, listen, explain, emphasize, explain, listen, emphasize, explain, listen, idle])


def main():
    images = texture_atlas()
    manifest = {"generator": "art/characters.py", "original": True, "atlasSize": 512, "forward": "+Z", "units": "metres", "characters": []}
    for kind in ("swordsman", "elite", "shield", "archer", "mage", "princess", "viewmodel"):
        glb = viewmodel(images) if kind=="viewmodel" else humanoid(kind, images)
        authored_animations(glb)
        manifest["characters"].append(glb.export())
    (OUT / "characters-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    main()
