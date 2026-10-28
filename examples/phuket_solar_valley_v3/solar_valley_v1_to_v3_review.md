# 普吉太阳谷 Google Earth 三维融合 (V1～V3) 完整技术复盘与经验提炼

本文档基于普吉太阳谷（Phuket Sun Valley）第一阶段三维展示项目从 V1、V2 到 V3 的真实代码演进、Google Earth Pro 实测截图与工程审计记录编写，作为 `blender-to-google-earth` Skill 的基准案例参考。

---

## 一、V1～V3 十二项核心技术过程还原

### 1. Blender 场景对象、集合、实例与材质的识别
- **原始场景结构**：源工程 `R46_100秒_低机位斜俯视与庭院生活.blend` 包含大量集合与对象（地形、61户别墅、酒店、道路、绿植、车辆、灯光及室内家具）。
- **集合实例（Collection Instance）机制**：西侧 8 栋住宅（`D1_独栋四层`～`D8_独栋四层`）及六层酒店（`酒店_六层_首层超市_临街通高玻璃`）并非直接的 `MESH` 对象，而是引用母版资产集合的 `EMPTY` 实例对象（`obj.instance_type == 'COLLECTION'`，通过 `obj.instance_collection.all_objects` 访问内部网格与 3D 文字 `FONT`）。

### 2. 选择性导出指定建筑（而非整场景导出）
- 针对目标建筑实例列表，遍历其 `instance_collection.all_objects`，仅提取 `MESH` 与必要な `FONT`（如建筑立面店招文字），跳过全区其他未选中的楼栋、地形网格与树木。
- 对室内细碎活动家具（沙发、床垫、水龙头等）按关键词过滤以降低面数，保留全部外立面、主体结构、屋顶光伏板及栏杆。

### 3. DAE 建筑模型转换与贴图兼容处理
- **UV 与法线**：利用 `bmesh` 合并子部件后执行 `triangulate` 与 `recalc_face_normals`，并按面法线主方向计算三向盒式投影 UV（Box UV）。
- **贴图与双面渲染**：Blender 原生 Cycles 复杂过程节点无法直接被 Google Earth 解析，因此将其映射为预生成的 `128x128` 确定性 PNG 贴图；导出 `.dae` 后通过 XML 后处理将贴图路径规范为相对文件名，并注入 `<extra><technique profile="GOOGLEEARTH"><double_sided>1</double_sided></technique></extra>`，解决单面网格在 Google Earth 中背面透明消失的问题。

### 4. UTM、WGS84 及 Blender 局部坐标转换
- 经核查，R46 场景中的 `site_ground` 边界顶点加上固定平移量 `(E0=426560.000, N0=895440.000)` 后，与测绘红线 DXF/KML 的 J01～J15 控制点在 `WGS 84 / UTM Zone 47N (EPSG:32647)` 下吻合（残差 <= 0.6mm）。
- 通过高斯-克吕格（横轴墨卡托）反算公式，将任意 `(X_bl, Y_bl)` 转换为 `(E_utm, N_utm)` 再反算为 WGS84 `(lon, lat)`，并计算场地中心子午线收敛角 $\gamma \approx -0.09369^\circ$。

### 5. 建筑实例缩放、旋转与坐标轴处理
- 将建筑网格顶点从实例局部坐标变换到世界坐标，减去建筑基底中心 `world_center`，再乘以子午线收敛角修正矩阵 `ROT_GAMMA_MAT`。
- 这样导出的每个建筑 `.dae` 自身已处于以基底中心为原点、正东（+X）正北（+Y）天顶（+Z）的局部坐标系中，因此在 KML `<Model>` 中只需设置 `<heading>0.0</heading>` 和 `<Scale>1,1,1</Scale>`，彻底避免了实例非均匀缩放在 KML 旋转后产生剪切变形（Shear）。

### 6. KML Model 定位与 KMZ 资源封装
- 每个建筑对应一个 `<Placemark><Model>`，采用 `<altitudeMode>relativeToGround</altitudeMode>`，配合建筑底部向下延伸 `-1.40m` 的灰黑色基座裙边（Plinth），消除坡地半边悬空问题。
- 将 `doc.kml`、`models/*.dae` 及 `models/*.png` 统一压缩打包为自包含 `.kmz`。

### 7. V1 道路失败的具体原因剖析
- V1 将道路切分为 10 段独立三维网格（`Road_Seg_01.dae`～`10.dae`），并添加了 `-2.20m` 的垂直厚路基裙边，且对部分路段施加了人工高度补偿（`+0.35m`、`+0.95m`）。
- **失败表现**：刚性平面切片无法贴合 Google Earth 连续起伏的 DEM 地形曲面，在段与段交界处产生明显的**台阶断口**；低视角下 `-2.20m` 的裙边暴露为突兀的**水泥厚墩侧壁**。

### 8. V2 使用 KML Polygon 贴地修复道路的完整方法
- 彻底废弃 V1 的三维切片道路 DAE，从 Blender 提取道路、人行道、入口铺装的朝上水平面片（`abs(normal.z) >= 0.5`），投影到 2D 平面。
- 使用 `Shapely` 执行 `unary_union` 合并破碎三角面，并按视觉优先级执行布尔差集 `difference`（人行道减去车行道，铺装减去车行道与人行道），确保图层间**零重叠、无闪烁（Z-fighting）**。
- 将多边形外环（`outerBoundaryIs`）与内孔（`innerBoundaryIs`）逐顶点反算为 WGS84 坐标，写入 KML `<Polygon><altitudeMode>clampToGround</altitudeMode>`，由 Google Earth 地形着色器自动贴合起伏地表。

