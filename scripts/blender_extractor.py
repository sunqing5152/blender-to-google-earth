#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 Blender 建筑提取、DAE 导出与道路原始面片提取器 (blender_extractor.py)
仅依赖 Blender 原生自带模块 (bpy, bmesh, mathutils, json)，完全由外部 JSON 任务配置驱动。
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import json
import math
import os
import re
import sys

DEFAULT_MAT_PALETTE = {
    "plaster_white": ("tex_plaster_white.png", (0.93, 0.91, 0.86), "stucco"),
    "wood_teak":     ("tex_wood_teak.png",     (0.42, 0.22, 0.10), "wood"),
    "solar_panel":   ("tex_solar_panel.png",   (0.08, 0.11, 0.16), "solar"),
    "glass_arch":    ("tex_glass_arch.png",    (0.24, 0.38, 0.52), "glass"),
    "metal_dark":    ("tex_metal_dark.png",    (0.18, 0.20, 0.22), "metal"),
    "roof_grey":     ("tex_roof_grey.png",     (0.70, 0.69, 0.64), "stucco"),
    "stone_paving":  ("tex_stone_paving.png",  (0.72, 0.71, 0.67), "paver"),
    "sandstone":     ("tex_sandstone.png",     (0.83, 0.78, 0.69), "paver"),
    "asphalt_road":  ("tex_asphalt_road.png",  (0.23, 0.24, 0.26), "asphalt"),
    "road_marking":  ("tex_road_marking.png",  (0.95, 0.95, 0.95), "flat"),
    "plinth_base":   ("tex_plinth_base.png",   (0.38, 0.38, 0.36), "stucco"),
}


def generate_procedural_textures(models_dir, palette=None):
    """在 models_dir 下生成 128x128 确定性建筑材质贴图 PNG"""
    palette = palette or DEFAULT_MAT_PALETTE
    size = 128
    tex_paths = {}
    os.makedirs(models_dir, exist_ok=True)
    for key, (fname, (br, bg, bb), style) in palette.items():
        fpath = os.path.join(models_dir, fname)
        tex_paths[key] = fpath
        img = bpy.data.images.get(fname) or bpy.data.images.new(fname, width=size, height=size)
        pixels = [1.0] * (size * size * 4)
        for y in range(size):
            for x in range(size):
                idx = (y * size + x) * 4
                h = ((x * 374761393 + y * 668265263) & 0xFFFFFFFF) / 4294967295.0
                delta = (h - 0.5) * 0.04
                r, g, b = br + delta, bg + delta, bb + delta
                if style == "wood":
                    stripe = math.sin(y * 0.45 + math.sin(x * 0.1) * 1.5) * 0.045
                    r, g, b = br + stripe + delta * 0.5, bg + stripe * 0.7 + delta * 0.5, bb + stripe * 0.4
                elif style == "solar":
                    if (x % 32 < 2) or (y % 16 < 1):
                        r, g, b = 0.22, 0.27, 0.34
                elif style == "glass":
                    grad = (y / float(size)) * 0.14 - 0.07
                    diag = 0.05 if ((x + y) % 64 < 6) else 0.0
                    r, g, b = br + grad + diag, bg + grad + diag, bb + grad * 1.2 + diag
                elif style == "paver":
                    if (x % 32 == 0) or (y % 32 == 0):
                        r, g, b = br - 0.07, bg - 0.07, bb - 0.07
                elif style == "asphalt":
                    delta = (h - 0.5) * 0.07
                    r, g, b = br + delta, bg + delta, bb + delta
                pixels[idx] = max(0.0, min(1.0, r))
                pixels[idx + 1] = max(0.0, min(1.0, g))
                pixels[idx + 2] = max(0.0, min(1.0, b))
                pixels[idx + 3] = 1.0
        img.pixels[:] = pixels
        img.filepath_raw = fpath
        img.file_format = 'PNG'
        img.save()
    return tex_paths


