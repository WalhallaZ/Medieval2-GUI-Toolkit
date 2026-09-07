"""Line-oriented ``descr_model_battle.txt`` support.

The game accepts this text form in preference to the old serialisation archive.
This module deliberately maps it onto ``modeldb``'s public entry shape, letting
the editors, transfer planner and sprite tools share one model vocabulary.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .modeldb import Animation, ModelDb, ModelEntry, Texture

ENCODING = "latin-1"
_TYPE = re.compile(r"(?mi)^\s*type\s+(.+?)\s*(?:;.*)?$")
_LINE = re.compile(r"(?mi)^(\s*)(type|scale|skeleton(?:_(?:horse|camel|elephant))?|skeleton_attachment_(?:primary|secondary)|mesh|texture(?:_attachments)?|torch)(\s+)(.*?)(\r?\n|$)")


def is_entry(raw: str) -> bool:
    return bool(_TYPE.search(raw))


def _parts(value: str) -> List[str]:
    return [p.strip() for p in value.split(",")]


def parse_entry_text(raw: str) -> ModelEntry:
    name = ""
    scale = 1.0
    lods: List[Tuple[str, int]] = []
    main: List[Texture] = []
    attach: List[Texture] = []
    anims: List[Animation] = []
    pri_weapons: List[str] = []
    sec_weapons: List[str] = []
    torch_i, torch = 0, [0.0] * 6
    for m in _LINE.finditer(raw):
        key, vals = m.group(2).lower(), _parts(m.group(4))
        if key == "type":
            name = (vals[0] if vals else "").lower()
        elif key == "scale" and vals:
            try: scale = float(vals[0])
            except ValueError: pass
        elif key == "mesh" and vals:
            try: dist = int(float(vals[1])) if len(vals) > 1 else 0
            except ValueError: dist = 0
            lods.append((vals[0], dist))
        elif key in ("texture", "texture_attachments") and vals:
            tex = vals[1] if len(vals) > 1 else ""
            nrm = vals[2] if len(vals) > 2 else ""
            spr = vals[3] if len(vals) > 3 else ""
            (main if key == "texture" else attach).append(Texture(vals[0].lower(), tex, nrm, spr))
        elif key.startswith("skeleton_attachment_") and vals:
            (pri_weapons if key.endswith("primary") else sec_weapons).append(vals[0])
        elif key.startswith("skeleton") and vals:
            mount = key.rsplit("_", 1)[-1] if "_" in key else "none"
            anims.append(Animation(mount, vals[0], vals[1] if len(vals) > 1 else ""))
        elif key == "torch" and vals:
            try:
                torch_i = int(float(vals[0])); torch = [float(x) for x in vals[1:7]]
                torch += [0.0] * (6 - len(torch))
            except ValueError: pass
    if not name:
        raise ValueError("a descr_model_battle entry needs a type line")
    if anims:
        anims[0].pri_weapons = pri_weapons
        anims[0].sec_weapons = sec_weapons
    return ModelEntry(name, scale, lods, main, attach, anims, torch_i, torch, raw=raw)


def parse_text(text: str) -> ModelDb:
    hits = list(_TYPE.finditer(text))
    if not hits:
        raise ValueError("no 'type' records found")
    preamble = text[:hits[0].start()]
    entries = [parse_entry_text(text[m.start():hits[i + 1].start() if i + 1 < len(hits) else len(text)])
               for i, m in enumerate(hits)]
    return ModelDb([], "", entries, trailing="", header_raw=preamble, format="dmb")


def parse_file(path: str | Path) -> ModelDb:
    return parse_text(Path(path).read_text(encoding=ENCODING))


def export_text(mod, names) -> str:
    """A self-contained descriptor containing the selected types."""
    wanted = {n.lower() for n in names}
    return mod.modeldb.header_raw + "".join(e.raw for e in mod.modeldb.entries if e.name in wanted)


def entry_path_spans(raw: str, pad: bool = False):
    out = []
    for m in _LINE.finditer(raw):
        key, value = m.group(2).lower(), m.group(4)
        if key == "mesh":
            end = value.find(",")
            end = len(value) if end < 0 else end
            out.append((m.start(4), m.start(4) + end, value[:end].strip(), "mesh"))
        elif key in ("texture", "texture_attachments"):
            parts = list(re.finditer(r"(?:^|,)\s*([^,\r\n]+)", value))
            for i, p in enumerate(parts[1:]):
                val = p.group(1).strip()
                start = m.start(4) + p.start(1) + len(p.group(1)) - len(p.group(1).lstrip())
                out.append((start, start + len(val), val, ("texture", "normal", "sprite")[i]))
    return out


def rewrite_paths_indexed(raw: str, index_map: Dict[int, str], pad: bool = False) -> str:
    edits = [(s, e, index_map[i]) for i, (s, e, _v, _k) in enumerate(entry_path_spans(raw))
             if i in index_map and index_map[i] is not None]
    for s, e, value in reversed(edits): raw = raw[:s] + value + raw[e:]
    return raw


def rewrite_entry_paths(raw: str, path_map: Dict[str, str], pad: bool = False) -> str:
    return rewrite_paths_indexed(raw, {i: path_map[v] for i, (_s, _e, v, _k) in enumerate(entry_path_spans(raw)) if v in path_map})


def path_slots_raw(raw: str, pad: bool = False) -> List[dict]:
    entry = parse_entry_text(raw); out = []; lod = 0
    textures = [("main", t) for t in entry.main_textures] + [("attach", t) for t in entry.attach_textures]
    ti = 0
    for i, (_s, _e, value, kind) in enumerate(entry_path_spans(raw)):
        if kind == "mesh":
            out.append({"i": i, "kind": kind, "value": value, "group": "lod", "faction": "", "label": f"LOD {lod} mesh"}); lod += 1
        else:
            group, tex = textures[ti]
            out.append({"i": i, "kind": kind, "value": value, "group": group, "faction": tex.faction,
                        "label": f"{tex.faction} {kind}" + (" (attachment)" if group == "attach" else "")})
            if kind == "sprite" or (group == "attach" and kind == "normal"): ti += 1
    return out


def entry_spans(raw: str) -> Dict[str, List[List[int]]]:
    """Code-view line ranges for descriptor fields (which have no prefixes)."""
    slots = path_slots_raw(raw)
    spans: Dict[str, List[List[int]]] = {"name": [[1, 1]]}
    for slot in slots:
        # Character offsets are converted to 1-based source lines, matching
        # codeview's existing span contract.
        at = entry_path_spans(raw)[slot["i"]][0]
        line = raw.count("\n", 0, at) + 1
        spans[f"path#{slot['i']}"] = [[line, line]]
        if slot["kind"] != "mesh":
            kind = slot["kind"] if slot["group"] == "main" else "attach_" + slot["kind"]
            spans[f"fac:{slot['faction']}:{kind}"] = [[line, line]]
    return spans


def rename_entry_raw(raw: str, new_name: str) -> str:
    m = _TYPE.search(raw)
    return raw if not m else raw[:m.start(1)] + new_name + raw[m.end(1):]


def _set_factions(raw: str, factions, prefer: Optional[str], exact: bool) -> str:
    wanted = list(dict.fromkeys(f.lower() for f in factions if f))
    lines = list(_LINE.finditer(raw)); edits = []
    for kind in ("texture", "texture_attachments"):
        records = [m for m in lines if m.group(2).lower() == kind]
        if not records: continue
        parsed = [(_parts(m.group(4))[0].lower(), m) for m in records]
        have = {f: m for f, m in parsed}; donor = have.get((prefer or "").lower()) or next((m for f, m in parsed if f != "slave"), records[0])
        targets = wanted if exact else [f for f in wanted if f not in have]
        if not targets: continue
        def cloned(f):
            return re.sub(r"^(\s*texture(?:_attachments)?\s+)[^,\s]+", r"\g<1>" + f,
                          donor.group(0), count=1, flags=re.I)
        if exact:
            repl = "".join((have[f].group(0) if f in have else cloned(f)) for f in targets)
            edits.append((records[0].start(), records[-1].end(), repl))
        else:
            added = "".join(cloned(f) for f in targets)
            edits.append((records[-1].end(), records[-1].end(), added))
    for s, e, val in reversed(edits): raw = raw[:s] + val + raw[e:]
    return raw


def add_texture_factions(raw: str, factions, prefer: Optional[str] = None, pad: bool = False) -> str:
    return _set_factions(raw, factions, prefer, False)


def set_texture_factions(raw: str, factions, prefer: Optional[str] = None, pad: bool = False) -> str:
    return _set_factions(raw, factions, prefer, True)
