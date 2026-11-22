#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy

ROOT = Path(".")
DATA = ROOT / "work" / "apk" / "assets" / "bin" / "Data"
OUT = ROOT / "output"
KEYWORDS = ("fish", "fisheye", "fish eye", "lens", "distort", "barrel", "warp", "fog", "mist", "nebl", "camera", "post")

def nbytes(value):
    try:
        return len(value) if value is not None else 0
    except Exception:
        return 0

def simple(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": len(value)}
    for attr in ("m_Source", "m_Offset", "m_Size", "m_PathID", "path_id"):
        if hasattr(value, attr):
            continue
    return str(value)[:300]

def main():
    env = UnityPy.load(str(DATA))
    counts = Counter()
    texture_rows, mesh_rows, audio_rows, shader_rows, material_rows = [], [], [], [], []
    named_rows, render_rows, quality_rows = [], [], []
    total_types = defaultdict(int)

    for obj in env.objects:
        kind = getattr(getattr(obj, "type", None), "name", "Unknown")
        counts[kind] += 1
        try:
            data = obj.parse_as_object()
        except Exception as exc:
            if kind in {"Texture2D", "Mesh", "AudioClip", "Shader", "Material", "RenderSettings", "Camera", "GameObject", "MonoBehaviour", "QualitySettings"}:
                named_rows.append({"type": kind, "asset_file": str(getattr(obj.assets_file, "name", "")), "path_id": int(obj.path_id), "parse_error": str(exc)[:180]})
            continue
        name = str(getattr(data, "m_Name", "") or "")
        base = {"type": kind, "name": name, "asset_file": str(getattr(obj.assets_file, "name", "")), "path_id": int(obj.path_id)}

        if kind == "Texture2D":
            width = int(getattr(data, "m_Width", 0) or 0)
            height = int(getattr(data, "m_Height", 0) or 0)
            try:
                raw_size = len(data.get_image_data())
            except Exception:
                raw_size = nbytes(getattr(data, "image_data", None))
            row = {**base, "width": width, "height": height, "format": simple(getattr(data, "m_TextureFormat", None)), "encoded_bytes": raw_size}
            texture_rows.append(row)
            total_types["texture_encoded_bytes"] += raw_size

        elif kind == "Mesh":
            vertex_data = getattr(data, "m_VertexData", None)
            index_buffer = getattr(data, "m_IndexBuffer", None)
            vertex_count = getattr(vertex_data, "m_VertexCount", None) if vertex_data is not None else None
            vertex_bytes = nbytes(getattr(vertex_data, "m_Data", None)) if vertex_data is not None else 0
            index_bytes = nbytes(index_buffer)
            submeshes = getattr(data, "m_SubMeshes", None)
            row = {**base, "vertex_count": simple(vertex_count), "vertex_data_bytes": vertex_bytes, "index_buffer_bytes": index_bytes, "submesh_count": len(submeshes) if submeshes is not None else None}
            mesh_rows.append(row)
            total_types["mesh_buffer_bytes"] += vertex_bytes + index_bytes

        elif kind == "AudioClip":
            audio_data = getattr(data, "m_AudioData", None)
            resource = getattr(data, "m_Resource", None)
            resource_size = getattr(resource, "m_Size", None) if resource is not None else None
            row = {**base,
                   "audio_data_bytes": nbytes(audio_data),
                   "resource_size": simple(resource_size),
                   "channels": simple(getattr(data, "m_Channels", None)),
                   "frequency": simple(getattr(data, "m_Frequency", None)),
                   "bits_per_sample": simple(getattr(data, "m_BitsPerSample", None)),
                   "length_seconds": simple(getattr(data, "m_Length", None)),
                   "load_type": simple(getattr(data, "m_LoadType", None)),
                   "compression_format": simple(getattr(data, "m_CompressionFormat", None))}
            audio_rows.append(row)
            total_types["audio_inline_bytes"] += nbytes(audio_data)
            try:
                total_types["audio_external_bytes"] += int(resource_size or 0)
            except Exception:
                pass

        elif kind == "Shader":
            shader_rows.append({**base, "platforms": simple(getattr(data, "platforms", None)), "parsed_form": bool(getattr(data, "m_ParsedForm", None))})
        elif kind == "Material":
            material_rows.append({**base, "shader": simple(getattr(data, "m_Shader", None)), "texture_env_count": len(getattr(data, "m_SavedProperties", {}).get("m_TexEnvs", [])) if isinstance(getattr(data, "m_SavedProperties", None), dict) else None})
        elif kind in {"RenderSettings", "Camera", "QualitySettings"}:
            fields = {}
            for attr in dir(data):
                if attr.startswith("m_") and any(k in attr.lower() for k in ("fog", "camera", "quality", "ambient", "skybox", "density", "color", "fov", "near", "far")):
                    try:
                        fields[attr] = simple(getattr(data, attr))
                    except Exception:
                        pass
            row = {**base, "fields": fields}
            (render_rows if kind in {"RenderSettings", "Camera"} else quality_rows).append(row)

        if any(word in name.lower() for word in KEYWORDS):
            named_rows.append({**base, "matched_keywords": [k for k in KEYWORDS if k in name.lower()]})

    def top(rows, key, count=80):
        return sorted(rows, key=lambda x: int(x.get(key, 0) or 0), reverse=True)[:count]

    report = {
        "unitypy_version": getattr(UnityPy, "__version__", "unknown"),
        "object_counts": dict(counts),
        "totals": dict(total_types),
        "texture_dimensions": dict(Counter(f"{r['width']}x{r['height']}" for r in texture_rows)),
        "textures_largest": top(texture_rows, "encoded_bytes", 120),
        "meshes_largest": top(mesh_rows, "vertex_data_bytes", 120),
        "audio_largest": top(audio_rows, "audio_data_bytes", 120),
        "shaders": shader_rows[:300],
        "materials": material_rows[:300],
        "render_and_camera_settings": render_rows[:300],
        "quality_settings": quality_rows[:100],
        "named_keyword_matches": named_rows[:500],
        "safety_note": "Inventory only. No game assets or gameplay settings were modified by this report job."
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "unity-asset-inventory.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({
        "object_counts": report["object_counts"],
        "texture_dimensions": report["texture_dimensions"],
        "totals": report["totals"],
        "largest_texture_examples": report["textures_largest"][:12],
        "largest_audio_examples": report["audio_largest"][:12],
        "largest_mesh_examples": report["meshes_largest"][:12],
        "render_camera_settings": report["render_and_camera_settings"][:30],
        "keyword_matches": report["named_keyword_matches"][:50],
        "report": str(path)
    }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