def classify_material_name(mat_name, custom_rules=None):
    if not mat_name:
        return "plaster_white"
    n = mat_name.lower()
    if custom_rules:
        for target_key, keywords in custom_rules.items():
            if any(k.lower() in n for k in keywords):
                return target_key
    if any(k in n for k in ["光伏", "solar"]):
        return "solar_panel"
    if any(k in n for k in ["玻璃", "视线", "glass", "railglass", "window"]):
        return "glass_arch"
    if any(k in n for k in ["木", "百叶", "timber", "deck", "wood"]):
        return "wood_teak"
    if any(k in n for k in ["金属", "框", "frame", "metal", "fascia", "black", "brick", "设备", "dark"]):
        return "metal_dark"
    if any(k in n for k in ["沥青", "road", "asphalt"]):
        return "asphalt_road"
    if any(k in n for k in ["标线", "虚线", "白线", "marking"]):
        return "road_marking"
    if any(k in n for k in ["砂石", "floor", "coping", "paver", "sand"]):
        return "sandstone"
    if any(k in n for k in ["铺装", "步道", "石", "stone", "sidewalk"]):
        return "stone_paving"
    if any(k in n for k in ["屋面", "roof"]):
        return "roof_grey"
    return "plaster_white"


def build_textured_materials(tex_paths, palette=None):
    palette = palette or DEFAULT_MAT_PALETTE
    bl_mats = {}
    for key, (fname, rgb, _) in palette.items():
        mat_name = f"GE_Mat_{key}"
        mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        mat.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
        nt = mat.node_tree
        nt.nodes.clear()
        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        bsdf.inputs["Roughness"].default_value = 0.25 if key == "glass_arch" else 0.65
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        img = bpy.data.images.get(fname) or bpy.data.images.load(tex_paths[key])
        tex_node.image = img
        nt.links.new(bsdf.inputs["Base Color"], tex_node.outputs["Color"])
        nt.links.new(out_node.inputs["Surface"], bsdf.outputs["BSDF"])
        bl_mats[key] = mat
    return bl_mats


def add_box_plinth(bm, min_x, max_x, min_y, max_y, z_top, z_bottom, mat_idx):
    verts = [
        bm.verts.new((min_x, min_y, z_bottom)),
        bm.verts.new((max_x, min_y, z_bottom)),
        bm.verts.new((max_x, max_y, z_bottom)),
        bm.verts.new((min_x, max_y, z_bottom)),
        bm.verts.new((min_x, min_y, z_top)),
        bm.verts.new((max_x, min_y, z_top)),
        bm.verts.new((max_x, max_y, z_top)),
        bm.verts.new((min_x, max_y, z_top)),
    ]
    quads = [
        (verts[0], verts[1], verts[5], verts[4]),
        (verts[1], verts[2], verts[6], verts[5]),
        (verts[2], verts[3], verts[7], verts[6]),
        (verts[3], verts[0], verts[4], verts[7]),
        (verts[4], verts[5], verts[6], verts[7]),
    ]
    for q in quads:
        f = bm.faces.new(q)
        f.material_index = mat_idx


