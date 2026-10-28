---
name: blender-to-google-earth
description: >-
  Blender 三维模型与 Google Earth 地理场景融合 (V1.0)。当用户需要将 Blender (.blend) 中的建筑、园区、道路或地块红线导出并配准到 Google Earth Pro (.kmz/.kml)，或需要修复 Google Earth 中的道路断口/台阶、低视角红线穿地消失、界址点重复标签、局部替换 KMZ 模型并执行自动化质量验收时使用此技能。
---

# Blender 三维模型与 Google Earth 地理场景融合 (`blender-to-google-earth`)

本技能提供一套经过真实项目验证的模块化工具链，用于将 Blender (`.blend`) 建筑规划模型与 Google Earth Pro 真实卫星地形进行高质量三维融合展示。

---

## 一、何时触发本技能與用户需提供的资料

### 1. 触发场景
- 用户希望将 `.blend` 场景中的指定建筑、道路导入 Google Earth Pro 生成 `.kmz`；
- 已有 `.kmz` 中的道路出现断口、台阶、悬空或突兀水泥厚路基，需改为贴地多边形修复；
- 地块红线在倾斜/低视角观察时穿入山坡消失，或界址点标签出现重影；
- 需要在不改动其余建筑的前提下，局部更新 `.kmz` 中的单栋建筑、道路或红线图层。

### 2. 用户需提供的输入资料与快速检查
1. **三维源模型**：`.blend` 文件（或已有 `.kmz` 归档）。
2. **目标范围说明**：需要导出的建筑名称/集合，是否包含道路与地块红线。
3. **地理定位依据（三选一）**：
   - **已知 UTM 原点 (`utm_offset`)**：给定 UTM 分带（1～60 N/S）及 Blender 原点对应的 `(E0, N0)`；
   - **控制点对 (`control_points`)**：给定至少 2 个 Blender 局部坐标与真实 WGS84/UTM 坐标的对应点（或地块红线 `.kml`/`.json`）；
   - **单点经纬度锚点 (`local_lonlat`)**：仅提供项目大致中心经纬度（仅生成候选展示定位）。

> **快速检查输入命令**：对未知 `.blend` 文件，必须先运行场景扫描器了解集合、实例 (`Collection Instance`) 与网格结构，严禁盲目猜测对象名：
> ```bash
> python3 ./scripts/b2ge_cli.py scan --blend <path/to/scene.blend> --output /tmp/scene_scan.json
> ```

---

## 二、五大工作模式自动决策机制与脚本调用

根据用户需求，选择最小必要工作模式（通过统一入口 [`b2ge_cli.py`](./scripts/b2ge_cli.py) 执行，支持 `--dry-run` 预检）：

| 工作模式 | 适用条件 | 调用子命令与核心脚本 |
| :--- | :--- | :--- |
| **模式1：新项目导入 (`build`)** | 从 `.blend` + 地理配准资料从零生成包含建筑、贴地道路与红线的 `.kmz` | `python3 ./scripts/b2ge_cli.py build --config project_config.yaml`<br>串联 [`blender_extractor.py`](./scripts/blender_extractor.py) → [`road_processor.py`](./scripts/road_processor.py) → [`redline_processor.py`](./scripts/redline_processor.py) → [`kmz_builder.py`](./scripts/kmz_builder.py) |
| **模式2：道路修复 (`road`)** | 已有 `.kmz` 建筑正常，仅需将断裂/厚路基的 3D 道路替换为 KML 贴地多边形 | `python3 ./scripts/b2ge_cli.py road --config project_config.yaml --base-kmz old.kmz --output-kmz new_road.kmz` |
| **模式3：红线优化 (`redline`)** | 已有 `.kmz` 建筑与道路正常，仅需修复低视角红线穿地消失及界址点重复标签 | `python3 ./scripts/b2ge_cli.py redline --config project_config.yaml --base-kmz old.kmz --output-kmz new_redline.kmz` |
| **模式4：局部模型更新 (`update`)** | 已有 `.kmz` 仅替换指定图层或单栋建筑，其余资产必须保持 SHA256 锁定不变 | `python3 ./scripts/b2ge_cli.py update --config project_config.yaml --target road\|redline --base-kmz old.kmz --output-kmz updated.kmz` |
| **模式5：成果检查 (`verify`)** | 对生成的 `.kmz` 执行 XML/DAE/贴图完整性检查、基线对比及真实 Google Earth Pro 截图验收 | `python3 ./scripts/b2ge_cli.py verify --kmz target.kmz [--baseline-kmz base.kmz] [--launch-ge]`（由 [`kmz_verifier.py`](./scripts/kmz_verifier.py) 驱动） |

