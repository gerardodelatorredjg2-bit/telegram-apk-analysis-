#!/usr/bin/env python3
"""Prepare a safe 3D geometry optimization inventory.

Read-only preparation: scans model file sizes and names. Does not simplify meshes,
alter skeletons, change materials, remove colliders, or rebuild the APK.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

MODEL_EXTS = {".fbx", ".obj", ".gltf", ".glb", ".dae", ".blend"}
PROTECTED = ("rig", "armature", "bone", "skeleton", "anim", "collider", "collision", "avatar", "player")
MESH_TERMS = ("mesh", "model", "geometry", "character", "prop", "ship", "environment")

def classify(path: Path) -> str:
    name = path.as_posix().lower()
    if any(term in name for term in PROTECTED):
        return "protected_review_only"
    if any(term in name for term in MESH_TERMS):
        return "mesh_candidate_manual_review"
    return "model_candidate_manual_review"

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only model/geometry inventory")
    parser.add_argument("root", type=Path, help="Extracted game assets directory")
    parser.add_argument("--output", type=Path, default=Path("geometry_optimization_inventory.json"))
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"directory not found: {args.root}")
    records, total = [], 0
    for path in args.root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MODEL_EXTS:
            continue
        size = path.stat().st_size
        total += size
        records.append({"path": str(path.relative_to(args.root)), "bytes": size,
                       "classification": classify(path), "bulk_simplification_allowed": False})
    records.sort(key=lambda r: r["bytes"], reverse=True)
    report = {
        "purpose": "3D model and geometry optimization preparation",
        "read_only": True, "assets_modified": 0,
        "mesh_simplification_performed": False, "build_performed": False,
        "model_file_count": len(records), "total_bytes": total,
        "preservation_constraints": [
            "Keep skeletons, bones, weights, and animation curves intact.",
            "Preserve UVs, materials, normals, tangents, and topology where required.",
            "Do not simplify colliders/collision meshes without gameplay verification.",
            "Keep originals; only optimize verified duplicate assets."
        ],
        "files": records
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Read-only geometry inventory written: {args.output}")
    print(f"Model files: {len(records)}; total size: {total} bytes")
    print("No models were modified and no APK was built.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
