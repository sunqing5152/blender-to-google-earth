# 05. 成功实践：V2 KML Polygon 贴地道路、布尔并差集与防闪烁方法

## 一、核心技术路线
将 Blender 中的道路、人行道与庭院入口铺装转换为 KML 原生 `<Polygon><altitudeMode>clampToGround</altitudeMode></Polygon>`，交由 Google Earth 底层地形着色器实时贴地渲染（Terrain Draping）。

## 二、五步标准处理流程（`blender_extractor.py` + `road_processor.py`）
1. **法线过滤提取顶面**：
   - 遍历道路 Mesh 的多边形，计算世界空间法线 `normal_world = mw.to_3x3() @ f.normal`。
   - 仅保留朝上的水平或缓坡顶面（`abs(normal_world.z) >= 0.5`），忽略侧面与底面。
2. **Shapely 拓扑修复与并集融合 (`unary_union`)**：
   - 将每个面片的二维投影顶点构造为 `shapely.geometry.Polygon`，对无效多边形执行 `p.buffer(0)` 自动修复自相交。
   - 调用 `unary_union(polys)` 将原本由数百个破碎三角面/四边形组成的网格合并为完整连续的多边形区域，彻底消除内部三角边接缝。
3. **层级布尔差集 (`difference`) 根除重叠闪烁 (Z-fighting)**：
   - 若人行道或入户铺装多边形与主车行道在局部重叠，同时设为 `clampToGround` 时会在 Google Earth 中产生剧烈的灰白交错闪烁。
   - **标准解法**：按视觉优先级排序（如：主车行道 -> 人行步道 -> 入户铺装 -> 停车垫层），启用 `subtract_previous: true`，自动执行 `clean_geom = u_geom.difference(accumulated_union)`，使各材质图层在二维平面上严格互斥、共边无缝。
4. **外环与内孔完整保留**：
   - 将 `Polygon` 的 `exterior` 转换为 KML `<outerBoundaryIs><LinearRing>`，将所有 `interiors`（如环岛中心绿地孔洞）转换为 `<innerBoundaryIs><LinearRing>`。
5. **道路标线提取 (`LineString + clampToGround`)**：
   - 针对白色中心虚线与车位标线网格，通过主方向投影计算每段标线的首尾中心端点，生成 `<LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>`。
