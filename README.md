# Blender to Google Earth (`blender-to-google-earth`)

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20V1.0-blue)](https://github.com/sunqing5152/blender-to-google-earth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Blender 3.x/4.x](https://img.shields.io/badge/Blender-3.x%20%7C%204.x-orange.svg)](https://www.blender.org/)

将 Blender (`.blend`) 建筑与规划三维模型融合到 Google Earth Pro (`.kmz`) 的通用开源工具链与 Antigravity 官方技能包。

---

## 🌟 核心解决的工程痛点

1. **道路断口与水泥厚路基根治**：
   - 彻底废弃传统 3D 刚性切片网格与向下拉伸厚裙边的错误做法；
   - 采用基于 Shapely 的 2D 拓扑合并与层级布尔差集（`unary_union` + `difference`），输出原生 KML 贴地多边形（`Polygon + clampToGround`），由 Google Earth 底层地形着色器贴地流形渲染，杜绝断裂与 Z-fighting 颜色闪烁。
2. **低视角倾斜斜视红线穿地根治**：
   - 解决长跨度界址点直线割线切入凸起山坡地形导致的局部消失；
   - 采用参数化等距加密线性插值（默认 2.0m）结合双层自适应架构（贴地层备用 + 浮空 1.0m 增强层默认显示），斜视下犹如立体激光束无遮挡呈现。
3. **界址点唯一标签与样式规范**：
   - 解耦独立 Placemark，彻底根除历史缓存双重文字重叠与重影。
4. **集合实例 (Collection Instance) 坐标无损烘焙**：
   - 自动展开实例子网格，将旋转与非均匀缩放直接烘焙至局部正东-正北顶点坐标系，KML `<Model>` 统一保持 `Scale=1,1,1`，杜绝倾斜剪切变形。
5. **结构化 XML DOM 组装与局部无损更新**：
   - 全面使用 `xml.etree.ElementTree` 操作，支持仅更新道路、仅更新红线或单栋建筑，未修改资产保持 SHA256 绝对锁定。

---

## 🚀 快速上手 (Quick Start)

### 1. 安装与依赖
```bash
git clone https://github.com/sunqing5152/blender-to-google-earth.git
cd blender-to-google-earth
pip install pyyaml shapely
```

### 2. 作为 Antigravity Skill 安装
```bash
# 安装至全局 Antigravity Skills 目录
mkdir -p ~/.gemini/config/skills/
cp -R . ~/.gemini/config/skills/blender-to-google-earth
```

### 3. 命令行常用操作 (`b2ge_cli.py`)
```bash
# 扫描任意 Blender 场景
python3 ./scripts/b2ge_cli.py scan --blend /path/to/scene.blend --output /tmp/scan.json

# 根据配置文件全量构建 KMZ (支持 --dry-run 预检)
python3 ./scripts/b2ge_cli.py build --config ./templates/project_config.yaml

# 局部更新已有 KMZ 的道路图层
python3 ./scripts/b2ge_cli.py road --config ./my_config.yaml --base-kmz old.kmz --output-kmz new_road.kmz

# 局部更新已有 KMZ 的红线图层
python3 ./scripts/b2ge_cli.py redline --config ./my_config.yaml --base-kmz old.kmz --output-kmz new_redline.kmz

# 执行质量门禁检查与 Google Earth Pro 真实飞行截图验收
python3 ./scripts/b2ge_cli.py verify --kmz ./output/scene_showcase.kmz --launch-ge
```

---

## 📁 目录结构
```text
.
├── SKILL.md                  # Antigravity Skill 核心定义与决策树
├── templates/
│   └── project_config.yaml   # 通用项目标准配置模板 (含详细中文注释)
├── scripts/                  # 8 个独立可执行 Python 工具
├── references/               # 7 篇技术要点与失败/成功案例手册
├── examples/                 # 普吉太阳谷 V3 复盘与独立合成场景样例
└── tests/                    # 自动化测试套件 (含 5 项全通过验证)
```

## 📄 开源许可
采用 [MIT License](LICENSE) 许可协议。