### 9. V3 红线加密、贴地与低视角增强的完整方法
- **原因定位**：原始红线仅含 15 个界址点（跨度达 70～170 米），在 `relativeToGround` 模式下两点间为三维空间直线弦（割线），遇到南侧 J06～J07 等凸起山坡时直接穿入地下，低视角斜视时被地形遮挡而消失。
- **修复机制**：对相邻界址点按 `2.0m` 步长做线性加密插值（15 点扩展为 419 点），并建立双层红线架构：
  - `01_地表贴合红线`：`clampToGround`，默认隐藏（`<visibility>0</visibility>`），供正俯视切换；
  - `02_低视角增强红线`：`relativeToGround` + 高度 `+1.00m`，默认开启（`<visibility>1</visibility>`），使红线在低角度斜视下连续悬浮于地表之上且不产生双线重影。
- **界址点去重**：将 J01～J15 剥离至独立子 Folder，每个点仅保留唯一 Placemark。

### 10. Google Earth Pro 实际加载、截图与验收方式
- 放弃不稳定的 GUI 鼠标拖拽模拟，改为在测试前重置 `~/Library/Application Support/Google Earth/myplaces.kml` 与 `UnfinishedSessions` 状态（消除历史残留图层与关闭弹窗）。
- 通过脚本动态修改 KMZ 内 `doc.kml` 的 `<LookAt>` 参数（经度、纬度、Range、Heading、Tilt），启动 Google Earth Pro 自动飞行到位，等待 13～14 秒稳定后调用 macOS `Quartz` 获取窗口 ID 并执行 `screencapture -l <wid>` 抓取真实渲染图像。

### 11. 建筑资源哈希、图层一致性与 KMZ 完整性检查
- 在局部迭代（V1→V2 修道路、V2→V3 修红线）时，计算 KMZ 内全部建筑 `.dae` 与 `.png` 的 SHA256 哈希值及坐标姿态，确保未修改资产 100% 零变动。

### 12. GitHub 独立分支及成果发布流程
- 在 Google Earth 展示项目独立目录初始化 Git，创建独立分支 `showcase/phuket-solar-valley-ge-v3` 推送至远端仓库，通过 `.gitignore` 过滤旧版中间包与大体积未用缓存，绝不污染其他施工图分支或 `main` 分支。

---

## 二、技术方法与参数的五维严格区分表

| 分类维度 | 具体内容与工程边界说明 |
| :--- | :--- |
| **1. 已实际验证有效的方法** | ① Collection Instance 烘焙至基底中心正东-正北局部坐标系导出 DAE；<br>② DAE 注入 `GOOGLEEARTH double_sided=1` 及同目录贴图相对路径；<br>③ 建筑底部添加深色 Plinth 基座裙边防止坡地悬空；<br>④ 展示型道路采用 `Shapely unary_union + difference` 转 KML `Polygon (clampToGround)`；<br>⑤ 坡地长跨度红线采用等距加密插值 + 双层分离（`clampToGround` 隐藏备选 + `relativeToGround` 浮空默认显示）；<br>⑥ 重置 `myplaces.kml` + `<LookAt>` 注入实现 Google Earth Pro 确定性飞行截图验收。 |
| **2. 曾经失败或已废弃的方法** | ① **已废弃**：将长距离道路切分为多段刚性 3D DAE 网格并添加 `-2.20m` 垂直厚路基（导致严重台阶断口与水泥墩侧壁）；<br>② **已废弃**：仅用稀疏原始界址点（跨度 >50m）直接设置 `relativeToGround + tessellate=1`（无法阻止长弦穿入凸起山坡）；<br>③ **已废弃**：同时默认勾选开启贴地红线与浮空红线（倾斜视角下出现上下两条红线的视差双影）；<br>④ **已废弃**：使用脆弱的正则表达式或字符串硬切片截取 KML 图层（易因缩进或名称微调而崩溃，现全面升级为 `ElementTree` 结构化操作）。 |
| **3. 太阳谷项目专用参数（严禁外推）** | ① 原点平移常数：`E0 = 426560.000, N0 = 895440.000` 及 `UTM Zone 47N (EPSG:32647)`；<br>② 固定对象名：`D1_独栋四层`～`D8_独栋四层`、`酒店_六层_首层超市_临街通高玻璃`、`road`、`sidewalk`；<br>③ 局部基底偏移量：独栋 `(6.75, 4.00, 0)`、酒店 `(15.00, 6.10, 0)` 及特定家具过滤词表；<br>④ 太阳谷 J01～J15 界址点坐标及特定 `0.78m` 建筑相对地面抬升值。 |
| **4. 可推广至其他项目的通用方法** | ① 扫描任意 `.blend` 输出集合、实例、网格与材质清单；<br>② 基于配置文件驱动的建筑提取、坐标配准（支持任意 UTM 带、控制点拟合或原位经纬度锚点）、贴地道路布尔处理、红线可配步长插值与 KMZ 结构化组装；<br>③ 局部图层/单栋建筑无损更新与 SHA256 基线锁定校验机制。 |
| **5. 尚未经独立验证的假设与限制** | ① 太阳谷 R46 场景虽在红线 J01～J15 上与测绘 DXF 满足平移对应，但内部建筑实例存在美术非均匀缩放（如 D1 为 `0.9286, 0.9365`），且无持牌测量师现场联测桩点，因此定位性质为**可视化候选配准（PROPOSED_CANDIDATE_ALIGNMENT）**，严禁宣称达到施工放线或测绘级绝对精度；<br>② `relativeToGround + 浮空高度` 虽能有效改善低视角红线遮挡，但若极端峡谷地形在两插值点间仍有剧烈突变，需进一步缩小插值步长或提高浮空高度，不能绝对化宣称“任何地形 100% 永不穿地”。 |
