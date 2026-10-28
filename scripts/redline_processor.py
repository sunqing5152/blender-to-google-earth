#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用地块红线与界址点处理器 (redline_processor.py)
支持从配置列表、JSON 或外部 KML 读取界址点，提供可配置步长加密插值、贴地+低视角浮空双层红线及界址点唯一标签。
"""

import json
import math
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple
from geo_transform import GeoTransformer, wgs84_to_utm


def load_boundary_points(redline_cfg: Dict[str, Any], geo: GeoTransformer) -> List[Dict[str, Any]]:
    """
    加载并标准化界址点列表，统一补充 id, utm_e, utm_n, wgs84_lon, wgs84_lat，并执行 ID 唯一性去重检查。
    """
    raw_pts = []
    if "points" in redline_cfg and redline_cfg["points"]:
        raw_pts = redline_cfg["points"]
    elif "source_json" in redline_cfg and redline_cfg["source_json"]:
        with open(redline_cfg["source_json"], "r", encoding="utf-8") as f:
            jdata = json.load(f)
        if isinstance(jdata, list):
            raw_pts = jdata
        elif "boundary_control_points_verification_J01_to_J15" in jdata:
            raw_pts = jdata["boundary_control_points_verification_J01_to_J15"]["points"]
        elif "points" in jdata:
            raw_pts = jdata["points"]
    elif "source_kml" in redline_cfg and redline_cfg["source_kml"]:
        tree = ET.parse(redline_cfg["source_kml"])
        root = tree.getroot()
        idx = 1
        for el in root.iter():
            if el.tag.endswith("Placemark"):
                name_el = next((c for c in el if c.tag.endswith("name")), None)
                pt_el = next((c for c in el.iter() if c.tag.endswith("Point")), None)
                if pt_el is not None:
                    coord_el = next((c for c in pt_el.iter() if c.tag.endswith("coordinates")), None)
                    if coord_el is not None and coord_el.text:
                        parts = coord_el.text.strip().split()[0].split(",")
                        raw_pts.append({
                            "id": name_el.text.strip() if (name_el is not None and name_el.text) else f"J{idx:02d}",
                            "wgs84_lon": float(parts[0]),
                            "wgs84_lat": float(parts[1])
                        })
                        idx += 1

    normalized = []
    seen_ids = set()
    for i, p in enumerate(raw_pts):
        pid = str(p.get("id", f"J{i + 1:02d}")).strip()
        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        if ("utm_e" in p or "utm_E" in p) and ("utm_n" in p or "utm_N" in p):
            ue = float(p.get("utm_e", p.get("utm_E")))
            un = float(p.get("utm_n", p.get("utm_N")))
            lon, lat, _ = geo.utm_to_wgs84(ue, un)
        elif "wgs84_lon" in p and "wgs84_lat" in p:
            lon = float(p["wgs84_lon"])
            lat = float(p["wgs84_lat"])
            ue, un, _, _, _ = wgs84_to_utm(lon, lat, geo.zone, geo.hemisphere)
        elif ("blender_x" in p or "blender_X" in p) and ("blender_y" in p or "blender_Y" in p):
            bx = float(p.get("blender_x", p.get("blender_X")))
            by = float(p.get("blender_y", p.get("blender_Y")))
            ue, un = geo.blender_to_utm(bx, by)
            lon, lat, _ = geo.utm_to_wgs84(ue, un)
        else:
            raise ValueError(f"界址点 {pid} 缺少有效坐标字段")

        normalized.append({
            "id": pid,
            "utm_e": round(ue, 4),
            "utm_n": round(un, 4),
            "wgs84_lon": round(lon, 8),
            "wgs84_lat": round(lat, 8)
        })
    return normalized


def interpolate_redline_rings(
    pts: List[Dict[str, Any]],
    geo: GeoTransformer,
    step_m: float = 2.0,
    height_offset_m: float = 1.0
) -> Tuple[str, str, int, float]:
    """在相邻界址点之间按指定步长 (step_m) 加密插值，返回 (clamp_coords_str, rel_coords_str, vertex_count, perimeter_m)"""
    if len(pts) < 3:
        raise ValueError("地块红线至少需要 3 个不重合的界址点")
    dense_clamp = []
    dense_rel = []
    n = len(pts)
    perimeter = 0.0

    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        e1, n1 = p1["utm_e"], p1["utm_n"]
        e2, n2 = p2["utm_e"], p2["utm_n"]
        dist = math.hypot(e2 - e1, n2 - n1)
        perimeter += dist
        steps = max(1, int(math.ceil(dist / step_m))) if (step_m and step_m > 0) else 1
        for s in range(steps):
            t = s / float(steps)
            ce = e1 + (e2 - e1) * t
            cn = n1 + (n2 - n1) * t
            lon, lat, _ = geo.utm_to_wgs84(ce, cn)
            dense_clamp.append(f"{lon:.8f},{lat:.8f},0")
            dense_rel.append(f"{lon:.8f},{lat:.8f},{height_offset_m:.2f}")

    p0 = pts[0]
    lon0, lat0, _ = geo.utm_to_wgs84(p0["utm_e"], p0["utm_n"])
    dense_clamp.append(f"{lon0:.8f},{lat0:.8f},0")
    dense_rel.append(f"{lon0:.8f},{lat0:.8f},{height_offset_m:.2f}")

    return " ".join(dense_clamp), " ".join(dense_rel), len(dense_rel), round(perimeter, 3)


def build_redline_styles_and_folder(
    redline_cfg: Dict[str, Any],
    geo: GeoTransformer
) -> Tuple[List[ET.Element], ET.Element, Dict[str, Any]]:
    """构建结构化红线样式列表、Folder 节点及统计摘要"""
    pts = load_boundary_points(redline_cfg, geo)
    step_m = float(redline_cfg.get("interpolation_step_m", 2.0))
    h_off = float(redline_cfg.get("enhanced_height_offset_m", 1.0))
    clamp_vis = "1" if redline_cfg.get("clamp_layer_visible", False) else "0"
    enh_vis = "1" if redline_cfg.get("enhanced_layer_visible", True) else "0"
    pts_vis = "1" if redline_cfg.get("points_layer_visible", True) else "0"

    clamp_str, rel_str, v_cnt, perim_m = interpolate_redline_rings(pts, geo, step_m=step_m, height_offset_m=h_off)

    st_clamp = ET.Element("Style", id="redlineClampStyle")
    ls1 = ET.SubElement(st_clamp, "LineStyle")
    ET.SubElement(ls1, "color").text = redline_cfg.get("clamp_color_abgr", "ff0022ff")
    ET.SubElement(ls1, "width").text = str(redline_cfg.get("clamp_width", 3.0))

    st_enh = ET.Element("Style", id="redlineEnhancedStyle")
    ls2 = ET.SubElement(st_enh, "LineStyle")
    ET.SubElement(ls2, "color").text = redline_cfg.get("enhanced_color_abgr", "ff0022ff")
    ET.SubElement(ls2, "width").text = str(redline_cfg.get("enhanced_width", 4.0))

    st_jpt = ET.Element("Style", id="jPtStyle")
    ics = ET.SubElement(st_jpt, "IconStyle")
    ET.SubElement(ics, "color").text = redline_cfg.get("point_icon_color_abgr", "ff0022ff")
    ET.SubElement(ics, "scale").text = str(redline_cfg.get("point_icon_scale", 0.65))
    ic = ET.SubElement(ics, "Icon")
    ET.SubElement(ic, "href").text = "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
    lbs = ET.SubElement(st_jpt, "LabelStyle")
    ET.SubElement(lbs, "color").text = redline_cfg.get("point_label_color_abgr", "ffffffff")
    ET.SubElement(lbs, "scale").text = str(redline_cfg.get("point_label_scale", 0.75))

    folder = ET.Element("Folder")
    ET.SubElement(folder, "name").text = redline_cfg.get("folder_name", "04_地块红线与界址点 (定位辅助·可分层开关)")
    ET.SubElement(folder, "open").text = "1"

    pm1 = ET.SubElement(folder, "Placemark")
    ET.SubElement(pm1, "name").text = redline_cfg.get("clamp_layer_name", "01_地表贴合红线 (俯视推荐)")
    ET.SubElement(pm1, "visibility").text = clamp_vis
    ET.SubElement(pm1, "styleUrl").text = "#redlineClampStyle"
    ls_c = ET.SubElement(pm1, "LineString")
    ET.SubElement(ls_c, "tessellate").text = "1"
    ET.SubElement(ls_c, "altitudeMode").text = "clampToGround"
    ET.SubElement(ls_c, "coordinates").text = clamp_str

    pm2 = ET.SubElement(folder, "Placemark")
    ET.SubElement(pm2, "name").text = redline_cfg.get("enhanced_layer_name", f"02_低视角增强红线 (倾斜推荐·高出地面{h_off:.1f}m)")
    ET.SubElement(pm2, "visibility").text = enh_vis
    ET.SubElement(pm2, "styleUrl").text = "#redlineEnhancedStyle"
    ls_e = ET.SubElement(pm2, "LineString")
    ET.SubElement(ls_e, "altitudeMode").text = "relativeToGround"
    ET.SubElement(ls_e, "coordinates").text = rel_str

    sub_f = ET.SubElement(folder, "Folder")
    ET.SubElement(sub_f, "name").text = redline_cfg.get("points_folder_name", f"03_界址点 ({pts[0]['id']}～{pts[-1]['id']})")
    ET.SubElement(sub_f, "open").text = "0"
    for p in pts:
        pm_p = ET.SubElement(sub_f, "Placemark")
        ET.SubElement(pm_p, "name").text = p["id"]
        ET.SubElement(pm_p, "visibility").text = pts_vis
        ET.SubElement(pm_p, "styleUrl").text = "#jPtStyle"
        pt_el = ET.SubElement(pm_p, "Point")
        ET.SubElement(pt_el, "altitudeMode").text = "clampToGround"
        ET.SubElement(pt_el, "coordinates").text = f"{p['wgs84_lon']:.8f},{p['wgs84_lat']:.8f},0"

    stats = {
        "unique_boundary_points": len(pts),
        "interpolated_vertices": v_cnt,
        "interpolation_step_m": step_m,
        "enhanced_height_offset_m": h_off,
        "perimeter_m": perim_m
    }
    return [st_clamp, st_enh, st_jpt], folder, stats
