#!/usr/bin/env python3
"""Read-only Unity asset diagnostics for Lethal Offline.

This deliberately does not mutate assets: it identifies the exact serialized
components/resources first so later patches can be scoped and round-trip tested.
"""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path
import UnityPy

DATA = Path("work/apk/assets/bin/Data")
OUT = Path("output")
OUT.mkdir(parents=True, exist_ok=True)

def plain(value, depth=0):
    if depth > 5:
        return str(value)[:300]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, dict):
        return {str(k): plain(v, depth + 1) for k, v in list(value.items())[:160]}
    if isinstance(value, (list, tuple)):
        return [plain(v, depth + 1) for v in value[:160]]
    if hasattr(value, "m_FileID") and hasattr(value, "m_PathID"):
        return {"m_FileID": int(value.m_FileID), "m_PathID": int(value.m_PathID)}
    if hasattr(value, "__dict__"):
        return {str(k): plain(v, depth + 1) for k, v in vars(value).items() if not str(k).startswith("_")}
    return str(value)[:500]

def parse_dict(obj):
    for method in ("parse_as_dict", "read_typetree"):
        fn = getattr(obj, method, None)
        if fn:
            try:
                result = fn()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
    try:
        value = obj.parse_as_object()
        if hasattr(value, "__dict__"):
            return vars(value)
    except Exception:
        pass
    return {}

def ptr_id(value):
    if isinstance(value, dict):
        return int(value.get("m_PathID", 0) or 0)
    return int(getattr(value, "m_PathID", 0) or 0)

env = UnityPy.load(str(DATA))

# Unity IL2CPP builds omit most custom MonoBehaviour typetrees from serialized
# assets. Generate them from the exact arm64 libil2cpp + global-metadata pair
# before inspecting any scene component; otherwise only the generic header is
# visible and settings for fog/cameras/volumes cannot be identified safely.
typetree_status = {"enabled": False}
il2cpp_path = Path("work/apk/lib/arm64-v8a/libil2cpp.so")
metadata_path = DATA / "Managed" / "Metadata" / "global-metadata.dat"
try:
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    unity_version = next(
        (str(getattr(o.assets_file, "unity_version", "")) for o in env.objects
         if getattr(o.assets_file, "unity_version", "")),
        ""
    )
    if not unity_version:
        raise RuntimeError("Unity version missing from serialized assets")
    if not il2cpp_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("IL2CPP binary or global-metadata.dat is missing")
    generator = TypeTreeGenerator(unity_version)
    generator.load_il2cpp(il2cpp_path.read_bytes(), metadata_path.read_bytes())
    env.typetree_generator = generator
    typetree_status = {
        "enabled": True,
        "unity_version": unity_version,
        "il2cpp_bytes": il2cpp_path.stat().st_size,
        "metadata_bytes": metadata_path.stat().st_size,
    }
except Exception as exc:
    typetree_status = {"enabled": False, "error": str(exc)[:1000]}

type_counts = Counter()
script_map = {}
gameobject_map = {}
records = []
audio = []
meshes = []
exceptions = []

objects = list(env.objects)
for obj in objects:
    type_counts[obj.type.name] += 1
    if obj.type.name == "MonoScript":
        try:
            d = parse_dict(obj)
            if not d:
                x = obj.parse_as_object()
                d = vars(x) if hasattr(x, "__dict__") else {}
            script_map[int(obj.path_id)] = {
                "class": str(d.get("m_ClassName", "")),
                "namespace": str(d.get("m_Namespace", "")),
                "assembly": str(d.get("m_AssemblyName", "")),
            }
        except Exception as exc:
            exceptions.append({"kind": "MonoScript", "path_id": int(obj.path_id), "error": str(exc)[:250]})
    elif obj.type.name == "GameObject":
        try:
            d = parse_dict(obj)
            name = d.get("m_Name", "")
            if not name:
                x = obj.parse_as_object()
                name = getattr(x, "m_Name", "")
            gameobject_map[int(obj.path_id)] = str(name or "")
        except Exception:
            pass

