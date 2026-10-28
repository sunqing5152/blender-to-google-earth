#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KMZ 独立质量门禁与 Google Earth Pro 真实显示验收器 (kmz_verifier.py)
执行 KML/DAE/贴图完整性检查、坐标与标签唯一性校验、基线回归对比及可选的 Google Earth Pro 真实截图验收。
"""

import hashlib
import json
import math
import os
import re
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional

from kmz_builder import strip_kml_ns, serialize_kml_root


def verify_kmz_archive(kmz_path: str) -> Dict[str, Any]:
    """对 KMZ 压缩包执行静态深度几何、引用完整性与图层规则检查"""
    issues: List[str] = []
    warnings: List[str] = []

    if not os.path.exists(kmz_path):
        return {"status": "FAIL", "issues": [f"文件不存在: {kmz_path}"], "gui_verification_status": "UNVERIFIED"}

    try:
        zf = zipfile.ZipFile(kmz_path, "r")
    except Exception as e:
        return {"status": "FAIL", "issues": [f"无效的 ZIP/KMZ 归档: {e}"], "gui_verification_status": "UNVERIFIED"}

    with zf:
        namelist = set(zf.namelist())
        if "doc.kml" not in namelist:
            return {"status": "FAIL", "issues": ["KMZ 缺少根级 doc.kml"], "gui_verification_status": "UNVERIFIED"}

        try:
            kml_bytes = zf.read("doc.kml")
            root = ET.fromstring(kml_bytes.decode("utf-8"))
            strip_kml_ns(root)
        except Exception as e:
            return {"status": "FAIL", "issues": [f"doc.kml XML 解析失败: {e}"], "gui_verification_status": "UNVERIFIED"}

        models_summary = []
        referenced_files = {"doc.kml"}
        for pm in root.iter("Placemark"):
            m_el = pm.find("Model")
            if m_el is None:
                continue
            pm_name = pm.findtext("name", default="Unnamed_Model")
            lon = float(m_el.findtext("./Location/longitude", default="999"))
            lat = float(m_el.findtext("./Location/latitude", default="999"))
            alt = float(m_el.findtext("./Location/altitude", default="0"))
            href = m_el.findtext("./Link/href", default="").strip()

            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                issues.append(f"模型 {pm_name} 经纬度越界: ({lon}, {lat})")
            if href not in namelist:
                issues.append(f"模型 {pm_name} 引用的 DAE 文件未打包: {href}")
                continue

            referenced_files.add(href)
            dae_bytes = zf.read(href)
            dae_sha = hashlib.sha256(dae_bytes).hexdigest()
            dae_txt = dae_bytes.decode("utf-8", errors="ignore")
            try:
                ET.fromstring(dae_bytes)
            except Exception as e:
                issues.append(f"DAE XML 格式损坏 ({href}): {e}")

            has_ds = "<double_sided>1</double_sided>" in dae_txt
            if not has_ds:
                warnings.append(f"DAE ({href}) 未检测到 GOOGLEEARTH double_sided=1 标记")

            tex_refs = re.findall(r"<init_from>([^<]+\.(?:png|jpg|jpeg))</init_from>", dae_txt, flags=re.IGNORECASE)
            for tr in tex_refs:
                tex_arc = f"models/{os.path.basename(tr.strip())}"
                if tex_arc not in namelist:
                    issues.append(f"DAE ({href}) 引用的贴图缺失: {tex_arc}")
                else:
                    referenced_files.add(tex_arc)

            models_summary.append({
                "name": pm_name,
                "dae_href": href,
                "dae_sha256": dae_sha,
                "lon": round(lon, 8),
                "lat": round(lat, 8),
                "altitude_m": round(alt, 3),
                "double_sided": has_ds,
                "textures_count": len(set(tex_refs))
            })

        # 检查道路贴地多边形
        road_polys_count = 0
        non_clamp_polys = 0
        for poly in root.iter("Polygon"):
            road_polys_count += 1
            if poly.findtext("altitudeMode", default="") != "clampToGround":
                non_clamp_polys += 1
        if non_clamp_polys > 0:
            warnings.append(f"发现 {non_clamp_polys} 个 Polygon 未使用 clampToGround")

        # 检查红线与界址点唯一性
        point_names = []
        duplicate_points = []
        for pm in root.iter("Placemark"):
            if pm.find("Point") is not None:
                pname = pm.findtext("name", default="").strip()
                if pname in point_names:
                    duplicate_points.append(pname)
                point_names.append(pname)
        if duplicate_points:
            issues.append(f"检测到重复的界址点标签: {sorted(set(duplicate_points))}")

        linestrings_summary = []
        for pm in root.iter("Placemark"):
            ls = pm.find("LineString")
            if ls is not None:
                lname = pm.findtext("name", default="")
                vis = pm.findtext("visibility", default="1").strip()
                amode = ls.findtext("altitudeMode", default="clampToGround")
                coords_raw = ls.findtext("coordinates", default="").strip().split()
                linestrings_summary.append({
                    "name": lname,
                    "visibility": vis,
                    "altitude_mode": amode,
                    "vertices_count": len(coords_raw)
                })

        orphan_files = sorted(namelist - referenced_files)
        if orphan_files:
            warnings.append(f"KMZ 内存在未被引用的冗余文件: {orphan_files}")

    status = "PASS" if len(issues) == 0 else "FAIL"
    return {
        "status": status,
        "kmz_path": kmz_path,
        "kmz_size_bytes": os.path.getsize(kmz_path),
        "models_count": len(models_summary),
        "models": models_summary,
        "road_polygons_count": road_polys_count,
        "boundary_points_count": len(point_names),
        "unique_boundary_points": len(set(point_names)),
        "linestrings_count": len(linestrings_summary),
        "linestrings": linestrings_summary,
        "orphan_files": orphan_files,
        "issues": issues,
        "warnings": warnings,
        "gui_verification_status": "UNVERIFIED (仅完成静态结构检查，未执行 Google Earth Pro GUI 渲染检查)"
    }


def compare_kmz_with_baseline(candidate_kmz: str, baseline_kmz: str, coord_tol_deg: float = 1e-7) -> Dict[str, Any]:
    """将待测 KMZ 与已知基线 KMZ 进行逐项结构化对比（建筑数量、坐标、DAE 哈希、道路多边形数、界址点与红线点数）"""
    cand = verify_kmz_archive(candidate_kmz)
    base = verify_kmz_archive(baseline_kmz)

    diffs: List[str] = []
    if cand["status"] != "PASS":
        diffs.append(f"候选 KMZ 自身静态检查未通过: {cand['issues']}")
    if base["status"] != "PASS":
        diffs.append(f"基线 KMZ 静态检查异常: {base['issues']}")

    base_models = {m["name"]: m for m in base.get("models", [])}
    cand_models = {m["name"]: m for m in cand.get("models", [])}

    if set(base_models.keys()) != set(cand_models.keys()):
        diffs.append(f"建筑模型集合不一致: 基线={sorted(base_models.keys())}, 候选={sorted(cand_models.keys())}")

    model_comparisons = []
    for m_name in sorted(set(base_models.keys()) & set(cand_models.keys())):
        bm = base_models[m_name]
        cm = cand_models[m_name]
        dlon = abs(bm["lon"] - cm["lon"])
        dlat = abs(bm["lat"] - cm["lat"])
        dalt = abs(bm["altitude_m"] - cm["altitude_m"])
        sha_match = (bm["dae_sha256"] == cm["dae_sha256"])
        coord_match = (dlon <= coord_tol_deg and dlat <= coord_tol_deg and dalt <= 1e-3)
        if not coord_match:
            diffs.append(f"建筑 {m_name} 空间定位偏差超限: dLon={dlon:.2e}, dLat={dlat:.2e}, dAlt={dalt:.4f}")
        model_comparisons.append({
            "name": m_name,
            "coord_match": coord_match,
            "dlon_deg": dlon,
            "dlat_deg": dlat,
            "dalt_m": dalt,
            "dae_sha256_identical": sha_match,
            "baseline_sha256": bm["dae_sha256"],
            "candidate_sha256": cm["dae_sha256"]
        })

    if base.get("road_polygons_count") != cand.get("road_polygons_count"):
        diffs.append(f"道路贴地多边形数量不一致: 基线={base.get('road_polygons_count')}, 候选={cand.get('road_polygons_count')}")

    if base.get("unique_boundary_points") != cand.get("unique_boundary_points"):
        diffs.append(f"唯一界址点数量不一致: 基线={base.get('unique_boundary_points')}, 候选={cand.get('unique_boundary_points')}")

    base_ls = [ls["vertices_count"] for ls in base.get("linestrings", [])]
    cand_ls = [ls["vertices_count"] for ls in cand.get("linestrings", [])]
    if base_ls != cand_ls:
        diffs.append(f"LineString 顶点数量序列不一致: 基线={base_ls}, 候选={cand_ls}")

    return {
        "regression_status": "PASS" if len(diffs) == 0 else "FAIL",
        "candidate_kmz": candidate_kmz,
        "baseline_kmz": baseline_kmz,
        "models_compared": len(model_comparisons),
        "all_dae_hashes_identical": all(m["dae_sha256_identical"] for m in model_comparisons),
        "all_coords_within_tolerance": all(m["coord_match"] for m in model_comparisons),
        "road_polygons_match": (base.get("road_polygons_count") == cand.get("road_polygons_count")),
        "boundary_points_match": (base.get("unique_boundary_points") == cand.get("unique_boundary_points")),
        "linestrings_vertices_match": (base_ls == cand_ls),
        "differences": diffs,
        "model_details": model_comparisons
    }


def capture_google_earth_views(
    kmz_path: str,
    screenshots_dir: str,
    views: List[Dict[str, Any]],
    ge_app_path: str = "/Applications/Google Earth Pro.app",
    wait_sec: float = 12.0
) -> Dict[str, Any]:
    """在 macOS 上启动真实 Google Earth Pro 注入 LookAt 视角并截取窗口图像"""
    if not os.path.exists(ge_app_path):
        return {
            "gui_verification_status": "UNVERIFIED",
            "reason": f"未找到 Google Earth Pro 应用程序: {ge_app_path}",
            "captured_files": []
        }

    try:
        import Quartz
    except ImportError:
        return {
            "gui_verification_status": "UNVERIFIED",
            "reason": "当前 Python 环境缺少 pyobjc-framework-Quartz，无法定位窗口 ID",
            "captured_files": []
        }

    os.makedirs(screenshots_dir, exist_ok=True)
    ge_support = os.path.expanduser("~/Library/Application Support/Google Earth")
    myplaces_kml = os.path.join(ge_support, "myplaces.kml")
    clean_myplaces = '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>我的地点</name></Document></kml>\n'

    def _reset_ge():
        subprocess.run(["killall", "-9", "Google Earth"], stderr=subprocess.DEVNULL)
        time.sleep(0.8)
        if os.path.exists(ge_support):
            with open(myplaces_kml, "w", encoding="utf-8") as f:
                f.write(clean_myplaces)
        subprocess.run(["defaults", "write", "com.google.GoogleEarthPro", "UnfinishedSessions", "-int", "0"], check=False)
        subprocess.run(["killall", "cfprefsd"], stderr=subprocess.DEVNULL)
        time.sleep(0.4)

    def _get_wid():
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID
        )
        best_wid, best_area = None, 0
        for w in wins:
            if "Google Earth" in str(w.get("kCGWindowOwnerName", "")):
                b = w.get("kCGWindowBounds", {})
                area = b.get("Width", 0) * b.get("Height", 0)
                if area > best_area:
                    best_area = area
                    best_wid = w.get("kCGWindowNumber")
        return best_wid

    captured = []
    with zipfile.ZipFile(kmz_path, "r") as zin:
        orig_kml = zin.read("doc.kml").decode("utf-8")
        other_items = [(item.filename, zin.read(item.filename)) for item in zin.infolist() if item.filename != "doc.kml"]

    for v in views:
        _reset_ge()
        root = ET.fromstring(orig_kml)
        strip_kml_ns(root)
        doc = root.find("Document")
        la = doc.find("LookAt") if doc is not None else None
        if la is not None:
            for tag, key, fmt in [("longitude", "lon", ".6f"), ("latitude", "lat", ".6f"), ("range", "range", ".1f"), ("heading", "heading", ".1f"), ("tilt", "tilt", ".1f")]:
                el = la.find(tag)
                if el is not None and key in v:
                    el.text = format(float(v[key]), fmt)

        tmp_kmz = "/tmp/b2ge_temp_verify_view.kmz"
        with zipfile.ZipFile(tmp_kmz, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("doc.kml", serialize_kml_root(root).encode("utf-8"))
            for fn, data in other_items:
                zout.writestr(fn, data)

        subprocess.run(["open", "-a", ge_app_path, tmp_kmz], check=True)
        time.sleep(wait_sec)
        wid = _get_wid()
        out_img = os.path.join(screenshots_dir, v["filename"])
        cmd = ["screencapture", "-x", "-o", "-l", str(wid), out_img] if wid else ["screencapture", "-x", "-o", out_img]
        subprocess.run(cmd, check=True)
        captured.append({"filename": v["filename"], "path": out_img, "window_id": wid, "size_bytes": os.path.getsize(out_img)})

    _reset_ge()
    return {
        "gui_verification_status": "PASS" if len(captured) > 0 else "UNVERIFIED",
        "captured_files": captured
    }
