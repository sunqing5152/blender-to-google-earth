# Blender to Google Earth (`blender-to-google-earth`)

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20V1.0-blue)](https://github.com/sunqing5152/blender-to-google-earth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Blender 3.x/4.x](https://img.shields.io/badge/Blender-3.x%20%7C%204.x-orange.svg)](https://www.blender.org/)

## 🎯 这个 Skill 到底是干什么的？

简单一句话：**它让 AI 具备“把三维规划设计一键搬进真实地球”的完整生产能力。**

当你做好了 Blender 里的建筑、小区、别墅或规划方案，想要放进 **Google Earth（谷歌地球）真实山体地形** 中汇报或展示时，传统流程极其繁琐且门槛极高（拆模型、转格式、算经纬度、写 KML 代码、打包 KMZ）。

**有了这个 Skill，你只需把 Blender 文件和地块坐标交给 AI，AI 会全自动完成全部工作：**
1. **自动读懂 Blender 场景**：自动识别哪些是建筑、哪些是道路、哪些是地块红线；
2. **自动算准真实地球坐标**：将三维模型的相对坐标（米）精确换算为地球真实经纬度与朝向；
3. **自动生成 KMZ 交付文件**：打包成 Google Earth 原生可直接双击打开的 `.kmz` 文件；
4. **自动确保专业级视觉品质**：消除了传统导入容易出现的“山地道路悬空断裂”和“红线穿进山体”等常见瑕疵；
5. **支持局部秒级换件**：后期如果改了某栋楼或换了路面，不用重新做整套，AI 自动只替换对应构件。

---

## 🏗️ 典型输入与输出

| 输入（你提供什么） | AI 处理过程（Skill 干了什么） | 最终输出（你得到什么） |
| :--- | :--- | :--- |
| 1. 任意 Blender 模型 (`.blend`)<br>2. 地理坐标（经纬度或控制点） | 自动扫描场景 → 提取建筑与几何 → 换算地球投影 → 组装结构化 KML/KMZ | 一个完整的 `.kmz` 成果包<br>*(双击即可在谷歌地球实景中漫游审查)* |

---

## 🌟 核心工程与自动化能力

1. **全自动资产扫描与提取**：
   - 自动解析 Blender 场景的集合与实例，按需导出指定建筑模型为标准的 DAE 格式并自动打包贴图。
2. **多坐标系严密配准**：
   - 支持全球 UTM 投影带正反算与控制点拟合，确保三维模型在真实地球上位置准确、尺度真实、朝向正确。
3. **山地地形自适应与画质保障**：
   - **道路**：自动采用 2D 拓扑贴地算法，让道路像地毯一样严密贴合起伏山体，杜绝悬空断裂；
   - **红线**：自动进行等距加密与微浮空处理，低角度斜视也能清晰可见，杜绝山坡遮挡。
4. **结构化无损局部更新**：
   - 采用标准 XML DOM 结构管理，支持“只换某一栋楼”或“只改道路图层”，其他模型保持原样，无需全量重跑。
5. **内置自动化质量门禁**：
   - 自动检查文件完整性、引用路径与坐标合理性，并可自动启动 Google Earth Pro 截取多角度画面核验。

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