# Inventory all audio and mesh resources without altering their payload or references.
for obj in objects:
    try:
        if obj.type.name == "AudioClip":
            x = obj.parse_as_object()
            resource = getattr(x, "m_Resource", None)
            audio.append({
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "name": str(getattr(x, "m_Name", "") or ""),
                "length_seconds": round(float(getattr(x, "m_Length", 0.0) or 0.0), 3),
                "frequency_hz": int(getattr(x, "m_Frequency", 0) or 0),
                "channels": int(getattr(x, "m_Channels", 0) or 0),
                "bits_per_sample": int(getattr(x, "m_BitsPerSample", 0) or 0),
                "compression_format": int(getattr(x, "m_CompressionFormat", 0) or 0),
                "load_type": int(getattr(x, "m_LoadType", 0) or 0),
                "resource": plain(resource),
                "embedded_audio_bytes": len(getattr(x, "m_AudioData", b"") or b""),
            })
        elif obj.type.name == "Mesh":
            x = obj.parse_as_object()
            submeshes = list(getattr(x, "m_SubMeshes", []) or [])
            index_count = sum(int(getattr(s, "indexCount", 0) or 0) for s in submeshes)
            meshes.append({
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "name": str(getattr(x, "m_Name", "") or ""),
                "vertex_count": int(getattr(x, "m_VertexCount", 0) or 0),
                "submesh_count": len(submeshes),
                "index_count": index_count,
                "index_format": int(getattr(x, "m_IndexFormat", 0) or 0),
                "readable": bool(getattr(x, "m_IsReadable", False)),
            })
    except Exception as exc:
        exceptions.append({"kind": obj.type.name, "path_id": int(obj.path_id), "error": str(exc)[:250]})

# Capture built-in render settings and camera defaults as well as custom components.
render_settings = []
camera_settings = []
for obj in objects:
    try:
        if obj.type.name == "RenderSettings":
            render_settings.append({
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "fields": plain(parse_dict(obj)),
            })
        elif obj.type.name == "Camera":
            camera_settings.append({
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "fields": plain(parse_dict(obj)),
            })
    except Exception as exc:
        exceptions.append({"kind": obj.type.name, "path_id": int(obj.path_id), "error": str(exc)[:250]})

# Map MonoBehaviours to script names and their owning GameObjects.
terms = re.compile(r"fog|lens|distort|volume|post.?process|camera|spectat|death|respawn|audio|micro|voice|player|network|input|quality|ship|monitor|hdrp|sky|global|profile|spooky|fixfog|chromatic|vignette", re.I)
for obj in objects:
    if obj.type.name != "MonoBehaviour":
        continue
    try:
        d = parse_dict(obj)
        sid = ptr_id(d.get("m_Script", {}))
        gid = ptr_id(d.get("m_GameObject", {}))
        script = script_map.get(sid, {})
        cls = script.get("class", "")
        ns = script.get("namespace", "")
        go_name = gameobject_map.get(gid, "")
        # Keep matching behaviors plus all components with missing script metadata
        # so the report makes parsing gaps visible.
        if terms.search(" ".join((cls, ns, go_name))) or not cls:
            records.append({
                "asset_file": str(getattr(obj.assets_file, "name", "")),
                "path_id": int(obj.path_id),
                "gameobject_path_id": gid,
                "gameobject": go_name,
                "script_path_id": sid,
                "script_class": cls,
                "script_namespace": ns,
                "script_assembly": script.get("assembly", ""),
                "serialized_fields": plain(d),
            })
    except Exception as exc:
        exceptions.append({"kind": "MonoBehaviour", "path_id": int(obj.path_id), "error": str(exc)[:250]})

report = {
    "unitypy_version": getattr(UnityPy, "__version__", "unknown"),
    "asset_type_counts": dict(sorted(type_counts.items())),
    "mono_script_count": len(script_map),
    "named_script_count": sum(bool(x.get("class")) for x in script_map.values()),
    "typetree_generator": typetree_status,
    "gameobject_count": len(gameobject_map),
    "render_settings": render_settings,
    "camera_settings": camera_settings,
    "relevant_monobehaviours": records,
    "audio_clips": sorted(audio, key=lambda x: x["length_seconds"], reverse=True),
    "mesh_summary": {
        "count": len(meshes),
        "total_vertices": sum(x["vertex_count"] for x in meshes),
        "total_indices": sum(x["index_count"] for x in meshes),
        "largest_meshes": sorted(meshes, key=lambda x: x["vertex_count"], reverse=True)[:120],
    },
    "parse_exceptions": exceptions[:200],
    "notes": [
        "Read-only inventory; no audio, mesh, scene, volume, camera, or gameplay resource was changed.",
        "IL2CPP typetree generation is attempted using the arm64 binary and the matching global-metadata.dat; its status is recorded above.",
        "Audio compression_format values are Unity serialized enum values, not human-readable labels.",
        "Mesh data and animation/skeleton/collider dependencies must be inspected before geometry reduction.",
    ],
}
path = OUT / "asset-diagnostics.json"
path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
print(json.dumps({
    "asset_type_counts": report["asset_type_counts"],
    "mono_script_count": report["mono_script_count"],
    "named_script_count": report["named_script_count"],
    "typetree_generator": report["typetree_generator"],
    "relevant_monobehaviour_count": len(records),
    "audio_clip_count": len(audio),
    "mesh_count": len(meshes),
    "mesh_vertices": report["mesh_summary"]["total_vertices"],
    "diagnostic_file": str(path),
}, indent=2))
