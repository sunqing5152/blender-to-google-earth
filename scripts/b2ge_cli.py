#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender-to-google-earth 统一命令行总入口 (b2ge_cli.py)
支持六大工作子命令：
  1. scan    : 扫描任意 Blender 场景对象、集合实例与材质
  2. build   : [模式1 新项目导入] 从 Blender + 配准/红线配置全流程构建 KMZ
  3. road    : [模式2 道路修复] 提取贴地多边形道路并无损更新至已有 KMZ
  4. redline : [模式3 红线优化] 生成双层加密插值红线与唯一界址点并无损更新至已有 KMZ
  5. update  : [模式4 局部模型更新] 局部替换指定建筑/道路/红线并校验其余资产 SHA256 不变
  6. verify  : [模式5 成果检查] 检验 KMZ/KML/DAE/贴图完整性、基线对比及真实 Google Earth Pro 截图验收
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from geo_transform import GeoTransformer
from road_processor import process_raw_roads_to_clean_data, build_road_styles_elements, build_road_folder_element
from redline_processor import build_redline_styles_and_folder
from kmz_builder import build_full_kmz, partial_update_kmz
from kmz_verifier import verify_kmz_archive, compare_kmz_with_baseline, capture_google_earth_views


def load_config_file(cfg_path: str) -> Dict[str, Any]:
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    ext = os.path.splitext(cfg_path)[1].lower()
    with open(cfg_path, "r", encoding="utf-8") as f:
        if ext in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(cfg_path))
    data["_config_dir"] = base_dir
    return data


def resolve_path(p: Optional[str], base_dir: str) -> Optional[str]:
    if not p:
        return None
    expanded = os.path.expanduser(p)
    if os.path.isabs(expanded):
        return expanded
    return os.path.abspath(os.path.join(base_dir, expanded))


def find_blender_executable(explicit_bin: Optional[str] = None) -> str:
    candidates = [
        explicit_bin,
        os.environ.get("BLENDER_BIN"),
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/usr/bin/blender",
        "/usr/local/bin/blender",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError("未找到可用的 Blender 可执行文件，请通过 --blender-bin 或环境变量 BLENDER_BIN 指定")


def cmd_scan(args) -> int:
    blend_file = os.path.abspath(os.path.expanduser(args.blend))
    if not os.path.exists(blend_file):
        print(f"[ERROR] Blender 文件不存在: {blend_file}", file=sys.stderr)
        return 1
    out_json = os.path.abspath(os.path.expanduser(args.output))
    blender_bin = find_blender_executable(args.blender_bin)
    scanner_py = os.path.join(SCRIPT_DIR, "blender_scanner.py")
    cmd = [blender_bin, "-b", blend_file, "--python", scanner_py, "--", "--output", out_json]
    if args.name_regex:
        cmd.extend(["--name-regex", args.name_regex])
    if args.collection:
        cmd.extend(["--collection", args.collection])
    if args.dry_run:
        print(f"[DRY-RUN] 将执行场景扫描命令: {' '.join(cmd)}")
        return 0
    subprocess.run(cmd, check=True)
    with open(out_json, "r", encoding="utf-8") as f:
        rep = json.load(f)
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=2))
    return 0


