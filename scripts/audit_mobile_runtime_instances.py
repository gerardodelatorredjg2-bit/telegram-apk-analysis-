#!/usr/bin/env python3
"""Audit whether mobile runtime MonoBehaviours are serialized into the original APK.

Read-only. Resolves IL2CPP MonoBehaviour script IDs using UnityPy's generated
typetree and records owner GameObjects, enabled/active state, and scene assets.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

ROOT = Path("work/apk")
DATA = ROOT / "assets/bin/Data"
OUT = Path("output/mobile-runtime-instance-audit.json")
TARGETS = {
    "MobileTouchControls", "MobileGameViewFit", "MobileTouchLook",
    "OfflineFullGameBootstrap", "OfflineOriginalMainMenu",
    "MobilePerformanceMode", "MobileControlsLayoutEditor",
}
PREFIXES = ("MobileTouch", "MobileGameViewFit", "OfflineFullGameBootstrap",
            "OfflineOriginalMainMenu", "MobilePerformanceMode")
def plain(x):
    if x is None or isinstance(x, (str, int, float, bool)): return x
    if hasattr(x, "m_PathID"): return int(x.m_PathID)
    if isinstance(x, (list, tuple)): return [plain(v) for v in x[:80]]
    if isinstance(x, dict): return {str(k): plain(v) for k,v in list(x.items())[:80]}
    return str(x)[:240]

env = UnityPy.load(str(DATA))
unity_version = next((str(getattr(o.assets_file, "unity_version", "")) for o in env.objects
                      if getattr(o.assets_file, "unity_version", "")), "")
if not unity_version: raise RuntimeError("Unity version not found in serialized assets")
generator = TypeTreeGenerator(unity_version)
generator.load_il2cpp((ROOT / "lib/arm64-v8a/libil2cpp.so").read_bytes(),
                      (DATA / "Managed/Metadata/global-metadata.dat").read_bytes())
env.typetree_generator = generator

scripts, objects = {}, {}
for o in env.objects:
    if o.type.name == "MonoScript":
        try:
            d=o.read_typetree()
            scripts[int(o.path_id)] = {
                "class": str(d.get("m_ClassName","") or ""),
                "namespace": str(d.get("m_Namespace","") or ""),
                "assembly": str(d.get("m_AssemblyName","") or ""),
            }
        except Exception: pass
    elif o.type.name == "GameObject":
        try:
            d=o.read_typetree()
            objects[int(o.path_id)] = {
                "name": str(d.get("m_Name","") or ""),
                "active": bool(d.get("m_IsActive", True)),
            }
        except Exception: pass

components=[]
counts=Counter()
parse_errors=[]
for o in env.objects:
    if o.type.name != "MonoBehaviour": continue
    try:
        h=o.parse_monobehaviour_head()
        sid=int(getattr(getattr(h,"m_Script",None),"m_PathID",0) or 0)
        gid=int(getattr(getattr(h,"m_GameObject",None),"m_PathID",0) or 0)
        s=scripts.get(sid,{})
        cls=s.get("class","")
        ns=s.get("namespace","")
        assembly=s.get("assembly","")
        if not (cls in TARGETS or any(cls.startswith(p) for p in PREFIXES)): continue
        full=f"{ns}.{cls}" if ns else cls
        fields={}
        try:
            node=generator.get_nodes_up(assembly, full)
            if node: fields=o.read_typetree(nodes=node)
        except Exception as e:
            parse_errors.append({"class":full,"error":str(e)[:300]})
        go=objects.get(gid,{})
        row={
            "class":full, "assembly":assembly,
            "asset_file":str(getattr(o.assets_file,"name","")),
            "component_path_id":int(o.path_id),
            "gameobject_path_id":gid, "gameobject":go.get("name",""),
            "gameobject_active":go.get("active"),
            "enabled":plain(fields.get("m_Enabled")) if fields else None,
            "serialized_fields": {k:plain(v) for k,v in fields.items()
                                  if k in {"m_Enabled","m_EditorHideFlags","m_Name","m_ExecutionOrder"}},
        }
        components.append(row); counts[full]+=1
    except Exception as e:
        parse_errors.append({"path_id":int(o.path_id),"error":str(e)[:300]})

report={
    "unity_version":unity_version,
    "unitypy_version":getattr(UnityPy,"__version__","unknown"),
    "mono_script_count":len(scripts),
    "matching_script_definitions":[{"class":f'{s["namespace"]}.{s["class"]}'.strip("."),
                                    "assembly":s["assembly"],"path_id":pid}
                                   for pid,s in scripts.items()
                                   if s["class"] in TARGETS or any(s["class"].startswith(p) for p in PREFIXES)],
    "serialized_component_counts":dict(counts),
    "serialized_components":components,
    "parse_errors":parse_errors[:200],
    "conclusion_note":"A class present in IL2CPP metadata does not prove a scene instance. This report checks serialized MonoBehaviour instances in the original APK; runtime-created instances still require call-site analysis or an Android device test."
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps({k:report[k] for k in ("unity_version","mono_script_count","matching_script_definitions","serialized_component_counts","serialized_components","parse_errors","conclusion_note")},indent=2,ensure_ascii=False))
