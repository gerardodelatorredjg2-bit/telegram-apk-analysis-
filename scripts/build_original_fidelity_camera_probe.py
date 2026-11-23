#!/usr/bin/env python3
"""Build an original-fidelity A/B candidate with only player-camera near clipping changed.

No textures, meshes, materials, lighting, shadows, audio, fog volumes, lens effects,
scene objects, or gameplay code are changed. This is a test candidate, not a claim
that a camera artifact is already fixed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import UnityPy

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
APK = ROOT / "input" / "original.apk"
DATA = ROOT / "work" / "apk" / "assets" / "bin" / "Data"
OUT = ROOT / "output"
REPORT = OUT / "camera-probe-report.json"
NEAR_BEFORE = 0.05
NEAR_AFTER = 0.10
CHUNK_SIZE = 1024 * 1024
SCENE_NAME = "level3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_attr(value, *names, default=None):
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def set_attr_existing(value, names, new_value):
    for name in names:
        if hasattr(value, name):
            setattr(value, name, new_value)
            return name
    available = sorted(name for name in dir(value) if not name.startswith("_"))
    raise AttributeError(f"Could not find any field from {names}; available={available[:80]}")


def ptr_id(pointer) -> int:
    return int(get_attr(pointer, "m_PathID", "path_id", default=0) or 0)


def camera_records(root: Path):
    env = UnityPy.load(str(root))
    gameobjects = {}
    camera_objects = []
    for obj in env.objects:
        if str(getattr(obj.assets_file, "name", "")) != SCENE_NAME:
            continue
        if obj.type.name == "GameObject":
            parsed = obj.parse_as_object()
            name = get_attr(parsed, "m_Name", "name", default="")
            gameobjects[int(obj.path_id)] = str(name or "")
        elif obj.type.name == "Camera":
            camera_objects.append(obj)
    records = []
    for obj in camera_objects:
        camera = obj.parse_as_object()
        go_pointer = get_attr(camera, "m_GameObject", "game_object")
        go_id = ptr_id(go_pointer)
        go_name = gameobjects.get(go_id, "")
        near_field = next(
            (name for name in ("near_clip_plane", "m_NearClipPlane") if hasattr(camera, name)),
            None,
        )
        if near_field is None:
            raise AttributeError(
                "UnityPy Camera object has no recognized near clip field; "
                f"available={[name for name in dir(camera) if not name.startswith('_')]}"
            )
        if go_name == "MainCamera":
            records.append({
                "object": obj,
                "camera": camera,
                "near_field": near_field,
                "gameobject_path_id": go_id,
                "camera_path_id": int(obj.path_id),
                "gameobject": go_name,
                "near_clip": float(getattr(camera, near_field)),
            })
    return env, records


def main():
    if not APK.is_file() or APK.stat().st_size < 100_000_000:
        raise FileNotFoundError(f"Original APK is missing or suspiciously small: {APK}")
    OUT.mkdir(parents=True, exist_ok=True)
    MODIFIED = ROOT / "work" / "modified"
    MODIFIED.mkdir(parents=True, exist_ok=True)

    env, records = camera_records(DATA)
    if len(records) != 4:
        raise RuntimeError(f"Expected exactly four player MainCamera objects in level3; found {len(records)}")
    for item in records:
        if abs(item["near_clip"] - NEAR_BEFORE) > 0.001:
            raise RuntimeError(
                f"Unexpected near clip on player camera pathID {item['camera_path_id']}: "
                f"{item['near_clip']} (expected {NEAR_BEFORE})"
            )

    changed_asset = None
    for item in records:
        setattr(item["camera"], item["near_field"], NEAR_AFTER)
        item["object"].patch(item["camera"])
        changed_asset = item["object"].assets_file

    if changed_asset is None or str(changed_asset.name) != SCENE_NAME:
        raise RuntimeError("Did not obtain the expected level3 serialized file")
    asset_bytes = changed_asset.save()
    if not isinstance(asset_bytes, (bytes, bytearray)) or not asset_bytes:
        raise RuntimeError("UnityPy returned empty level3 asset data")
    (DATA / SCENE_NAME).write_bytes(asset_bytes)
    (MODIFIED / SCENE_NAME).write_bytes(asset_bytes)

    # Reload the modified serialized file and verify every player camera value.
    verify_env, verify_records = camera_records(MODIFIED)
    if len(verify_records) != 4:
        raise RuntimeError(f"Round-trip camera count mismatch: {len(verify_records)}")
    for item in verify_records:
        if abs(item["near_clip"] - NEAR_AFTER) > 0.001:
            raise RuntimeError(
                f"Round-trip near-clip validation failed on camera pathID {item['camera_path_id']}: "
                f"{item['near_clip']}"
            )

    original_hash = sha256(APK)
    unsigned = OUT / "LethalOffline-OriginalFidelity-CameraProbe-unsigned.apk"
    with zipfile.ZipFile(APK, "r") as source:
        infos = source.infolist()
        level_entries = [
            info for info in infos
            if info.filename == f"assets/bin/Data/{SCENE_NAME}"
            or re.fullmatch(re.escape(f"assets/bin/Data/{SCENE_NAME}") + r"\.split\d+", info.filename)
        ]
        if not level_entries:
            raise RuntimeError("Original APK does not contain the expected level3 Unity asset chunks")
        template = level_entries[0]
        if any(info.compress_type != template.compress_type for info in level_entries):
            raise RuntimeError("Original level3 chunks have inconsistent compression methods")
        with zipfile.ZipFile(unsigned, "w", allowZip64=True) as output:
            for info in infos:
                name = info.filename
                if name == f"assets/bin/Data/{SCENE_NAME}" or re.fullmatch(
                    re.escape(f"assets/bin/Data/{SCENE_NAME}") + r"\.split\d+", name
                ):
                    continue
                upper = name.upper()
                if upper.startswith("META-INF/") and upper.endswith(
                    (".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")
                ):
                    continue
                with source.open(info, "r") as src, output.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)

            for index, offset in enumerate(range(0, len(asset_bytes), CHUNK_SIZE)):
                chunk = asset_bytes[offset:offset + CHUNK_SIZE]
                info = zipfile.ZipInfo(
                    f"assets/bin/Data/{SCENE_NAME}.split{index}",
                    date_time=template.date_time,
                )
                info.compress_type = template.compress_type
                info.external_attr = 0o100644 << 16
                output.writestr(info, chunk)

    report = {
        "candidate": "OriginalFidelity-CameraProbe",
        "base": "original-apk",
        "original_apk_sha256": original_hash,
        "modified_scene": SCENE_NAME,
        "change": "Player MainCamera m_NearClipPlane: 0.05 -> 0.10",
        "camera_count": len(records),
        "cameras": [
            {
                "gameobject_path_id": x["gameobject_path_id"],
                "camera_path_id": x["camera_path_id"],
                "gameobject": x["gameobject"],
                "near_clip_before": NEAR_BEFORE,
                "near_clip_after": NEAR_AFTER,
            }
            for x in records
        ],
        "roundtrip_validation": {
            "passed": True,
            "player_main_cameras_found": len(verify_records),
            "all_near_clip_values_verified": True,
        },
        "preserved": [
            "all original textures and mipmaps",
            "all original meshes, materials, shaders, and scene geometry",
            "all original HDRP fog and lens-distortion components",
            "all original lighting, shadows, reflections, and quality settings",
            "all original audio, voice, networking, and gameplay binaries",
            "all original scenes except the four player-camera near-clip values in level3",
        ],
        "limitations": [
            "This is an isolated near-clipping A/B candidate for the reported black geometry/camera-intersection symptom.",
            "It is not a fix for IL2CPP spectator-camera logic, the fog transition, audio glitches, touch UI design, terminal interaction, or update notifications.",
            "It requires testing on the target Android device before being treated as a fix.",
        ],
        "unsigned_apk_bytes": unsigned.stat().st_size,
        "unsigned_apk_sha256": sha256(unsigned),
        "modified_level3_bytes": len(asset_bytes),
        "modified_level3_sha256": hashlib.sha256(asset_bytes).hexdigest(),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
