#!/usr/bin/env python3
"""Read-only check for serialized mobile controls and offline bootstrap instances."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import UnityPy

DATA=Path("work/apk/assets/bin/Data")
OUT=Path("output/mobile-runtime-instance-audit.json")
PREFIXES=("MobileTouch","MobileGameViewFit","OfflineFullGameBootstrap","OfflineOriginalMainMenu","MobilePerformanceMode")
TARGETS={"MobileTouchControls","MobileGameViewFit","OfflineFullGameBootstrap","OfflineOriginalMainMenu","MobilePerformanceMode"}
def get_script(ref):
    if ref is None: return None
    try: return ref.deref_parse_as_object()
    except Exception: return None
def get_owner(ref):
    if ref is None: return None
    try: return ref.deref_parse_as_object()
    except Exception: return None
env=UnityPy.load(str(DATA))
counts=Counter()
components=[]
errors=[]
scripts=set()
for obj in env.objects:
    if obj.type.name!="MonoBehaviour": continue
    try:
        head=obj.parse_monobehaviour_head()
        script=get_script(getattr(head,"m_Script",None))
        if script is None: continue
        cls=str(getattr(script,"m_ClassName","") or "")
        ns=str(getattr(script,"m_Namespace","") or "")
        assembly=str(getattr(script,"m_AssemblyName","") or "")
        if not (cls in TARGETS or any(cls.startswith(p) for p in PREFIXES)): continue
        owner=get_owner(getattr(head,"m_GameObject",None))
        row={
            "class":f"{ns}.{cls}".strip("."),
            "assembly":assembly,
            "asset_file":str(getattr(obj.assets_file,"name","")),
            "component_path_id":int(obj.path_id),
            "gameobject_path_id":int(getattr(getattr(head,"m_GameObject",None),"m_PathID",0) or 0),
            "gameobject":str(getattr(owner,"m_Name","") or "") if owner else "",
            "gameobject_active":bool(getattr(owner,"m_IsActive",True)) if owner else None,
            "enabled":bool(getattr(head,"m_Enabled",True)),
        }
        components.append(row)
        counts[row["class"]]+=1
        scripts.add((row["class"],assembly))
    except Exception as e:
        errors.append({"path_id":int(obj.path_id),"error":str(e)[:300]})
report={
    "unitypy_version":getattr(UnityPy,"__version__","unknown"),
    "mono_behaviour_instances_scanned":sum(1 for o in env.objects if o.type.name=="MonoBehaviour"),
    "matching_script_definitions":[{"class":c,"assembly":a} for c,a in sorted(scripts)],
    "serialized_component_counts":dict(counts),
    "serialized_components":components,
    "parse_errors":errors[:200],
    "note":"This is a static inventory of serialized instances. Runtime-created components still require examining their callers or testing the app on an Android device."
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