- **标准配置模板**：复制 [`templates/project_config.yaml`](./templates/project_config.yaml) 到目标项目工作目录修改参数。
- **环境说明**：`b2ge_cli.py` 在系统 `python3`（含 `PyYAML`, `shapely`）下运行，内部自动探测并调用后台 Blender 执行 `blender_scanner.py` 与 `blender_extractor.py`（Blender 端脚本仅依赖原生自带模块 `bpy`, `bmesh`, `json`）。

---

## 三、关键技术准则与常见故障定位

1. **建筑实例导出为空或变形**：
   - 检查对象是否为 `EMPTY (instance_type='COLLECTION')`。`blender_extractor.py` 会自动展开 `instance_collection` 并将旋转与非均匀缩放烘焙至局部正东-正北顶点，KML `<Model>` 保持 `Scale=1,1,1`。详见 [01_blender_to_dae_conversion.md](./references/01_blender_to_dae_conversion.md)。
2. **建筑单面透明或贴图丢失**：
   - 确保 `.dae` 注入了 `<double_sided>1</double_sided>`，且 `<init_from>` 为同目录纯文件名。详见 [02_kml_kmz_dae_organization.md](./references/02_kml_kmz_dae_organization.md)。
3. **道路断口、台阶与多边形重叠闪烁 (Z-fighting)**：
   - 展示型道路严禁默认采用 V1 离散 3D 切片与 `-2.20m` 厚裙边（失败案例见 [04_v1_road_failure_case_study.md](./references/04_v1_road_failure_case_study.md)）。
   - 统一采用 `KML Polygon + clampToGround`，并开启 `subtract_previous: true` 执行 Shapely `unary_union` 与 `difference` 布尔差集。详见 [05_v2_draped_road_polygon_guide.md](./references/05_v2_draped_road_polygon_guide.md)。
4. **低视角斜视时红线切入山坡消失或出现双轨重影**：
   - 采用可配步长加密插值（如 `interpolation_step_m: 2.0`）+ 双层红线架构：默认开启 `relativeToGround` 浮空增强线（如 `+1.0m`），默认隐藏 `clampToGround` 贴地线（避免视差双影），界址点独立建组去重。详见 [06_v3_redline_and_labels_guide.md](./references/06_v3_redline_and_labels_guide.md)。

---

## 四、诚实性边界、原始文件安全与完成标准

1. **严禁自动做出测绘级承诺**：
   - 缺少持牌测量师联测控制桩或仅凭单点经纬度/目视配准时，必须将配准状态标为 `CANDIDATE_ALIGNMENT`，严禁宣称“毫米级真实定位”或“可用于施工放线”。详见 [03_crs_and_georeferencing.md](./references/03_crs_and_georeferencing.md)。
2. **原始文件安全铁律**：
   - 严禁修改用户的原始 `.blend` 工程；局部更新时严禁原地覆盖输入基线 `.kmz`，必须输出到新路径并核验未修改建筑的 `dae_sha256` 100% 一致。
3. **真正完成的判定标准**：
   - `b2ge_cli.py verify` 静态结构检查必须为 `PASS`（零缺失贴图、零孤儿文件、零重复界址点）；
   - 环境具备 Google Earth Pro 时，执行真实加载与多视角（鸟瞰、45°中景、70°+极低斜视）截图核验；若环境无法运行 GUI，必须如实标记 `gui_verification_status: UNVERIFIED`。详见 [07_google_earth_pro_qa_checklist.md](./references/07_google_earth_pro_qa_checklist.md) 与太阳谷复盘案例 [solar_valley_v1_to_v3_review.md](./examples/phuket_solar_valley_v3/solar_valley_v1_to_v3_review.md)。
