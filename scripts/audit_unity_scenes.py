#!/usr/bin/env python3
"""Read-only scene, camera, and lighting inventory for the packaged Unity APK."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy

DATA = Path("work/apk/assets/bin/Data")
OUT = Path("output")
OUT.mkdir(parents=True, exist_ok=True)


def plain(value, depth=0):
    if depth > 5:
        return str(value)[:250]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, dict):
        return {str(k): plain(v, depth + 1) for k, v in list(value.items())[:120]}
    if isinstance(value, (list, tuple)):
        return [plain(v, depth + 1) for v in value[:120]]
    if hasattr(value, "m_PathID"):
        return {
            "m_FileID": int(getattr(value, "m_FileID", 0) or 0),
            "m_PathID": int(getattr(value, "m_PathID", 0) or 0),
        }
    if hasattr(value, "__dict__"):
        return {
            str(k): plain(v, depth + 1)
            for k, v in vars(value).items()
            if not str(k).startswith("_")
        }
    return str(value)[:250]


def read_fields(obj):
    for name in ("parse_as_dict", "read_typetree"):
        method = getattr(obj, name, None)
        if method:
            try:
                result = method()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
    try:
        parsed = obj.parse_as_object()
        if hasattr(parsed, "__dict__"):
            return vars(parsed)
    except Exception:
        pass
    return {}


def field(data, *names, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def ptr_id(value):
    if isinstance(value, dict):
        return int(value.get("m_PathID", 0) or 0)
    return int(getattr(value, "m_PathID", 0) or 0)


def ptr_file_id(value):
    if isinstance(value, dict):
        return int(value.get("m_FileID", 0) or 0)
    return int(getattr(value, "m_FileID", 0) or 0)


def vector(value):
    value = plain(value)
    if isinstance(value, dict):
        return {k: value.get(k) for k in ("x", "y", "z", "w") if k in value}
    return value


def camera_summary(asset, obj, data, go_names, transform_by_go, transforms, camera_index):
    go_ref = field(data, "m_GameObject", "m_GameObject")
    go_id = ptr_id(go_ref)
    go_name = go_names.get((asset, go_id), "")
    transform = transform_by_go.get((asset, go_id))
    hierarchy = []
    seen = set()
    current = transform
    for _ in range(8):
        if not current or current in seen:
            break
        seen.add(current)
        node = transforms.get((asset, current), {})
        node_go = ptr_id(field(node, "m_GameObject"))
        hierarchy.append(go_names.get((asset, node_go), ""))
        father = ptr_id(field(node, "m_Father"))
        current = father if father else None

    near = field(data, "near clip plane", "m_NearClipPlane", default=None)
    far = field(data, "far clip plane", "m_FarClipPlane", default=None)
    fov = field(data, "field of view", "m_FieldOfView", default=None)
    target = field(data, "m_TargetTexture")
    enabled = field(data, "m_Enabled", default=None)
    warnings = []
    try:
        if near is not None and float(near) < 0.025:
            warnings.append("near_clip_very_small_review_camera_collision")
        if near is not None and far is not None and float(far) <= float(near):
            warnings.append("far_clip_not_greater_than_near_clip")
    except (TypeError, ValueError):
        pass

    return {
        "asset_file": asset,
        "path_id": int(obj.path_id),
        "gameobject_path_id": go_id,
        "gameobject": go_name,
        "hierarchy_root_to_leaf": list(reversed([x for x in hierarchy if x])),
        "enabled": enabled,
        "near_clip": near,
        "far_clip": far,
        "field_of_view": fov,
        "depth": field(data, "m_Depth", default=None),
        "culling_mask": plain(field(data, "m_CullingMask")),
        "target_texture": plain(target),
        "occlusion_culling": field(data, "m_OcclusionCulling", default=None),
        "warnings": warnings,
    }


env = UnityPy.load(str(DATA))
objects = list(env.objects)
scene_re = re.compile(r"^level\d+$", re.IGNORECASE)

go_names = {}
transform_by_go = {}
transforms = {}
scene_counts = defaultdict(Counter)
camera_records = []
light_records = []
asset_files = sorted({str(getattr(o.assets_file, "name", "")) for o in objects})

# First pass: collect scene object names and transform relationships.
for obj in objects:
    asset = str(getattr(obj.assets_file, "name", ""))
    if not scene_re.match(asset):
        continue
    if obj.type.name == "GameObject":
        data = read_fields(obj)
        go_names[(asset, int(obj.path_id))] = str(field(data, "m_Name", default="") or "")
    elif obj.type.name in ("Transform", "RectTransform"):
        data = read_fields(obj)
        go_id = ptr_id(field(data, "m_GameObject"))
        transforms[(asset, int(obj.path_id))] = data
        if go_id:
            transform_by_go[(asset, go_id)] = int(obj.path_id)

# Second pass: scene statistics, camera settings, and lights.
for obj in objects:
    asset = str(getattr(obj.assets_file, "name", ""))
    if not scene_re.match(asset):
        continue
    scene_counts[asset][obj.type.name] += 1
    if obj.type.name == "Camera":
        camera_records.append(camera_summary(
            asset, obj, read_fields(obj), go_names, transform_by_go,
            transforms, len(camera_records)
        ))
    elif obj.type.name == "Light":
        data = read_fields(obj)
        go_id = ptr_id(field(data, "m_GameObject"))
        light_records.append({
            "asset_file": asset,
            "path_id": int(obj.path_id),
            "gameobject_path_id": go_id,
            "gameobject": go_names.get((asset, go_id), ""),
            "enabled": field(data, "m_Enabled", default=None),
            "light_type": field(data, "m_Type", default=None),
            "intensity": field(data, "m_Intensity", default=None),
            "range": field(data, "m_Range", default=None),
            "shadows": field(data, "m_Shadows", default=None),
            "color": plain(field(data, "m_Color")),
        })

# Inspect PlayerSettings splash configuration without changing the APK.
player_splash = []
for obj in objects:
    if obj.type.name != "PlayerSettings":
        continue
    try:
        settings = obj.parse_as_object()
        logo_entries = []
        for entry in list(getattr(settings, "m_SplashScreenLogos", []) or []):
            pointer = getattr(entry, "logo", None)
            target_name = ""
            target_type = ""
            target_error = ""
            if pointer is not None:
                try:
                    target_reader = pointer.deref()
                    target = target_reader.read()
                    target_name = str(getattr(target, "m_Name", "") or getattr(target, "name", "") or "")
                    target_type = type(target).__name__
                    try:
                        sprite_data = getattr(target, "m_RD", None)
                        texture_pointer = getattr(sprite_data, "texture", None)
                        if texture_pointer is not None:
                            texture = texture_pointer.deref_parse_as_object()
                            preview = getattr(texture, "image", None)
                        else:
                            preview = getattr(target, "image", None)
                        if preview is not None:
                            preview_dir = OUT / "splash-previews"
                            preview_dir.mkdir(parents=True, exist_ok=True)
                            path_id = int(getattr(pointer, "m_PathID", 0) or 0)
                            preview_path = preview_dir / f"splash-logo-{path_id}.png"
                            preview.save(preview_path)
                    except Exception:
                        pass
                except Exception as exc:
                    target_error = str(exc)[:200]
            logo_entries.append({
                "duration_seconds": float(getattr(entry, "duration", 0.0) or 0.0),
                "pointer": plain(pointer),
                "resolved_name": target_name,
                "resolved_type": target_type,
                "resolve_error": target_error,
            })
        unity_logo_pointer = getattr(settings, "m_UnitySplashLogo", None)
        unity_logo_name = ""
        unity_logo_type = ""
        unity_logo_error = ""
        if unity_logo_pointer is not None:
            try:
                unity_logo = unity_logo_pointer.deref_parse_as_object()
                unity_logo_name = str(getattr(unity_logo, "m_Name", "") or getattr(unity_logo, "name", "") or "")
                unity_logo_type = type(unity_logo).__name__
            except Exception as exc:
                unity_logo_error = str(exc)[:200]
        player_splash.append({
            "show_unity_splash_screen": bool(getattr(settings, "m_ShowUnitySplashScreen", False)),
            "show_unity_splash_logo": bool(getattr(settings, "m_ShowUnitySplashLogo", False)),
            "splash_logo_count": len(logo_entries),
            "splash_logos": logo_entries,
            "unity_splash_logo_pointer": plain(unity_logo_pointer),
            "unity_splash_logo_resolved_name": unity_logo_name,
            "unity_splash_logo_resolved_type": unity_logo_type,
            "unity_splash_logo_resolve_error": unity_logo_error,
        })
    except Exception as exc:
        player_splash.append({"error": str(exc)[:500]})

# Inspect known fog-repair quads, fog exclusion volumes, and their render materials.
object_lookup = {
    (str(getattr(obj.assets_file, "name", "")), int(obj.path_id)): obj
    for obj in objects
}
renderer_by_go = defaultdict(list)
meshfilter_by_go = defaultdict(list)
transform_by_go_object = {}
for obj in objects:
    asset = str(getattr(obj.assets_file, "name", ""))
    if not scene_re.match(asset):
        continue
    try:
        data = read_fields(obj)
        go_id = ptr_id(field(data, "m_GameObject"))
        if not go_id:
            continue
        if obj.type.name == "MeshRenderer":
            renderer_by_go[(asset, go_id)].append((obj, data))
        elif obj.type.name == "MeshFilter":
            meshfilter_by_go[(asset, go_id)].append((obj, data))
        elif obj.type.name in ("Transform", "RectTransform"):
            transform_by_go_object[(asset, ptr_id(field(data, "m_GameObject")))] = data
    except Exception:
        pass

def resolved_object(pointer):
    if pointer is None:
        return None
    try:
        return pointer.deref_parse_as_object()
    except Exception:
        try:
            return pointer.deref().read()
        except Exception:
            return None

special_renderers = []
special_fog_objects = []
for (asset, go_id), go_name in go_names.items():
    if not (go_name.startswith("Quad_FixFogRendering") or go_name in ("FogExclusionZone", "Foggy", "SpookyFog")):
        continue
    transform = transform_by_go_object.get((asset, go_id), {})
    record = {
        "asset_file": asset,
        "gameobject_path_id": go_id,
        "gameobject": go_name,
        "local_position": vector(field(transform, "m_LocalPosition")),
        "local_rotation": vector(field(transform, "m_LocalRotation")),
        "local_scale": vector(field(transform, "m_LocalScale")),
        "renderers": [],
        "mesh_filters": [],
        "components": [],
    }
    if go_name.startswith("Quad_FixFogRendering"):
        for renderer_obj, renderer_data in renderer_by_go.get((asset, go_id), []):
            materials = []
            for pointer in list(field(renderer_data, "m_Materials", default=[]) or []):
                material = resolved_object(pointer)
                if material is None:
                    materials.append({"pointer": plain(pointer), "resolve_error": True})
                    continue
                shader_pointer = getattr(material, "m_Shader", None)
                shader = resolved_object(shader_pointer)
                materials.append({
                    "name": str(getattr(material, "m_Name", "") or ""),
                    "shader_name": str(getattr(shader, "m_Name", "") or "") if shader is not None else "",
                    "shader_pointer": plain(shader_pointer),
                    "render_queue": getattr(material, "m_CustomRenderQueue", None),
                    "pointer": plain(pointer),
                })
            record["renderers"].append({
                "path_id": int(renderer_obj.path_id),
                "enabled": field(renderer_data, "m_Enabled"),
                "cast_shadows": field(renderer_data, "m_CastShadows"),
                "receive_shadows": field(renderer_data, "m_ReceiveShadows"),
                "materials": materials,
            })
        for filter_obj, filter_data in meshfilter_by_go.get((asset, go_id), []):
            pointer = field(filter_data, "m_Mesh")
            mesh = resolved_object(pointer)
            submeshes = list(getattr(mesh, "m_SubMeshes", []) or []) if mesh is not None else []
            bounds = getattr(mesh, "m_LocalAABB", None) if mesh is not None else None
            record["mesh_filters"].append({
                "path_id": int(filter_obj.path_id),
                "mesh_pointer": plain(pointer),
                "mesh_name": str(getattr(mesh, "m_Name", "") or "") if mesh is not None else "",
                "vertex_count": int(getattr(mesh, "m_VertexCount", 0) or 0) if mesh is not None else None,
                "submesh_count": len(submeshes),
                "index_count": sum(int(getattr(x, "indexCount", 0) or 0) for x in submeshes),
                "bounds": plain(bounds),
            })
        special_renderers.append(record)
    else:
        # Keep the fog-volume object transform and activity status for focused diagnosis.
        special_fog_objects.append(record)

scenes = []
for asset in sorted(scene_counts, key=lambda s: (int(re.search(r"\d+", s).group()) if re.search(r"\d+", s) else 9999, s)):
    counts = scene_counts[asset]
    scenes.append({
        "scene_asset": asset,
        "gameobjects": counts.get("GameObject", 0),
        "transforms": counts.get("Transform", 0) + counts.get("RectTransform", 0),
        "cameras": counts.get("Camera", 0),
        "lights": counts.get("Light", 0),
        "mesh_renderers": counts.get("MeshRenderer", 0),
        "mesh_filters": counts.get("MeshFilter", 0),
        "colliders": sum(v for k, v in counts.items() if k.endswith("Collider")),
        "monobehaviours": counts.get("MonoBehaviour", 0),
        "type_counts": dict(sorted(counts.items())),
    })

summary = {
    "unitypy_version": getattr(UnityPy, "__version__", "unknown"),
    "asset_file_count": len(asset_files),
    "scene_asset_count": len(scenes),
    "scene_assets": scenes,
    "camera_count": len(camera_records),
    "cameras": camera_records,
    "light_count": len(light_records),
    "player_splash_settings": player_splash,
    "special_renderers": special_renderers,
    "special_fog_objects": special_fog_objects,
    "lights": light_records,
    "runtime_test_performed": False,
    "limitations": [
        "This is a read-only inspection of serialized Unity assets, not a live game launch.",
        "Runtime-created controls and camera behaviours may not be represented as scene components.",
        "Camera warnings are triage hints only; a physical-device reproduction is needed before changing values.",
    ],
}
(OUT / "scene-camera-audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

lines = [
    "# Unity scene and camera audit",
    "",
    f"- UnityPy: {summary['unitypy_version']}",
    f"- Serialized scene assets: {len(scenes)}",
    f"- Camera components: {len(camera_records)}",
    f"- Light components: {len(light_records)}",
    "- Runtime execution: **not performed**",
    "",
    "| Scene asset | GameObjects | Cameras | Lights | Mesh renderers | Colliders | MonoBehaviours |",
    "|---|---:|---:|---:|---:|---:|---:|",
]
for scene in scenes:
    lines.append(
        f"| {scene['scene_asset']} | {scene['gameobjects']} | {scene['cameras']} | "
        f"{scene['lights']} | {scene['mesh_renderers']} | {scene['colliders']} | "
        f"{scene['monobehaviours']} |"
    )
lines += ["", "## Camera triage", ""]
for camera in camera_records:
    path = " / ".join(camera["hierarchy_root_to_leaf"]) or camera["gameobject"] or "(unnamed)"
    warning = ", ".join(camera["warnings"]) if camera["warnings"] else "none"
    lines.append(
        f"- {camera['asset_file']} pathID {camera['path_id']}: {path}; "
        f"near={camera['near_clip']}, far={camera['far_clip']}, "
        f"FOV={camera['field_of_view']}; warnings={warning}"
    )
lines += [
    "",
    "## Limitations",
    "",
    *[f"- {item}" for item in summary["limitations"]],
]
(OUT / "scene-camera-audit.md").write_text("\n".join(lines) + "\n")
print(json.dumps({
    "scene_assets": len(scenes),
    "cameras": len(camera_records),
    "lights": len(light_records),
    "json": "output/scene-camera-audit.json",
    "markdown": "output/scene-camera-audit.md",
}, indent=2))
