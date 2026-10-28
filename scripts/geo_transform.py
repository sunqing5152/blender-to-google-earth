#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用地理坐标转换与配准引擎 (geo_transform.py)
支持全球任意 UTM 分带 (1~60, N/S) 与 WGS84 经纬度正反算、控制点最小二乘配准及局部锚点定位。
"""

import math
from typing import Dict, List, Tuple, Any, Optional

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
UTM_K0 = 0.9996


def wgs84_to_utm(lon_deg: float, lat_deg: float, zone: Optional[int] = None, hemisphere: Optional[str] = None) -> Tuple[float, float, int, str, float]:
    """将 WGS84 (经度, 纬度) 转换为 UTM (Easting, Northing, zone, hemisphere, gamma_deg)"""
    if zone is None:
        zone = int((lon_deg + 180.0) // 6.0) + 1
        zone = max(1, min(60, zone))
    if hemisphere is None:
        hemisphere = "N" if lat_deg >= 0.0 else "S"
    hemisphere = hemisphere.upper()

    e2 = 2.0 * WGS84_F - WGS84_F ** 2
    ep2 = e2 / (1.0 - e2)
    lon0 = math.radians((zone - 1) * 6.0 - 180.0 + 3.0)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)

    N = WGS84_A / math.sqrt(1.0 - e2 * sin_lat ** 2)
    T = tan_lat ** 2
    C = ep2 * cos_lat ** 2
    A = cos_lat * (lon - lon0)

    M = WGS84_A * (
        (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0) * lat
        - (3.0 * e2 / 8.0 + 3.0 * e2 ** 2 / 32.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(2.0 * lat)
        + (15.0 * e2 ** 2 / 256.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(4.0 * lat)
        - (35.0 * e2 ** 3 / 3072.0) * math.sin(6.0 * lat)
    )

    easting = 500000.0 + UTM_K0 * N * (
        A
        + (1.0 - T + C) * A ** 3 / 6.0
        + (5.0 - 18.0 * T + T ** 2 + 72.0 * C - 58.0 * ep2) * A ** 5 / 120.0
    )
    northing = UTM_K0 * (
        M + N * tan_lat * (
            A ** 2 / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C ** 2) * A ** 4 / 24.0
            + (61.0 - 58.0 * T + T ** 2 + 600.0 * C - 330.0 * ep2) * A ** 6 / 720.0
        )
    )
    if hemisphere == "S":
        northing += 10000000.0

    gamma = math.degrees(math.atan(math.tan(lon - lon0) * sin_lat))
    return easting, northing, zone, hemisphere, gamma


def utm_to_wgs84(easting: float, northing: float, zone: int, hemisphere: str = "N") -> Tuple[float, float, float]:
    """将任意 UTM 分带 (Easting, Northing) 反算为 WGS84 (lon_deg, lat_deg, gamma_deg)"""
    if not (1 <= int(zone) <= 60):
        raise ValueError(f"无效的 UTM 分带号: {zone} (必须在 1~60 之间)")
    hemisphere = hemisphere.upper()
    if hemisphere not in ("N", "S"):
        raise ValueError(f"无效的半球标识: {hemisphere} (必须为 'N' 或 'S')")

    e2 = 2.0 * WGS84_F - WGS84_F ** 2
    ep2 = e2 / (1.0 - e2)
    lon0 = math.radians((int(zone) - 1) * 6.0 - 180.0 + 3.0)

    x = easting - 500000.0
    y = northing - (10000000.0 if hemisphere == "S" else 0.0)

    M = y / UTM_K0
    mu = M / (WGS84_A * (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0))
    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))

    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1 ** 3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1 ** 2 / 16.0 - 55.0 * e1 ** 4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1 ** 3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1 ** 4 / 512.0) * math.sin(8.0 * mu)
    )

    sin_p1 = math.sin(phi1)
    cos_p1 = math.cos(phi1)
    tan_p1 = math.tan(phi1)

    N1 = WGS84_A / math.sqrt(1.0 - e2 * sin_p1 ** 2)
    T1 = tan_p1 ** 2
    C1 = ep2 * cos_p1 ** 2
    R1 = WGS84_A * (1.0 - e2) / ((1.0 - e2 * sin_p1 ** 2) ** 1.5)
    D = x / (N1 * UTM_K0)

    lat = phi1 - (N1 * tan_p1 / R1) * (
        D ** 2 / 2.0
        - (5.0 + 3.0 * T1 + 10.0 * C1 - 4.0 * C1 ** 2 - 9.0 * ep2) * D ** 4 / 24.0
        + (61.0 + 90.0 * T1 + 298.0 * C1 + 45.0 * T1 ** 2 - 252.0 * ep2 - 3.0 * C1 ** 2) * D ** 6 / 720.0
    )
    lon = lon0 + (
        D
        - (1.0 + 2.0 * T1 + C1) * D ** 3 / 6.0
        + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * C1 ** 2 + 8.0 * ep2 + 24.0 * T1 ** 2) * D ** 5 / 120.0
    ) / cos_p1

    gamma = math.degrees(math.atan(math.tan(lon - lon0) * math.sin(lat)))
    return math.degrees(lon), math.degrees(lat), gamma


class GeoTransformer:
    """
    通用场景地理配准变换器：
    将 Blender 局部平面坐标 (x, y) 转换为 UTM (E, N) 与 WGS84 (lon, lat)：
        E = E0 + scale * (x * cos(theta) - y * sin(theta))
        N = N0 + scale * (x * sin(theta) + y * cos(theta))
    """

    def __init__(self, crs_cfg: Dict[str, Any]):
        self.mode = crs_cfg.get("mode", "utm_offset")
        self.zone: int = int(crs_cfg.get("utm_zone", 47))
        self.hemisphere: str = str(crs_cfg.get("hemisphere", "N")).upper()
        self.e0: float = 500000.0
        self.n0: float = 0.0
        self.rotation_deg: float = float(crs_cfg.get("rotation_deg", 0.0))
        self.scale: float = float(crs_cfg.get("scale", 1.0))
        self.registration_status: str = "CANDIDATE_ALIGNMENT (候选展示定位·严禁用于工程测绘放线)"
        self.rmse_m: Optional[float] = None
        self.max_residual_m: Optional[float] = None

        if self.mode == "utm_offset":
            if "origin_easting" not in crs_cfg or "origin_northing" not in crs_cfg:
                raise ValueError("utm_offset 模式必须提供 origin_easting 和 origin_northing")
            self.e0 = float(crs_cfg["origin_easting"])
            self.n0 = float(crs_cfg["origin_northing"])
            self.registration_status = crs_cfg.get(
                "registration_status",
                "UTM_OFFSET_ALIGNMENT (基于给定UTM原点配准·需核实控制桩后方可用于施工)"
            )

        elif self.mode == "local_lonlat":
            lon0 = float(crs_cfg["origin_lon"])
            lat0 = float(crs_cfg["origin_lat"])
            e, n, z, h, _ = wgs84_to_utm(lon0, lat0)
            self.e0, self.n0, self.zone, self.hemisphere = e, n, z, h
            self.registration_status = "CANDIDATE_DISPLAY_ONLY (仅基于单点经纬度锚点的候选展示定位·非测绘级)"

        elif self.mode == "control_points":
            cpts = crs_cfg.get("control_points", [])
            if len(cpts) < 2:
                raise ValueError("control_points 模式至少需要 2 个控制点对")
            allow_scale = bool(crs_cfg.get("allow_scale_fit", False))
            self._fit_control_points(cpts, allow_scale=allow_scale, crs_cfg=crs_cfg)
        else:
            raise ValueError(f"不支持的坐标配准模式: {self.mode}")

        _, _, self.site_gamma_deg = utm_to_wgs84(self.e0, self.n0, self.zone, self.hemisphere)

    def _fit_control_points(self, cpts: List[Dict[str, Any]], allow_scale: bool, crs_cfg: Dict[str, Any]):
        """使用二维最小二乘 Helmert 相似/刚体变换拟合控制点对"""
        bl_pts: List[Tuple[float, float]] = []
        utm_pts: List[Tuple[float, float]] = []

        first = cpts[0]
        if "wgs84_lon" in first and "wgs84_lat" in first and "utm_zone" not in crs_cfg:
            _, _, self.zone, self.hemisphere, _ = wgs84_to_utm(float(first["wgs84_lon"]), float(first["wgs84_lat"]))

        for pt in cpts:
            bx, by = float(pt["blender_x"]), float(pt["blender_y"])
            if "utm_e" in pt and "utm_n" in pt:
                ue, un = float(pt["utm_e"]), float(pt["utm_n"])
            elif "wgs84_lon" in pt and "wgs84_lat" in pt:
                ue, un, _, _, _ = wgs84_to_utm(float(pt["wgs84_lon"]), float(pt["wgs84_lat"]), self.zone, self.hemisphere)
            else:
                raise ValueError(f"控制点 {pt.get('id')} 缺少 utm_e/utm_n 或 wgs84_lon/wgs84_lat")
            bl_pts.append((bx, by))
            utm_pts.append((ue, un))

        n = len(bl_pts)
        cx_b = sum(p[0] for p in bl_pts) / n
        cy_b = sum(p[1] for p in bl_pts) / n
        ce_u = sum(p[0] for p in utm_pts) / n
        cn_u = sum(p[1] for p in utm_pts) / n

        num_a = 0.0
        num_b = 0.0
        den = 0.0
        for (bx, by), (ue, un) in zip(bl_pts, utm_pts):
            dx, dy = bx - cx_b, by - cy_b
            de, dn = ue - ce_u, un - cn_u
            num_a += dx * de + dy * dn
            num_b += dx * dn - dy * de
            den += dx * dx + dy * dy

        if den < 1e-12:
            raise ValueError("控制点在 Blender 空间中退化重合，无法拟合变换")

        theta = math.atan2(num_b, num_a)
        self.rotation_deg = math.degrees(theta)
        if allow_scale:
            self.scale = math.hypot(num_a, num_b) / den
        else:
            self.scale = 1.0

        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        self.e0 = ce_u - self.scale * (cx_b * cos_t - cy_b * sin_t)
        self.n0 = cn_u - self.scale * (cx_b * sin_t + cy_b * cos_t)

        residuals = []
        for (bx, by), (ue, un) in zip(bl_pts, utm_pts):
            pe, pn = self.blender_to_utm(bx, by)
            residuals.append(math.hypot(pe - ue, pn - un))
        self.max_residual_m = max(residuals)
        self.rmse_m = math.sqrt(sum(r * r for r in residuals) / n)
        self.registration_status = crs_cfg.get(
            "registration_status",
            f"CONTROL_POINT_FITTED (N={n}, RMSE={self.rmse_m:.4f}m, MaxRes={self.max_residual_m:.4f}m·可视化配准)"
        )

    def blender_to_utm(self, x: float, y: float) -> Tuple[float, float]:
        rad = math.radians(self.rotation_deg)
        c, s = math.cos(rad), math.sin(rad)
        e = self.e0 + self.scale * (x * c - y * s)
        n = self.n0 + self.scale * (x * s + y * c)
        return e, n

    def blender_to_wgs84(self, x: float, y: float) -> Tuple[float, float, float]:
        e, n = self.blender_to_utm(x, y)
        return utm_to_wgs84(e, n, self.zone, self.hemisphere)

    def utm_to_wgs84(self, e: float, n: float) -> Tuple[float, float, float]:
        return utm_to_wgs84(e, n, self.zone, self.hemisphere)

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "utm_zone": self.zone,
            "hemisphere": self.hemisphere,
            "origin_easting_m": round(self.e0, 4),
            "origin_northing_m": round(self.n0, 4),
            "rotation_deg": round(self.rotation_deg, 6),
            "scale": round(self.scale, 6),
            "site_meridian_convergence_deg": round(self.site_gamma_deg, 6),
            "rmse_m": round(self.rmse_m, 5) if self.rmse_m is not None else None,
            "max_residual_m": round(self.max_residual_m, 5) if self.max_residual_m is not None else None,
            "registration_status": self.registration_status,
        }
