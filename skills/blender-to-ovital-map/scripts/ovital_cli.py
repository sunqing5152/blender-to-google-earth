#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奥维离线包工具：Google Earth KMZ位置 + 独立OBJ/MTL/贴图 → 合体OBJ。
本程序不操作奥维，不制造ovmod，不凭空生成绝对海拔。
"""
import argparse, csv, hashlib, json, math, re, shutil, sys, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {"k": "http://www.opengis.net/kml/2.2"}
TEXTURE_KEYS = {"map_Kd", "map_Ka", "map_Ks", "bump", "map_Bump", "norm", "disp"}


def models_in_kmz(path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("doc.kml"))
    models = []
    for p in root.findall(".//k:Placemark", NS):
        m = p.find("k:Model", NS)
        if m is None:
            continue
        get = lambda tag, default="": m.findtext(tag, default, NS)
        obj = {
            "name": p.findtext("k:name", "", NS),
            "href": get("k:Link/k:href"),
            "lon": float(get("k:Location/k:longitude")),
            "lat": float(get("k:Location/k:latitude")),
            "alt": float(get("k:Location/k:altitude", "0")),
            "mode": get("k:altitudeMode", "clampToGround"),
            "heading": float(get("k:Orientation/k:heading", "0")),
            "tilt": float(get("k:Orientation/k:tilt", "0")),
            "roll": float(get("k:Orientation/k:roll", "0")),
            "scale": [float(get("k:Scale/k:"+axis, "1")) for axis in "xyz"],
        }
        if not obj["name"] or not obj["href"]:
            raise ValueError("KML 模型缺少 name/href")
        if Path(obj["href"]).is_absolute() or ".." in Path(obj["href"]).parts:
            raise ValueError("KML模型路径不安全")
        models.append(obj)
    if not models or len(set(m["name"] for m in models)) != len(models):
        raise ValueError("KMZ中没有模型或建筑名称重复")
    return root, models


def offsets_in_meters(models, anchor):
    try:
        from pyproj import CRS, Transformer
    except ImportError as exc:
        raise RuntimeError("请安装 pyproj；不可用经纬度差直接当作米") from exc
    proj = CRS.from_proj4(
        f"+proj=aeqd +lat_0={anchor['lat']} +lon_0={anchor['lon']} "
        "+datum=WGS84 +units=m +no_defs")
    transform = Transformer.from_crs("EPSG:4326", proj, always_xy=True)
    return {m["name"]: (*transform.transform(m["lon"], m["lat"]), 0.0) for m in models}


def safe(s):
    return re.sub(r'[^\w\u4e00-\u9fff-]+', "_", s).strip("_") or "model"


def obj_stats(path, up):
    mins = [float("inf")] * 3
    maxs = [-float("inf")] * 3
    n = faces = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            xyz = [float(v) for v in line.split()[1:4]]
            if len(xyz) != 3 or any(not math.isfinite(x) for x in xyz):
                raise ValueError("OBJ顶点无效：" + str(path))
            for i, x in enumerate(xyz):
                mins[i] = min(mins[i], x)
                maxs[i] = max(maxs[i], x)
            n += 1
        elif line.startswith("f "):
            faces += 1
    if not n or not faces:
        raise ValueError("OBJ缺失有效模型：" + str(path))
    h = 1 if up == "Y" else 2
    return {"vertices": n, "faces": faces,
            "bottom": round(mins[h], 5), "top": round(maxs[h], 5),
            "height": round(maxs[h]-mins[h], 5)}


def collect_mtl(model, obj_path, tex_dir):
    mtl = obj_path.with_suffix(".mtl")
    if not mtl.is_file():
        raise FileNotFoundError("缺失MTL：" + str(mtl))
    result, mapping = [], {}
    for line in mtl.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split(maxsplit=1)
        if not parts:
            result.append(line)
            continue
        key = parts[0]
        if key == "newmtl":
            original = parts[1]
            renamed = safe(model) + "__" + safe(original)
            mapping[original] = renamed
            result.append("newmtl " + renamed)
        elif key in TEXTURE_KEYS:
            if len(parts) < 2 or parts[1].startswith("-"):
                raise ValueError("暂不支持含选项的MTL贴图声明：" + line)
            tex = (mtl.parent / parts[1]).resolve()
            if not tex.is_relative_to(mtl.parent.resolve()) or not tex.is_file():
                raise FileNotFoundError("缺失贴图：" + parts[1])
            digest = hashlib.sha256(tex.read_bytes()).hexdigest()[:12]
            dst = digest + "_" + safe(tex.stem) + tex.suffix.lower()
            if not (tex_dir / dst).exists():
                shutil.copy2(tex, tex_dir / dst)
            result.append(key + " textures/" + dst)
        else:
            result.append(line)
    if not mapping:
        raise ValueError("MTL没有材质：" + str(mtl))
    return mapping, result


def face_index(s, count, shift):
    if not s:
        return ""
    i = int(s)
    if i == 0:
        raise ValueError("OBJ索引不允许是0")
    i = i if i > 0 else count + i + 1
    if i < 1 or i > count:
        raise ValueError("OBJ面索引越界")
    return str(i + shift)


def merge_one(out, obj_path, name, delta, up, shifts, material_names):
    dx, dn, dz = delta
    verts, attrs, faces = [], [], []
    n = [0, 0, 0]
    for line in obj_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            x, y, z = map(float, line.split()[1:4])
            if up == "Y":
                x, y, z = x+dx, y+dz, z-dn
            else:
                x, y, z = x+dx, y+dn, z+dz
            verts.append(f"v {x:.7f} {y:.7f} {z:.7f}")
            n[0] += 1
        elif line.startswith("vt "):
            attrs.append(line)
            n[1] += 1
        elif line.startswith("vn "):
            attrs.append(line)
            n[2] += 1
        elif line.startswith("f "):
            faces.append(line)
        elif line.startswith("usemtl "):
            material = line[7:].strip()
            if material not in material_names:
                raise ValueError("材质引用不存在：" + material)
            faces.append("usemtl " + material_names[material])
        elif line.startswith("s "):
            faces.append(line)
    out.write("\no " + safe(name) + "\ng " + safe(name) + "\n")
    # OBJ规范里顶点、纹理坐标、法线索引各自独立，按原始出现顺序无关。
    out.write("\n".join(verts + attrs) + "\n")
    for line in faces:
        if not line.startswith("f "):
            out.write(line + "\n")
            continue
        new_tokens = []
        for tok in line[2:].split():
            fields = tok.split("/")
            shifted = [face_index(fields[0], n[0], shifts[0])]
            if len(fields) >= 2:
                shifted.append(face_index(fields[1], n[1], shifts[1]))
            if len(fields) >= 3:
                shifted.append(face_index(fields[2], n[2], shifts[2]))
            new_tokens.append("/".join(shifted))
        out.write("f " + " ".join(new_tokens) + "\n")
    for i in range(3):
        shifts[i] += n[i]


def build(args):
    kmz, objdir, output = Path(args.kmz), Path(args.obj_dir), Path(args.output)
    if not kmz.is_file() or not objdir.is_dir():
        raise FileNotFoundError("KMZ文件或OBJ目录不存在")
    root, models = models_in_kmz(kmz)
    anchor = next((m for m in models if m["name"] == args.anchor), None)
    if anchor is None:
        raise ValueError("找不到锚点建筑：" + args.anchor)
    if any(m["mode"] != anchor["mode"] or abs(m["alt"]-anchor["alt"]) > 1e-6 for m in models):
        raise ValueError("各建筑高度模式或偏移不一致；单一锚点合并需人工确认")
    for m in models:
        if any(abs(m[k]) > 1e-6 for k in ("heading", "tilt", "roll")) or any(abs(v-1)>1e-6 for v in m["scale"]):
            raise ValueError(m["name"] + " 的KML存在旋转或缩放；需先烘焙，V1拒绝忽略变换")
        candidates = [objdir / (Path(m["href"]).stem + ".obj"), objdir / (m["name"] + ".obj")]
        m["obj"] = next((p for p in candidates if p.is_file()), None)
        if m["obj"] is None:
            raise FileNotFoundError("找不到独立OBJ：" + m["name"])
        m["stats"] = obj_stats(m["obj"], args.obj_up_axis)
    shifts = offsets_in_meters(models, anchor)
    report = {"模型数": len(models), "锚点": args.anchor,
              "源高度模式": anchor["mode"], "源高度偏移米": anchor["alt"],
              "模型": [{"名称": m["name"], "偏东米": round(shifts[m["name"]][0], 3),
                       "偏北米": round(shifts[m["name"]][1], 3),
                       "原始模型高度米": m["stats"]["height"]} for m in models]}
    if args.dry_run:
        print(json.dumps({"预检": "PASS（未写文件）", **report}, ensure_ascii=False, indent=2))
        return
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("输出目录非空，为防止覆盖请选择新目录")
    output.mkdir(parents=True, exist_ok=True)
    textures = output / "textures"
    textures.mkdir()
    combined = output / "奥维_建筑合体模型.obj"
    mtl = output / "奥维_建筑合体模型.mtl"
    shifts_count = [0, 0, 0]
    mtl_lines = []
    with combined.open("w", encoding="utf-8") as out:
        out.write("mtllib " + mtl.name + "\n")
        for m in models:
            mapping, lines = collect_mtl(m["name"], m["obj"], textures)
            mtl_lines += lines + [""]
            merge_one(out, m["obj"], m["name"], shifts[m["name"]], args.obj_up_axis,
                      shifts_count, mapping)
    mtl.write_text("\n".join(mtl_lines), encoding="utf-8")
    with (output / "奥维_单体定位清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["名称", "经度WGS84", "纬度WGS84", "源高度模式", "源高度米", "源OBJ"])
        for m in models:
            w.writerow([m["name"], m["lon"], m["lat"], m["mode"], m["alt"], m["obj"].name])
    model_tag = "{" + NS["k"] + "}Model"
    place_tag = "{" + NS["k"] + "}Placemark"
    for parent in root.iter():
        for child in list(parent):
            if child.tag == place_tag and child.find(model_tag) is not None:
                parent.remove(child)
    ET.ElementTree(root).write(output / "道路与红线_独立图层.kml", encoding="utf-8", xml_declaration=True)
    metadata = {"OBJ上轴": args.obj_up_axis, "锚点建筑": anchor["name"],
                "锚点经度": anchor["lon"], "锚点纬度": anchor["lat"],
                "源高度模式": anchor["mode"], "源高度偏移米": anchor["alt"],
                "模型": report["模型"],
                "原始模型底点": {m["name"]: m["stats"]["bottom"] for m in models},
                "禁止绝对海拔猜测": True,
                "提示": "合体OBJ单一锚点，高差位置不能逐栋贴地；仅用户手动奥维导入可确认显示"}
    (output / "奥维_定位参数.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    guide = (
        "# 奥维导入说明（仅离线文件）\n\n"
        "1. 在Mac版奥维3D模式导入合体OBJ，保持同目录MTL和textures文件夹不变。\n"
        f"2. 模型锚点：经度 {anchor['lon']:.8f}，纬度 {anchor['lat']:.8f}，旋转0，比例1；境外WGS84数据不选GCJ-02。\n"
        f"3. 源KML高度模式 {anchor['mode']}，高度偏移 {anchor['alt']}米。\n"
        "4. 如原来为相对地面高度，优先在奥维测试相对于地面同值；绝不能凭空加一个固定海拔数。\n"
        "5. 道路与红线单独导入，道路未显示或红色填充可能涉及客户端图层表现。\n"
        "6. 本流程不会生成ovmod、不操作奥维GUI。地形不平时单一锚点无法逐栋贴地。\n"
    )
    (output / "README_奥维导入说明.md").write_text(guide, encoding="utf-8")
    print(json.dumps({"构建": "完成", **report, "校验": verify(output)}, ensure_ascii=False, indent=2))


def verify(folder):
    folder = Path(folder)
    metadata = json.loads((folder / "奥维_定位参数.json").read_text(encoding="utf-8"))
    obj_path = folder / "奥维_建筑合体模型.obj"
    mat_path = folder / "奥维_建筑合体模型.mtl"
    obj_groups = {}
    current = None
    up = 1 if metadata["OBJ上轴"] == "Y" else 2
    numverts = numfaces = 0
    for line in obj_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("o "):
            current = line[2:].strip()
            obj_groups[current] = [float("inf"), -float("inf")]
        elif line.startswith("v "):
            numverts += 1
            h = float(line.split()[1+up])
            obj_groups[current][0] = min(h, obj_groups[current][0])
            obj_groups[current][1] = max(h, obj_groups[current][1])
        elif line.startswith("f "):
            numfaces += 1
    if len(obj_groups) != len(metadata["模型"]):
        raise ValueError("合体模型数量不符")
    for entry in metadata["模型"]:
        n = entry["名称"]
        actual = obj_groups[safe(n)]
        original_bottom = metadata["原始模型底点"][n]
        if abs(actual[0] - original_bottom) > 0.02:
            raise ValueError(n + " 出现异常垂直平移")
        if abs((actual[1]-actual[0]) - entry["原始模型高度米"]) > 0.02:
            raise ValueError(n + " 高度或缩放异常")
    materials = mat_path.read_text(encoding="utf-8")
    for key, filename in re.findall(r"^(map_\w+|bump|norm|disp) textures/(\S+)$", materials, re.M):
        if not (folder / "textures" / filename).is_file():
            raise FileNotFoundError("贴图引用丢失：" + filename)
    root = ET.parse(folder / "道路与红线_独立图层.kml").getroot()
    if root.findall(".//k:Model", NS):
        raise ValueError("二维KML中不应包含三维Model")
    return {"静态校验": "PASS（不等于奥维实机验证）",
            "建筑数": len(obj_groups), "顶点": numverts, "面": numfaces}


def main():
    parser = argparse.ArgumentParser(description="奥维OBJ离线导入包，禁止伪造ovmod或绝对海拔")
    p = parser.add_subparsers(dest="action", required=True)
    a = p.add_parser("inspect", help="查看KMZ模型坐标")
    a.add_argument("--kmz", required=True)
    b = p.add_parser("build", help="用已有独立OBJ生成带地理定位的合体OBJ")
    b.add_argument("--kmz", required=True)
    b.add_argument("--obj-dir", required=True)
    b.add_argument("--anchor", required=True)
    b.add_argument("--output", required=True)
    b.add_argument("--obj-up-axis", choices=["Y", "Z"], default="Y")
    b.add_argument("--dry-run", action="store_true")
    c = p.add_parser("verify", help="离线验收包")
    c.add_argument("--package", required=True)
    args = parser.parse_args()
    if args.action == "inspect":
        _, models = models_in_kmz(Path(args.kmz))
        print(json.dumps(models, ensure_ascii=False, indent=2))
    elif args.action == "build":
        build(args)
    else:
        print(json.dumps(verify(args.package), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("错误：" + str(exc), file=sys.stderr)
        raise SystemExit(2)