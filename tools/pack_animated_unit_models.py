#!/usr/bin/env python3
"""Append validated original Warrior rig and skin data to an immutable v1 package."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(HERE))
import pack_unit_models as static_packer  # noqa: E402

EXPECTED_MEMBERS = {
    "ART_DEF_UNIT_MEMBER_WARRIOR_V2": 3,
    "ART_DEF_UNIT_MEMBER_WARRIOR": 6,
    "ART_DEF_UNIT_MEMBER_WARRIOR_V4": 3,
}
MAX_JSON = 64 * 1024 * 1024
MAX_PACKAGE = 64 * 1024 * 1024
MAX_VERTICES = 200_000
MAX_INDICES = 600_000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    data = path.read_bytes()
    require(0 < len(data) <= MAX_JSON, f"JSON size outside bound: {path}")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid UTF-8 JSON: {path}") from error
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def ascii_bytes(value: str, label: str) -> bytes:
    require(isinstance(value, str) and value and "\0" not in value, f"Invalid {label}")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} must be ASCII") from error


def packed_string(value: str, label: str) -> bytes:
    encoded = ascii_bytes(value, label)
    require(len(encoded) <= 4096, f"{label} exceeds the package bound")
    return static_packer.u32(len(encoded)) + encoded


def pack_i32(value: int, label: str) -> bytes:
    require(isinstance(value, int) and not isinstance(value, bool) and
            -(1 << 31) <= value < (1 << 31), f"{label} outside i32 range")
    return struct.pack("<i", value)


def pack_f32(value, label: str) -> bytes:
    number = static_packer.finite_number(value, label)
    return static_packer.f32(number)


def safe_payload(exports: Path, record: dict, label: str) -> tuple[Path, bytes, dict]:
    require(isinstance(record, dict) and isinstance(record.get("extracted"), dict),
            f"Missing extracted provenance for {label}")
    item = record["extracted"]
    raw_path = item.get("path")
    expected_sha = str(item.get("sha256", "")).lower()
    require(isinstance(raw_path, str) and len(expected_sha) == 64,
            f"Invalid extracted provenance for {label}")
    path = Path(raw_path).resolve(strict=True)
    require(path.is_file() and path.is_relative_to(exports), f"{label} escapes the export snapshot")
    data = path.read_bytes()
    require(digest(data) == expected_sha and expected_sha == str(record.get("sha256", "")).lower(),
            f"{label} extracted payload hash mismatch")
    if "bytes" in item:
        require(len(data) == item["bytes"], f"{label} extracted byte count mismatch")
    return path, data, item


def records_by_path(value, label: str) -> dict[str, str]:
    if isinstance(value, dict):
        records = [{"path": path, "sha256": sha} for path, sha in value.items()]
    else:
        require(isinstance(value, list), f"{label} must be a path/hash list")
        records = value
    output = {}
    for row in records:
        require(isinstance(row, dict) and isinstance(row.get("path"), str), f"Invalid {label} record")
        sha = str(row.get("sha256", "")).lower()
        require(len(sha) == 64, f"Invalid SHA-256 in {label}")
        key = str(Path(row["path"]).resolve()).casefold()
        require(key not in output, f"Duplicate path in {label}: {row['path']}")
        output[key] = sha
    return output


def parse_v1_package(data: bytes, manifest: dict) -> tuple[list[dict], list[dict]]:
    require(len(data) <= MAX_PACKAGE and len(data) >= 20, "Static package size is invalid")
    require(data[:8] == b"ZSUNIT01" and struct.unpack_from("<I", data, 8)[0] == 1,
            "Static unit package is not ZSUNIT01 v1")
    cursor = 12

    def u32() -> int:
        nonlocal cursor
        require(cursor + 4 <= len(data), "Truncated v1 package integer")
        value = struct.unpack_from("<I", data, cursor)[0]
        cursor += 4
        return value

    texture_count = u32()
    expected_textures = manifest.get("textures")
    require(isinstance(expected_textures, list) and texture_count == len(expected_textures) and
            0 < texture_count <= 64, "v1 texture count differs from static manifest")
    textures = []
    for index in range(texture_count):
        size = u32()
        require(128 <= size <= 16 * 1024 * 1024 and cursor + size <= len(data), "Invalid v1 DDS record size")
        payload = data[cursor:cursor + size]
        cursor += size
        info = static_packer.dds_info(payload, f"v1 texture {index}")
        expected = expected_textures[index]
        require(info["sha256"] == expected.get("sha256") and size == expected.get("bytes"),
                f"v1 texture {index} differs from static manifest")
        textures.append({"sha256": info["sha256"], "bytes": size})

    art_count = u32()
    arts_meta = manifest.get("arts")
    require(art_count == 1 and isinstance(arts_meta, list) and len(arts_meta) == 1,
            "Expected one static Warrior art record")
    name_len = u32()
    require(0 < name_len <= 256 and cursor + name_len <= len(data), "Invalid v1 art name")
    try:
        art_tag = data[cursor:cursor + name_len].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("v1 art tag is not ASCII") from error
    cursor += name_len
    expected_art = arts_meta[0]
    require(art_tag == manifest.get("art_tag") == expected_art.get("tag"), "v1 art identity mismatch")
    mesh_count = u32()
    mesh_meta = expected_art.get("meshes")
    require(isinstance(mesh_meta, list) and mesh_count == len(mesh_meta) == expected_art.get("mesh_count") == 12,
            "v1 mesh count differs from static manifest")
    meshes = []
    total_vertices = 0
    total_indices = 0
    for mesh_index in range(mesh_count):
        texture = u32()
        vertex_count = u32()
        index_count = u32()
        expected = mesh_meta[mesh_index]
        require(texture < texture_count and 0 < vertex_count <= MAX_VERTICES and
                0 < index_count <= MAX_INDICES and index_count % 3 == 0,
                f"Invalid v1 mesh dimensions at index {mesh_index}")
        require(vertex_count == expected.get("vertices") and index_count == expected.get("indices") and
                texture == expected.get("texture_index"), f"v1 mesh {mesh_index} differs from static manifest")
        require(cursor + vertex_count * 32 + index_count * 4 <= len(data), "Truncated v1 mesh payload")
        vertices = []
        for _ in range(vertex_count):
            vertex = struct.unpack_from("<8f", data, cursor)
            cursor += 32
            require(all(math.isfinite(v) and abs(v) <= 10000 for v in vertex), "Invalid v1 static vertex float")
            require(all(abs(v) <= 2 for v in vertex[:3]), "v1 static position exceeds tile-space bounds")
            normal_length = sum(v * v for v in vertex[3:6])
            require(0.5 <= normal_length <= 1.5, "Invalid v1 static normal")
            vertices.append(vertex)
        indices = list(struct.unpack_from(f"<{index_count}I", data, cursor))
        cursor += index_count * 4
        require(all(index < vertex_count for index in indices), "v1 index outside its mesh vertex array")
        total_vertices += vertex_count
        total_indices += index_count
        meshes.append({"texture": texture, "vertices": vertices, "indices": indices,
                       "metadata": expected})
    require(cursor == len(data), "Unexpected bytes at end of v1 static package")
    require(total_vertices <= 1_000_000 and total_indices <= 3_000_000,
            "Static geometry exceeds the v1 loader bounds")
    return textures, meshes


def build_animation_extension(exports: Path, export_manifest: dict, static_manifest: dict,
                              static_meshes: list[dict]) -> tuple[bytes, list[dict], list[dict], list[dict], dict]:
    outputs = export_manifest.get("outputs")
    require(isinstance(outputs, list) and len(outputs) == len(EXPECTED_MEMBERS),
            "Expected exactly three original unit member export rows")
    output_by_member = {}
    for row in outputs:
        require(isinstance(row, dict), "Invalid export output row")
        member = row.get("member_type")
        require(member in EXPECTED_MEMBERS and member not in output_by_member,
                f"Unexpected or duplicate member in source manifest: {member}")
        output_by_member[member] = row
    require(set(output_by_member) == set(EXPECTED_MEMBERS), "Original member set mismatch")
    gsd_path, gsd_data, gsd_info = safe_payload(exports, export_manifest.get("gsd"), "original GSD")
    gsd_name = ascii_bytes(gsd_path.name, "GSD basename")
    require(b"/" not in gsd_name and b"\\" not in gsd_name and b".." not in gsd_name,
            "GSD package filename is not a safe basename")
    embedded = [{"name": gsd_path.name, "data": gsd_data, "role": "gsd",
                 "source_path": str(gsd_path), "source_sha256": digest(gsd_data)}]

    ordered_members = list(EXPECTED_MEMBERS)
    models = []
    model_export_jsons = {}
    rigs = []
    rig_metadata = []
    member_start = 0
    for rig_index, member in enumerate(ordered_members):
        row = output_by_member[member]
        json_path = static_packer.safe_export_json(exports, row.get("json"))
        exported = static_packer.load_json(json_path)
        json_sha = digest_file(json_path)
        require(json_sha == row["json"].get("sha256", "").lower(), f"JSON hash mismatch for {member}")
        model_path, model_data, model_origin = safe_payload(exports, row.get("model"), f"{member} model GR2")
        idle_path, idle_data, idle_origin = safe_payload(exports, row.get("idle"), f"{member} IdleA GR2")
        require(exported.get("source_sha256", "").lower() == digest(model_data) and
                exported.get("animation_sha256", "").lower() == digest(idle_data),
                f"Exported JSON GR2 hash differs from extracted originals for {member}")
        require(exported.get("gsd_sha256", "").lower() == digest(gsd_data),
                f"Exported JSON GSD hash differs for {member}")
        require(exported.get("models") and len(exported["models"]) == 1,
                f"Expected one original rig model for {member}")
        model = exported["models"][0]
        bones = model.get("bones")
        pose = exported.get("pose")
        require(isinstance(bones, list) and isinstance(pose, dict), f"Missing skeleton or animation sample for {member}")
        source_result = static_packer.validate_transform_evidence(
            exported, member, EXPECTED_MEMBERS[member], member_start)
        require(pose.get("method") == "original_track_curve_samples" and
                static_packer.finite_number(pose.get("time"), "pose.time") == 0.0,
                f"Rig pose evidence is not the original IdleA t=0 sample for {member}")
        source_meshes = exported.get("meshes")
        require(isinstance(source_meshes, list) and len(source_meshes) == 1,
                f"Expected one original mesh per member rig: {member}")
        source_mesh = source_meshes[0]
        require(isinstance(source_mesh.get("vertices"), list) and
                0 < len(source_mesh["vertices"]) <= MAX_VERTICES,
                f"Invalid original source vertex count for {member}")
        source_indices = []
        for triangle in source_mesh.get("triangles", []):
            source_indices.extend(static_packer.array(triangle, 3, "source triangle"))
        require(source_indices and len(source_indices) % 3 == 0 and len(source_indices) <= MAX_INDICES,
                f"Invalid source triangle index count for {member}")
        bindings = source_mesh.get("bindings")
        bone_index = {bone["name"]: index for index, bone in enumerate(bones)}
        require(isinstance(bindings, list) and bindings and len(set(bindings)) == len(bindings) and
                all(name in bone_index for name in bindings), f"Invalid mesh binding table for {member}")

        idle_file_index = 4
        embedded.append({"name": model_path.name, "data": model_data, "role": "model",
                         "member_type": member, "source_path": str(model_path),
                         "source_sha256": digest(model_data)})
        models.append({"path": model_path, "data": model_data, "record": row.get("model"), "member": member})
        model_export_jsons[member] = (exported, json_path, json_sha)

        rigs.append({"member": member, "gsd_file_index": 0, "model_file_index": rig_index + 1,
                     "animation_file_index": idle_file_index,
                     "transpose_scale": bool(pose.get("scale_shear_transposed")),
                     "duration": static_packer.finite_number(pose.get("duration"), "IdleA duration"),
                     "bones": bones})
        rig_metadata.append({"member_type": member, "gsd_file_index": 0, "model_file_index": rig_index + 1,
                             "animation_file_index": idle_file_index,
                             "transpose_scale": bool(pose.get("scale_shear_transposed")),
                             "duration": float(pose["duration"]), "bone_count": len(bones),
                             "source_mesh_vertex_count": len(source_mesh["vertices"]),
                             "source_mesh_index_count": len(source_indices),
                             "independent_t0_validation": source_result})
        member_start += EXPECTED_MEMBERS[member]

    # IdleA is shared by all three source rigs and stored once at file index 4.
    first_idle = safe_payload(exports, output_by_member[ordered_members[0]].get("idle"), "original IdleA GR2")
    idle_path, idle_data = first_idle[0], first_idle[1]
    for member in ordered_members[1:]:
        row = output_by_member[member]
        other_path, other_data, _ = safe_payload(exports, row.get("idle"), f"{member} IdleA GR2")
        require(other_data == idle_data and other_path.name == idle_path.name,
                "The three stock rigs do not reference one identical IdleA file")
    embedded.append({"name": idle_path.name, "data": idle_data, "role": "animation",
                     "source_path": str(idle_path), "source_sha256": digest(idle_data)})
    require(len(embedded) == 5 and len({item["name"].casefold() for item in embedded}) == 5,
            "Embedded original file set must contain GSD, three models, and one deduplicated IdleA")
    for item in embedded:
        encoded = ascii_bytes(item["name"], "embedded basename")
        require(Path(item["name"]).name == item["name"] and "/" not in item["name"] and
                "\\" not in item["name"] and ".." not in item["name"], "Embedded filename is not a safe basename")
        item["encoded_name"] = encoded
    require(member_start == 12 and len(rigs) == 3, "Unexpected Warrior member/rig count")

    manifest_arts = static_manifest["arts"]
    original_mesh_meta = manifest_arts[0]["meshes"]
    require(len(static_meshes) == len(original_mesh_meta) == 12, "Static v1 mesh records are not the expected 12 instances")
    extension = bytearray()
    extension += static_packer.u32(len(embedded))
    for item in embedded:
        extension += static_packer.u32(len(item["encoded_name"])) + item["encoded_name"]
        extension += static_packer.u32(len(item["data"])) + item["data"]
    extension += static_packer.u32(len(rigs))
    for rig_index, rig in enumerate(rigs):
        extension += static_packer.u32(rig["gsd_file_index"])
        extension += static_packer.u32(rig["model_file_index"])
        extension += static_packer.u32(rig["animation_file_index"])
        extension += static_packer.u32(1 if rig["transpose_scale"] else 0)
        extension += pack_f32(rig["duration"], "rig duration")
        bones = rig["bones"]
        extension += static_packer.u32(len(bones))
        for bone in bones:
            extension += packed_string(bone["name"], "bone name")
            extension += pack_i32(bone["parent"], "bone parent")
            for field, count in (("inverse", 16), ("local_position", 3),
                                 ("local_orientation", 4), ("local_scale_shear", 9)):
                for value in static_packer.array(bone.get(field), count, f"bone.{field}"):
                    extension += pack_f32(value, f"bone.{field}")

    animated_mesh_meta = []
    extension += static_packer.u32(len(static_meshes))
    static_mesh_index = 0
    member_start = 0
    t0_errors = []
    total_animated_vertices = 0
    for rig_index, member in enumerate(ordered_members):
        exported, json_path, json_sha = model_export_jsons[member]
        bones = exported["models"][0]["bones"]
        pose = exported["pose"]
        bone_index = {bone["name"]: index for index, bone in enumerate(bones)}
        for formation_offset in range(EXPECTED_MEMBERS[member]):
            formation_slot = member_start + formation_offset
            for source_mesh_index, source_mesh in enumerate(exported["meshes"]):
                v1_mesh = static_meshes[static_mesh_index]
                metadata = original_mesh_meta[static_mesh_index]
                require(metadata.get("member_type") == member and metadata.get("formation_slot") == formation_slot and
                        metadata.get("vertices") == len(source_mesh["vertices"]) and
                        metadata.get("indices") == len(v1_mesh["indices"]),
                        f"v1 instance/rig mapping differs for {member} formation slot {formation_slot}")
                require(v1_mesh["indices"] == [index for triangle in source_mesh["triangles"] for index in triangle],
                        f"v1 mesh topology differs from original GR2 export for {member}")
                bindings = source_mesh["bindings"]
                extension += static_packer.u32(0)  # The v1 package has one ART_DEF_UNIT__WARRIOR art.
                extension += static_packer.u32(static_mesh_index)  # Reuse its corresponding t=0 static mesh.
                extension += static_packer.u32(rig_index)
                extension += static_packer.u32(formation_slot)
                extension += static_packer.u32(len(source_mesh["vertices"]))
                mesh_max_error = 0.0
                for vertex_index, vertex in enumerate(source_mesh["vertices"]):
                    position = static_packer.array(vertex.get("position"), 3, "vertex.position")
                    normal = static_packer.array(vertex.get("normal"), 3, "vertex.normal")
                    uv = static_packer.array(vertex.get("uv"), 2, "vertex.uv")
                    for value in (*position, *normal, *uv):
                        extension += pack_f32(value, "animated source vertex")
                    raw_indices = static_packer.array(vertex.get("boneIndices"), 4, "vertex.boneIndices")
                    raw_weights = static_packer.array(vertex.get("boneWeights"), 4, "vertex.boneWeights")
                    mapped_indices = []
                    weights = []
                    for raw_index, raw_weight in zip(raw_indices, raw_weights):
                        require(isinstance(raw_index, int) and not isinstance(raw_index, bool) and
                                0 <= raw_index < len(bindings), "Animated vertex binding index out of range")
                        require(isinstance(raw_weight, int) and not isinstance(raw_weight, bool) and
                                0 <= raw_weight <= 255, "Animated vertex weight is outside u8 range")
                        binding_name = bindings[raw_index]
                        require(binding_name in bone_index, "Animated vertex binding name is absent from rig")
                        mapped_indices.append(bone_index[binding_name])
                        weights.append(raw_weight)
                    require(sum(weights) == 255, "Animated vertex byte weights do not sum to 255")
                    for absolute_index in mapped_indices:
                        extension += static_packer.u32(absolute_index)
                    extension += bytes(weights)

                    # Independently regenerate the original candidate t=0 static vertex.
                    expected_vertex = static_packer.transform_vertex(vertex, source_mesh, bones,
                        pose["matrices"], formation_slot)
                    packed_expected = struct.unpack("<8f", b"".join(pack_f32(v, "static t=0 vertex")
                        for group in expected_vertex for v in group))
                    actual_vertex = v1_mesh["vertices"][vertex_index]
                    mesh_max_error = max(mesh_max_error, *(abs(a - b) for a, b in zip(packed_expected, actual_vertex)))
                require(mesh_max_error <= 2.0e-6, f"Independent static t=0 geometry mismatch in {member}/{formation_slot}: {mesh_max_error}")
                t0_errors.append({"member_type": member, "mesh_index": source_mesh_index,
                                  "v1_mesh_index": static_mesh_index, "formation_slot": formation_slot,
                                  "max_float_error": mesh_max_error})
                animated_mesh_meta.append({"art_index": 0, "mesh_index": static_mesh_index,
                    "rig_index": rig_index, "formation_slot": formation_slot,
                    "vertex_count": len(source_mesh["vertices"]), "member_type": member,
                    "source_mesh_index": source_mesh_index,
                    "triangle_index_count": len(v1_mesh["indices"])})
                total_animated_vertices += len(source_mesh["vertices"])
                static_mesh_index += 1
        member_start += EXPECTED_MEMBERS[member]
    require(static_mesh_index == 12 and total_animated_vertices <= 1_000_000,
            "Animated mesh aggregate exceeds the v1 runtime catalog bounds")
    require(len(extension) + 12 + len(static_meshes) * 52 <= MAX_PACKAGE,
            "Animated unit package exceeds 64 MiB")

    file_metadata = [{"name": item["name"], "bytes": len(item["data"]), "sha256": digest(item["data"]),
                      "role": item["role"], **({"member_type": item["member_type"]} if "member_type" in item else {})}
                     for item in embedded]
    extension_metadata = {"format_version": 2, "embedded_files": file_metadata,
        "rig_count": len(rigs), "rigs": rig_metadata, "rig_order": ordered_members,
        "rig_mesh_mapping_note": "Rig rows follow original member order; all three rows reference one deduplicated IdleA animation file.",
        "animated_mesh_count": len(animated_mesh_meta),
        "animated_vertex_count": total_animated_vertices, "animated_meshes": animated_mesh_meta,
        "static_t0_independent_mesh_checks": {"mesh_count": len(t0_errors), "maximum_float_error": max(row["max_float_error"] for row in t0_errors),
                                               "records": t0_errors},
        "transform_policy": {
            "rig_source": "Original extracted Civ V GR2 skeleton bones, inverse bind matrices, and local bind transforms.",
            "animation_source": "Original shared Warrior_IdleA.gr2; exporter sampled original track curves at t=0 for independent bind/pose validation.",
            "transpose_scale": "Per-rig boolean encoded as u32 0/1 from pose.scale_shear_transposed.",
            "vertex_skinning": "Source-space GR2 position/normal/UV and absolute bone indices mapped from mesh binding names; original byte weights retained and sum to 255.",
            "static_mesh_link": "Each animated mesh points to its corresponding unchanged v1 t=0 art/mesh/formation slot; this package contains no per-frame baked geometry."
        }}
    return bytes(extension), embedded, rig_metadata, animated_mesh_meta, extension_metadata


def validate_extension(data: bytes, static_data: bytes, embedded: list[dict], rigs: list[dict],
                       animated_meshes: list[dict]) -> dict:
    require(data[:12] == b"ZSUNIT02" + struct.pack("<I", 2), "Invalid ZSUNIT02 v2 header")
    require(data[12:len(static_data)] == static_data[12:], "Static v1 payload changed during v2 packaging")
    cursor = len(static_data)

    def take(count: int) -> bytes:
        nonlocal cursor
        require(0 <= count <= len(data) - cursor, "Truncated v2 extension")
        out = data[cursor:cursor + count]
        cursor += count
        return out

    def u32() -> int:
        return struct.unpack("<I", take(4))[0]

    files = []
    require(u32() == len(embedded), "Serialized embedded-file count differs")
    for expected in embedded:
        name_len = u32()
        name = take(name_len).decode("ascii", "strict")
        size = u32()
        payload = take(size)
        require(name == expected["name"] and payload == expected["data"], "Serialized embedded file mismatch")
        files.append({"name": name, "bytes": size, "sha256": digest(payload)})
    require(u32() == len(rigs), "Serialized rig count differs")
    parsed_bones = []
    for rig_index, rig in enumerate(rigs):
        indices = [u32(), u32(), u32()]
        transpose = u32()
        duration = struct.unpack("<f", take(4))[0]
        count = u32()
        require(indices == [rig["gsd_file_index"], rig["model_file_index"], rig["animation_file_index"]] and
                transpose in (0, 1) and transpose == (1 if rig["transpose_scale"] else 0) and
                math.isclose(duration, rig["duration"], rel_tol=1e-6) and count == len(rig["bones"]),
                f"Serialized rig header mismatch at {rig_index}")
        names = []
        parents = []
        for expected_bone in rig["bones"]:
            name_len = u32()
            name = take(name_len).decode("ascii", "strict")
            parent = struct.unpack("<i", take(4))[0]
            matrix_and_local = struct.unpack("<32f", take(32 * 4))
            require(name == expected_bone["name"] and parent == expected_bone["parent"] and
                    all(math.isfinite(v) for v in matrix_and_local), f"Serialized rig bone differs at {name}")
            names.append(name)
            parents.append(parent)
        for i, parent in enumerate(parents):
            require(parent == -1 or 0 <= parent < len(parents), "Serialized rig parent is outside its bone array")
            seen = set()
            node = i
            while node >= 0:
                require(node not in seen, "Serialized rig parent cycle")
                seen.add(node)
                node = parents[node]
        parsed_bones.append(len(names))
    require(u32() == len(animated_meshes), "Serialized animated-mesh count differs")
    for expected in animated_meshes:
        values = [u32() for _ in range(5)]
        wanted = [expected["art_index"], expected["mesh_index"], expected["rig_index"],
                  expected["formation_slot"], expected["vertex_count"]]
        require(values == wanted, "Serialized animated-mesh header differs")
        for _ in range(values[4]):
            floats = struct.unpack("<8f", take(8 * 4))
            indices = struct.unpack("<4I", take(4 * 4))
            weights = take(4)
            require(all(math.isfinite(value) for value in floats) and sum(weights) == 255 and
                    all(index < parsed_bones[values[2]] for index in indices),
                    "Invalid serialized animated vertex")
    require(cursor == len(data), "Trailing v2 package extension bytes")
    return {"embedded_file_count": len(files), "rig_count": len(parsed_bones),
            "rig_bone_counts": parsed_bones, "animated_mesh_count": len(animated_meshes),
            "animated_vertex_count": sum(row["vertex_count"] for row in animated_meshes),
            "extension_bytes": len(data) - len(static_data)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-manifest", type=Path, required=True,
                        help="PASS_ORIGINAL_UNIT_PACKAGE v1 manifest")
    parser.add_argument("--exports", type=Path, required=True,
                        help="Sealed PASS_STOCK_UNIT_EXPORT directory")
    args = parser.parse_args(argv)
    static_manifest_path = args.static_manifest.resolve(strict=True)
    exports = args.exports.resolve(strict=True)
    require(static_manifest_path.is_file() and exports.is_dir(), "Static manifest/export path is invalid")
    require(exports.is_relative_to(PROJECT.resolve()), "Export directory must remain inside this workspace")
    static_manifest = load_json(static_manifest_path)
    require(static_manifest.get("schema") == 1 and static_manifest.get("status") == "PASS_ORIGINAL_UNIT_PACKAGE",
            "Static v1 manifest is not PASS_ORIGINAL_UNIT_PACKAGE schema 1")
    static_package_record = static_manifest.get("package", {})
    require(static_package_record.get("format") == "ZSUNIT01 v1", "Input static package is not ZSUNIT01 v1")
    static_package_path = Path(static_package_record.get("path", "")).resolve(strict=True)
    require(static_package_path.is_file() and static_package_path.stat().st_size == static_package_record.get("bytes"),
            "Static v1 package path/length mismatch")
    static_data = static_package_path.read_bytes()
    static_sha = digest(static_data)
    require(static_sha == static_package_record.get("sha256") and
            static_sha == static_package_path.parent.name,
            "Static v1 package SHA/path identity mismatch")

    export_manifest_path = exports / "export-manifest.json"
    expected_export_record = static_manifest.get("source_export_manifest", {})
    require(Path(expected_export_record.get("path", "")).resolve() == export_manifest_path.resolve(),
            "--exports does not match the source export manifest recorded by v1")
    export_manifest_sha = digest_file(export_manifest_path)
    require(export_manifest_sha == expected_export_record.get("sha256"),
            "Source export manifest hash differs from v1 provenance")
    export_manifest = load_json(export_manifest_path)
    require(export_manifest.get("schema") == 1 and export_manifest.get("status") == "PASS_STOCK_UNIT_EXPORT",
            "Source export manifest is not PASS_STOCK_UNIT_EXPORT schema 1")
    require(export_manifest.get("run_id") == "20261005T072135Z",
            "Unexpected stock export snapshot; expected the authorized 20261005T072135Z inputs")

    static_before = records_by_path(static_manifest.get("original_inputs_before"), "v1 original inputs")
    static_after = records_by_path(static_manifest.get("original_inputs_after"), "v1 original inputs after")
    require(static_before == static_after, "v1 input hashes changed between its recorded before/after snapshots")
    export_inputs = records_by_path(export_manifest.get("inputs"), "export original inputs")
    export_after = records_by_path(export_manifest.get("inputs_after"), "export original inputs after")
    require(export_inputs == export_after, "Stock export original inputs changed during its recorded run")
    for path_key, expected_sha in export_inputs.items():
        require(static_before.get(path_key) == expected_sha,
                f"v1 manifest and stock export disagree on original input hash: {path_key}")

    # The v1 loader header is code provenance, not a runtime asset. The loader
    # was explicitly migrated after v1; verify the frozen copy that produced
    # v1 instead of requiring the authorized current source to remain unchanged.
    historical_header_rows = [(Path(path), sha) for path, sha in static_manifest["original_inputs_before"].items()
                              if Path(path).name.casefold() == "worldunitassets.h"]
    require(len(historical_header_rows) == 1, "Expected one historical WorldUnitAssets.h provenance record")
    historical_header_path, historical_header_sha = historical_header_rows[0]
    frozen_header_path = (static_package_path.parent / "WorldUnitAssets.v1.h").resolve(strict=True)
    frozen_header_sha = digest_file(frozen_header_path)
    require(frozen_header_sha == historical_header_sha,
            "Frozen v1 WorldUnitAssets.h copy differs from the static manifest")

    # Hash all recorded immutable inputs now; the source package remains untouched.
    snapshot_paths = {Path(key) for key in static_manifest["original_inputs_before"]
                      if Path(key).name.casefold() != "worldunitassets.h"}
    snapshot_paths.add(frozen_header_path)
    snapshot_paths.update(Path(row["path"]) for row in export_manifest["inputs"])
    snapshot_paths.update((static_manifest_path, static_package_path, export_manifest_path))
    exported_payload_records = [export_manifest.get("gsd")]
    for row in export_manifest.get("outputs", []):
        require(isinstance(row, dict), "Invalid source output while collecting immutable payloads")
        static_packer.safe_export_json(exports, row.get("json"))
        snapshot_paths.add(Path(row["json"]["path"]) if Path(row["json"]["path"]).is_absolute()
                           else exports / row["json"]["path"])
        exported_payload_records.extend(row.get(key) for key in ("model", "idle", "fxsxml"))
    for record in exported_payload_records:
        if not isinstance(record, dict):
            continue
        extracted = record.get("extracted")
        if isinstance(extracted, dict) and isinstance(extracted.get("path"), str):
            extracted_path = Path(extracted["path"]).resolve(strict=True)
            require(extracted_path.is_file() and extracted_path.is_relative_to(exports),
                    "Frozen extracted payload escapes stock export directory")
            snapshot_paths.add(extracted_path)
    source_before = {str(path.resolve(strict=True)): digest_file(path) for path in sorted(snapshot_paths, key=str)}
    for path in snapshot_paths:
        key = str(path.resolve()).casefold()
        expected = (historical_header_sha if path.resolve() == frozen_header_path else
                    static_before.get(key, export_inputs.get(key)))
        if expected:
            require(source_before[str(path.resolve(strict=True))] == expected,
                    f"Current original/static input hash differs from the frozen manifests: {path}")
    require(source_before[str(static_manifest_path)] == digest_file(static_manifest_path) and
            source_before[str(static_package_path)] == static_sha and
            source_before[str(export_manifest_path)] == export_manifest_sha,
            "Static or export manifest/package changed during input snapshot")

    textures, static_meshes = parse_v1_package(static_data, static_manifest)
    extension, embedded, rig_metadata, animated_meshes, animation_metadata = build_animation_extension(
        exports, export_manifest, static_manifest, static_meshes)
    package_data = bytearray(static_data)
    package_data[:12] = b"ZSUNIT02" + struct.pack("<I", 2)
    package_data += extension
    require(len(package_data) <= MAX_PACKAGE, "v2 unit asset package exceeds 64 MiB")
    # Parse the serialized extension against records reconstructed from source exports.
    export_rows = {row["member_type"]: row for row in export_manifest["outputs"]}
    validation_rigs = []
    for index, member in enumerate(EXPECTED_MEMBERS):
        exported = static_packer.load_json(static_packer.safe_export_json(exports, export_rows[member]["json"]))
        pose = exported["pose"]
        validation_rigs.append({"member": member, "gsd_file_index": 0,
            "model_file_index": index + 1, "animation_file_index": 4,
            "transpose_scale": bool(pose["scale_shear_transposed"]), "duration": float(pose["duration"]),
            "bones": exported["models"][0]["bones"]})
    validation = validate_extension(bytes(package_data), static_data, embedded,
                                    validation_rigs, animated_meshes)

    source_after_build = {str(path.resolve(strict=True)): digest_file(path) for path in sorted(snapshot_paths, key=str)}
    require(source_before == source_after_build, "An original/frozen input changed during v2 package construction")
    package_sha = digest(bytes(package_data))
    output_root = PROJECT / "Build" / "UnitAssets" / package_sha
    require(output_root.resolve().is_relative_to((PROJECT / "Build" / "UnitAssets").resolve()),
            "Unsafe content-addressed output path")
    require(not output_root.exists(), f"Immutable package output already exists: {output_root}")
    output_root.mkdir(parents=True)
    package_path = output_root / "unit-assets.bin"
    package_path.write_bytes(package_data)
    require(digest_file(package_path) == package_sha, "Written v2 package SHA-256 mismatch")
    source_after_write = {str(path.resolve(strict=True)): digest_file(path) for path in sorted(snapshot_paths, key=str)}
    require(source_before == source_after_write, "An original/frozen input changed during v2 package write")

    file_metadata = animation_metadata["embedded_files"]
    manifest_out = {
        "schema": 1,
        "status": "PASS_ORIGINAL_UNIT_PACKAGE",
        "package": {"path": str(package_path), "sha256": package_sha,
                    "bytes": len(package_data), "format": "ZSUNIT02 v2"},
        "art_tag": static_manifest["art_tag"],
        "source_static_package": {"path": str(static_package_path), "sha256": static_sha,
                                  "bytes": len(static_data), "format": "ZSUNIT01 v1"},
        "source_static_manifest": {"path": str(static_manifest_path),
                                   "sha256": source_before[str(static_manifest_path)],
                                   "schema": static_manifest["schema"], "status": static_manifest["status"]},
        "source_export_manifest": {"path": str(export_manifest_path), "sha256": export_manifest_sha,
                                   "status": export_manifest["status"], "run_id": export_manifest["run_id"],
                                   "inputs": export_manifest["inputs"]},
        "original_inputs_before": static_manifest["original_inputs_before"],
        "original_inputs_after": static_manifest["original_inputs_after"],
        "historical_loader_header_verification": {
            "original_path": str(historical_header_path),
            "expected_sha256": historical_header_sha,
            "verified_copy": str(frozen_header_path),
            "verified_copy_sha256": frozen_header_sha,
            "current_source_header_sha256": digest_file(historical_header_path),
            "note": "Historical v1 code provenance verified from its frozen copy; current loader is an authorized migration."
        },
        "v2_source_hashes_before": source_before,
        "v2_source_hashes_after": source_after_write,
        "unit_selection": static_manifest["unit_selection"],
        "member_scale": static_manifest["member_scale"],
        "formation_original": static_manifest["formation_original"],
        "formation_candidate": static_manifest["formation_candidate"],
        "coordinate_and_skinning_policy": static_manifest["coordinate_and_skinning_policy"],
        "textures": static_manifest["textures"],
        "arts": static_manifest["arts"],
        "source_models": static_manifest["source_models"],
        "animation": animation_metadata,
        "serialized_extension_validation": validation,
        "limits": [*static_manifest.get("limits", []),
                   "Animation data packages original IdleA GR2; runtime interpolation/playback is not validated by packaging.",
                   "Static t=0 package payload is preserved byte-for-byte after the 12-byte format header."]
    }
    manifest_path = output_root / "unit-assets.manifest.json"
    manifest_path.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written_manifest = load_json(manifest_path)
    require(written_manifest.get("status") == "PASS_ORIGINAL_UNIT_PACKAGE" and
            written_manifest.get("package", {}).get("sha256") == package_sha and
            digest_file(package_path) == package_sha,
            "Written v2 manifest/package read-back validation failed")
    print(json.dumps({"status": manifest_out["status"], "package": manifest_out["package"],
        "manifest": str(manifest_path), "source_static_package_sha256": static_sha,
        "embedded_file_count": len(file_metadata), "rig_count": len(rig_metadata),
        "bone_counts": [row["bone_count"] for row in rig_metadata],
        "animated_mesh_count": len(animated_meshes),
        "animated_vertex_count": animation_metadata["animated_vertex_count"],
        "static_t0_max_float_error": animation_metadata["static_t0_independent_mesh_checks"]["maximum_float_error"],
        "serialized_extension_validation": validation}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        print(json.dumps({"status": "FAIL_ORIGINAL_UNIT_PACKAGE_V2", "error": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)
