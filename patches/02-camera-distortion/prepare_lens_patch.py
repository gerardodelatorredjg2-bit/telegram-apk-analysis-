#!/usr/bin/env python3
"""Preparatory Unity LensDistortion patch. Not executed automatically.

Dry-run is the default. Apply only to a copied APK/assets file after reviewing
the report; this does not rebuild the APK.
"""
import argparse
import json
from pathlib import Path

try:
    import UnityPy
except ImportError:
    raise SystemExit("UnityPy is required (install it in the patch environment).")

DISTORTION_NAMES = {"LensDistortion", "Lens Distortion"}
INTENSITY_KEYS = ("intensity", "Intensity", "m_Intensity")


def get_tree(obj):
    try:
        return obj.read_typetree()
    except Exception:
        return None


def walk(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, key, child, value
            yield from walk(child, child_path)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, f"{path}[{i}]")


def main():
    parser = argparse.ArgumentParser(description="Safely inspect/reduce Unity lens distortion.")
    parser.add_argument("input", type=Path, help="Unity serialized asset file")
    parser.add_argument("--output", type=Path, help="output copy (required with --apply)")
    parser.add_argument("--apply", action="store_true", help="write proposed changes to output")
    parser.add_argument("--confirm-lens-patch", action="store_true", help="required safety flag")
    args = parser.parse_args()

    if args.apply and (not args.output or not args.confirm_lens_patch):
        parser.error("--apply requires --output and --confirm-lens-patch")
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error("Output must be a separate file; never overwrite the input.")

    env = UnityPy.load(str(args.input))
    candidates = []
    for obj in env.objects:
        tree = get_tree(obj)
        if not isinstance(tree, dict):
            continue
        typename = str(tree.get("m_Name", tree.get("name", "")))
        class_name = getattr(obj.type, "name", str(obj.type))
        is_lens = ("LensDistortion" in class_name) or (typename in DISTORTION_NAMES)
        if not is_lens:
            continue
        found = []
        for _, key, val, parent in walk(tree):
            if key in INTENSITY_KEYS and isinstance(val, (int, float)):
                found.append((parent, key, val))
        candidates.append((obj, tree, found, class_name, typename))

    print(json.dumps({"input": str(args.input), "lens_components": len(candidates)}, indent=2))
    for index, (_, _, found, cls, name) in enumerate(candidates):
        print(f"Candidate {index}: class={cls}, name={name!r}, intensity_fields={len(found)}")
        for _, key, value in found:
            print(f"  {key}: {value} -> 0 (proposed neutralization)")

    if not args.apply:
        print("DRY RUN ONLY: no files changed. Inspect candidate fields before applying.")
        return

    changed = 0
    for obj, tree, found, _, _ in candidates:
        if not found:
            continue
        for parent, key, old in found:
            parent[key] = 0
        try:
            obj.save_typetree(tree)
            changed += len(found)
        except Exception as exc:
            raise RuntimeError(f"Failed to serialize lens component; aborting output: {exc}") from exc

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        env.save(str(args.output))
    except Exception as exc:
        raise RuntimeError(f"Asset write failed; input untouched: {exc}") from exc
    print(f"Saved proposed output: {args.output}; fields neutralized: {changed}")


if __name__ == "__main__":
    main()
