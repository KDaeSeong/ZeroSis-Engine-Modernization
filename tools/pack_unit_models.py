#!/usr/bin/env python3
"""Package validated stock Warrior GR2 exports for WorldUnitAssets.h.

The exporter is the trusted source of Granny bone/model data; this tool checks
the sealed export manifest against the installed Civ V inputs, skins the stock
Warrior mesh from the sampled t=0 pose, and writes the exact ZSUNIT01 v1 format.
It never writes into the game installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(HERE))
from civ5_ui_assets import Fpk  # noqa: E402

DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
EXPECTED_MEMBERS = {
    "ART_DEF_UNIT_MEMBER_WARRIOR_V2": 3,
    "ART_DEF_UNIT_MEMBER_WARRIOR": 6,
    "ART_DEF_UNIT_MEMBER_WARRIOR_V4": 3,
}
MAX_JSON = 64 * 1024 * 1024
MAX_DDS = 16 * 1024 * 1024
MAX_PACKAGE = 64 * 1024 * 1024
MAX_VERTICES = 200_000
MAX_INDICES = 600_000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def finite_number(value, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} is not numeric")
    out = float(value)
    require(math.isfinite(out), f"{label} is not finite")
    return out


def array(value, length: int, label: str) -> list:
    require(isinstance(value, list) and len(value) == length, f"{label} must contain {length} entries")
    return value


def text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    require(child is not None and child.text is not None, f"Missing XML field {name}")
    return child.text.strip()


def resolve_pack_name(pack: Fpk, reference: str) -> str:
    normalized = reference.replace("\\", "/").strip("/").casefold()
    exact = [entry.name for entry in pack.entries.values()
             if entry.name.replace("\\", "/").casefold() == normalized]
    if exact:
        require(len(exact) == 1, f"Ambiguous exact FPK reference {reference}")
        return exact[0]
    basename = normalized.rsplit("/", 1)[-1]
    matches = [entry.name for entry in pack.entries.values()
               if entry.name.replace("\\", "/").casefold().rsplit("/", 1)[-1] == basename]
    require(len(matches) == 1, f"Expected a unique FPK basename for {reference}; got {matches}")
    return matches[0]


def safe_export_json(exports: Path, record: dict) -> Path:
    require(isinstance(record, dict) and isinstance(record.get("path"), str), "Invalid manifest JSON path record")
    raw = Path(record["path"])
    path = (raw if raw.is_absolute() else exports / raw).resolve(strict=True)
    require(path.is_relative_to(exports) and path.is_file(), "Export JSON escapes the sealed export directory")
    require(path.stat().st_size <= MAX_JSON, "Export JSON exceeds 64 MiB bound")
    actual = sha256_file(path)
    require(re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))) is not None and
            actual == record["sha256"].lower(), "Export JSON SHA-256 mismatch")
    return path


def safe_manifest_payload(exports: Path, record: dict, label: str) -> Path:
    require(isinstance(record, dict) and isinstance(record.get("extracted"), dict),
            f"Missing extracted provenance for {label}")
    item = record["extracted"]
    require(isinstance(item.get("path"), str) and re.fullmatch(r"[0-9a-f]{64}",
            str(item.get("sha256", ""))) is not None, f"Invalid extracted provenance for {label}")
    path = Path(item["path"]).resolve(strict=True)
    require(path.is_relative_to(exports) and path.is_file(), f"Extracted {label} escapes export directory")
    require(sha256_file(path) == item["sha256"].lower(), f"Extracted {label} hash mismatch")
    return path


def mat_vec(matrix: list[float], vector: list[float]) -> list[float]:
    # Granny exporter uses column-major 4x4 arrays; multiply a column vector.
    return [sum(matrix[row + 4 * col] * vector[col] for col in range(4)) for row in range(4)]


def linear_vec(matrix: list[float], vector: list[float]) -> list[float]:
    return [sum(matrix[row + 4 * col] * vector[col] for col in range(3)) for row in range(3)]


def normalized(v: list[float], label: str) -> list[float]:
    length = math.sqrt(sum(x * x for x in v))
    require(math.isfinite(length) and length > 1.0e-8, f"{label} has zero/invalid length")
    return [x / length for x in v]


def matrix_multiply(a: list[float], b: list[float]) -> list[float]:
    return [sum(a[row + 4 * k] * b[k + 4 * col] for k in range(4))
            for col in range(4) for row in range(4)]


def local_matrix(position: list[float], quaternion: list[float], scale_shear: list[float],
                 transpose_scale: bool) -> list[float]:
    position = [finite_number(v, "local position") for v in array(position, 3, "local position")]
    q = [finite_number(v, "local orientation") for v in array(quaternion, 4, "local orientation")]
    scale_shear = [finite_number(v, "local scale/shear") for v in array(scale_shear, 9, "local scale/shear")]
    norm = math.sqrt(sum(v * v for v in q))
    require(0.99 < norm < 1.01, "Local quaternion is not near unit length")
    x, y, z, w = [v / norm for v in q]
    # Match the documented Granny column-vector quaternion construction.
    rotation = [1 - 2*y*y - 2*z*z, 2*x*y + 2*w*z, 2*x*z - 2*w*y, 0,
                2*x*y - 2*w*z, 1 - 2*x*x - 2*z*z, 2*y*z + 2*w*x, 0,
                2*x*z + 2*w*y, 2*y*z - 2*w*x, 1 - 2*x*x - 2*y*y, 0,
                0, 0, 0, 1]
    shear = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for row in range(3):
        for col in range(3):
            shear[row + 4 * col] = scale_shear[col + 3 * row if transpose_scale else row + 3 * col]
    result = matrix_multiply(rotation, shear)
    result[12:15] = position
    return result


def compose_world(local: list[list[float]], parents: list[int]) -> list[list[float]]:
    world: list[list[float] | None] = [None] * len(local)
    visiting = [False] * len(local)

    def visit(index: int) -> list[float]:
        require(not visiting[index], "Skeleton parent cycle")
        if world[index] is not None:
            return world[index]
        visiting[index] = True
        parent = parents[index]
        world[index] = local[index] if parent < 0 else matrix_multiply(visit(parent), local[index])
        visiting[index] = False
        return world[index]

    for i in range(len(local)):
        visit(i)
    return [m for m in world if m is not None]


def matrix_max_error(actual: list[float], expected: list[float]) -> float:
    return max(abs(a - b) for a, b in zip(actual, expected))


def validate_transform_evidence(exported: dict, member: str, instance_count: int,
                                slot_start: int) -> dict:
    require(isinstance(exported.get("models"), list) and len(exported["models"]) == 1,
            f"Expected one model in {member}")
    model = exported["models"][0]
    bones = model.get("bones")
    require(isinstance(bones, list) and 0 < len(bones) <= 512, f"Invalid skeleton in {member}")
    names = []
    parents = []
    for bone in bones:
        require(isinstance(bone, dict) and isinstance(bone.get("name"), str) and
                bone["name"] and bone["name"] not in names, f"Missing/duplicate skeleton name in {member}")
        names.append(bone["name"])
        parent = bone.get("parent")
        require(isinstance(parent, int) and not isinstance(parent, bool) and -1 <= parent < len(bones),
                f"Invalid skeleton parent in {member}")
        parents.append(parent)
        for key in ("local_position", "local_orientation", "local_scale_shear"):
            require(key in bone, f"Missing {key} from source skeleton record")
    pose = exported.get("pose")
    require(isinstance(pose, dict) and pose.get("method") == "original_track_curve_samples",
            f"Pose is not an original animation-curve sample in {member}")
    require(finite_number(pose.get("time"), "pose.time") == 0.0 and
            finite_number(pose.get("duration"), "pose.duration") > 0,
            f"Pose time/duration invalid in {member}")
    transpose_scale = pose.get("scale_shear_transposed")
    require(isinstance(transpose_scale, bool), "Missing scale/shear layout evidence")
    require(pose.get("bone_names") == names, f"Pose skeleton ordering differs in {member}")
    sampled_tracks = pose.get("sampled_tracks")
    require(isinstance(sampled_tracks, list) and len(sampled_tracks) <= len(bones),
            f"Invalid sampled curve list in {member}")
    track_map = {}
    identity_curves = 0
    for track in sampled_tracks:
        require(isinstance(track, dict) and isinstance(track.get("name"), str) and
                track["name"] in names and track["name"] not in track_map,
                f"Unknown/duplicate sampled curve name in {member}")
        for key, dim, identity_value in (("position", 3, [0, 0, 0]),
                                         ("orientation", 4, [0, 0, 0, 1]),
                                         ("scale_shear", 9, [1, 0, 0, 0, 1, 0, 0, 0, 1])):
            values = [finite_number(v, f"sampled {key}") for v in array(track.get(key), dim, f"sampled {key}")]
            flag = track.get(key.replace("_shear", "") + "_identity") if key != "scale_shear" else track.get("scale_identity")
            require(isinstance(flag, bool), f"Missing {key} curve identity flag")
            if flag:
                require(all(abs(a - b) <= 1e-7 for a, b in zip(values, identity_value)),
                        f"Identity {key} curve differs from identity values")
                identity_curves += 1
        track_map[track["name"]] = track

    bind_local = [local_matrix(b["local_position"], b["local_orientation"], b["local_scale_shear"],
                               transpose_scale) for b in bones]
    bind_world = compose_world(bind_local, parents)
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    bind_error = max(matrix_max_error(matrix_multiply(world, [finite_number(v, "inverse bind") for v in array(bone.get("inverse"), 16, "inverse bind")]), identity)
                     for world, bone in zip(bind_world, bones))
    recorded_bind_error = finite_number(pose.get("bind_matrix_max_error"), "recorded bind error")
    require(bind_error < 0.002 and abs(bind_error - recorded_bind_error) < 0.002,
            f"Independent skeleton bind composition failed in {member}: computed={bind_error}, recorded={recorded_bind_error}")

    animated_local = []
    for bone in bones:
        track = track_map.get(bone["name"])
        if track is None:
            animated_local.append(local_matrix(bone["local_position"], bone["local_orientation"],
                                               bone["local_scale_shear"], transpose_scale))
        else:
            animated_local.append(local_matrix(track["position"], track["orientation"],
                                               track["scale_shear"], transpose_scale))
    computed_pose = compose_world(animated_local, parents)
    given_pose = pose.get("matrices")
    require(isinstance(given_pose, list) and len(given_pose) == len(bones),
            f"Pose matrix count differs from skeleton in {member}")
    given_pose = [[finite_number(v, "pose matrix") for v in array(m, 16, "pose matrix")] for m in given_pose]
    pose_error = max(matrix_max_error(actual, expected) for actual, expected in zip(computed_pose, given_pose))
    require(pose_error < 0.002, f"Independent t=0 curve composition failed in {member}: {pose_error}")

    meshes = exported.get("meshes")
    require(isinstance(meshes, list) and meshes, f"No source geometry in {member}")
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    skinned_min = [float("inf")] * 3
    skinned_max = [float("-inf")] * 3
    for mesh in meshes:
        bindings = mesh.get("bindings")
        require(isinstance(bindings, list) and bindings and all(name in names for name in bindings),
                f"Invalid source bone binding in {member}")
        for vertex in mesh.get("vertices", []):
            pos = [finite_number(v, "source vertex position") for v in array(vertex.get("position"), 3, "source vertex position")]
            normal = [finite_number(v, "source vertex normal") for v in array(vertex.get("normal"), 3, "source vertex normal")]
            array(vertex.get("uv"), 2, "source vertex UV")
            indices = array(vertex.get("boneIndices"), 4, "source vertex indices")
            weights = array(vertex.get("boneWeights"), 4, "source vertex weights")
            require(sum(weights) == 255 and all(isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 255 for w in weights),
                    f"Source skin weights invalid in {member}")
            require(all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(bindings) for i in indices),
                    f"Source skin indices invalid in {member}")
            require(math.sqrt(sum(x*x for x in normal)) > 1e-8, f"Source normal is zero in {member}")
            for axis in range(3):
                bounds_min[axis] = min(bounds_min[axis], pos[axis])
                bounds_max[axis] = max(bounds_max[axis], pos[axis])
            for slot in range(slot_start, slot_start + instance_count):
                out_pos, _, _ = transform_vertex(vertex, mesh, bones, computed_pose, slot)
                for axis in range(3):
                    skinned_min[axis] = min(skinned_min[axis], out_pos[axis])
                    skinned_max[axis] = max(skinned_max[axis], out_pos[axis])
    extents = [bounds_max[i] - bounds_min[i] for i in range(3)]
    require(extents[2] > extents[1] * 3.0 and extents[2] > 1.0,
            f"Source mesh bounds do not support the expected Z-up source basis in {member}: {extents}")
    require(all(abs(v) <= 2.0 for v in skinned_min + skinned_max),
            f"Skinned candidate geometry exceeds package tile bounds in {member}")
    return {"method": pose["method"], "curve_tracks": len(track_map),
            "curve_identity_flags": identity_curves, "bind_fallback_bones": len(bones) - len(track_map),
            "bind_matrix_max_error_independent": bind_error,
            "pose_matrix_max_error_independent": pose_error,
            "source_bounds_xyz": {"min": bounds_min, "max": bounds_max, "extents": extents,
                                  "basis_check": "Z extent exceeds Y extent by >3x"},
            "skinned_candidate_bounds_xyz": {"min": skinned_min, "max": skinned_max,
                                             "tile_bound": 2.0}}


def dds_info(data: bytes, label: str) -> dict:
    require(128 <= len(data) <= MAX_DDS and data[:4] == b"DDS ", f"Invalid/oversized DDS {label}")
    words = struct.unpack_from("<32I", data)
    require(words[1] == 124 and words[19] == 32 and words[20] == 4,
            f"Unexpected DDS header sizes/FOURCC flag for {label}")
    require(words[6] == 0 and words[28] == 0, f"Volume/cubemap DDS is unsupported: {label}")
    # NVTT stock DDS files use the reserved header bytes for its private marker;
    # WorldUnitAssets.h ignores those words and validates the fields below.
    width, height, mip_count = words[4], words[3], words[7]
    require(0 < width <= 4096 and 0 < height <= 4096 and 0 < mip_count <= 13,
            f"DDS dimensions/mip count outside loader bounds: {label}")
    fourcc = words[21]
    block = 8 if fourcc == 0x31545844 else 16 if fourcc in (0x33545844, 0x35545844) else 0
    require(block != 0, f"Unsupported stock DDS compression in {label}")
    allowed_mips = 0
    dim = max(width, height)
    while dim:
        allowed_mips += 1
        dim >>= 1
    require(mip_count <= allowed_mips, f"DDS mip count exceeds dimensions: {label}")
    offset = 128
    for level in range(mip_count):
        w, h = max(1, width >> level), max(1, height >> level)
        offset += ((w + 3) // 4) * ((h + 3) // 4) * block
        require(offset <= len(data), f"Truncated DDS mip chain: {label}")
    require(offset == len(data), f"Unexpected DDS trailing bytes: {label}")
    return {"width": width, "height": height, "mips": mip_count,
            "format": {0x31545844: "BC1", 0x33545844: "BC2", 0x35545844: "BC3"}[fourcc],
            "bytes": len(data), "sha256": sha256(data)}


def f32(value: float) -> bytes:
    require(math.isfinite(value) and abs(value) <= 10000.0, "Package float is nonfinite or outside loader bound")
    return struct.pack("<f", value)


def u32(value: int) -> bytes:
    require(isinstance(value, int) and 0 <= value <= 0xFFFFFFFF, "Package integer outside u32 range")
    return struct.pack("<I", value)


def transform_vertex(vertex: dict, mesh: dict, model_bones: list[dict], pose_matrices: list[list[float]],
                     formation_slot: int) -> tuple[list[float], list[float], list[float]]:
    position = array(vertex.get("position"), 3, "vertex.position")
    normal = array(vertex.get("normal"), 3, "vertex.normal")
    for i in range(3):
        position[i] = finite_number(position[i], "vertex.position")
        normal[i] = finite_number(normal[i], "vertex.normal")
    source_position = [*position, 1.0]
    source_normal = normal
    bindings = mesh["bindings"]
    bone_names = [bone["name"] for bone in model_bones]
    bone_index_by_name = {name: i for i, name in enumerate(bone_names)}
    v_indices = array(vertex.get("boneIndices"), 4, "vertex.boneIndices")
    v_weights = array(vertex.get("boneWeights"), 4, "vertex.boneWeights")
    weights = []
    skinned_pos = [0.0, 0.0, 0.0, 0.0]
    skinned_normal = [0.0, 0.0, 0.0]
    for lane, (raw_index, raw_weight) in enumerate(zip(v_indices, v_weights)):
        require(isinstance(raw_index, int) and not isinstance(raw_index, bool) and
                0 <= raw_index < len(bindings), "Skin binding index out of range")
        require(isinstance(raw_weight, int) and not isinstance(raw_weight, bool) and
                0 <= raw_weight <= 255, "Skin weight is not a byte")
        weights.append(raw_weight)
        if not raw_weight:
            continue
        bone_name = bindings[raw_index]
        require(bone_name in bone_index_by_name, f"Skin binding names an unknown bone: {bone_name}")
        bi = bone_index_by_name[bone_name]
        inv_bind = [finite_number(x, "bone.inverse") for x in array(model_bones[bi].get("inverse"), 16, "bone.inverse")]
        pose = pose_matrices[bi]
        bind_pos = mat_vec(inv_bind, source_position)
        world_pos = mat_vec(pose, bind_pos)
        world_normal = linear_vec(pose, linear_vec(inv_bind, source_normal))
        factor = raw_weight / 255.0
        for axis in range(4):
            skinned_pos[axis] += world_pos[axis] * factor
        for axis in range(3):
            skinned_normal[axis] += world_normal[axis] * factor
    require(sum(weights) == 255, "Vertex skin weights do not sum to 255")
    require(abs(skinned_pos[3]) > 1.0e-8, "Skinned vertex has invalid homogeneous W")
    x, source_y, source_z = skinned_pos[0] / skinned_pos[3], skinned_pos[1] / skinned_pos[3], skinned_pos[2] / skinned_pos[3]
    # Granny source is Z-up. Renderer coordinates are X/Y-up/Z-forward.
    # Four-by-three row-major slot placement is a candidate centered grid.
    col, row = formation_slot % 4, formation_slot // 4
    offset_x = (col - 1.5) * 13.0
    offset_z = (row - 1.0) * 13.0
    member_scale = 0.14
    candidate_scale = 1.0 / 80.0
    out_position = [(x * member_scale + offset_x) * candidate_scale,
                    source_z * member_scale * candidate_scale,
                    (-source_y * member_scale + offset_z) * candidate_scale]
    out_normal = normalized([skinned_normal[0], skinned_normal[2], -skinned_normal[1]], "skinned normal")
    uv = array(vertex.get("uv"), 2, "vertex.uv")
    out_uv = [finite_number(uv[0], "vertex.uv"), finite_number(uv[1], "vertex.uv")]
    require(all(abs(v) <= 2.0 for v in out_position), "Candidate unit vertex exceeds ±2 tile bound")
    return out_position, out_normal, out_uv


def load_json(path: Path) -> dict:
    data = path.read_bytes()
    require(0 < len(data) <= MAX_JSON, f"JSON size outside bound: {path}")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid UTF-8 JSON: {path}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--validate-transforms-only", action="store_true",
                         help="independently validate original bind/curve matrix composition without packaging")
    args = parser.parse_args()
    exports = args.exports.resolve(strict=True)
    require(exports.is_dir(), "--exports must name a directory")
    game = args.game.resolve(strict=True)
    require(exports.is_relative_to(PROJECT.resolve()) and not exports.is_relative_to(game),
            "Export JSON directory must be a workspace candidate, outside the game installation")

    source_manifest_path = exports / "export-manifest.json"
    manifest = load_json(source_manifest_path)
    require(manifest.get("status") == "PASS_STOCK_UNIT_EXPORT", "Source export manifest is not a stock-export PASS")
    outputs = manifest.get("outputs")
    require(isinstance(outputs, list) and len(outputs) == 3, "Expected three Warrior member JSON outputs")
    require(isinstance(manifest.get("inputs"), (dict, list)) and manifest["inputs"],
            "Source manifest has no original input provenance")
    by_member = {}
    for output in outputs:
        require(isinstance(output, dict), "Invalid export output row")
        member = output.get("member_type")
        require(member in EXPECTED_MEMBERS and member not in by_member, "Unexpected/duplicate member export")
        path = safe_export_json(exports, output.get("json"))
        by_member[member] = (path, load_json(path), output["json"]["sha256"].lower())
    require(set(by_member) == set(EXPECTED_MEMBERS), "Warrior export member set mismatch")

    if args.validate_transforms_only:
        gsd_record = manifest.get("gsd")
        safe_manifest_payload(exports, gsd_record, "string database")
        gsd_hash = gsd_record.get("sha256", "").lower()
        results = []
        slot_start = 0
        for member, count in EXPECTED_MEMBERS.items():
            _, exported, _ = by_member[member]
            output_record = next(row for row in outputs if row.get("member_type") == member)
            safe_manifest_payload(exports, output_record.get("model"), f"{member} model")
            safe_manifest_payload(exports, output_record.get("idle"), f"{member} idle")
            require(exported.get("source_sha256", "").lower() == output_record["model"].get("sha256", "").lower(),
                    f"Exported model hash does not match provenance manifest for {member}")
            require(exported.get("animation_sha256", "").lower() == output_record["idle"].get("sha256", "").lower(),
                    f"Exported idle hash does not match provenance manifest for {member}")
            require(exported.get("gsd_sha256", "").lower() == gsd_hash,
                    f"Exported GSD hash does not match provenance manifest for {member}")
            results.append({"member_type": member, **validate_transform_evidence(exported, member, count, slot_start)})
            slot_start += count
        print(json.dumps({"status": "PASS_ORIGINAL_TRANSFORM_REVIEW", "run_id": manifest.get("run_id"),
                          "members": results,
                          "claim_boundary": "matrix/bind/curve and source geometry checks only; no package/runtime/retail visual claim"}, indent=2))
        return 0

    model_fpk_path = game / "Resource" / "Common" / "UnitModels.fpk"
    texture_fpk_path = game / "Resource" / "DX9" / "UnitsTextures.fpk"
    unit_art_path = game / "Assets" / "Units" / "Civ5ArtDefines_Units.xml"
    member_art_path = game / "Assets" / "Units" / "Civ5ArtDefines_UnitMembers.xml"
    formations_path = game / "Assets" / "Units" / "UnitFormations.xml"
    source_paths = [source_manifest_path, model_fpk_path, texture_fpk_path, unit_art_path,
                    member_art_path, formations_path,
                    PROJECT / "Source" / "Presentation" / "WorldUnitAssets.h"]
    for member, (path, data, expected_hash) in by_member.items():
        source_paths.append(path)
    source_paths = [path.resolve(strict=True) for path in source_paths]
    before = {str(path): sha256_file(path) for path in source_paths}

    model_pack = Fpk(model_fpk_path)
    texture_pack = Fpk(texture_fpk_path)
    gsd_name = resolve_pack_name(model_pack, "unitmodels_stringdatabase.gsd")
    gsd_data, gsd_info = model_pack.read(gsd_name)
    art_root = ET.parse(unit_art_path).getroot()
    unit_rows = [node for node in art_root.findall(".//UnitArtInfo")
                 if text(node, "Type") == "ART_DEF_UNIT__WARRIOR"]
    require(len(unit_rows) == 1, "Original unit art XML must contain exactly one Warrior entry")
    unit_row = unit_rows[0]
    require(text(unit_row, "Formation") == "Warrior", "Warrior formation tag changed")
    selected = []
    for row in unit_row.findall("UnitMemberArt"):
        member = text(row, "MemberType")
        count = int(text(row, "MemberCount"))
        selected.append((member, count))
    require(selected == list(EXPECTED_MEMBERS.items()),
            f"Original Warrior member selection differs: {selected}")

    member_root = ET.parse(member_art_path).getroot()
    member_rows = {}
    for row in member_root.findall(".//UnitMemberArtInfo"):
        node = row.find("Type")
        if node is not None and node.text and node.text.strip() in EXPECTED_MEMBERS:
            tag = node.text.strip()
            require(tag not in member_rows, f"Duplicate original member XML row: {tag}")
            member_rows[tag] = {"scale": float(text(row, "fScale")),
                                "fxsxml": text(row, "Granny").replace("\\", "/")}
    require(set(member_rows) == set(EXPECTED_MEMBERS) and all(v["scale"] == 0.14 for v in member_rows.values()),
            "Original Warrior member fScale rows failed validation")

    formations_root = ET.parse(formations_path).getroot()
    formation_rows = [row for row in formations_root.findall(".//Formation") if text(row, "Name") == "Warrior"]
    require(len(formation_rows) == 1, "Expected one original Warrior formation row")
    formation = formation_rows[0]
    formation_source = {key: text(formation, key) for key in
                        ("SpacingX", "SpacingY", "SpacingMultiplier", "PerRowInc", "YOffsetInc",
                         "YOffsetCurved", "Stagger", "UnitRandomness", "BlockRandomness", "TotalWidth",
                         "XBlockSize", "XBlockSpacingCount", "YBlockSize", "YBlockSpacingCount", "CenterWidth")}
    require(int(formation_source["SpacingX"]) == 13 and int(formation_source["SpacingY"]) == 13 and
            int(formation_source["TotalWidth"]) == 4, "Warrior formation spacing/width differ from original")

    texture_cache: dict[str, tuple[int, bytes, dict]] = {}
    texture_records = []
    art_meshes = []
    source_links = []
    total_instances = 0
    slot_start = 0
    for member, instance_count in selected:
        export_path, exported, json_hash = by_member[member]
        require(exported.get("source_sha256"), f"Missing source GR2 digest for {member}")
        require(exported.get("gsd_sha256", "").lower() == gsd_info["sha256"],
                f"GSD digest mismatch for {member}")
        require(re.fullmatch(r"[0-9a-f]{64}", exported["source_sha256"].lower()) is not None and
                re.fullmatch(r"[0-9a-f]{64}", exported.get("animation_sha256", "").lower()) is not None,
                f"Invalid GR2 digest fields for {member}")
        require(isinstance(exported.get("models"), list) and len(exported["models"]) == 1,
                f"Expected exactly one original model in {member}")
        model = exported["models"][0]
        bones = model.get("bones")
        require(isinstance(bones, list) and 0 < len(bones) <= 512, f"Invalid skeleton bone array for {member}")
        bone_names = []
        for bone in bones:
            require(isinstance(bone.get("name"), str) and bone["name"] and bone["name"] not in bone_names,
                    f"Missing/duplicate bone name in {member}")
            bone_names.append(bone["name"])
            require(isinstance(bone.get("parent"), int) and not isinstance(bone["parent"], bool) and
                    -1 <= bone["parent"] < len(bones) and bone["parent"] != len(bone_names) - 1,
                    f"Invalid bone parent in {member}")
            inverse = array(bone.get("inverse"), 16, "bone.inverse")
            for value in inverse:
                finite_number(value, "bone.inverse")
        pose = exported.get("pose")
        require(isinstance(pose, dict) and finite_number(pose.get("time"), "pose.time") == 0.0,
                f"Missing exact t=0 pose for {member}")
        finite_number(pose.get("duration"), "pose.duration")
        require(pose["duration"] > 0, "Idle animation duration must be positive")
        require(pose.get("bone_names") == bone_names, f"Pose bone order differs from model bones for {member}")
        pose_matrices = pose.get("matrices")
        require(isinstance(pose_matrices, list) and len(pose_matrices) == len(bones),
                f"Pose matrix count differs from skeleton for {member}")
        pose_matrices = [[finite_number(v, "pose matrix") for v in array(matrix, 16, "pose matrix")]
                         for matrix in pose_matrices]

        fxs_name = resolve_pack_name(model_pack, member_rows[member]["fxsxml"])
        fxs_bytes, fxs_provenance = model_pack.read(fxs_name)
        fxs_root = ET.fromstring(fxs_bytes)
        model_refs = [node.attrib.get("file", "").strip().replace("\\", "/") for node in fxs_root.findall(".//Mesh")]
        idle_refs = [node.attrib.get("file", "").strip().replace("\\", "/") for node in fxs_root.findall(".//Animation")
                     if Path(node.attrib.get("file", "")).name.casefold() == "warrior_idlea.gr2"]
        require(len(model_refs) == 1 and Path(model_refs[0]).name.casefold().endswith(".gr2"),
                f"FXSXML model reference is missing/ambiguous for {member}")
        require(len(idle_refs) == 1, f"FXSXML base IdleA reference is missing/ambiguous for {member}")
        source_model_name = resolve_pack_name(model_pack, model_refs[0])
        source_model_bytes, source_model_info = model_pack.read(source_model_name)
        source_idle_name = resolve_pack_name(model_pack, idle_refs[0])
        source_idle_bytes, source_idle_info = model_pack.read(source_idle_name)
        require(sha256(source_model_bytes) == exported["source_sha256"].lower(),
                f"Model JSON was exported from a different GR2 than the original FPK: {member}")
        require(sha256(source_idle_bytes) == exported["animation_sha256"].lower(),
                f"Pose JSON was sampled from a different idle GR2 than the original FPK: {member}")
        gsd_digest = exported["gsd_sha256"].lower()
        declared_textures = {Path(node.attrib["file"].replace("\\", "/")).name.casefold()
                             for node in fxs_root.findall(".//Texture") if node.attrib.get("file")}

        meshes = exported.get("meshes")
        require(isinstance(meshes, list) and 0 < len(meshes) <= 64, f"Invalid mesh list in {member}")
        current_member_meshes = []
        mesh_names = set()
        for mesh_index, mesh in enumerate(meshes):
            mesh_name = mesh.get("name")
            require(isinstance(mesh_name, str) and mesh_name and mesh_name not in mesh_names,
                    f"Missing/duplicate mesh name in {member}")
            mesh_names.add(mesh_name)
            bindings = mesh.get("bindings")
            require(isinstance(bindings, list) and bindings and len(bindings) <= 256 and
                    all(isinstance(name, str) and name in bone_names for name in bindings),
                    f"Invalid skin bindings in {member}/{mesh_name}")
            require(len(set(bindings)) == len(bindings), f"Duplicate skin binding names in {member}/{mesh_name}")
            materials = mesh.get("materials")
            require(isinstance(materials, list) and len(materials) == 1,
                    f"Expected one bound stock material for {member}/{mesh_name}")
            material = materials[0]
            diffuse = material.get("diffuse")
            sref = material.get("sref")
            require(isinstance(diffuse, str) and diffuse and isinstance(sref, str) and sref,
                    f"Missing material diffuse/SREF names for {member}/{mesh_name}")
            diffuse_base = Path(diffuse.replace("\\", "/")).name
            sref_base = Path(sref.replace("\\", "/")).name
            require(diffuse_base.casefold() in declared_textures and sref_base.casefold() in declared_textures,
                    f"Material diffuse/SREF is not declared by source FXSXML for {member}/{mesh_name}")
            diffuse_record = resolve_pack_name(texture_pack, diffuse_base)
            diffuse_bytes, diffuse_origin = texture_pack.read(diffuse_record)
            diffuse_info = dds_info(diffuse_bytes, diffuse_record)
            texture_key = diffuse_info["sha256"]
            if texture_key not in texture_cache:
                texture_id = len(texture_records)
                texture_cache[texture_key] = (texture_id, diffuse_bytes, {**diffuse_origin, **diffuse_info,
                                                                          "filename": diffuse_base,
                                                                          "source_aliases": [diffuse_base]})
                texture_records.append(texture_cache[texture_key][2])
            elif diffuse_base not in texture_cache[texture_key][2]["source_aliases"]:
                texture_cache[texture_key][2]["source_aliases"].append(diffuse_base)
            texture_id = texture_cache[texture_key][0]
            vertices = mesh.get("vertices")
            triangles = mesh.get("triangles")
            require(isinstance(vertices, list) and 0 < len(vertices) <= MAX_VERTICES,
                    f"Invalid vertex count for {member}/{mesh_name}")
            require(isinstance(triangles, list) and 0 < len(triangles) * 3 <= MAX_INDICES,
                    f"Invalid triangle count for {member}/{mesh_name}")
            indices = []
            for tri in triangles:
                tri = array(tri, 3, "triangle")
                for index in tri:
                    require(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(vertices),
                            f"Triangle index outside vertex range in {member}/{mesh_name}")
                    indices.append(index)
            current_member_meshes.append({"name": mesh_name, "source_member": member,
                                          "source_mesh_index": mesh_index, "texture": texture_id,
                                          "source_texture": {"diffuse": diffuse, "sref": sref,
                                                             "material_name": material.get("name"),
                                                             "shader": material.get("shader"),
                                                             "alpha": material.get("alpha"),
                                                             "skinBones": material.get("skinBones")},
                                          "vertices": vertices, "indices": indices,
                                          "bindings": bindings, "source_model_bones": bones,
                                          "pose_matrices": pose_matrices,
                                          "instance_start": slot_start, "instance_count": instance_count})
        for instance_offset in range(instance_count):
            formation_slot = slot_start + instance_offset
            total_instances += 1
            for mesh in current_member_meshes:
                baked_vertices = []
                for vertex in mesh["vertices"]:
                    p, n, uv = transform_vertex(vertex, mesh, mesh["source_model_bones"],
                                                mesh["pose_matrices"], formation_slot)
                    baked_vertices.append((*p, *n, *uv))
                # Every member instance retains its original mesh and topology.
                current = {"texture": mesh["texture"], "vertices": baked_vertices,
                           "indices": mesh["indices"], "name": mesh["name"],
                           "source_member": member, "formation_slot": formation_slot,
                           "source_texture": mesh["source_texture"]}
                art_meshes.append(current)
        slot_start += instance_count
        source_links.append({"member_type": member, "member_count": instance_count,
                             "export_json": str(export_path), "export_json_sha256": json_hash,
                             "source_gr2": source_model_info, "idle_gr2": source_idle_info,
                             "fxsxml": fxs_provenance, "gsd": gsd_info,
                             "mesh_count_per_member": len(current_member_meshes),
                             "source_scale": member_rows[member]["scale"],
                             "pose_time": pose["time"], "idle_duration": pose["duration"],
                             "source_fxs_textures": sorted(declared_textures)})
    require(total_instances == 12 and slot_start == 12, "Warrior art must preserve exactly twelve original members")
    require(0 < len(texture_records) <= 64, "Invalid package texture count")
    require(0 < len(art_meshes) <= 128, "Invalid package mesh count")
    require(sum(len(mesh["vertices"]) for mesh in art_meshes) <= 1_000_000 and
            sum(len(mesh["indices"]) for mesh in art_meshes) <= 3_000_000,
            "Aggregate unit geometry exceeds the C++ loader catalog bound")

    data = bytearray(b"ZSUNIT01")
    data += u32(1)
    data += u32(len(texture_records))
    for record in texture_records:
        source = resolve_pack_name(texture_pack, record["filename"])
        dds_bytes, _ = texture_pack.read(source)
        require(sha256(dds_bytes) == record["sha256"], "Diffuse texture changed between read and package")
        data += u32(len(dds_bytes)) + dds_bytes
    data += u32(1)
    art_tag = "ART_DEF_UNIT__WARRIOR"
    encoded_tag = art_tag.encode("ascii")
    data += u32(len(encoded_tag)) + encoded_tag
    data += u32(len(art_meshes))
    for mesh in art_meshes:
        vertices = mesh["vertices"]
        indices = mesh["indices"]
        require(0 < len(vertices) <= MAX_VERTICES and 0 < len(indices) <= MAX_INDICES and len(indices) % 3 == 0,
                "Invalid packaged mesh dimensions")
        data += u32(mesh["texture"]) + u32(len(vertices)) + u32(len(indices))
        for vertex in vertices:
            require(len(vertex) == 8, "Pack vertex must have eight floats")
            for value in vertex:
                data += f32(float(value))
        for index in indices:
            data += u32(index)
        if len(data) > MAX_PACKAGE:
            raise ValueError("Unit asset package exceeds loader's 64 MiB bound")

    package_sha = sha256(data)
    output_root = (PROJECT / "Build" / "UnitAssets" / package_sha).resolve()
    require(output_root.is_relative_to((PROJECT / "Build" / "UnitAssets").resolve()), "Unsafe package path")
    require(not output_root.exists(), f"Package output already exists: {output_root}")
    output_root.mkdir(parents=True)
    package_path = output_root / "unit-assets.bin"
    package_path.write_bytes(data)
    require(sha256_file(package_path) == package_sha, "Written package hash mismatch")
    after = {str(path): sha256_file(path) for path in source_paths}
    require(before == after, "An original or frozen input changed during packaging")
    manifest_out = {
        "schema": 1, "status": "PASS_ORIGINAL_UNIT_PACKAGE", "package": {
            "path": str(package_path), "sha256": package_sha, "bytes": len(data), "format": "ZSUNIT01 v1"},
        "art_tag": art_tag, "source_export_manifest": {"path": str(source_manifest_path),
            "sha256": before[str(source_manifest_path)], "status": manifest["status"],
            "inputs": manifest["inputs"]},
        "original_inputs_before": before, "original_inputs_after": after,
        "unit_selection": [{"member_type": member, "count": count} for member, count in selected],
        "member_scale": {member: member_rows[member]["scale"] for member in member_rows},
        "formation_original": formation_source,
        "formation_candidate": {"layout": "4 columns x 3 rows, row-major centered", "spacingX": 13,
                                "spacingY": 13, "randomness": 0, "curve": 0,
                                "note": "Candidate offsets use original spacing values before 1/80 tile scaling."},
        "coordinate_and_skinning_policy": {
            "matrix_layout": "column-major 4x4; poseWorld * inverseWorldBind * [position,1]",
            "position": "weighted skinning by byte weights /255; Z-up to X/Y-up/Z-forward; member scale 0.14; centered formation offsets; divide by 80",
            "normal": "weighted 3x3 poseWorld * inverseWorldBind; Z-up to X/Y-up/Z-forward; normalized",
            "topology": "original triangles and per-member source mesh retained for all 12 instances"},
        "textures": texture_records, "arts": [{"tag": art_tag, "mesh_count": len(art_meshes),
            "instances": total_instances, "meshes": [{"name": mesh["name"],
                "member_type": mesh["source_member"], "formation_slot": mesh["formation_slot"],
                "texture_index": mesh["texture"], "vertices": len(mesh["vertices"]),
                "indices": len(mesh["indices"]), "diffuse": mesh["source_texture"]["diffuse"],
                "sref": mesh["source_texture"]["sref"], "material": mesh["source_texture"]}
                for mesh in art_meshes]}],
        "source_models": source_links,
        "limits": ["Candidate centered formation; original formation randomness and Y curvature are not reproduced.",
                   "Material alpha behavior is not decoded by this package format.",
                   "Renderer uses diffuse only; original SREF names are preserved as provenance but not packaged.",
                   "Stock source mesh/pose provenance does not establish retail visual equivalence."]}
    manifest_path = output_root / "unit-assets.manifest.json"
    manifest_path.write_text(json.dumps(manifest_out, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest_out["status"], "package_sha256": package_sha,
                      "bytes": len(data), "path": str(package_path), "manifest": str(manifest_path),
                      "textures": len(texture_records), "meshes": len(art_meshes),
                      "instances": total_instances}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"PACKAGE_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        raise
