#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 Google Earth 贴地道路处理器 (road_processor.py)
利用 Shapely 执行二维布尔并集 (unary_union) 与层级差集 (difference)，生成 KML Polygon (clampToGround) 结构。
"""

from typing import Dict, List, Any, Tuple
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
from geo_transform import GeoTransformer


def rings_to_clean_union(raw_rings: List[List[List[float]]], min_area: float = 0.001):
    polys = []
    for ring in raw_rings:
        if len(ring) < 3:
            continue
        pts = [( float(p[0]), float(p[1]) ) for p in ring]
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_valid and not p.is_empty and p.area >= min_area:
            polys.append(p)
    if not polys:
        return Polygon()
    return unary_union(polys)


def geom_to_poly_dicts(geom, min_area: float = 0.01) -> List[Dict[str, Any]]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        if geom.area < min_area:
            return []
        return [{
            "exterior": [[round(x, 3), round(y, 3)] for x, y in geom.exterior.coords],
            "interiors": [[[round(x, 3), round(y, 3)] for x, y in r.coords] for r in geom.interiors],
            "area_m2": round(geom.area, 3)
        }]
    elif isinstance(geom, (MultiPolygon, GeometryCollection)):
        out = []
        for g in geom.geoms:
            out.extend(geom_to_poly_dicts(g, min_area=min_area))
        return out
    return []


def process_raw_roads_to_clean_data(raw_roads: Dict[str, Any]) -> Dict[str, Any]:
    """
    对原始道路面片按图层优先级执行 unary_union 与 difference，返回拓扑无重叠的多边形数据。
    """
    accumulated = Polygon()
    processed_layers = []

    for lyr in raw_roads.get("polygon_layers", []):
        u_geom = rings_to_clean_union(lyr.get("raw_rings", []))
        if lyr.get("subtract_previous", False) and not accumulated.is_empty:
            clean_geom = u_geom.difference(accumulated)
        else:
            clean_geom = u_geom
        if not clean_geom.is_empty:
            accumulated = unary_union([accumulated, clean_geom]) if not accumulated.is_empty else clean_geom
        p_dicts = geom_to_poly_dicts(clean_geom)
        total_area = round(sum(d["area_m2"] for d in p_dicts), 2)
        processed_layers.append({
            "id": lyr["id"],
            "name": lyr.get("name", lyr["id"]),
            "style_id": lyr.get("style_id", f"style_{lyr['id']}"),
            "color_abgr": lyr.get("color_abgr", "ff3a3a3c"),
            "polygons": p_dicts,
            "total_area_m2": total_area
        })

    return {
        "polygon_layers": processed_layers,
        "marking_layers": raw_roads.get("marking_layers", [])
    }


def _coords_str_from_xy(coords_xy: List[List[float]], geo: GeoTransformer) -> str:
    pts = []
    for x, y in coords_xy:
        lon, lat, _ = geo.blender_to_wgs84(float(x), float(y))
        pts.append(f"{lon:.8f},{lat:.8f},0")
    return " ".join(pts)


def build_road_styles_elements(processed_roads: Dict[str, Any]) -> List[ET.Element]:
    styles = []
    seen = set()
    for lyr in processed_roads.get("polygon_layers", []):
        sid = lyr["style_id"]
        if sid in seen:
            continue
        seen.add(sid)
        st = ET.Element("Style", id=sid)
        ls = ET.SubElement(st, "LineStyle")
        ET.SubElement(ls, "color").text = "00000000"
        ET.SubElement(ls, "width").text = "0"
        ps = ET.SubElement(st, "PolyStyle")
        ET.SubElement(ps, "color").text = lyr.get("color_abgr", "ff3a3a3c")
        ET.SubElement(ps, "outline").text = "0"
        styles.append(st)

    for mk in processed_roads.get("marking_layers", []):
        sid = mk["style_id"]
        if sid in seen:
            continue
        seen.add(sid)
        st = ET.Element("Style", id=sid)
        ls = ET.SubElement(st, "LineStyle")
        ET.SubElement(ls, "color").text = mk.get("color_abgr", "ffffffff")
        ET.SubElement(ls, "width").text = str(mk.get("width", 2.0))
        styles.append(st)
    return styles


def build_road_folder_element(
    processed_roads: Dict[str, Any],
    geo: GeoTransformer,
    folder_name: str = "03_小区内部道路与入口硬质铺装 (贴地多边形)"
) -> ET.Element:
    """构建结构化的 KML 道路 Folder Element (clampToGround)"""
    root_folder = ET.Element("Folder")
    ET.SubElement(root_folder, "name").text = folder_name
    ET.SubElement(root_folder, "open").text = "1"

    for lyr in processed_roads.get("polygon_layers", []):
        sub_f = ET.SubElement(root_folder, "Folder")
        ET.SubElement(sub_f, "name").text = lyr["name"]
        ET.SubElement(sub_f, "open").text = "0"
        for idx, p_dict in enumerate(lyr.get("polygons", [])):
            pm = ET.SubElement(sub_f, "Placemark")
            ET.SubElement(pm, "name").text = f"{lyr['id']}_{idx + 1}"
            ET.SubElement(pm, "styleUrl").text = f"#{lyr['style_id']}"
            poly_el = ET.SubElement(pm, "Polygon")
            ET.SubElement(poly_el, "altitudeMode").text = "clampToGround"
            outer = ET.SubElement(poly_el, "outerBoundaryIs")
            lr_out = ET.SubElement(outer, "LinearRing")
            ET.SubElement(lr_out, "coordinates").text = _coords_str_from_xy(p_dict["exterior"], geo)
            for inter in p_dict.get("interiors", []):
                inner = ET.SubElement(poly_el, "innerBoundaryIs")
                lr_in = ET.SubElement(inner, "LinearRing")
                ET.SubElement(lr_in, "coordinates").text = _coords_str_from_xy(inter, geo)

    for mk in processed_roads.get("marking_layers", []):
        segs = mk.get("segments", [])
        if not segs:
            continue
        sub_f = ET.SubElement(root_folder, "Folder")
        ET.SubElement(sub_f, "name").text = mk["name"]
        ET.SubElement(sub_f, "open").text = "0"
        for idx, seg in enumerate(segs):
            pm = ET.SubElement(sub_f, "Placemark")
            ET.SubElement(pm, "name").text = f"{mk['id']}_{idx + 1}"
            ET.SubElement(pm, "styleUrl").text = f"#{mk['style_id']}"
            ls_el = ET.SubElement(pm, "LineString")
            ET.SubElement(ls_el, "tessellate").text = "1"
            ET.SubElement(ls_el, "altitudeMode").text = "clampToGround"
            ET.SubElement(ls_el, "coordinates").text = _coords_str_from_xy(seg, geo)

    return root_folder
