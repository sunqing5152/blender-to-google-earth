# 02. KML / KMZ / DAE 资源组织与兼容性规范

## 一、KMZ 压缩包标准目录结构
一个规范、自包含的 Google Earth `.kmz` 归档（ZIP 格式）应采用如下结构：
```text
project_showcase.kmz
├── doc.kml                   # 必须位于根目录，UTF-8 编码
└── models/                   # 存放所有被引用的 DAE 模型与贴图
    ├── Bldg_01.dae
    ├── Bldg_02.dae
    ├── tex_plaster_white.png
    └── tex_glass_arch.png
```

## 二、路径引用铁律
1. **`doc.kml` 引用 `.dae`**：
   - 在 `<Model><Link><href>` 中使用相对路径 `models/Bldg_01.dae`。
   - 严禁写入本机绝对路径（如 `/Users/...` 或 `C:\...`）。
2. **`.dae` 引用贴图 `.png`**：
   - 由于 `.dae` 与 `.png` 均位于 `models/` 同级目录下，`.dae` 内部的 `<library_images><image><init_from>` 应直接写纯文件名（如 `<init_from>tex_plaster_white.png</init_from>`）。
   - Blender 原生导出有时会带入相对子路径或绝对路径，必须通过 `postprocess_dae_xml()` 规范化为纯文件名。
3. **剔除孤儿资源 (Orphan Assets)**：
   - 打包 KMZ 时，应通过 `collect_referenced_assets()` 自动扫描 `doc.kml` 实际引用的 `.dae` 及其关联贴图，严禁把已废弃的旧模型（如旧版三维道路切片）塞入 KMZ。

## 三、使用 ElementTree 替代脆弱的字符串/正则截取
1. **旧版教训**：
   - 早期脚本曾使用 `re.search(r"<Folder>.*?</Folder>")` 或 `kml.find("<name>03_...")` 截取 KML 片段。一旦标签属性、缩进或图层名微调，极易截断闭合标签或丢失样式定义。
2. **结构化 DOM 规范**：
   - 在 `kmz_builder.py` 与 `kmz_verifier.py` 中，全面采用 `xml.etree.ElementTree` 解析与组装 KML 节点树，通过 `ET.indent(root, space="  ")` 输出格式严整的 XML。
   - 局部更新时，按节点树精确定位目标 `<Style>` 与 `<Folder>` 进行原位替换，确保其余 `<Placemark>` 与模型资产 100% 零损伤。
