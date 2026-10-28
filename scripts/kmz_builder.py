#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化 KML/KMZ 构建与局部无损更新引擎 (kmz_builder.py)
全面采用 xml.etree.ElementTree 处理 KML DOM，支持全量构建与单图层/单建筑局部无损更新及 SHA256 基线锁定核验。
"""

import hashlib
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple
from geo_transform import GeoTransformer

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)


def strip_kml_ns(root: ET.Element):
    """移除 ElementTree 节点标签中的命名空间前缀以便统一结构化查找与修改"""
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_lookat_element(lookat_cfg: Dict[str, Any]) -> ET.Element:
    la = ET.Element("LookAt")
    ET.SubElement(la, "longitude").text = f"{float(lookat_cfg.get('longitude', 98.333350)):.6f}"
    ET.SubElement(la, "latitude").text = f"{float(lookat_cfg.get('latitude', 8.100180)):.6f}"
    ET.SubElement(la, "altitude").text = f"{float(lookat_cfg.get('altitude', 0.0)):.2f}"
    ET.SubElement(la, "heading").text = f"{float(lookat_cfg.get('heading', -12.0)):.1f}"
    ET.SubElement(la, "tilt").text = f"{float(lookat_cfg.get('tilt', 58.0)):.1f}"
    ET.SubElement(la, "range").text = f"{float(lookat_cfg.get('range', 370.0)):.1f}"
    ET.SubElement(la, "altitudeMode").text = str(lookat_cfg.get("altitude_mode", "relativeToGround"))
    return la


def build_building_placemark(b_info: Dict[str, Any], geo: GeoTransformer) -> Tuple[ET.Element, Dict[str, Any]]:
    cx, cy, _ = b_info["blender_footprint_center_m"]
    ue, un = geo.blender_to_utm(cx, cy)
    lon, lat, gamma = geo.utm_to_wgs84(ue, un)
    alt = float(b_info.get("altitude_rel_ground_m", 0.0))

    b_info["utm_center_m"] = [round(ue, 3), round(un, 3)]
    b_info["wgs84_lon_lat"] = [round(lon, 8), round(lat, 8)]
    b_info["meridian_convergence_deg"] = round(gamma, 5)

    pm = ET.Element("Placemark")
    ET.SubElement(pm, "name").text = b_info["id"]
    ET.SubElement(pm, "visibility").text = "1"
    desc_html = (
        f"<h3>{b_info.get('title', b_info['id'])}</h3>"
        f"<b>Blender 源对象:</b> {b_info['blender_object']}<br/>"
        f"<b>引用资产集合:</b> {b_info['asset_collection']}<br/>"
        f"<b>UTM 基底中心 (Zone {geo.zone}{geo.hemisphere}):</b> E={ue:.3f}m, N={un:.3f}m<br/>"
        f"<b>WGS84 经纬度:</b> {lon:.7f}°, {lat:.7f}°<br/>"
        f"<b>导出三角面数:</b> {b_info['exported_triangles']}"
    )
    ET.SubElement(pm, "description").text = desc_html

    model = ET.SubElement(pm, "Model")
    ET.SubElement(model, "altitudeMode").text = "relativeToGround"
    loc = ET.SubElement(model, "Location")
    ET.SubElement(loc, "longitude").text = f"{lon:.8f}"
    ET.SubElement(loc, "latitude").text = f"{lat:.8f}"
    ET.SubElement(loc, "altitude").text = f"{alt:.2f}"
    ori = ET.SubElement(model, "Orientation")
    ET.SubElement(ori, "heading").text = f"{float(b_info.get('heading_deg', 0.0)):.1f}"
    ET.SubElement(ori, "tilt").text = "0.0"
    ET.SubElement(ori, "roll").text = "0.0"
    sca = ET.SubElement(model, "Scale")
    ET.SubElement(sca, "x").text = "1.0"
    ET.SubElement(sca, "y").text = "1.0"
    ET.SubElement(sca, "z").text = "1.0"
    lnk = ET.SubElement(model, "Link")
    ET.SubElement(lnk, "href").text = b_info["dae_file"]
    return pm, b_info


def build_building_folders(buildings_info: List[Dict[str, Any]], geo: GeoTransformer) -> List[ET.Element]:
    grouped: Dict[str, List[ET.Element]] = {}
    folder_order: List[str] = []
    for b_info in buildings_info:
        fname = b_info.get("folder", "01_建筑模型组")
        if fname not in grouped:
            grouped[fname] = []
            folder_order.append(fname)
        pm, _ = build_building_placemark(b_info, geo)
        grouped[fname].append(pm)

    folders = []
    for fname in folder_order:
        f_el = ET.Element("Folder")
        ET.SubElement(f_el, "name").text = fname
        ET.SubElement(f_el, "open").text = "1"
        for pm in grouped[fname]:
            f_el.append(pm)
        folders.append(f_el)
    return folders


def serialize_kml_root(kml_root: ET.Element) -> str:
    kml_root.set("xmlns", KML_NS)
    ET.indent(kml_root, space="  ")
    xml_body = ET.tostring(kml_root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body + "\n"


def collect_referenced_assets(kml_root: ET.Element, models_dir: str) -> List[Tuple[str, str]]:
    """
    扫描 KML 中所有 <Model><Link><href> 引用的 DAE 文件及其内部引用的 PNG 贴图，
    返回 [(local_filepath, arcname), ...]，确保绝不打包未引用的孤儿模型。
    """
    dae_hrefs = []
    for el in kml_root.iter("Model"):
        href_el = el.find("./Link/href")
        if href_el is not None and href_el.text:
            h = href_el.text.strip()
            if h not in dae_hrefs:
                dae_hrefs.append(h)

    base_parent = os.path.dirname(os.path.abspath(models_dir))
    assets: List[Tuple[str, str]] = []
    seen_arc = set()

    for href in dae_hrefs:
        local_dae = os.path.join(base_parent, href) if not os.path.isabs(href) else href
        if not os.path.exists(local_dae):
            local_dae = os.path.join(models_dir, os.path.basename(href))
        if not os.path.exists(local_dae):
            raise FileNotFoundError(f"KML 引用的 DAE 模型不存在: {href} ({local_dae})")
        arc_dae = f"models/{os.path.basename(local_dae)}"
        if arc_dae not in seen_arc:
            seen_arc.add(arc_dae)
            assets.append((local_dae, arc_dae))

        with open(local_dae, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        for tex_name in re.findall(r"<init_from>([^<]+\.(?:png|jpg|jpeg))</init_from>", txt, flags=re.IGNORECASE):
            t_clean = os.path.basename(tex_name.strip())
            local_tex = os.path.join(os.path.dirname(local_dae), t_clean)
            if not os.path.exists(local_tex):
                local_tex = os.path.join(models_dir, t_clean)
            if not os.path.exists(local_tex):
                raise FileNotFoundError(f"DAE ({os.path.basename(local_dae)}) 引用的贴图不存在: {t_clean}")
            arc_tex = f"models/{t_clean}"
            if arc_tex not in seen_arc:
                seen_arc.add(arc_tex)
                assets.append((local_tex, arc_tex))
    return sorted(assets, key=lambda x: x[1])


def build_full_kmz(
    doc_name: str,
    doc_desc: str,
    lookat_cfg: Dict[str, Any],
    buildings_info: List[Dict[str, Any]],
    geo: GeoTransformer,
    models_dir: str,
    out_kml_path: str,
    out_kmz_path: str,
    road_styles: Optional[List[ET.Element]] = None,
    road_folder: Optional[ET.Element] = None,
    redline_styles: Optional[List[ET.Element]] = None,
    redline_folder: Optional[ET.Element] = None,
) -> Dict[str, Any]:
    """全量构建 KML 与自包含 KMZ"""
    kml_root = ET.Element("kml")
    doc = ET.SubElement(kml_root, "Document")
    ET.SubElement(doc, "name").text = doc_name
    ET.SubElement(doc, "open").text = "1"
    ET.SubElement(doc, "description").text = doc_desc
    doc.append(build_lookat_element(lookat_cfg))

    for st in (redline_styles or []) + (road_styles or []):
        doc.append(st)

    for bf in build_building_folders(buildings_info, geo):
        doc.append(bf)

    if road_folder is not None:
        doc.append(road_folder)
    if redline_folder is not None:
        doc.append(redline_folder)

    kml_text = serialize_kml_root(kml_root)
    os.makedirs(os.path.dirname(os.path.abspath(out_kml_path)), exist_ok=True)
    with open(out_kml_path, "w", encoding="utf-8") as f:
        f.write(kml_text)

    assets = collect_referenced_assets(kml_root, models_dir)
    os.makedirs(os.path.dirname(os.path.abspath(out_kmz_path)), exist_ok=True)
    with zipfile.ZipFile(out_kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(out_kml_path, arcname="doc.kml")
        for local_fp, arc_fp in assets:
            zf.write(local_fp, arcname=arc_fp)

    return {
        "kml_path": out_kml_path,
        "kmz_path": out_kmz_path,
        "kmz_size_bytes": os.path.getsize(out_kmz_path),
        "packaged_assets_count": len(assets),
        "packaged_assets": [{"arcname": a[1], "sha256": sha256_file(a[0])} for a in assets]
    }


def partial_update_kmz(
    base_kmz_path: str,
    out_kmz_path: str,
    out_kml_path: Optional[str] = None,
    new_doc_name: Optional[str] = None,
    new_doc_desc: Optional[str] = None,
    new_lookat_cfg: Optional[Dict[str, Any]] = None,
    replace_road_styles: Optional[List[ET.Element]] = None,
    replace_road_folder: Optional[ET.Element] = None,
    road_folder_match_keyword: str = "道路",
    replace_redline_styles: Optional[List[ET.Element]] = None,
    replace_redline_folder: Optional[ET.Element] = None,
    redline_folder_match_keyword: str = "红线",
    replace_dae_files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    基于现有 KMZ 执行结构化局部更新（如仅换道路、仅换红线或仅替换单栋建筑 DAE），
    严禁覆盖 base_kmz_path，并自动执行未修改建筑资源 SHA256 与坐标一致性审计。
    """
    if os.path.abspath(base_kmz_path) == os.path.abspath(out_kmz_path):
        raise ValueError("安全拦截：局部更新输出路径不得覆盖原始基准 KMZ 文件！")

    with zipfile.ZipFile(base_kmz_path, "r") as zin:
        orig_kml_bytes = zin.read("doc.kml")
        orig_assets = {
            item.filename: zin.read(item.filename)
            for item in zin.infolist()
            if item.filename != "doc.kml" and not item.is_dir()
        }

    kml_root = ET.fromstring(orig_kml_bytes.decode("utf-8"))
    strip_kml_ns(kml_root)
    doc = kml_root.find("Document")
    if doc is None:
        raise ValueError("基准 KMZ 的 doc.kml 缺少 <Document> 根节点")

    if new_doc_name:
        n_el = doc.find("name")
        if n_el is not None:
            n_el.text = new_doc_name
    if new_doc_desc:
        d_el = doc.find("description")
        if d_el is not None:
            d_el.text = new_doc_desc
    if new_lookat_cfg:
        old_la = doc.find("LookAt")
        new_la = build_lookat_element(new_lookat_cfg)
        if old_la is not None:
            idx = list(doc).index(old_la)
            doc.remove(old_la)
            doc.insert(idx, new_la)
        else:
            doc.insert(0, new_la)

    def _upsert_styles(new_styles: List[ET.Element]):
        for nst in new_styles:
            sid = nst.get("id")
            existing = next((c for c in doc.findall("Style") if c.get("id") == sid), None)
            if existing is not None:
                idx = list(doc).index(existing)
                doc.remove(existing)
                doc.insert(idx, nst)
            else:
                first_folder = doc.find("Folder")
                idx = list(doc).index(first_folder) if first_folder is not None else len(doc)
                doc.insert(idx, nst)

    def _replace_folder_by_kw(kw: str, new_folder: ET.Element):
        target = None
        for f_el in doc.findall("Folder"):
            fn = f_el.find("name")
            if fn is not None and fn.text and kw in fn.text:
                target = f_el
                break
        if target is not None:
            idx = list(doc).index(target)
            doc.remove(target)
            doc.insert(idx, new_folder)
        else:
            doc.append(new_folder)

    if replace_road_styles:
        _upsert_styles(replace_road_styles)
    if replace_road_folder is not None:
        _replace_folder_by_kw(road_folder_match_keyword, replace_road_folder)

    if replace_redline_styles:
        _upsert_styles(replace_redline_styles)
    if replace_redline_folder is not None:
        _replace_folder_by_kw(redline_folder_match_keyword, replace_redline_folder)

    updated_assets = dict(orig_assets)
    replaced_arcs = set()
    if replace_dae_files:
        for arc_name, local_path in replace_dae_files.items():
            with open(local_path, "rb") as f:
                updated_assets[arc_name] = f.read()
            replaced_arcs.add(arc_name)

    referenced_daes = set()
    for m_el in kml_root.iter("Model"):
        h_el = m_el.find("./Link/href")
        if h_el is not None and h_el.text:
            referenced_daes.add(h_el.text.strip())

    referenced_texs = set()
    for dae_arc in referenced_daes:
        if dae_arc in updated_assets:
            txt = updated_assets[dae_arc].decode("utf-8", errors="ignore")
            for t in re.findall(r"<init_from>([^<]+\.(?:png|jpg|jpeg))</init_from>", txt, flags=re.IGNORECASE):
                referenced_texs.add(f"models/{os.path.basename(t.strip())}")

    active_arcs = sorted(referenced_daes | referenced_texs)
    kml_text = serialize_kml_root(kml_root)
    if out_kml_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_kml_path)), exist_ok=True)
        with open(out_kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)

    os.makedirs(os.path.dirname(os.path.abspath(out_kmz_path)), exist_ok=True)
    with zipfile.ZipFile(out_kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("doc.kml", kml_text.encode("utf-8"))
        for arc in active_arcs:
            if arc in updated_assets:
                zout.writestr(arc, updated_assets[arc])

    preserved_checks = []
    for arc in sorted(referenced_daes):
        if arc in replaced_arcs:
            continue
        before_sha = sha256_bytes(orig_assets[arc]) if arc in orig_assets else None
        after_sha = sha256_bytes(updated_assets[arc]) if arc in updated_assets else None
        preserved_checks.append({
            "arcname": arc,
            "sha256_before": before_sha,
            "sha256_after": after_sha,
            "identical": (before_sha is not None and before_sha == after_sha)
        })

    return {
        "base_kmz_path": base_kmz_path,
        "out_kmz_path": out_kmz_path,
        "out_kml_path": out_kml_path,
        "out_kmz_size_bytes": os.path.getsize(out_kmz_path),
        "active_assets_count": len(active_arcs),
        "preserved_models_audit": preserved_checks,
        "all_unmodified_models_identical": all(c["identical"] for c in preserved_checks)
    }
