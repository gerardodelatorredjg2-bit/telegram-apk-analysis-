#!/usr/bin/env python3
"""Prepare a spectator-camera repair by inventorying IL2CPP symbols/strings.

This is a preparation/diagnostic patch only. It does NOT modify APK files,
execute a binary patch, or rebuild the game. Lethal Offline is IL2CPP and the
actual spectator-camera control flow must be identified before a safe edit can
be authored.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TERMS = (
    "spectator", "spectate", "dead", "death", "camera", "playercontrollerb",
    "killslocalplayer", "cameraswitch", "freecamera",
)
ASCII_STRING = re.compile(rb"[\x20-\x7e]{4,}")


def scan_file(path: Path) -> list[str]:
    found: set[str] = set()
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"[skip] {path}: {exc}")
        return []
    for match in ASCII_STRING.finditer(data):
        value = match.group().decode("ascii", errors="ignore")
        lower = value.lower()
        if any(term in lower for term in TERMS):
            found.add(value[:500])
    return sorted(found, key=str.casefold)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory spectator/camera strings in IL2CPP files")
    parser.add_argument("root", type=Path, help="Extracted game folder (read-only scan)")
    parser.add_argument("--output", type=Path, default=Path("spectator_camera_candidates.json"))
    args = parser.parse_args()
    root = args.root
    if not root.is_dir():
        parser.error(f"folder not found: {root}")

    candidates: dict[str, list[str]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".so", ".dat", ".bin"}:
            continue
        matches = scan_file(path)
        if matches:
            candidates[str(path.relative_to(root))] = matches

    report = {
        "purpose": "spectator-camera patch preparation",
        "read_only": True,
        "patch_applied": False,
        "build_performed": False,
        "warning": (
            "String matches do not prove code paths. Confirm spectator camera update, "
            "death transition, target switching, and camera lifetime in IL2CPP metadata "
            "before writing any binary modification."
        ),
        "files": candidates,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Read-only inventory written: {args.output}")
    print(f"Files with candidate strings: {len(candidates)}")
    print("No game files were changed and no APK was built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