def cmd_build(args) -> int:
    cfg = load_config_file(args.config)
    cdir = cfg["_config_dir"]
    blend_file = resolve_path(cfg.get("blender_file"), cdir)
    out_dir = resolve_path(cfg.get("output_dir", "./output"), cdir)
    models_dir = os.path.join(out_dir, "models")
    out_kmz = resolve_path(cfg.get("output_kmz", os.path.join(out_dir, "scene_showcase.kmz")), cdir)
    out_kml = resolve_path(cfg.get("output_kml", os.path.join(out_dir, "doc.kml")), cdir)

    if not blend_file or not os.path.exists(blend_file):
        raise FileNotFoundError(f"配置中的 blender_file 不存在: {blend_file}")

    geo = GeoTransformer(cfg["coordinate_reference"])
    if "redline" in cfg and cfg["redline"].get("source_json"):
        cfg["redline"]["source_json"] = resolve_path(cfg["redline"]["source_json"], cdir)
    if "redline" in cfg and cfg["redline"].get("source_kml"):
        cfg["redline"]["source_kml"] = resolve_path(cfg["redline"]["source_kml"], cdir)

    if args.dry_run:
        print(json.dumps({
            "mode": "build (dry-run)",
            "blender_file": blend_file,
            "output_kmz": out_kmz,
            "buildings_count": len(cfg.get("buildings", [])),
            "roads_enabled": bool(cfg.get("roads", {}).get("enabled", True)),
            "redline_enabled": bool(cfg.get("redline", {}).get("enabled", True)),
            "crs_summary": geo.summary_dict()
        }, ensure_ascii=False, indent=2))
        return 0

    os.makedirs(models_dir, exist_ok=True)
    blender_bin = find_blender_executable(args.blender_bin or cfg.get("blender_executable"))
    extractor_py = os.path.join(SCRIPT_DIR, "blender_extractor.py")

    with tempfile.TemporaryDirectory() as tmpdir:
        task_json = os.path.join(tmpdir, "extract_task.json")
        res_json = os.path.join(tmpdir, "extract_result.json")
        task_payload = {
            "models_dir": models_dir,
            "site_gamma_deg": geo.site_gamma_deg,
            "crs_rotation_deg": geo.rotation_deg,
            "extract_buildings": True,
            "buildings": cfg.get("buildings", []),
            "extract_roads": bool(cfg.get("roads", {}).get("enabled", True)),
            "roads": cfg.get("roads", {}),
            "export_glb_path": resolve_path(cfg.get("output_glb"), cdir) if cfg.get("export_glb") else None,
            "material_classification_rules": cfg.get("material_classification_rules")
        }
        with open(task_json, "w", encoding="utf-8") as f:
            json.dump(task_payload, f, ensure_ascii=False, indent=2)

        subprocess.run([blender_bin, "-b", blend_file, "--python", extractor_py, "--", "--task-json", task_json, "--output-json", res_json], check=True)
        with open(res_json, "r", encoding="utf-8") as f:
            ext_res = json.load(f)

    road_styles, road_folder = None, None
    if ext_res.get("raw_roads") and cfg.get("roads", {}).get("enabled", True):
        clean_roads = process_raw_roads_to_clean_data(ext_res["raw_roads"])
        road_styles = build_road_styles_elements(clean_roads)
        road_folder = build_road_folder_element(clean_roads, geo, folder_name=cfg["roads"].get("folder_name", "03_小区内部道路与入口硬质铺装 (贴地多边形)"))

    rl_styles, rl_folder, rl_stats = None, None, None
    if cfg.get("redline", {}).get("enabled", True):
        rl_styles, rl_folder, rl_stats = build_redline_styles_and_folder(cfg["redline"], geo)

    build_summary = build_full_kmz(
        doc_name=cfg.get("project_name", "Blender_GoogleEarth_Showcase"),
        doc_desc=cfg.get("project_description", f"自动生成展示模型 | 配准状态: {geo.registration_status}"),
        lookat_cfg=cfg.get("look_at", {}),
        buildings_info=ext_res["buildings"],
        geo=geo,
        models_dir=models_dir,
        out_kml_path=out_kml,
        out_kmz_path=out_kmz,
        road_styles=road_styles,
        road_folder=road_folder,
        redline_styles=rl_styles,
        redline_folder=rl_folder,
    )
    qa_report = verify_kmz_archive(out_kmz)
    final_rep = {"build": build_summary, "crs": geo.summary_dict(), "redline_stats": rl_stats, "verification": qa_report}
    rep_path = os.path.join(out_dir, "b2ge_build_report.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(final_rep, f, ensure_ascii=False, indent=2)
    print(f"[B2GE_BUILD] 完成 KMZ 构建与门禁校验 ({qa_report['status']}) -> {out_kmz}")
    return 0 if qa_report["status"] == "PASS" else 1


def cmd_road(args) -> int:
    cfg = load_config_file(args.config)
    cdir = cfg["_config_dir"]
    base_kmz = os.path.abspath(os.path.expanduser(args.base_kmz)) if args.base_kmz else resolve_path(cfg.get("base_kmz"), cdir)
    out_kmz = os.path.abspath(os.path.expanduser(args.output_kmz)) if args.output_kmz else resolve_path(cfg.get("output_kmz"), cdir)
    out_kml = resolve_path(cfg.get("output_kml"), cdir)
    blend_file = resolve_path(cfg.get("blender_file"), cdir)
    geo = GeoTransformer(cfg["coordinate_reference"])

    if args.dry_run:
        print(json.dumps({"mode": "road (dry-run)", "base_kmz": base_kmz, "output_kmz": out_kmz}, ensure_ascii=False, indent=2))
        return 0

    blender_bin = find_blender_executable(args.blender_bin or cfg.get("blender_executable"))
    extractor_py = os.path.join(SCRIPT_DIR, "blender_extractor.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        task_json = os.path.join(tmpdir, "road_task.json")
        res_json = os.path.join(tmpdir, "road_res.json")
        with open(task_json, "w", encoding="utf-8") as f:
            json.dump({"models_dir": tmpdir, "extract_buildings": False, "extract_roads": True, "roads": cfg["roads"]}, f)
        subprocess.run([blender_bin, "-b", blend_file, "--python", extractor_py, "--", "--task-json", task_json, "--output-json", res_json], check=True)
        with open(res_json, "r", encoding="utf-8") as f:
            raw_roads = json.load(f)["raw_roads"]

    clean_roads = process_raw_roads_to_clean_data(raw_roads)
    r_styles = build_road_styles_elements(clean_roads)
    r_folder = build_road_folder_element(clean_roads, geo, folder_name=cfg["roads"].get("folder_name", "03_小区内部道路与入口硬质铺装 (贴地多边形)"))
    upd = partial_update_kmz(base_kmz, out_kmz, out_kml_path=out_kml, replace_road_styles=r_styles, replace_road_folder=r_folder)
    print(json.dumps(upd, ensure_ascii=False, indent=2))
    return 0 if upd["all_unmodified_models_identical"] else 1


def cmd_redline(args) -> int:
    cfg = load_config_file(args.config)
    cdir = cfg["_config_dir"]
    base_kmz = os.path.abspath(os.path.expanduser(args.base_kmz)) if args.base_kmz else resolve_path(cfg.get("base_kmz"), cdir)
    out_kmz = os.path.abspath(os.path.expanduser(args.output_kmz)) if args.output_kmz else resolve_path(cfg.get("output_kmz"), cdir)
    out_kml = resolve_path(cfg.get("output_kml"), cdir)
    geo = GeoTransformer(cfg["coordinate_reference"])
    if cfg.get("redline", {}).get("source_json"):
        cfg["redline"]["source_json"] = resolve_path(cfg["redline"]["source_json"], cdir)
    if cfg.get("redline", {}).get("source_kml"):
        cfg["redline"]["source_kml"] = resolve_path(cfg["redline"]["source_kml"], cdir)

    if args.dry_run:
        print(json.dumps({"mode": "redline (dry-run)", "base_kmz": base_kmz, "output_kmz": out_kmz}, ensure_ascii=False, indent=2))
        return 0

    rl_styles, rl_folder, rl_stats = build_redline_styles_and_folder(cfg["redline"], geo)
    upd = partial_update_kmz(
        base_kmz, out_kmz, out_kml_path=out_kml,
        new_doc_name=cfg.get("project_name"),
        new_doc_desc=cfg.get("project_description"),
        new_lookat_cfg=cfg.get("look_at"),
        replace_redline_styles=rl_styles,
        replace_redline_folder=rl_folder
    )
    upd["redline_stats"] = rl_stats
    print(json.dumps(upd, ensure_ascii=False, indent=2))
    return 0 if upd["all_unmodified_models_identical"] else 1


def cmd_update(args) -> int:
    return cmd_redline(args) if args.target == "redline" else cmd_road(args)


def cmd_verify(args) -> int:
    kmz_path = os.path.abspath(os.path.expanduser(args.kmz))
    rep = verify_kmz_archive(kmz_path)
    if args.baseline_kmz:
        base_path = os.path.abspath(os.path.expanduser(args.baseline_kmz))
        rep["baseline_comparison"] = compare_kmz_with_baseline(kmz_path, base_path)
    if args.launch_ge:
        views = [{"filename": "GE_Verify_01_Overview.png"}, {"filename": "GE_Verify_02_LowTilt.png", "tilt": 70.0, "range": 220.0}]
        if args.views_json and os.path.exists(args.views_json):
            with open(args.views_json, "r", encoding="utf-8") as f:
                views = json.load(f)
        sc_dir = os.path.abspath(os.path.expanduser(args.screenshots_dir or os.path.join(os.path.dirname(kmz_path), "screenshots_verify")))
        ge_res = capture_google_earth_views(kmz_path, sc_dir, views, wait_sec=float(args.wait_sec))
        rep["gui_verification_status"] = ge_res["gui_verification_status"]
        rep["gui_details"] = ge_res
    if args.output_report:
        with open(os.path.abspath(os.path.expanduser(args.output_report)), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["status"] == "PASS" else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b2ge_cli.py",
        description="Blender 三维模型与 Google Earth 地理场景融合 (blender-to-google-earth) 统一命令行工具"
    )
    parser.add_argument("--blender-bin", help="指定 Blender 可执行文件路径 (默认自动探测)")
    parser.add_argument("--dry-run", action="store_true", help="仅校验配置并输出执行计划，不执行实际写盘或 Blender 导出")

    sub = parser.add_subparsers(dest="subcommand", required=True, help="工作模式子命令")

    # 1. scan
    p_scan = sub.add_parser("scan", help="扫描任意 .blend 场景对象、集合实例、材质与包围盒")
    p_scan.add_argument("--blend", required=True, help="输入 .blend 文件路径")
    p_scan.add_argument("--output", default="/tmp/blender_scene_scan.json", help="输出 JSON 报告路径")
    p_scan.add_argument("--name-regex", help="按对象名称正则表达式过滤")
    p_scan.add_argument("--collection", help="按所属集合名称过滤")

    # 2. build (模式1：新项目导入)
    p_build = sub.add_parser("build", help="[模式1 新项目导入] 根据配置文件全流程生成 DAE、贴地道路、加密红线与 KMZ")
    p_build.add_argument("--config", required=True, help="项目配置文件路径 (.yaml 或 .json)")

    # 3. road (模式2：道路修复)
    p_road = sub.add_parser("road", help="[模式2 道路修复] 生成 KML 贴地多边形道路并无损更新至已有 KMZ")
    p_road.add_argument("--config", required=True, help="项目配置文件路径 (.yaml 或 .json)")
    p_road.add_argument("--base-kmz", help="输入的待修复基准 KMZ 路径")
    p_road.add_argument("--output-kmz", help="修复后的新 KMZ 输出路径 (严禁与 base-kmz 相同)")

    # 4. redline (模式3：红线优化)
    p_rl = sub.add_parser("redline", help="[模式3 红线优化] 生成双层加密插值红线与唯一界址点并无损更新至已有 KMZ")
    p_rl.add_argument("--config", required=True, help="项目配置文件路径 (.yaml 或 .json)")
    p_rl.add_argument("--base-kmz", help="输入的待优化基准 KMZ 路径")
    p_rl.add_argument("--output-kmz", help="优化后的新 KMZ 输出路径 (严禁与 base-kmz 相同)")

    # 5. update (模式4：局部模型更新)
    p_upd = sub.add_parser("update", help="[模式4 局部更新] 仅替换指定图层(road/redline)并审计未改动建筑资产哈希")
    p_upd.add_argument("--config", required=True, help="项目配置文件路径 (.yaml 或 .json)")
    p_upd.add_argument("--target", choices=["road", "redline"], required=True, help="局部更新的目标图层类型")
    p_upd.add_argument("--base-kmz", required=True, help="输入的基准 KMZ 路径")
    p_upd.add_argument("--output-kmz", required=True, help="局部更新后的新 KMZ 输出路径")

    # 6. verify (模式5：成果检查)
    p_ver = sub.add_parser("verify", help="[模式5 成果检查] 执行 KMZ 静态门禁、基线对比与可选 Google Earth Pro 真实截图验收")
    p_ver.add_argument("--kmz", required=True, help="待检查的 KMZ 文件路径")
    p_ver.add_argument("--baseline-kmz", help="可选：用于回归对比的基线 KMZ 文件路径")
    p_ver.add_argument("--launch-ge", action="store_true", help="可选：在 macOS 上启动真实 Google Earth Pro 抓取实测截图")
    p_ver.add_argument("--views-json", help="可选：自定义截图视角 JSON 文件路径")
    p_ver.add_argument("--screenshots-dir", help="截图输出目录")
    p_ver.add_argument("--wait-sec", type=float, default=12.0, help="Google Earth 飞行等待秒数 (默认 12s)")
    p_ver.add_argument("--output-report", help="将验证报告保存为 JSON 文件")

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    dispatch = {
        "scan": cmd_scan,
        "build": cmd_build,
        "road": cmd_road,
        "redline": cmd_redline,
        "update": cmd_update,
        "verify": cmd_verify,
    }
    return dispatch[args.subcommand](args)


if __name__ == "__main__":
    sys.exit(main())
