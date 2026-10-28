#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 Blender 场景扫描器 (blender_scanner.py)
在 Blender 后台执行，扫描任意 .blend 文件的集合、集合实例 (Collection Instances)、独立网格、材质与包围盒信息。
"""

import bpy
from mathutils import Vector
import json
import os
import re
import sys
import math


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    out_json = "/tmp/blender_scene_scan.json"
    name_regex = None
    col_filter = None
    i = 0
    while i < len(argv):
        if argv[i] == "--output" and i + 1 < len(argv):
            out_json = argv[i + 1]
            i += 2
        elif argv[i] == "--name-regex" and i + 1 < len(argv):
            name_regex = argv[i + 1]
            i += 2
        elif argv[i] == "--collection" and i + 1 < len(argv):
            col_filter = argv[i + 1]
            i += 2
        else:
            i += 1
    return out_json, name_regex, col_filter


def get_world_bbox(obj):
    if not hasattr(obj, "bound_box") or obj.bound_box is None:
        loc = obj.matrix_world.translation
        return [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)], [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)]
    mw = obj.matrix_world
    pts = [mw @ Vector(corner) for corner in obj.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)], [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)]


def scan_scene(name_regex=None, col_filter=None):
    pat = re.compile(name_regex) if name_regex else None

    collections_info = []
    for col in bpy.data.collections:
        collections_info.append({
            "name": col.name,
            "direct_objects_count": len(col.objects),
            "all_objects_count": len(col.all_objects),
            "children_collections": [c.name for c in col.children]
        })

    instances_info = []
    meshes_info = []
    other_objects_count = {}

    for obj in bpy.context.scene.objects:
        if pat and not pat.search(obj.name):
            continue
        user_cols = [c.name for c in obj.users_collection]
        if col_filter and col_filter not in user_cols:
            continue

        loc, rot, sca = obj.matrix_world.decompose()
        eul = rot.to_euler('XYZ')

        if obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION' and obj.instance_collection is not None:
            icol = obj.instance_collection
            sub_meshes = [o for o in icol.all_objects if o.type == 'MESH' and o.data is not None]
            sub_fonts = [o for o in icol.all_objects if o.type == 'FONT']
            total_polys = sum(len(o.data.polygons) for o in sub_meshes)
            mats = sorted({m.name for o in sub_meshes for m in o.data.materials if m is not None})
            instances_info.append({
                "name": obj.name,
                "instance_collection": icol.name,
                "parent_collections": user_cols,
                "location_m": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
                "rotation_euler_deg": [round(math.degrees(eul.x), 3), round(math.degrees(eul.y), 3), round(math.degrees(eul.z), 3)],
                "scale": [round(sca.x, 4), round(sca.y, 4), round(sca.z, 4)],
                "sub_mesh_objects": len(sub_meshes),
                "sub_font_objects": len(sub_fonts),
                "total_polygons": total_polys,
                "materials": mats
            })
        elif obj.type == 'MESH' and obj.data is not None:
            bmin, bmax = get_world_bbox(obj)
            dims = [round(bmax[i] - bmin[i], 3) for i in range(3)]
            mats = [m.name for m in obj.data.materials if m is not None]
            meshes_info.append({
                "name": obj.name,
                "parent_collections": user_cols,
                "location_m": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
                "rotation_euler_deg": [round(math.degrees(eul.x), 3), round(math.degrees(eul.y), 3), round(math.degrees(eul.z), 3)],
                "scale": [round(sca.x, 4), round(sca.y, 4), round(sca.z, 4)],
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "bbox_min_m": bmin,
                "bbox_max_m": bmax,
                "dimensions_m": dims,
                "materials": mats
            })
        else:
            other_objects_count[obj.type] = other_objects_count.get(obj.type, 0) + 1

    all_materials = [m.name for m in bpy.data.materials]
    scn = bpy.context.scene
    report = {
        "blend_filepath": bpy.data.filepath,
        "blender_version": bpy.app.version_string,
        "scene_name": scn.name,
        "unit_system": scn.unit_settings.system,
        "unit_scale_length": round(scn.unit_settings.scale_length, 6),
        "summary": {
            "total_collections": len(collections_info),
            "collection_instances_count": len(instances_info),
            "standalone_meshes_count": len(meshes_info),
            "other_objects_by_type": other_objects_count,
            "total_materials": len(all_materials)
        },
        "collections": collections_info,
        "collection_instances": instances_info,
        "standalone_meshes": meshes_info,
        "materials": all_materials
    }
    return report


if __name__ == "__main__":
    out_path, name_regex, col_filter = parse_args()
    rep = scan_scene(name_regex=name_regex, col_filter=col_filter)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"[B2GE_SCANNER] 扫描完成 -> {out_path} (实例:{rep['summary']['collection_instances_count']}, 网格:{rep['summary']['standalone_meshes_count']})")
