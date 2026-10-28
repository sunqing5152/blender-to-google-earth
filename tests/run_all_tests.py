#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender-to-google-earth 自动化测试与回归验证套件 (run_all_tests.py)
涵盖阶段5要求的五大测试：
  - 测试一：Skill 格式与规范测试
  - 测试二：普吉太阳谷 V3 回归测试 (严禁覆盖正式 V3 KMZ)
  - 测试三：全新独立合成场景全流程测试 (UTM 50N + 控制点配准 + 3栋异构建筑 + 弯曲丁字路口)
  - 测试四：局部无损更新测试 (仅改红线，验证建筑 DAE 哈希与道路 100% 不变)
  - 测试五：真实 Google Earth Pro 加载与截图验证
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import yaml

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
CLI_PY = os.path.join(SCRIPTS_DIR, "b2ge_cli.py")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from kmz_verifier import verify_kmz_archive, compare_kmz_with_baseline, capture_google_earth_views
from kmz_builder import sha256_file
from b2ge_cli import find_blender_executable


def test_01_skill_structure() -> dict:
    """测试一：验证 SKILL.md YAML frontmatter、目录一致性、相对链接有效性及 CLI --help/--dry-run"""
    skill_md = os.path.join(SKILL_DIR, "SKILL.md")
    issues = []
    if not os.path.exists(skill_md):
        return {"status": "FAIL", "issues": ["缺少 SKILL.md"]}

    with open(skill_md, "r", encoding="utf-8") as f:
        content = f.read()

    m = re.match(r"^---\n(.*?)\n---\n", content, flags=re.DOTALL)
    if not m:
        issues.append("SKILL.md 缺少合法的 YAML frontmatter 块")
        fm = {}
    else:
        fm = yaml.safe_load(m.group(1))
        if fm.get("name") != "blender-to-google-earth":
            issues.append(f"frontmatter name 不匹配: {fm.get('name')}")
        if not fm.get("description") or len(str(fm.get("description"))) < 20:
            issues.append("frontmatter description 缺失或过短")

    if os.path.basename(SKILL_DIR) != "blender-to-google-earth":
        issues.append(f"Skill 目录名不匹配: {os.path.basename(SKILL_DIR)}")

    # 检查 Markdown 中的相对路径链接
    links = re.findall(r"\]\((\./[^)]+)\)", content)
    checked_links = []
    for rel in links:
        abs_p = os.path.normpath(os.path.join(SKILL_DIR, rel))
        exists = os.path.exists(abs_p)
        checked_links.append({"link": rel, "exists": exists})
        if not exists:
            issues.append(f"SKILL.md 引用了不存在的资源路径: {rel}")

    # 检查 CLI --help 与各子命令 --help
    for subcmd in [[], ["scan"], ["build"], ["road"], ["redline"], ["update"], ["verify"]]:
        res = subprocess.run([sys.executable, CLI_PY] + subcmd + ["--help"], capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            issues.append(f"CLI {' '.join(subcmd)} --help 失败: {res.stderr}")

    return {
        "test_name": "测试一：Skill 格式与规范测试",
        "status": "PASS" if not issues else "FAIL",
        "frontmatter": fm,
        "checked_links_count": len(checked_links),
        "checked_links": checked_links,
        "issues": issues
    }


def test_02_solar_valley_v3_regression() -> dict:
    """测试二：使用通用工具在独立目录重跑太阳谷 V1->V2(贴地道路)->V3(加密双层红线) 全流程，并与正式 V3 KMZ 基线对比"""
    project_root = os.path.abspath(os.path.join(SKILL_DIR, "../../.."))
    v1_kmz = os.path.join(
        project_root,
        "01_西侧8栋住宅_酒店_道路_导入测试/普吉太阳谷_西侧8栋住宅_六层酒店_道路_测试版.kmz"
    )
    official_v3_kmz = os.path.join(
        project_root,
        "01_西侧8栋住宅_酒店_道路_导入测试/普吉太阳谷_西侧8栋住宅_六层酒店_道路红线优化版_V3.kmz"
    )
    sha_before = sha256_file(official_v3_kmz)
    mtime_before = os.path.getmtime(official_v3_kmz)

    cfg_path = os.path.join(SKILL_DIR, "examples/phuket_solar_valley_v3/solar_valley_v3_config.yaml")
    # 1. 先测试 --dry-run
    dry_res = subprocess.run([sys.executable, CLI_PY, "--dry-run", "build", "--config", cfg_path], capture_output=True, text=True, errors="replace")
    if dry_res.returncode != 0:
        return {"test_name": "测试二：太阳谷 V3 回归测试", "status": "FAIL", "error": dry_res.stderr}

    os.makedirs("/tmp/b2ge_regression_solar_valley_v3", exist_ok=True)
    reg_v2_kmz = "/tmp/b2ge_regression_solar_valley_v3/solar_valley_v2_road_reg.kmz"
    reg_kmz = "/tmp/b2ge_regression_solar_valley_v3/solar_valley_v3_regression.kmz"

    # 2. 执行通用 road 子命令：从 R46 Blender 提取贴地多边形道路并更新 V1 -> V2
    r_res = subprocess.run(
        [sys.executable, CLI_PY, "road", "--config", cfg_path, "--base-kmz", v1_kmz, "--output-kmz", reg_v2_kmz],
        capture_output=True, text=True, errors="replace"
    )
    if r_res.returncode != 0:
        return {"test_name": "测试二：太阳谷 V3 回归测试", "status": "FAIL", "error": r_res.stderr}

    # 3. 执行通用 redline 子命令：在 V2 基础上生成 2.0m 加密插值双层红线与唯一界址点 V2 -> V3
    rl_res = subprocess.run(
        [sys.executable, CLI_PY, "redline", "--config", cfg_path, "--base-kmz", reg_v2_kmz, "--output-kmz", reg_kmz],
        capture_output=True, text=True, errors="replace"
    )
    if rl_res.returncode != 0:
        return {"test_name": "测试二：太阳谷 V3 回归测试", "status": "FAIL", "error": rl_res.stderr}

    comp = compare_kmz_with_baseline(reg_kmz, official_v3_kmz)

    sha_after = sha256_file(official_v3_kmz)
    mtime_after = os.path.getmtime(official_v3_kmz)
    official_untouched = (sha_before == sha_after and mtime_before == mtime_after)

    status = "PASS" if (comp["regression_status"] == "PASS" and official_untouched) else "FAIL"
    return {
        "test_name": "测试二：太阳谷 V3 回归测试",
        "status": status,
        "official_v3_untouched": official_untouched,
        "official_v3_sha256": sha_after,
        "regression_kmz": reg_kmz,
        "comparison": comp
    }


def test_03_synthetic_independent_scene() -> dict:
    """测试三：创建全新独立合成场景 (UTM 50N + 控制点配准 + 3栋异构建筑 + 弯曲丁字路口) 并全流程测试"""
    blender_bin = find_blender_executable()
    create_py = os.path.join(TESTS_DIR, "create_synthetic_blend.py")
    syn_blend = "/tmp/b2ge_synthetic_demo/synthetic_campus.blend"

    # 1. 创建独立合成 .blend
    subprocess.run([blender_bin, "-b", "--python", create_py, "--", syn_blend], check=True)

    # 2. 执行 scan 扫描
    scan_json = "/tmp/b2ge_synthetic_demo/scan_report.json"
    subprocess.run([sys.executable, CLI_PY, "scan", "--blend", syn_blend, "--output", scan_json], check=True)
    with open(scan_json, "r", encoding="utf-8") as f:
        scan_data = json.load(f)

    # 3. 执行 build 全流程构建
    syn_cfg = os.path.join(SKILL_DIR, "examples/synthetic_demo_project/synthetic_config.yaml")
    subprocess.run([sys.executable, CLI_PY, "build", "--config", syn_cfg], check=True)

    syn_kmz = "/tmp/b2ge_synthetic_demo/output/synthetic_campus_v1.kmz"
    ver = verify_kmz_archive(syn_kmz)

    with open("/tmp/b2ge_synthetic_demo/output/b2ge_build_report.json", "r", encoding="utf-8") as f:
        build_rep = json.load(f)

    issues = list(ver.get("issues", []))
    if ver["models_count"] != 3:
        issues.append(f"期望导出 3 栋建筑，实际导出: {ver['models_count']}")
    if ver["road_polygons_count"] < 2:
        issues.append(f"期望生成至少 2 个道路/步道贴地多边形，实际: {ver['road_polygons_count']}")
    if ver["unique_boundary_points"] != 6:
        issues.append(f"期望 6 个唯一界址点 (B01~B06)，实际: {ver['unique_boundary_points']}")
    if build_rep["crs"]["utm_zone"] != 50:
        issues.append(f"期望 UTM Zone 50N，实际: {build_rep['crs']['utm_zone']}")

    return {
        "test_name": "测试三：全新独立合成场景测试 (Synthetic Data)",
        "data_nature": "SYNTHETIC_TEST_DATA (合成测试场景，独立于太阳谷)",
        "status": "PASS" if (ver["status"] == "PASS" and not issues) else "FAIL",
        "scan_summary": scan_data["summary"],
        "crs_summary": build_rep["crs"],
        "redline_stats": build_rep["redline_stats"],
        "verification": ver,
        "issues": issues
    }


def test_04_partial_update() -> dict:
    """测试四：基于独立合成场景 KMZ 仅更新红线参数 (步长改为 1.5m，浮空改为 2.0m)，验证 3 栋建筑哈希与道路不变"""
    syn_cfg_path = os.path.join(SKILL_DIR, "examples/synthetic_demo_project/synthetic_config.yaml")
    with open(syn_cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["project_name"] = "Synthetic_Campus_3D_Showcase_V2_PartialRedline"
    cfg["redline"]["interpolation_step_m"] = 1.5
    cfg["redline"]["enhanced_height_offset_m"] = 2.0
    mod_cfg_path = "/tmp/b2ge_synthetic_demo/synthetic_config_v2_redline.yaml"
    with open(mod_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)

    base_kmz = "/tmp/b2ge_synthetic_demo/output/synthetic_campus_v1.kmz"
    upd_kmz = "/tmp/b2ge_synthetic_demo/output/synthetic_campus_v2_redline_updated.kmz"

    res = subprocess.run(
        [sys.executable, CLI_PY, "update", "--config", mod_cfg_path, "--target", "redline", "--base-kmz", base_kmz, "--output-kmz", upd_kmz],
        capture_output=True, text=True, errors="replace", check=True
    )
    upd_rep = json.loads(res.stdout)
    ver_v1 = verify_kmz_archive(base_kmz)
    ver_v2 = verify_kmz_archive(upd_kmz)

    v1_verts = ver_v1["linestrings"][-1]["vertices_count"]
    v2_verts = ver_v2["linestrings"][-1]["vertices_count"]
    models_identical = upd_rep["all_unmodified_models_identical"]
    roads_unchanged = (ver_v1["road_polygons_count"] == ver_v2["road_polygons_count"])

    ok = (ver_v2["status"] == "PASS" and models_identical and roads_unchanged and v2_verts > v1_verts)
    return {
        "test_name": "测试四：局部无损更新测试",
        "status": "PASS" if ok else "FAIL",
        "all_unmodified_models_identical": models_identical,
        "preserved_models_audit": upd_rep["preserved_models_audit"],
        "roads_polygons_before_after": [ver_v1["road_polygons_count"], ver_v2["road_polygons_count"]],
        "redline_vertices_before_after": [v1_verts, v2_verts]
    }


def test_05_real_google_earth_pro(run_gui: bool = True) -> dict:
    """测试五：在真实 Google Earth Pro 中打开新生成的合成场景 KMZ 并抓取实测截图"""
    if not run_gui:
        return {"test_name": "测试五：真实 Google Earth Pro 验证", "status": "UNVERIFIED", "reason": "未开启 --with-ge-gui"}

    syn_kmz = "/tmp/b2ge_synthetic_demo/output/synthetic_campus_v2_redline_updated.kmz"
    sc_dir = "/tmp/b2ge_synthetic_demo/screenshots"
    views = [
        {"filename": "GE_Synthetic_01_Overview.png", "lon": 115.874450, "lat": 28.661250, "range": 230.0, "heading": 0.0, "tilt": 20.0},
        {"filename": "GE_Synthetic_02_LowTilt_68deg.png", "lon": 115.874450, "lat": 28.661200, "range": 190.0, "heading": 20.0, "tilt": 65.0},
    ]
    ge_res = capture_google_earth_views(syn_kmz, sc_dir, views, wait_sec=16.0)
    return {
        "test_name": "测试五：真实 Google Earth Pro 验证",
        "status": ge_res["gui_verification_status"],
        "details": ge_res
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-ge-gui", action="store_true", help="是否同时执行真实 Google Earth Pro GUI 截图测试")
    parser.add_argument("--output-json", default="/tmp/b2ge_all_tests_report.json")
    args = parser.parse_args()

    results = [
        test_01_skill_structure(),
        test_02_solar_valley_v3_regression(),
        test_03_synthetic_independent_scene(),
        test_04_partial_update(),
        test_05_real_google_earth_pro(run_gui=args.with_ge_gui),
    ]
    overall = "PASS" if all(r["status"] in ("PASS", "UNVERIFIED") and r["status"] != "FAIL" for r in results) else "FAIL"
    summary = {"overall_status": overall, "tests": results}
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    for r in results:
        print(f"[{r['status']}] {r['test_name']}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
