#!/usr/bin/env python3
"""Prepared fog patch for Lethal Offline (NOT RUN).

Conservative patch targeting built-in Unity RenderSettings only. It does not
blindly alter HDRP VolumeProfiles or custom fog MonoBehaviours because their
serialized field layouts still need inspection. Default mode is dry-run.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import UnityPy

ROOT = Path("work/apk/assets/bin/Data")
REPORT = Path("output/fog-patch-preview.json")
DENSITY_FACTOR = 0.65  # reduce built-in fog density by 35%, retaining fog
BLUE_REDUCTION = 0.90   # reduce excess blue channel relative to red/green
TARGET_TYPES = {"RenderSettings"}

def as_dict(obj):
    for method in ("parse_as_dict", "read_typetree"):
        fn = getattr(obj, method, None)
        if fn:
            try:
                value = fn()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    return {}

def adjust_color(color):
    if not isinstance(color, dict):
        return color, False
    rgb = [color.get(k) for k in ("r", "g", "b")]
    if not all(isinstance(v, (int, float)) for v in rgb):
        return color, False
    # Only reduce blue when it is measurably above the other channels.
    if rgb[2] <= max(rgb[0], rgb[1]) * 1.10:
        return color, False
    changed = dict(color)
    changed["b"] = max(0.0, float(rgb[2]) * BLUE_REDUCTION)
    return changed, True

def preview_and_patch(apply=False):
    env = UnityPy.load(str(ROOT))
    changes, skipped, touched = [], [], []
    for obj in env.objects:
        if obj.type.name not in TARGET_TYPES:
            continue
        try:
            tree = as_dict(obj)
            if not tree:
                skipped.append({"path_id": int(obj.path_id), "reason": "typetree unavailable"})
                continue
            candidate = dict(tree)
            item = {"asset_file": str(getattr(obj.assets_file, "name", "")),
                    "path_id": int(obj.path_id), "before": {}, "after": {}}
            changed = False
            # Do not enable fog if it was intentionally disabled in the original.
            if candidate.get("m_Fog") is True and isinstance(candidate.get("m_FogDensity"), (int, float)):
                old = float(candidate["m_FogDensity"])
                new = max(0.0, old * DENSITY_FACTOR)
                if new != old:
                    item["before"]["m_FogDensity"] = old
                    item["after"]["m_FogDensity"] = new
                    candidate["m_FogDensity"] = new
                    changed = True
            fog_color_key = "m_FogColor"
            if candidate.get("m_Fog") is True and fog_color_key in candidate:
                new_color, did = adjust_color(candidate[fog_color_key])
                if did:
                    item["before"][fog_color_key] = candidate[fog_color_key]
                    item["after"][fog_color_key] = new_color
                    candidate[fog_color_key] = new_color
                    changed = True
            if changed:
                changes.append(item)
                if apply:
                    obj.save_typetree(candidate)
                    touched.append(item)
            else:
                skipped.append({"path_id": int(obj.path_id), "reason": "no safe fog adjustment matched"})
        except Exception as exc:
            skipped.append({"path_id": int(obj.path_id), "reason": str(exc)[:400]})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"dry_run": not apply, "density_factor": DENSITY_FACTOR,
        "blue_reduction": BLUE_REDUCTION, "changes_preview": changes,
        "objects_written": touched, "skipped": skipped}, indent=2))
    if apply:
        # Only after explicit confirmation; caller must rebuild asset bundle separately.
        for assets_file in env.files:
            try:
                out = Path("work/modified") / Path(getattr(assets_file, "name", "assets")).name
                out.parent.mkdir(parents=True, exist_ok=True)
                assets_file.save(out)
            except Exception as exc:
                print(f"WARNING: failed saving asset file {getattr(assets_file, 'name', '')}: {exc}")
    print(json.dumps({"preview_count": len(changes), "written_count": len(touched),
                     "skipped_count": len(skipped), "report": str(REPORT)}, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; never use without review")
    parser.add_argument("--confirm-fog-patch", action="store_true", help="required together with --apply")
    args = parser.parse_args()
    if args.apply and not args.confirm_fog_patch:
        parser.error("--apply requires --confirm-fog-patch")
    preview_and_patch(apply=args.apply)
