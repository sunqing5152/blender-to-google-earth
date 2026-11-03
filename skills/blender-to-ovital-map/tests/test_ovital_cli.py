#!/usr/bin/env python3
"""不访问奥维GUI的合成小项目测试。全部产物放临时目录自动清理。"""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

CLI_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ovital_cli.py"
spec = importlib.util.spec_from_file_location("ovital_cli", CLI_PATH)
ovital = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ovital)


def make_fixture(root, up="Y"):
    a = root / "source.kmz"
    models = root / "obj"
    models.mkdir()
    name1, name2 = "建筑甲", "建筑乙"
    for name in (name1, name2):
        geo = [(0, 0, 0), (2, 0, 0), (2, 10, 1), (0, 10, 1)] if up == "Y" else [(0, 0, 0), (2, 0, 0), (2, 1, 10), (0, 1, 10)]
        vertices = "\n".join("v " + " ".join(str(v) for v in pt) for pt in geo)
        (models / (name+".obj")).write_text(
            f"mtllib {name}.mtl\n" + vertices +
            "\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 1 0\nusemtl MAT\nf 1/1/1 2/2/1 3/3/1\nf 1/1/1 3/3/1 4/1/1\n",
            encoding="utf-8")
        (models / (name+".mtl")).write_text("newmtl MAT\nKd 1 1 1\nmap_Kd texture.png\n", encoding="utf-8")
    (models / "texture.png").write_bytes(b"fake-valid-for-path-check")
    kmldata = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>建筑甲</name><Model><altitudeMode>relativeToGround</altitudeMode>
<Location><longitude>101.0000</longitude><latitude>12.0000</latitude><altitude>0.78</altitude></Location>
<Orientation><heading>0</heading><tilt>0</tilt><roll>0</roll></Orientation>
<Scale><x>1</x><y>1</y><z>1</z></Scale><Link><href>models/建筑甲.dae</href></Link></Model></Placemark>
<Placemark><name>建筑乙</name><Model><altitudeMode>relativeToGround</altitudeMode>
<Location><longitude>101.0001</longitude><latitude>12.0002</latitude><altitude>0.78</altitude></Location>
<Orientation><heading>0</heading><tilt>0</tilt><roll>0</roll></Orientation>
<Scale><x>1</x><y>1</y><z>1</z></Scale><Link><href>models/建筑乙.dae</href></Link></Model></Placemark>
<Placemark><name>地界</name><LineString><coordinates>101,12,0 101.1,12,0</coordinates></LineString></Placemark>
</Document></kml>"""
    with zipfile.ZipFile(a, "w") as zipf:
        zipf.writestr("doc.kml", kmldata)
    return a, models


class OvitalSkillTests(unittest.TestCase):
    def run_case(self, up):
        with tempfile.TemporaryDirectory(prefix="ovital_skill_test_") as temp:
            t = Path(temp)
            kmz, objdir = make_fixture(t, up=up)
            output = t / "output"
            args = type("Args", (), {"kmz": str(kmz), "obj_dir": str(objdir),
                                     "anchor": "建筑甲", "obj_up_axis": up,
                                     "output": str(output), "dry_run": False})()
            ovital.build(args)
            result = ovital.verify(output)
            self.assertEqual(result["建筑数"], 2)
            meta = json.loads((output/"奥维_定位参数.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["源高度模式"], "relativeToGround")
            self.assertEqual(meta["源高度偏移米"], .78)
            self.assertNotIn("11.78", json.dumps(meta))
            items = {x["名称"]: x for x in meta["模型"]}
            self.assertGreater(items["建筑乙"]["偏东米"], 10)
            self.assertGreater(items["建筑乙"]["偏北米"], 20)
            self.assertEqual(items["建筑乙"]["原始模型高度米"], 10.0)
            self.assertEqual(len(list((output/"textures").glob("*"))), 1)
            self.assertFalse(ET.parse(output/"道路与红线_独立图层.kml").getroot().findall(".//k:Model", ovital.NS))
            self.assertTrue((output/"README_奥维导入说明.md").is_file())
            with self.assertRaises(FileExistsError):
                ovital.build(args)

    def test_y_up_vertical_axis_protected(self):
        self.run_case("Y")

    def test_z_up_vertical_axis_protected(self):
        self.run_case("Z")

    def test_reject_wrong_height_offset(self):
        with tempfile.TemporaryDirectory(prefix="ovital_skill_test_") as temp:
            t = Path(temp)
            kmz, objdir = make_fixture(t)
            with zipfile.ZipFile(kmz) as archive:
                text = archive.read("doc.kml").decode()
            text = text.replace("<altitude>0.78</altitude>", "<altitude>1.78</altitude>", 1)
            with zipfile.ZipFile(kmz, "w") as archive:
                archive.writestr("doc.kml", text)
            args = type("Args", (), {"kmz": str(kmz), "obj_dir": str(objdir),
                                     "anchor": "建筑甲", "obj_up_axis": "Y",
                                     "output": str(t/"output"), "dry_run": True})()
            with self.assertRaises(ValueError):
                ovital.build(args)


if __name__ == "__main__":
    unittest.main()