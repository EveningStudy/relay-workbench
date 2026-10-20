"""Generate editable Relay geometry, inertia and URDF from YAML."""
from pathlib import Path
import xml.etree.ElementTree as ET
import json
import numpy as np
import trimesh
import yaml
from scipy.spatial.transform import Rotation


def generate(config="configs/robot.yaml"):
    cfg = yaml.safe_load(Path(config).read_text())
    out = Path("assets/robot")
    out.mkdir(parents=True, exist_ok=True)
    root = ET.Element("robot", name="Relay")
    links, joints = [], []
    def link(name, size=None, center=(0, 0, 0), color=(0.68, 0.77, 0.82, 1), rounded=False):
        e = ET.SubElement(root, "link", name=name)
        mass, inertia = 0.01, np.eye(3) * 1e-5
        if size is not None:
            mesh = trimesh.creation.box(extents=size)
            if rounded:
                # A low-poly convex rounded housing, with primitive collision below.
                pts = trimesh.creation.icosphere(subdivisions=2).vertices
                pts = pts * (np.array(size) / 2)
                mesh = trimesh.convex.convex_hull(pts)
            mass = float(mesh.volume * cfg["density_kg_m3"])
            inertia = mesh.moment_inertia * cfg["density_kg_m3"]
            mesh.export(out / f"{name}.stl")
            visual = ET.SubElement(e, "visual")
            ET.SubElement(visual, "origin", xyz=" ".join(map(str, center)))
            ET.SubElement(ET.SubElement(visual, "geometry"), "mesh", filename=f"{name}.stl")
            ET.SubElement(ET.SubElement(visual, "material", name=name), "color", rgba=" ".join(map(str, color)))
            collision = ET.SubElement(e, "collision")
            ET.SubElement(collision, "origin", xyz=" ".join(map(str, center)))
            ET.SubElement(ET.SubElement(collision, "geometry"), "box", size=" ".join(map(str, size)))
        inertial = ET.SubElement(e, "inertial")
        ET.SubElement(inertial, "origin", xyz=" ".join(map(str, center)))
        ET.SubElement(inertial, "mass", value=str(max(mass, 0.01)))
        ET.SubElement(inertial, "inertia", ixx=str(inertia[0, 0]), iyy=str(inertia[1, 1]), izz=str(inertia[2, 2]), ixy="0", ixz="0", iyz="0")
        links.append(dict(name=name, mass=mass, size=size, center=center))
    def joint(name, parent, child, kind="fixed", xyz=(0, 0, 0), axis=(0, 0, 1), limits=(-2.6, 2.6), rpy=(0, 0, 0), effort=80, velocity=1.5, mimic=None):
        e = ET.SubElement(root, "joint", name=name, type=kind)
        ET.SubElement(e, "parent", link=parent)
        ET.SubElement(e, "child", link=child)
        ET.SubElement(e, "origin", xyz=" ".join(map(str, xyz)), rpy=" ".join(map(str, rpy)))
        if kind != "fixed":
            ET.SubElement(e, "axis", xyz=" ".join(map(str, axis)))
            ET.SubElement(e, "limit", lower=str(limits[0]), upper=str(limits[1]), velocity=str(velocity), effort=str(effort))
            ET.SubElement(e, "dynamics", damping="1", friction="0.1")
            if mimic:
                ET.SubElement(e, "mimic", joint=mimic, multiplier="1", offset="0")
        joints.append(dict(name=name, parent=parent, child=child, kind=kind, xyz=xyz, rpy=list(rpy), axis=axis, limits=limits, effort=effort, velocity=velocity))
    for n in ["world", "base_slide_x", "base_slide_y"]:
        link(n)
    link("base", cfg["base_size"], (0, 0, 0.10), (0.10, 0.15, 0.20, 1), True)
    joint("base_x", "world", "base_slide_x", "prismatic", axis=(1, 0, 0), limits=(-3, 3), effort=1500, velocity=0.5)
    joint("base_y", "base_slide_x", "base_slide_y", "prismatic", axis=(0, 1, 0), limits=(-3, 3), effort=1500, velocity=0.5)
    joint("base_yaw", "base_slide_y", "base", "revolute", limits=(-12.56, 12.56), effort=1500)
    link("column_fixed", cfg["column_size"], (0, 0, 0.27))
    joint("column_mount", "base", "column_fixed", xyz=(0, 0, 0.18))
    # Keep the moving tube inside the fixed column even at maximum extension.
    link("lift_link", [0.075, 0.075, 0.62], (0, 0, -0.30))
    joint("lift", "column_fixed", "lift_link", "prismatic", xyz=(0, 0, 0.54), axis=(0, 0, 1), limits=(0, cfg["lift_stroke"]), effort=1500, velocity=0.15)
    link("torso", cfg["torso_size"], (0, 0, 0.12))
    joint("hip_pitch", "lift_link", "torso", "revolute", axis=(0, 1, 0), limits=(-np.pi/12, np.pi/4), effort=600, velocity=0.5)
    link("head_pan_link", [0.07, 0.07, 0.17], (0, 0, -0.08))
    joint("head_pan", "torso", "head_pan_link", "revolute", xyz=(0, 0, 0.38), limits=(-1.8, 1.8))
    link("head", [0.16, 0.22, 0.11], (0.035, 0, 0), (0.1, 0.2, 0.25, 1), True)
    joint("head_tilt", "head_pan_link", "head", "revolute", axis=(0, 1, 0), limits=(-0.7, 1.1))
    optical = Rotation.from_matrix([[0, 0, 1], [-1, 0, 0], [0, -1, 0]]).as_euler("xyz")
    for side, sign in [("left", 1), ("right", -1)]:
        cam = f"head_cam_{side}"
        link(cam)
        joint(cam+"_mount", "head", cam, xyz=(0.12, sign*cfg["stereo_baseline"]/2, 0), rpy=optical)
        parent = "torso"
        specs = [("shoulder_pitch", (0, 1, 0), (0, sign*0.20, 0.22), None),
                 ("shoulder_roll", (1, 0, 0), (0, 0, 0), None),
                 ("shoulder_yaw", (0, 0, 1), (0, 0, 0), [0.09, 0.09, 0.29]),
                 ("elbow", (0, 1, 0), (0, 0, -0.29), [0.075, 0.075, 0.25]),
                 ("wrist_yaw", (0, 0, 1), (0, 0, -0.25), None),
                 ("wrist_pitch", (0, 1, 0), (0, 0, 0), None),
                 ("wrist_roll", (1, 0, 0), (0, 0, 0), [0.07, 0.08, 0.08])]
        for label, axis, xyz, size in specs:
            name = f"{side}_{label}"
            child = name+"_link"
            link(child, size if size else [0.085]*3, (0, 0, -size[2]/2) if size else (0, 0, 0), rounded=True)
            limits = (-2.4, 0.0) if label == "elbow" else (-2.6, 2.6)
            joint(name, parent, child, "revolute", xyz=xyz, axis=axis, limits=limits)
            parent = child
        cam = "wrist_cam_"+("l" if side == "left" else "r")
        link(cam)
        wrist_optical=Rotation.from_matrix(Rotation.from_euler('y',2.3).as_matrix()@Rotation.from_euler('xyz',optical).as_matrix()).as_euler('xyz')
        joint(cam+"_mount", parent, cam, xyz=(-0.02, sign*0.10, -0.15), rpy=wrist_optical)
        link(side+"_palm", [0.06, 0.09, 0.035])
        joint(side+"_palm_mount", parent, side+"_palm", xyz=(0, 0, -0.09))
        for i, sg in enumerate([1, -1]):
            child = f"{side}_finger_{i}"
            link(child, [0.025, 0.018, 0.07], (0, 0, -0.035))
            joint(child+"_joint", side+"_palm", child, "prismatic", xyz=(0, sg*0.025, 0), axis=(0, sg, 0), limits=(0, 0.025), effort=20, velocity=0.1, mimic=f"{side}_finger_0_joint" if i else None)
    ET.indent(root)
    ET.ElementTree(root).write(out / "relay.urdf", encoding="utf-8", xml_declaration=True)
    (out / "design.json").write_text(json.dumps(dict(links=links, joints=joints), indent=2), encoding="utf-8", newline="\n")
    doc = ["# Relay robot", "", "An experimental simulated robot with procedural meshes and declared design parameters. No physical robot was built.", "", "Editable source: `configs/robot.yaml` and `p2/robot/gen_robot.py`. Regenerate with `python -m p2.robot.gen_robot`.", "", "Mesh volume times assumed homogeneous density supplies link masses and trimesh inertias. These are design assumptions, not hardware measurements. Collision uses bounding boxes. Self collision is disabled because the virtual shoulder joints coincide; environment collision remains enabled. Gripper second fingers use URDF mimic joints.", "", "SAPIEN joint drives implement PD position control for the upper body and velocity control for the holonomic virtual base.", "", "All dimensions, joint limits, efforts, velocities and masses below are design values generated from the config and procedural source.", "", "| Joint | Type | Limits | Axis | Origin xyz | Origin rpy | Effort | Velocity |", "|---|---|---|---|---|---|---|---|"]
    doc += [f"| {j['name']} | {j['kind']} | {j['limits']} | {j['axis']} | {j['xyz']} | {j['rpy']} | {j['effort']} | {j['velocity']} |" for j in joints]
    doc += ["", "## Link geometry", "", "Assumed masses, mesh dimensions and centres of mass follow. Open the procedural operator view to inspect the model.", "", "| Link | Mass kg | Size m | COM m |", "|---|---|---|---|"]
    doc += [f"| {l['name']} | {l['mass']:.5f} | {l['size']} | {l['center']} |" for l in links]
    Path("docs/ROBOT.md").write_text("\n".join(doc), encoding="utf-8", newline="\n")
    print(json.dumps({"links": len(links), "joints": len(joints), "actuated_and_mimic": sum(j['kind'] != 'fixed' for j in joints), "urdf": str(out / 'relay.urdf')}))
    return cfg


if __name__ == "__main__":
    generate()
