#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建全新独立合成 Blender 测试场景 (create_synthetic_blend.py)
注：本脚本生成合成测试数据 (Synthetic Test Data)，用于在完全不依赖太阳谷目录、建筑名或 UTM 47N 原点的条件下验证通用工具链。
包含：
  - 2 个集合实例建筑 (Alpha_Tower_Inst, Beta_Hall_Inst) + 1 个独立 Mesh 建筑 (Gamma_Pavilion_Mesh)
  - 1 条弯曲主路 + 1 条支路形成的丁字路口 (Main_Curved_Road, North_Branch_Road)
  - 1 条与道路局部重叠的人行道 (Campus_Sidewalk，验证布尔差集)
  - 5 段道路中心标线 (Dash_Line_01~05)
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math
import os
import sys


def get_or_make_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    return m


def make_box_mesh(name, size_xyz, offset_xyz=(0, 0, 0), mat_name="白墙_Plaster"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size_xyz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(offset_xyz), verts=bm.verts)
    me = bpy.data.meshes.new(name + "_me")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(get_or_make_mat(mat_name))
    obj = bpy.data.objects.new(name, me)
    return obj


def build_synthetic_scene(out_blend_path: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = 'METRIC'
    scn.unit_settings.scale_length = 1.0

    # 1. 创建母版资产集合 Col_Asset_Alpha_Tower
    asset_col = bpy.data.collections.new("Col_Asset_Alpha_Tower")
    scn.collection.children.link(asset_col)

    core_body = make_box_mesh("Tower_Wall_Body", (14.0, 10.0, 12.0), (0.0, 0.0, 6.0), "外墙涂料_Plaster")
    glass_curtain = make_box_mesh("Tower_Glass_Facade", (14.2, 8.0, 9.0), (0.0, 0.0, 5.5), "建筑玻璃_Glass")
    roof_solar = make_box_mesh("Tower_Solar_Roof", (12.0, 8.0, 0.4), (0.0, 0.0, 12.2), "屋顶光伏_Solar")
    wood_canopy = make_box_mesh("Tower_Wood_Canopy", (6.0, 3.0, 0.3), (0.0, -6.0, 3.5), "柚木百叶_Wood")
    indoor_desk = make_box_mesh("Indoor_Furniture_Desk", (1.6, 0.8, 0.75), (0.0, 0.0, 0.4), "室内木桌_Wood")

    for o in [core_body, glass_curtain, roof_solar, wood_canopy, indoor_desk]:
        asset_col.objects.link(o)
    asset_col.hide_viewport = True
    asset_col.hide_render = True

    # 2. 创建建筑集合并放置 2 个 Collection Instance + 1 个独立 Mesh 建筑
    bldg_col = bpy.data.collections.new("Synt_Buildings")
    scn.collection.children.link(bldg_col)

    inst1 = bpy.data.objects.new("Alpha_Tower_Inst", None)
    inst1.instance_type = 'COLLECTION'
    inst1.instance_collection = asset_col
    inst1.location = (-35.0, -18.0, 0.0)
    inst1.rotation_euler = (0.0, 0.0, math.radians(15.0))
    inst1.scale = (1.0, 1.0, 1.0)
    bldg_col.objects.link(inst1)

    inst2 = bpy.data.objects.new("Beta_Hall_Inst", None)
    inst2.instance_type = 'COLLECTION'
    inst2.instance_collection = asset_col
    inst2.location = (5.0, -20.0, 0.0)
    inst2.rotation_euler = (0.0, 0.0, math.radians(-10.0))
    inst2.scale = (1.15, 0.95, 0.85)
    bldg_col.objects.link(inst2)

    gamma_obj = make_box_mesh("Gamma_Pavilion_Mesh", (18.0, 12.0, 8.5), (42.0, 12.0, 4.25), "深灰金属_Metal")
    bldg_col.objects.link(gamma_obj)

    # 3. 创建弯曲道路 + 北向丁字路口支路 + 局部重叠人行道
    road_col = bpy.data.collections.new("Synt_Roads")
    scn.collection.children.link(road_col)

    bm_road = bmesh.new()
    pts_center = [(-60.0, 0.0), (-30.0, 0.0), (0.0, 4.0), (30.0, 12.0), (65.0, 15.0)]
    half_w = 3.5
    for i in range(len(pts_center) - 1):
        x0, y0 = pts_center[i]
        x1, y1 = pts_center[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        nx, ny = -dy / L * half_w, dx / L * half_w
        v0 = bm_road.verts.new((x0 - nx, y0 - ny, 0.1))
        v1 = bm_road.verts.new((x1 - nx, y1 - ny, 0.1))
        v2 = bm_road.verts.new((x1 + nx, y1 + ny, 0.1))
        v3 = bm_road.verts.new((x0 + nx, y0 + ny, 0.1))
        bm_road.faces.new((v0, v1, v2, v3))
    me_road = bpy.data.meshes.new("Main_Curved_Road_me")
    bm_road.to_mesh(me_road)
    bm_road.free()
    me_road.materials.append(get_or_make_mat("沥青路面_Road"))
    obj_road = bpy.data.objects.new("Main_Curved_Road", me_road)
    road_col.objects.link(obj_road)

    # 北向丁字路口支路 (与主路在 (0, 4) 处相交重叠)
    bm_br = bmesh.new()
    vb = [bm_br.verts.new((-3.0, 2.0, 0.1)), bm_br.verts.new((3.0, 2.0, 0.1)), bm_br.verts.new((3.0, 35.0, 0.1)), bm_br.verts.new((-3.0, 35.0, 0.1))]
    bm_br.faces.new(vb)
    me_br = bpy.data.meshes.new("North_Branch_Road_me")
    bm_br.to_mesh(me_br)
    bm_br.free()
    obj_br = bpy.data.objects.new("North_Branch_Road", me_br)
    road_col.objects.link(obj_br)

    # 故意与主车行道有重叠的人行道面片 (测试 difference 去重)
    bm_sw = bmesh.new()
    vs = [bm_sw.verts.new((-55.0, -5.5, 0.15)), bm_sw.verts.new((25.0, -5.5, 0.15)), bm_sw.verts.new((25.0, -1.5, 0.15)), bm_sw.verts.new((-55.0, -1.5, 0.15))]
    bm_sw.faces.new(vs)
    me_sw = bpy.data.meshes.new("Campus_Sidewalk_me")
    bm_sw.to_mesh(me_sw)
    bm_sw.free()
    obj_sw = bpy.data.objects.new("Campus_Sidewalk", me_sw)
    road_col.objects.link(obj_sw)

    # 道路虚线
    for idx in range(5):
        xc = -45.0 + idx * 20.0
        yc = 0.0 if xc < 0 else (xc / 60.0) * 12.0
        d_obj = make_box_mesh(f"Dash_Line_{idx+1:02d}", (3.0, 0.25, 0.02), (xc, yc, 0.18), "道路白线_Marking")
        road_col.objects.link(d_obj)

    os.makedirs(os.path.dirname(os.path.abspath(out_blend_path)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend_path)
    print(f"[SYNTHETIC_SCENE] 合成测试场景创建完成 -> {out_blend_path}")


if __name__ == "__main__":
    argv = sys.argv
    out_p = argv[argv.index("--") + 1] if "--" in argv else "/tmp/b2ge_synthetic_demo/synthetic_campus.blend"
    build_synthetic_scene(out_p)
