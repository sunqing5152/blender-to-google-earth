# 03. 坐标转换、子午线收敛角与配准误差说明

## 一、三层坐标系统转换链
在将 Blender 建筑场景融合到 Google Earth 时，涉及三个坐标空间：
1. **Blender 场景局部坐标系 $(X_{\text{bl}}, Y_{\text{bl}}, Z_{\text{bl}})$**：
   - 笛卡尔右手系，单位通常为米（m），一般约定 $+X$ 为场景东向，$+Y$ 为场景北向，$+Z$ 为天顶向上。
2. **高斯-克吕格 / UTM 投影平面坐标系 $(E, N)$**：
   - 横轴墨卡托等角投影（如 `UTM Zone 47N` 对应中央经线 $99^\circ\text{E}$，`UTM Zone 50N` 对应 $117^\circ\text{E}$）。
   - 平面二维相似变换公式：
     $$E = E_0 + S \cdot (X_{\text{bl}} \cos\theta - Y_{\text{bl}} \sin\theta)$$
     $$N = N_0 + S \cdot (X_{\text{bl}} \sin\theta + Y_{\text{bl}} \cos\theta)$$
3. **Google Earth WGS84 地理坐标系 $(\text{Lon}, \text{Lat}, \text{Alt})$**：
   - 采用 WGS84 椭球体（$a=6378137.0\text{m}, f=1/298.257223563$），经纬度单位为度（°）。

## 二、子午线收敛角 ($\gamma$) 修正
- 在 UTM 投影网格中，除中央经线外，“坐标纵轴北（Grid North）”与“真北（True North）”之间存在子午线收敛角 $\gamma$：
  $$\gamma = \arctan(\tan(\lambda - \lambda_0) \cdot \sin\varphi)$$
- 虽然 $\gamma$ 通常小于 $1.5^\circ$（例如普吉岛约为 $-0.0937^\circ$），但对于跨度数百米的总图，若不修正会导致远端建筑与红线偏离数十厘米。`geo_transform.py` 自动计算场地中心 $\gamma$ 并补偿至模型旋转矩阵。

## 三、配准精度等级与诚实性红线
1. **严禁外推固定参数**：
   - 普吉太阳谷的 `E0=426560, N0=895440, UTM 47N` 仅适用于该项目，绝不可直接用于其他场地。
2. **禁止在无测绘依据时做出测绘级承诺**：
   - 当用户仅提供大致经纬度、卫星图目视对齐或美术场景内存在非均匀缩放时，脚本会自动将 `registration_status` 标记为 `CANDIDATE_ALIGNMENT` 或 `CANDIDATE_DISPLAY_ONLY`。
   - 汇报时必须如实说明其为“规划可视化展示配准”，严禁使用“100%测绘级精度”“可用于施工放线”等夸大表述。
