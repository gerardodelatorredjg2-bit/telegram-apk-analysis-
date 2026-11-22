#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import UnityPy

DATA = Path("work/apk/assets/bin/Data")
OUT = Path("output")

def pptr_read(value):
    try:
        return value.read()
    except Exception:
        return None

def attr(value, key, default=None):
    try:
        return getattr(value, key)
    except Exception:
        return default

def as_text(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:500]

def typed_tree(obj):
    for method in ("read_typetree", "parse_as_dict"):
        fn = attr(obj, method)
        if callable(fn):
            try:
                value = fn()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    try:
        value = obj.parse_as_object()
        return {k: as_text(v) for k, v in vars(value).items() if not k.startswith("_")}
    except Exception:
        return {}

def main():
    env = UnityPy.load(str(DATA))
    objects = list(env.objects)
    scripts = {}
    objects_by_file_path = {
        (str(attr(attr(obj, "assets_file"), "name", "")), int(obj.path_id)): obj
        for obj in objects
    }
    for obj in objects:
        if attr(attr(obj, "type"), "name") != "MonoScript":
            continue
        data = attr(obj, "parse_as_object")
        if not callable(data):
            continue
        try:
            x = data()
            scripts[int(obj.path_id)] = {
                "name": as_text(attr(x, "m_Name")),
                "class": as_text(attr(x, "m_ClassName")),
                "namespace": as_text(attr(x, "m_Namespace")),
                "assembly": as_text(attr(x, "m_AssemblyName")),
                "asset_file": str(attr(attr(obj, "assets_file"), "name", ""))
            }
        except Exception:
            pass

    targeted = []
    relevant_mb = []
    volume_candidates = []
    for obj in objects:
        kind = attr(attr(obj, "type"), "name", "Unknown")
        if kind == "GameObject":
            try:
                go = obj.parse_as_object()
            except Exception:
                continue
            name = str(attr(go, "m_Name", "") or "")
            if not any(t in name.lower() for t in ("fog", "volume", "camera", "post", "weather", "mist")):
                continue
            components = []
            for pair in attr(go, "m_Component", []) or []:
                ptr = attr(pair, "component")
                comp_path_id = int(attr(ptr, "path_id", 0) or 0)
                go_asset = str(attr(attr(obj, "assets_file"), "name", ""))
                comp_obj = objects_by_file_path.get((go_asset, comp_path_id))
                if comp_obj is None:
                    continue
                comp_kind = attr(attr(comp_obj, "type"), "name", "Unknown")
                comp_name = ""
                script = None
                props = {}
                try:
                    comp_data = comp_obj.parse_as_object()
                    comp_name = str(attr(comp_data, "m_Name", "") or "")
                    if comp_kind == "MonoBehaviour":
                        sp = attr(comp_data, "m_Script")
                        sd = pptr_read(sp)
                        if sd is not None:
                            script = {
                                "class": as_text(attr(sd, "m_ClassName")),
                                "namespace": as_text(attr(sd, "m_Namespace")),
                                "assembly": as_text(attr(sd, "m_AssemblyName")),
                                "script_path_id": int(attr(sp, "path_id", 0) or 0)
                            }
                        props = typed_tree(comp_obj)
                except Exception:
                    pass
                components.append({
                    "component_path_id": comp_path_id,
                    "type": comp_kind,
                    "name": comp_name,
                    "script": script,
                    "properties": props
                })
            targeted.append({
                "asset_file": str(attr(attr(obj, "assets_file"), "name", "")),
                "path_id": int(obj.path_id),
                "name": name,
                "active": bool(attr(go, "m_IsActive", True)),
                "layer": as_text(attr(go, "m_Layer")),
                "components": components
            })

        if kind == "MonoBehaviour":
            try:
                data = obj.parse_as_object()
            except Exception:
                continue
            sp = attr(data, "m_Script")
            sd = pptr_read(sp)
            if sd is None:
                continue
            cls = str(attr(sd, "m_ClassName", "") or "")
            ns = str(attr(sd, "m_Namespace", "") or "")
            if not any(t in (cls + " " + ns).lower() for t in ("fog", "volume", "lens", "distort", "weather", "postprocess", "postprocessing")):
                continue
            go_ptr = attr(data, "m_GameObject")
            go = pptr_read(go_ptr)
            go_name = str(attr(go, "m_Name", "") or "") if go is not None else ""
            go_path = int(attr(go_ptr, "path_id", 0) or 0) if go_ptr is not None else None
            relevant_mb.append({
                "asset_file": str(attr(attr(obj, "assets_file"), "name", "")),
                "path_id": int(obj.path_id),
                "script": {"class": cls, "namespace": ns, "assembly": as_text(attr(sd, "m_AssemblyName")), "script_path_id": int(attr(sp, "path_id", 0) or 0)},
                "game_object": go_name,
                "game_object_path_id": go_path,
                "properties": typed_tree(obj)
            })

    report = {
        "mono_scripts": list(scripts.values()),
        "target_gameobjects": targeted,
        "relevant_monobehaviours": relevant_mb,
        "notes": "Inspection only; no gameplay assets modified."
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "unity-volume-fog-lens-details.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({
        "target_gameobjects": targeted[:80],
        "relevant_monobehaviours": relevant_mb[:120],
        "script_classes_matching": [x for x in scripts.values() if any(t in ((x.get("class") or "") + " " + (x.get("namespace") or "")).lower() for t in ("fog", "volume", "lens", "distort", "weather", "postprocess"))]
    }, indent=2, ensure_ascii=False)[:45000])

if __name__ == "__main__":
    main()
