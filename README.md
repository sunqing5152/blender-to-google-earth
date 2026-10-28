# Blender to Google Earth (`blender-to-google-earth`)

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20V1.0-blue)](https://github.com/sunqing5152/blender-to-google-earth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Blender 3.x/4.x](https://img.shields.io/badge/Blender-3.x%20%7C%204.x-orange.svg)](https://www.blender.org/)

**一句话介绍**：把你在 Blender 里做好的建筑、小区、别墅和道路，**一键完美搬进 Google Earth（谷歌地球）实景山体上**，不卡顿、不穿帮、道路像地毯一样严丝合缝贴着地面，红线在任何角度都清晰可见。

---

## 💡 用大白话讲：它到底解决了什么头疼问题？

平时做规划或者汇报时，把 3D 模型放进谷歌地球经常遇到 3 个“灾难现场”：

1. **道路像“悬空断桥”或“笨重水泥块”**：
   - *以前*：直接把 3D 道路塞进谷歌地球，山地高低不平，路要么悬空在天上，要么陷在泥土里，要么只能加一个巨厚的“水泥底座”，特别丑。
   - *现在*：系统自动把道路变成**“智能贴地彩带”**，像一层薄膜地毯顺着山体真实起伏自动铺平，哪怕几百米山路也是完全平整顺滑的。
2. **地块红线“走着走着钻进山里消失了”**：
   - *以前*：两点连一条线，只要中间有个小土坡，斜着看红线就被土坡挡住了。
   - *现在*：系统自动在红线上**每隔 2 米打一个点**，紧贴山坡起伏，并且默认在地面上方 **1 米处浮空发光显示**，就像一道立体激光围栏，无论从多低的角度斜看，红线永远清晰连贯。
3. **改一次图，整套文件重新倒腾一遍**：
   - *现在*：支持**“局部换零件”**。如果你只改了一栋楼，或者只改了道路颜色，点一下更新，只换那个部分，其他建筑和贴图原封不动，秒级完成。

---

## 🌟 核心工程能力 (技术特性)

1. **道路断口与水泥厚路基根治**：
   - 彻底废弃传统 3D 刚性网格与厚裙边做法；
   - 采用 2D 拓扑合并与层级布尔差集，输出原生 KML 贴地多边形（`clampToGround`），由 Google Earth 底层着色器贴地流形渲染。
2. **低视角倾斜斜视红线穿地根治**：
   - 采用参数化等距加密线性插值（默认 2.0m）结合双层架构（贴地备用 + 浮空 1.0m 增强层默认显示）。
3. **界址点唯一标签与样式规范**：
   - 解耦独立 Placemark，彻底根除历史重影。
4. **集合实例 (Collection Instance) 坐标无损烘焙**：
   - 自动展开实例子网格，将旋转与缩放烘焙至正东-正北顶点坐标系，杜绝倾斜变形。
5. **结构化 XML DOM 组装与局部无损更新**：
   - 全面使用结构化 XML 操作，局部更新不伤及其他建筑资产。

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
