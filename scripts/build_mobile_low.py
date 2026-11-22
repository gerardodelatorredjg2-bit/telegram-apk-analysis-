#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

import UnityPy
from PIL import Image

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
APK = ROOT / "input" / "original.apk"
DATA = ROOT / "work" / "apk" / "assets" / "bin" / "Data"
MODIFIED = ROOT / "work" / "modified"
OUT = ROOT / "output"
CHUNK_SIZE = 1024 * 1024

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def resize_normal_map(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    import numpy as np
    src = img.convert("RGBA")
    a = np.asarray(src, dtype=np.float32)
    # Resize normal-vector channels independently, then renormalize them.
    planes = []
    for channel in range(3):
        plane = Image.fromarray(a[:, :, channel], mode="F").resize(size, Image.Resampling.LANCZOS)
        planes.append(np.asarray(plane, dtype=np.float32))
    vec = np.stack(planes, axis=-1) / 127.5 - 1.0
    lengths = np.linalg.norm(vec, axis=-1, keepdims=True)
    vec = vec / np.maximum(lengths, 1e-6)
    rgb = np.clip((vec * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    alpha = Image.fromarray(a[:, :, 3], mode="F").resize(size, Image.Resampling.LANCZOS)
    alpha = np.clip(np.asarray(alpha), 0, 255).astype(np.uint8)
    rgba = np.dstack((rgb, alpha))
    return Image.fromarray(rgba, mode="RGBA")

def patch_quality(obj, records):
    settings = obj.parse_as_object()
    current = list(settings.m_QualitySettings or [])
    if not current:
        raise RuntimeError("QualitySettings has no quality profile; refusing to invent one.")

    # Keep a copy of the original profile so High remains available as profile 1.
    high = current[0]
    # Construct a shallow copy from the dataclass fields; deep-copying Unity PPtrs
    # also tries to copy their binary readers and fails on EndianBinaryReader.
    from attrs import evolve
    low = evolve(high)
    low.name = "Low (Mobile)"
    low.shadows = 0                  # disabled on the Low Mobile profile
    low.shadowDistance = 0.0
    low.shadowResolution = 0
    low.shadowCascades = 0
    low.pixelLightCount = 0
    low.antiAliasing = 0
    low.anisotropicTextures = 0
    low.lodBias = 0.45
    low.maximumLODLevel = 2
    low.globalTextureMipmapLimit = 1
    low.streamingMipmapsActive = True
    low.streamingMipmapsMemoryBudget = 128.0
    low.streamingMipmapsMaxFileIORequests = 128
    low.streamingMipmapsRenderersPerFrame = 64
    low.realtimeReflectionProbes = False
    low.particleRaycastBudget = 16
    low.terrainBasemapDistance = 250.0
    low.terrainBillboardStart = 15.0
    low.terrainDetailDensityScale = 0.15
    low.terrainDetailDistance = 10.0
    low.terrainMaxTrees = 15
    low.terrainPixelError = 3.0
    low.terrainTreeDistance = 300.0
    low.asyncUploadBufferSize = 4
    low.asyncUploadTimeSlice = 1
    low.softVegetation = False
    if hasattr(low, "skinWeights"):
        low.skinWeights = 2
    settings.m_QualitySettings = [low, high]
    settings.m_CurrentQuality = 0
    settings.m_DefaultMobileQuality = 0
    obj.patch(settings)
    records["quality"] = {
        "original_profiles": [getattr(x, "name", "") for x in current],
        "new_profiles": ["Low (Mobile)", getattr(high, "name", "High")],
        "default_mobile_profile": 0,
        "low_profile": {
            "shadows": low.shadows,
            "shadow_distance": low.shadowDistance,
            "shadow_resolution": low.shadowResolution,
            "shadow_cascades": low.shadowCascades,
            "pixel_lights": low.pixelLightCount,
            "lod_bias": low.lodBias,
            "mipmap_limit": low.globalTextureMipmapLimit,
            "streaming_mipmap_budget_mb": low.streamingMipmapsMemoryBudget,
            "reflection_probes": low.realtimeReflectionProbes,
            "terrain_tree_distance": low.terrainTreeDistance,
            "terrain_detail_distance": low.terrainDetailDistance,
        },
    }

def patch_player_settings(obj):
    settings = obj.parse_as_object()
    names = list(getattr(settings, "qualitySettingsNames", None) or [])
    if names:
        original = names[0]
        settings.qualitySettingsNames = ["Low (Mobile)", original]
        obj.patch(settings)
        return {"qualitySettingsNames": settings.qualitySettingsNames}
    raise RuntimeError("PlayerSettings.qualitySettingsNames is empty; cannot safely sync quality indices.")

def main():
    if not APK.exists():
        raise FileNotFoundError(APK)
    OUT.mkdir(parents=True, exist_ok=True)
    MODIFIED.mkdir(parents=True, exist_ok=True)

    env = UnityPy.load(str(DATA))
    changed_files = {}
    report = {
        "unitypy_version": getattr(UnityPy, "__version__", "unknown"),
        "texture_changes": [],
        "texture_skips": [],
        "quality": {},
        "player_settings": None,
        "saved_asset_files": {},
        "notes": [
            "Mobile Low targets a maximum texture dimension of 1024px, except UI/text assets.",
            "Both original and low mobile quality profiles are retained; low mobile is selected by default.",
            "Texture assets are resized in their existing Unity texture format; normal maps are renormalized after resampling.",
            "Scenes, colliders, meshes, audio, network code, voice resources, and both Android ABIs are preserved.",
            "Runtime frame rate and visual effects must still be checked on a physical Android device.",
        ],
    }

    quality_obj = None
    player_obj = None
    for obj in env.objects:
        if obj.type.name == "QualitySettings" and getattr(obj.assets_file, "name", "") == "globalgamemanagers":
            quality_obj = obj
        elif obj.type.name == "PlayerSettings" and getattr(obj.assets_file, "name", "") == "globalgamemanagers":
            player_obj = obj
    if quality_obj is None or player_obj is None:
        raise RuntimeError("Could not locate QualitySettings and PlayerSettings in globalgamemanagers.")

    patch_quality(quality_obj, report)
    report["player_settings"] = patch_player_settings(player_obj)
    changed_files[id(quality_obj.assets_file)] = quality_obj.assets_file

    # Aggressive mobile texture cap: reduce all oversized non-UI textures to 1024px max side.
    # Keep text/UI elements sharp; retain texture formats and regenerate full mip chains.
    max_dimension = 1024
    ui_name_tokens = (
        "manual", "splash", "logo", "font", "glyph", "icon", "cursor",
        "crosshair", "reticle", "subtitle", "button", "hud", "ui_",
    )
    for obj in env.objects:
        if obj.type.name != "Texture2D":
            continue
        try:
            tex = obj.parse_as_object()
            width = int(getattr(tex, "m_Width", 0) or 0)
            height = int(getattr(tex, "m_Height", 0) or 0)
            if width <= 0 or height <= 0 or max(width, height) <= max_dimension:
                continue

            name = str(getattr(tex, "m_Name", "") or "")
            lower_name = name.lower()
            if any(token in lower_name for token in ui_name_tokens):
                report["texture_skips"].append({
                    "name": name,
                    "reason": "preserved UI/text asset",
                    "old_dimensions": [width, height],
                })
                continue

            fmt = int(getattr(tex, "m_TextureFormat", 0) or 0)
            try:
                old_data_size = len(tex.get_image_data())
            except Exception:
                old_data_size = 0

            img = tex.image
            if img is None:
                report["texture_skips"].append({"name": name, "reason": "UnityPy did not decode the texture"})
                continue

            scale = max_dimension / float(max(width, height))
            target_w = max(4, int(round((width * scale) / 4.0)) * 4)
            target_h = max(4, int(round((height * scale) / 4.0)) * 4)
            target = (target_w, target_h)

            if "normal" in lower_name or "nrm" in lower_name:
                resized = resize_normal_map(img, target)
            else:
                resized = img.resize(target, Image.Resampling.LANCZOS)

            mip_count = int(math.log2(min(target))) + 1
            tex.set_image(resized, target_format=fmt, mipmap_count=mip_count)
            try:
                new_data_size = len(tex.get_image_data())
            except Exception:
                new_data_size = 0

            # If UnityPy cannot report sizes, retain the resized image only when
            # dimensions changed successfully. If size is known, demand a saving.
            if old_data_size > 0 and new_data_size > 0 and new_data_size >= old_data_size:
                report["texture_skips"].append({
                    "name": name,
                    "reason": "resized encoding was not smaller",
                    "old_dimensions": [width, height],
                    "new_dimensions": list(target),
                    "old_encoded_bytes": old_data_size,
                    "new_encoded_bytes": new_data_size,
                })
                continue

            obj.patch(tex)
            changed_files[id(obj.assets_file)] = obj.assets_file
            report["texture_changes"].append({
                "name": name,
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "old_dimensions": [width, height],
                "new_dimensions": list(target),
                "format": fmt,
                "old_encoded_bytes": old_data_size,
                "new_encoded_bytes": new_data_size,
                "normal_map_renormalized": ("normal" in lower_name or "nrm" in lower_name),
            })
        except Exception as exc:
            report["texture_skips"].append({"path_id": int(obj.path_id), "reason": str(exc)[:500]})

    if not report["texture_changes"]:
        raise RuntimeError("No oversized textures could be safely resized; refusing to create an unchanged build.")

    report["texture_summary"] = {
        "max_dimension": max_dimension,
        "changed_count": len(report["texture_changes"]),
        "skipped_count": len(report["texture_skips"]),
        "old_encoded_bytes": sum(int(x.get("old_encoded_bytes", 0) or 0) for x in report["texture_changes"]),
        "new_encoded_bytes": sum(int(x.get("new_encoded_bytes", 0) or 0) for x in report["texture_changes"]),
        "encoded_bytes_saved_estimate": sum(
            max(0, int(x.get("old_encoded_bytes", 0) or 0) - int(x.get("new_encoded_bytes", 0) or 0))
            for x in report["texture_changes"]
        ),
    }

    # Save each modified Unity serialized file once.
    outputs = {}
    for asset_file in changed_files.values():
        name = str(asset_file.name)
        raw = asset_file.save()
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise RuntimeError(f"UnityPy returned empty data for {name}")
        path = MODIFIED / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        outputs[name] = path
        report["saved_asset_files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    # Recreate Unity's 1 MiB split-file naming from the original APK's entry list.
    # The earlier extraction step has already joined and deleted the original split fragments.
    with zipfile.ZipFile(APK, "r") as original_zip:
        original_names = set(original_zip.namelist())
    replacements = {}
    for name, path in outputs.items():
        prefix = f"assets/bin/Data/{name}.split"
        had_split = any(
            entry.startswith(prefix) and entry[len(prefix):].isdigit()
            for entry in original_names
        )
        if had_split:
            merged = DATA / name
            if merged.exists():
                merged.unlink()
            for old in DATA.glob(name + ".split[0-9]*"):
                old.unlink()
            with path.open("rb") as src:
                index = 0
                while True:
                    block = src.read(CHUNK_SIZE)
                    if not block:
                        break
                    chunk_path = DATA / f"{name}.split{index}"
                    chunk_path.write_bytes(block)
                    replacements[f"assets/bin/Data/{name}.split{index}"] = chunk_path
                    index += 1
            path.unlink()
        else:
            dest = DATA / name
            shutil.copy2(path, dest)
            replacements[f"assets/bin/Data/{name}"] = dest

    # Round-trip validate all modified dimensions and the Low Mobile profile.
    verify = UnityPy.load(str(DATA))
    q_ok = False
    texture_ok = {}
    required_tex = {
        (x["asset_file"], int(x["path_id"])): tuple(int(v) for v in x["new_dimensions"])
        for x in report["texture_changes"]
    }
    for obj in verify.objects:
        if obj.type.name == "QualitySettings" and getattr(obj.assets_file, "name", "") == "globalgamemanagers":
            q = obj.parse_as_object()
            profs = list(q.m_QualitySettings or [])
            q_ok = (
                len(profs) >= 2
                and getattr(profs[0], "name", "") == "Low (Mobile)"
                and int(q.m_CurrentQuality) == 0
                and float(profs[0].shadowDistance) == 0.0
                and int(profs[0].shadows) == 0
                and int(profs[0].pixelLightCount) == 0
            )
        elif obj.type.name == "Texture2D":
            key = (str(getattr(obj.assets_file, "name", "")), int(obj.path_id))
            if key not in required_tex:
                continue
            try:
                t = obj.parse_as_object()
                dims = (int(t.m_Width), int(t.m_Height))
                if dims == required_tex[key]:
                    texture_ok[key] = dims
            except Exception:
                pass

    if not q_ok:
        raise RuntimeError("Low Mobile QualitySettings round-trip validation failed.")
    missing_textures = set(required_tex) - set(texture_ok)
    if missing_textures:
        raise RuntimeError(f"Texture round-trip validation failed: missing {len(missing_textures)} of {len(required_tex)} modified textures.")
    report["roundtrip_validation"] = {
        "quality_profile": True,
        "modified_textures_required": len(required_tex),
        "matching_textures_found": len(texture_ok),
        "all_modified_textures_present": True,
        "max_texture_dimension_after_patch": max(max(v) for v in texture_ok.values()),
    }

    # Rewrite APK while preserving every original entry except the serialized files changed above.
    unsigned = ROOT / "output" / "LethalOffline-MobileLow-unsigned.apk"
    base_names = set(outputs)
    with zipfile.ZipFile(APK, "r") as zin:
        infos = zin.infolist()
        direct_infos = {}
        chunk_compression = {}
        for info in infos:
            filename = info.filename
            for base in base_names:
                direct = f"assets/bin/Data/{base}"
                if filename == direct:
                    direct_infos[base] = info
                elif re.fullmatch(re.escape(direct) + r"\.split\d+", filename):
                    chunk_compression[base] = info
        with zipfile.ZipFile(unsigned, "w", allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for info in infos:
                filename = info.filename
                skip = False
                for base in base_names:
                    direct = f"assets/bin/Data/{base}"
                    if filename == direct or re.fullmatch(re.escape(direct) + r"\.split\d+", filename):
                        skip = True
                        break
                if skip:
                    continue
                # Old v1 signatures no longer apply after modifying the archive.
                if filename.upper().startswith("META-INF/") and filename.upper().endswith((".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")):
                    continue
                with zin.open(info, "r") as src, zout.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)

            # Restore modified files under exactly the original Unity path scheme.
            for filename, path in replacements.items():
                rel = filename.removeprefix("assets/bin/Data/")
                # Keep the archive's original storage/deflate choice for this asset family.
                base_asset = next((k for k in base_names if rel == k or rel.startswith(k + ".split")), None)
                if base_asset is not None and base_asset in chunk_compression:
                    ctype = chunk_compression[base_asset].compress_type
                    dt = chunk_compression[base_asset].date_time
                else:
                    original_info = direct_infos.get(rel)
                    ctype = original_info.compress_type if original_info else zipfile.ZIP_STORED
                    dt = original_info.date_time if original_info else (2026, 1, 1, 0, 0, 0)
                zi = zipfile.ZipInfo(filename, date_time=dt)
                zi.compress_type = ctype
                zi.external_attr = 0o100644 << 16
                with path.open("rb") as src, zout.open(zi, "w") as dst:
                    shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)

    report["apk"] = {"original_bytes": APK.stat().st_size, "unsigned_bytes": unsigned.stat().st_size, "zip_deflate_level": 9}
    report["apk"]["unsigned_sha256"] = sha256(unsigned)
    (OUT / "optimization-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({
        "textures_resized": len(report["texture_changes"]),
        "textures_skipped": len(report["texture_skips"]),
        "changed_assets": report["saved_asset_files"],
        "roundtrip": report["roundtrip_validation"],
        "apk_bytes": report["apk"],
    }, indent=2))

if __name__ == "__main__":
    main()
