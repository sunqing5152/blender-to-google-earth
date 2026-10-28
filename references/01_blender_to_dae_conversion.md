# 01. Blender 到 Google Earth 的模型转换要点

## 一、集合实例 (Collection Instance) 与普通网格的识别
1. **Collection Instance (`EMPTY`)**：
   - 在大型建筑规划场景中，重复户型或复杂单体常以 `obj.type == 'EMPTY'` 且 `obj.instance_type == 'COLLECTION'` 的形式存在。
   - 若直接选中该 `EMPTY` 执行 `bpy.ops.wm.collada_export(selected=True)`，导出的 `.dae` 将为空几何体！
   - **正确做法**：遍历 `obj.instance_collection.all_objects`，提取其中的 `MESH` 与需要保留的 `FONT`（3D 文字），将各子对象的 `o.matrix_world` 与实例母矩阵 `inst_obj.matrix_world` 组合变换到统一的局部坐标系中合并为单一 `BMesh`。
2. **室内构件的选择性保留/剔除**：
   - 严禁无条件删除所有子对象。应通过配置文件的 `exclude_subobject_keywords` 按用户目标过滤室内活动家具（如沙发、床垫、水龙头等），以将单栋建筑三角面数控制在 5,000～30,000 面的流畅区间。

## 二、实例缩放、旋转与局部原点烘焙
1. **避免 KML 非均匀缩放引起的剪切变形 (Shear)**：
   - 当 Blender 实例同时具有旋转角和 XY 非均匀缩放时，若在 KML `<Model>` 中分别填入 `<Orientation>` 与 `<Scale>`，由于旋转与缩放矩阵乘法顺序差异，极易导致模型歪斜或与道路错位。
   - **验证成功的标准做法**：计算建筑基底世界中心 `world_center`，构造变换矩阵：
     `base_mat = ROT_GAMMA_MAT @ Translation(-world_center) @ inst_obj.matrix_world`
     直接将实例缩放、Z 轴旋转及子午线收敛角修正烘焙进 `.dae` 网格顶点。导出后，KML `<Model>` 统一保持 `<heading>0.0</heading>` 与 `<Scale>1.0, 1.0, 1.0</Scale>`。

## 三、材质贴图与双面渲染 (Double-Sided)
1. **贴图兼容**：
   - Google Earth Pro 的 COLLADA 解析器不支持 Blender Cycles/EEVEE 复杂程序化 Shader 节点（如 Noise、Ramp、Mix Shader）。
   - 必须将材质烘培或映射为标准 PNG/JPG 图像纹理，并绑定在 `Principled BSDF` 的 `Base Color` 输入端。
2. **双面渲染注入**：
   - 建筑模型常含单面玻璃、栏杆或法线朝向不一的叶片。导出 `.dae` 后必须在 `</profile_COMMON>` 后注入：
     ```xml
     <extra><technique profile="GOOGLEEARTH"><double_sided>1</double_sided></technique></extra>
     ```
3. **防坡地悬空基座裙边 (Plinth)**：
   - Google Earth 的 DEM 地形存在局部坡度，建筑以 `relativeToGround` 放置时常出现半边悬空漏光。
   - 建议在建筑基底外框内缩 5～15cm 处向下拉伸 `-1.2m ~ -1.5m` 的深灰色基座盒子（`plinth_base`），使建筑自然扎根于坡地。
