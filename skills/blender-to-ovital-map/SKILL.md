---
name: blender-to-ovital-map
description: >-
  将建筑 Blender/Google Earth 成果中的独立 OBJ/MTL/贴图及 KMZ 地理定位数据制作成 Mac 奥维互动地图可手动导入的离线模型包；检查 OBJ 坐标轴、建筑高度、WGS84 锚点、相对地面高度与材质。用于奥维三维建筑导入、合并多栋建筑、纠正模型整体悬空或坐标轴错用，不操作奥维 GUI，不生成伪造的 ovmod。
---

# Blender → 奥维互动地图三维模型导入（独立 Skill V1.0）

## 职责边界

本 Skill 的目标是为奥维互动地图制作 OBJ/MTL/贴图、建筑定位数据及可选的二维道路红线 KML，**不是 Google Earth 导出 Skill**。

- Google Earth KMZ 的生成、Google Earth 贴地道路和红线显示，交由独立的 blender-to-google-earth Skill。
- 奥维导入路径、OBJ 合并、奥维高度模式与离线验证，由本 Skill 单独管理。
- 不修改另一个 Skill；不调用奥维 GUI，不操作收藏夹或缓存；不伪造 ovmod。
- V1 已自动化并测试的是「已有 Google Earth KMZ 建筑锚点 + 对应独立 OBJ/MTL/贴图」场景。
- 只有 .blend 而没有 KMZ/独立 OBJ 的任务，先用 Blender 按各栋建筑导出 OBJ/MTL/贴图并取得可靠地理锚点；**本 V1 不谎称可以直接处理任意 .blend 并完成地理定位**。

## 触发场景

1. 已有 KMZ 在 Google Earth 能显示建筑，但在奥维导入 KMZ 后只出现道路；
2. 需要将多栋建筑合并为一套奥维易于导入的 OBJ 模型；
3. 需要检查 OBJ 垂直轴、独立建筑与合体模型相对位置、建筑异常升高或悬空；
4. 需要生成建筑坐标表及道路/红线的独立 KML，不要求 AI 操作奥维软件。

## 输入与前置核验

至少提供：来源 KMZ（内含 doc.kml 的 Model 坐标）、与 KML 对应的一套独立 OBJ、每个 OBJ 的 MTL 和引用贴图；明确一栋作为地理锚点。建议先确认 OBJ 上轴：Y-up 或 Z-up。

先运行只读操作：

    python3 scripts/ovital_cli.py inspect --kmz /绝对路径/项目.kmz

再执行预检：

    python3 scripts/ovital_cli.py build \
      --kmz /绝对路径/项目.kmz \
      --obj-dir /绝对路径/单体OBJ目录 \
      --anchor "基准建筑名称" \
      --obj-up-axis Y \
      --output /绝对路径/新的空输出目录 \
      --dry-run

- 预检检查全部 KML Model 锚点、模型文件、几何高度、MTL与贴图可用性、水平偏移。
- 如果各栋存在非零旋转、倾斜、非1缩放或不同高度模式，当前实现会报错停止，**不允许静默忽略变换**。
- 如缺少 OBJ，必须先从源 DAE 或 Blender 合法导出对应的单栋 OBJ/MTL/贴图，再继续；不得只改 DAE 扩展名。

## 正式离线构建

确认预检后，去掉 --dry-run 并使用空输出目录：

    python3 scripts/ovital_cli.py build \
      --kmz /绝对路径/项目.kmz \
      --obj-dir /绝对路径/单体OBJ目录 \
      --anchor "基准建筑名称" \
      --obj-up-axis Y \
      --output /绝对路径/新的空输出目录

输出包括：

- 奥维_建筑合体模型.obj（实际建筑数量由源 KMZ 决定）
- 奥维_建筑合体模型.mtl 及 textures/ 贴图（按哈希去重）
- 奥维_定位参数.json（所有建筑相对锚点的米制平面偏移）
- 奥维_单体定位清单.csv
- 道路与红线_独立图层.kml（去掉所有 KML Model，避免奥维只读取二维元素）
- README_奥维导入说明.md

默认不会生成 DAE 或 ovmod。OBJ 作为已在 Mac 奥维中由用户实测能导入的优先格式；其他格式须通过独立验证。

再次核验：

    python3 scripts/ovital_cli.py verify --package /绝对路径/输出目录

此工具检验对象数量、顶点和面、每栋垂直底点和高度、材质引用、KML XML。PASS 只表示静态文件通过，**不等于 Mac 奥维 GUI 运行通过**。

## 三条绝对不可违反的经验

1. **OBJ 上轴**：Blender 原始场景常为 Z-up，本项目导出的 OBJ 则为 Y-up。对于这类 OBJ，水平东向加到 X，水平北向加到负 Z，垂直高度加到 Y；不得把北向偏移加到 OBJ Y。见 references/01_轴向与合体模型.md。
2. **高度基准**：KML relativeToGround=0.78m 不是绝对海拔 11.78m。绝对海拔需要目标软件地形数据和真实基准，不得用假定的 11.0+0.78 推算。见 references/02_高度模式与奥维手动验收.md。
3. **单一锚点限制**：合体 OBJ 对各栋应用正确的平面相对位移，但在奥维内整个合体模型只有一套高度锚点，并不会让每栋沿真实地形分别接地；山坡起伏可能产生局部悬空/埋地。须如实说明。

## 成功案例与独立性

太阳谷案例来源于 ../项目目录/02_奥维互动地图_8栋住宅及酒店_导入测试/V2_建筑高度与坐标轴修正版/，具有8栋住宅、六层酒店、合并 OBJ、真实 Mac 奥维截图；实际成功设置为 WGS84，经纬度 98.33184944 / 8.09992113，关闭 GCJ-02，高度模式相对于地面 0.78m，旋转0°，比例1。这些是**该案例参数，不是默认硬编码值**。

详见 examples/太阳谷实战复盘.md。改造逻辑后须跑 tests/test_ovital_cli.py 的合成样例测试与太阳谷 V2 回归测试。

## 文件安全与 GitHub

不得覆盖原始 V3 KMZ、R46 Blender、原奥维 V2 OBJ；新输出放空目录；优先只提交 Skill 的脚本、文档、配置和小规模测试数据，避免重复上传大模型。GitHub 以现有 Google Earth 工程分支管理两个独立 Skill，不触及 D1 施工图分支或 main。