def postprocess_dae_xml(dae_path):
    """规范化 DAE 贴图相对路径并注入 Google Earth 双面渲染标记"""
    with open(dae_path, "r", encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(
        r"<init_from>[^<]*?(tex_[a-zA-Z0-9_]+\.png)</init_from>",
        r"<init_from>\1</init_from>",
        txt
    )
    extra_block = (
        "      </profile_COMMON>\n"
        "      <extra><technique profile=\"GOOGLEEARTH\">"
        "<double_sided>1</double_sided></technique></extra>"
    )
    if "<double_sided>1</double_sided>" not in txt:
        txt = txt.replace("      </profile_COMMON>", extra_block)
    with open(dae_path, "w", encoding="utf-8") as f:
        f.write(txt)


def finalize_bmesh_and_export_dae(bm, used_mat_keys, bl_mats, obj_name, dae_path):
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    uv_layer = bm.loops.layers.uv.verify()
    scale_uv = 2.5
    for f in bm.faces:
        no = f.normal
        ax, ay, az = abs(no.x), abs(no.y), abs(no.z)
        for loop in f.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                u, v = co.x / scale_uv, co.y / scale_uv
            elif ax >= ay:
                u, v = co.y / scale_uv, co.z / scale_uv
            else:
                u, v = co.x / scale_uv, co.z / scale_uv
            loop[uv_layer].uv = (u, v)

    me = bpy.data.meshes.new(obj_name + "_mesh")
    bm.to_mesh(me)
    if len(me.uv_layers) > 0:
        me.uv_layers[0].name = "UVMap"
    for k in used_mat_keys:
        me.materials.append(bl_mats[k])

    obj = bpy.data.objects.new(obj_name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.collada_export(
        filepath=dae_path,
        selected=True,
        triangulate=False,
        use_texture_copies=False
    )
    postprocess_dae_xml(dae_path)
    return obj


def compute_objects_local_bbox(objs):
    xs, ys, zs = [], [], []
    for o in objs:
        if o.type == 'MESH' and o.data is not None and len(o.data.vertices) > 0:
            mw = o.matrix_world
            for corner in o.bound_box:
                p = mw @ Vector(corner)
                xs.append(p.x)
                ys.append(p.y)
                zs.append(p.z)
    if not xs:
        return (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def extract_single_building(b_cfg, models_dir, bl_mats, rot_gamma_mat, mat_rules=None):
    """
    通用单个建筑提取：支持 Collection Instance 或 普通 Mesh 对象 / 集合。
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    export_id = b_cfg["id"]
    source_name = b_cfg["source_object"]
    exclude_kws = b_cfg.get("exclude_subobject_keywords", [])
    alt_rel = float(b_cfg.get("altitude_rel_ground_m", 0.0))
    group_folder = b_cfg.get("folder", "01_建筑模型组")
    desc_title = b_cfg.get("title", export_id)

    src_obj = bpy.data.objects.get(source_name)
    src_col = bpy.data.collections.get(source_name) if src_obj is None else None
    if src_obj is None and src_col is None:
        raise ValueError(f"在 Blender 场景中找不到目标对象或集合: {source_name}")

    is_instance = (src_obj is not None and src_obj.type == 'EMPTY' and src_obj.instance_type == 'COLLECTION' and src_obj.instance_collection is not None)

    if is_instance:
        asset_col = src_obj.instance_collection
        sub_objs = [o for o in asset_col.all_objects if o.type in {'MESH', 'FONT'}]
        inst_mw = src_obj.matrix_world
        if "local_center" in b_cfg and b_cfg["local_center"] is not None:
            lc = Vector(b_cfg["local_center"])
        else:
            bx0, bx1, by0, by1, bz0, _ = compute_objects_local_bbox(sub_objs)
            lc = Vector((0.5 * (bx0 + bx1), 0.5 * (by0 + by1), bz0))
        world_center = inst_mw @ lc
        base_mat = rot_gamma_mat @ Matrix.Translation(-world_center) @ inst_mw
        loc, rot, sca = inst_mw.decompose()
        eul = rot.to_euler('XYZ')
        asset_col_name = asset_col.name
    elif src_obj is not None:
        sub_objs = [src_obj] + [c for c in src_obj.children_recursive if c.type in {'MESH', 'FONT'}]
        bx0, bx1, by0, by1, bz0, _ = compute_objects_local_bbox(sub_objs)
        if "local_center" in b_cfg and b_cfg["local_center"] is not None:
            world_center = src_obj.matrix_world @ Vector(b_cfg["local_center"])
        else:
            world_center = Vector((0.5 * (bx0 + bx1), 0.5 * (by0 + by1), bz0))
        base_mat = rot_gamma_mat @ Matrix.Translation(-world_center)
        loc, rot, sca = src_obj.matrix_world.decompose()
        eul = rot.to_euler('XYZ')
        asset_col_name = src_obj.users_collection[0].name if src_obj.users_collection else "SceneCollection"
    else:
        sub_objs = [o for o in src_col.all_objects if o.type in {'MESH', 'FONT'}]
        bx0, bx1, by0, by1, bz0, _ = compute_objects_local_bbox(sub_objs)
        world_center = Vector((0.5 * (bx0 + bx1), 0.5 * (by0 + by1), bz0))
        base_mat = rot_gamma_mat @ Matrix.Translation(-world_center)
        loc, eul, sca = world_center, Vector((0.0, 0.0, 0.0)), Vector((1.0, 1.0, 1.0))
        asset_col_name = src_col.name

    bm = bmesh.new()
    used_mat_keys = []
    mat_key_to_idx = {}

    def get_mat_idx(m_key):
        if m_key not in mat_key_to_idx:
            mat_key_to_idx[m_key] = len(used_mat_keys)
            used_mat_keys.append(m_key)
        return mat_key_to_idx[m_key]

    orig_obj_count = 0
    kept_obj_count = 0
    for o in sub_objs:
        orig_obj_count += 1
        if exclude_kws and any(kw in o.name for kw in exclude_kws):
            continue
        if o.type == 'MESH' and o.data is not None:
            tmp = bmesh.new()
            tmp.from_mesh(o.data)
        elif o.type == 'FONT':
            if any(kw in o.name for kw in exclude_kws) or "字后发光层" in o.name:
                continue
            o.data.resolution_u = 2
            depsgraph.update()
            eval_o = o.evaluated_get(depsgraph)
            me_font = eval_o.to_mesh()
            if me_font is None or len(me_font.polygons) == 0:
                eval_o.to_mesh_clear()
                continue
            tmp = bmesh.new()
            tmp.from_mesh(me_font)
            eval_o.to_mesh_clear()
            bmesh.ops.remove_doubles(tmp, verts=tmp.verts[:], dist=0.002)
            bmesh.ops.dissolve_limit(tmp, angle_limit=math.radians(5.0), verts=tmp.verts[:], edges=tmp.edges[:])
        else:
            continue

        kept_obj_count += 1
        xform = base_mat @ o.matrix_world
        tmp.transform(xform)
        mats = o.data.materials if hasattr(o.data, "materials") else []
        for f in tmp.faces:
            orig_m = mats[f.material_index] if (len(mats) > 0 and f.material_index < len(mats)) else None
            m_key = classify_material_name(orig_m.name if orig_m else "", mat_rules)
            if o.type == 'FONT':
                m_key = "road_marking"
            f.material_index = get_mat_idx(m_key)

        me_tmp = bpy.data.meshes.new("tmp_part")
        tmp.to_mesh(me_tmp)
        tmp.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)

    plinth_bounds = b_cfg.get("plinth_bounds")
    auto_plinth = b_cfg.get("auto_plinth_depth_m")
    if plinth_bounds is not None:
        px0, px1, py0, py1, pz_top, pz_bot = plinth_bounds
        tmp_p = bmesh.new()
        add_box_plinth(tmp_p, px0, px1, py0, py1, pz_top, pz_bot, get_mat_idx("plinth_base"))
        tmp_p.transform(base_mat)
        me_p = bpy.data.meshes.new("tmp_plinth")
        tmp_p.to_mesh(me_p)
        tmp_p.free()
        bm.from_mesh(me_p)
        bpy.data.meshes.remove(me_p)
    elif auto_plinth is not None and float(auto_plinth) > 0 and len(bm.verts) > 0:
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        z0 = min(zs)
        add_box_plinth(bm, min(xs) + 0.05, max(xs) - 0.05, min(ys) + 0.05, max(ys) - 0.05, z0 + 0.02, z0 - float(auto_plinth), get_mat_idx("plinth_base"))

    dae_filename = f"{export_id}.dae"
    dae_path = os.path.join(models_dir, dae_filename)
    merged_obj = finalize_bmesh_and_export_dae(bm, used_mat_keys, bl_mats, f"GE_{export_id}", dae_path)
    merged_obj.location = rot_gamma_mat @ world_center
    poly_count = len(merged_obj.data.polygons)
    bm.free()

    return merged_obj, {
        "id": export_id,
        "title": desc_title,
        "folder": group_folder,
        "blender_object": source_name,
        "asset_collection": asset_col_name,
        "dae_file": f"models/{dae_filename}",
        "orig_sub_objects": orig_obj_count,
        "kept_sub_objects": kept_obj_count,
        "exported_triangles": poly_count,
        "blender_instance_loc_m": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
        "blender_footprint_center_m": [round(world_center.x, 4), round(world_center.y, 4), round(world_center.z, 4)],
        "blender_rot_z_deg": round(math.degrees(eul.z), 4),
        "blender_scale": [round(sca.x, 4), round(sca.y, 4), round(sca.z, 4)],
        "altitude_rel_ground_m": alt_rel
    }


def extract_mesh_2d_rings(obj_name, bbox_filter=None):
    """提取网格中法线朝上的面片顶点环，返回 [(x, y), ...] 的列表供系统 Python Shapely 处理"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH' or obj.data is None:
        return []
    mw = obj.matrix_world
    me = obj.data
    rings = []
    for f in me.polygons:
        nw = mw.to_3x3() @ f.normal
        if abs(nw.z) < 0.5:
            continue
        wverts = [mw @ me.vertices[v_idx].co for v_idx in f.vertices]
        c = sum(wverts, Vector((0, 0, 0))) / len(wverts)
        if bbox_filter:
            if "x_min" in bbox_filter and c.x <= bbox_filter["x_min"]:
                continue
            if "x_max" in bbox_filter and c.x >= bbox_filter["x_max"]:
                continue
            if "y_min" in bbox_filter and c.y <= bbox_filter["y_min"]:
                continue
            if "y_max" in bbox_filter and c.y >= bbox_filter["y_max"]:
                continue
        pts = [[round(v.x, 3), round(v.y, 3)] for v in wverts]
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def extract_marking_segments(prefix_or_names, mode="centerline"):
    """从标线网格对象提取二维线段列表 [[[x1,y1],[x2,y2]], ...]"""
    segments = []
    prefixes = [prefix_or_names] if isinstance(prefix_or_names, str) else list(prefix_or_names)
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.data is None:
            continue
        if not any(obj.name == p or obj.name.startswith(p) for p in prefixes):
            continue
        mw = obj.matrix_world
        verts = [mw @ v.co for v in obj.data.vertices]
        if len(verts) < 2:
            continue
        center = sum(verts, Vector((0, 0, 0))) / len(verts)
        max_dist = 0.0
        pt_pair = (verts[0], verts[1])
        for i in range(len(verts)):
            for j in range(i + 1, len(verts)):
                d = (verts[i] - verts[j]).length
                if d > max_dist:
                    max_dist = d
                    pt_pair = (verts[i], verts[j])
        if mode == "centerline" and len(verts) >= 4:
            v_dir = (pt_pair[1] - pt_pair[0]).normalized()
            projs = [((v - center).dot(v_dir), v) for v in verts]
            projs.sort(key=lambda item: item[0])
            neg_pts = [item[1] for item in projs[:len(verts) // 2]]
            pos_pts = [item[1] for item in projs[len(verts) // 2:]]
            p_start = sum(neg_pts, Vector((0, 0, 0))) / len(neg_pts)
            p_end = sum(pos_pts, Vector((0, 0, 0))) / len(pos_pts)
            segments.append([[round(p_start.x, 3), round(p_start.y, 3)], [round(p_end.x, 3), round(p_end.y, 3)]])
        else:
            segments.append([[round(pt_pair[0].x, 3), round(pt_pair[0].y, 3)], [round(pt_pair[1].x, 3), round(pt_pair[1].y, 3)]])
    return segments


def extract_raw_roads(road_cfg):
    """根据配置提取各道路图层原始面片及标线"""
    layers_out = []
    for lyr in road_cfg.get("polygon_layers", []):
        raw_rings = []
        for src in lyr.get("source_objects", []):
            if isinstance(src, str):
                raw_rings.extend(extract_mesh_2d_rings(src))
            elif isinstance(src, dict):
                raw_rings.extend(extract_mesh_2d_rings(src["object"], bbox_filter=src.get("bbox_filter")))
        for rect in lyr.get("local_rect_transforms", []):
            ref_obj = bpy.data.objects.get(rect["reference_object"])
            if ref_obj:
                mw = ref_obj.matrix_world
                x0, x1, y0, y1 = rect["bounds"]
                pts = [mw @ Vector((x0, y0, 0.0)), mw @ Vector((x1, y0, 0.0)), mw @ Vector((x1, y1, 0.0)), mw @ Vector((x0, y1, 0.0))]
                raw_rings.append([[round(p.x, 3), round(p.y, 3)] for p in pts])
        layers_out.append({
            "id": lyr["id"],
            "name": lyr.get("name", lyr["id"]),
            "style_id": lyr.get("style_id", "roadAsphaltStyle"),
            "color_abgr": lyr.get("color_abgr", "ff3a3a3c"),
            "subtract_previous": bool(lyr.get("subtract_previous", False)),
            "raw_rings": raw_rings
        })

    markings_out = []
    for mk in road_cfg.get("marking_layers", []):
        segs = extract_marking_segments(mk.get("object_prefixes", []), mode=mk.get("extract_mode", "centerline"))
        markings_out.append({
            "id": mk["id"],
            "name": mk.get("name", mk["id"]),
            "style_id": mk.get("style_id", "roadMarkingWhiteStyle"),
            "color_abgr": mk.get("color_abgr", "ffffffff"),
            "width": float(mk.get("width", 2.0)),
            "segments": segs
        })
    return {"polygon_layers": layers_out, "marking_layers": markings_out}


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    task_json = argv[argv.index("--task-json") + 1]
    out_json = argv[argv.index("--output-json") + 1]

    with open(task_json, "r", encoding="utf-8") as f:
        task = json.load(f)

    models_dir = task["models_dir"]
    gamma_deg = float(task.get("site_gamma_deg", 0.0))
    crs_rot_deg = float(task.get("crs_rotation_deg", 0.0))
    net_rot_rad = math.radians(crs_rot_deg - gamma_deg)
    rot_mat = Matrix.Rotation(net_rot_rad, 4, 'Z')

    buildings_info = []
    created_objs = []
    if task.get("extract_buildings", True) and task.get("buildings"):
        tex_paths = generate_procedural_textures(models_dir)
        bl_mats = build_textured_materials(tex_paths)
        mat_rules = task.get("material_classification_rules")
        for b_cfg in task["buildings"]:
            m_obj, b_info = extract_single_building(b_cfg, models_dir, bl_mats, rot_mat, mat_rules=mat_rules)
            buildings_info.append(b_info)
            created_objs.append(m_obj)

    if task.get("export_glb_path") and created_objs:
        bpy.ops.object.select_all(action='DESELECT')
        for o in created_objs:
            o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=task["export_glb_path"], use_selection=True, export_format='GLB')

    raw_roads = None
    if task.get("extract_roads", False) and task.get("roads"):
        raw_roads = extract_raw_roads(task["roads"])

    result = {"buildings": buildings_info, "raw_roads": raw_roads}
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[B2GE_EXTRACTOR] 提取完成 -> {out_json} (建筑:{len(buildings_info)})")


if __name__ == "__main__":
    main()
