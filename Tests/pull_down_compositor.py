"""Compile five immutable Lua PullDown captures without starting a native host.

The projection retains the real widget, promoted overlay and captured input
identities. It is an isolated control proof: the complete original LoadMenu
continues to fail closed on its unmeasured AutoCheck control. All generated
atlas files share one private directory and are hashed before guarded removal.
"""
from __future__ import annotations

import copy
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from ui_pixel_scene import (Compiler, centered_button_text_bounds, economic_walk,
                            intersect, layout_text, rect)

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
SNAPSHOTS = PROJECT / "evidence/load_menu/pull_down/component_snapshots.json"
INLINE_ICONS = PROJECT / "evidence/ui_popup/assets/inline_icons.json"
EVIDENCE = PROJECT / "evidence/load_menu/pull_down"
FROZEN = {
    "compiler": (PROJECT / "tools/ui_pixel_scene.py",
                 "8b53fd8b11838f021d51fd5ae33f46947635315b85dd130a611e76d7a429da63"),
    "renderer": (PROJECT / "tools/render_ui_popup.py",
                 "32ce3afa81b01021c2f9933b83ec59f174f0727b4b0c0c10882470985141e010"),
    "snapshots": (SNAPSHOTS,
                  "c28a2c8fa1f715c6574e06f4d8a954da5cbd4f58d9b9857642f774bbcb9cddfc"),
}
EXPECTED = (
    ("closed", 2784, 1, 34),
    ("opened", 7472, 5, 93),
    ("overflowing", 13688, 10, 171),
    ("scrolled", 13688, 10, 171),
    ("resized", 13688, 10, 171),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def suppress_own_fault_ui() -> dict:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint32]
    kernel.SetErrorMode.restype = ctypes.c_uint32
    kernel.GetErrorMode.argtypes = []
    kernel.GetErrorMode.restype = ctypes.c_uint32
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    mask = 0x1 | 0x2 | 0x8000
    kernel.SetErrorMode(kernel.GetErrorMode() | mask)
    if kernel.GetErrorMode() & mask != mask:
        raise RuntimeError("Own Python process fault UI suppression was not retained")
    kernel.WerSetFlags.argtypes = [ctypes.c_uint32]
    kernel.WerSetFlags.restype = ctypes.c_long
    kernel.WerGetFlags.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.WerGetFlags.restype = ctypes.c_long
    set_status = kernel.WerSetFlags(32)
    flags = ctypes.c_uint32()
    get_status = kernel.WerGetFlags(kernel.GetCurrentProcess(), ctypes.byref(flags))
    if set_status < 0 or get_status < 0 or not flags.value & 32:
        raise RuntimeError("Own Python WER no-UI suppression was not retained")
    return {"own_python_process_only": True, "module": "Kernel32.dll",
            "error_mode_mask": mask, "wer_flags": flags.value,
            "set_hresult": set_status, "get_hresult": get_status}


def project_widget(snapshot: dict) -> dict:
    result = copy.deepcopy(snapshot)
    widget = result["pullDowns"][0]
    nodes = {node["key"]: node for node in economic_walk(result["tree"])}
    children = [nodes[widget["key"]]]
    if widget["opened"]:
        children.append(nodes[widget["popupKey"]])
    result["tree"]["children"] = children
    keys = {node["key"] for node in economic_walk(result["tree"])}
    result["inputTargets"] = [target for target in result["inputTargets"] if target["key"] in keys]
    result["scrollTargets"] = [target for target in result["scrollTargets"]
                               if target["key"] == widget["scrollPanelKey"]]
    return result


def packet_sections(packet: bytes, directory: Path) -> dict:
    if packet[:8] != b"ZSUPIX02" or len(packet) < 32:
        raise AssertionError("Compiler did not return a bounded ZSUPIX02 packet")
    width, height, textures, sprites, hits, scroll = struct.unpack_from("<6I", packet, 8)
    if (width, height) != (1920, 1080) or textures > 64 or sprites > 10000:
        raise AssertionError("Packet header exceeds the captured viewport or resource bounds")
    offset, paths = 32, []
    for _ in range(textures):
        size, = struct.unpack_from("<I", packet, offset)
        offset += 4
        if not 0 < size < 4096 or offset + size > len(packet):
            raise AssertionError("Packet texture path length is invalid")
        relative = packet[offset:offset + size].decode("utf-8")
        path = (directory / relative).resolve(strict=True)
        if not path.is_relative_to(directory) or not path.is_file():
            raise AssertionError("Packet texture escaped its generated private directory")
        paths.append(relative)
        offset += size
    offset += sprites * struct.calcsize("<IQ16f")
    decoded_hits, decoded_scroll = [], []
    for collection, count in ((decoded_hits, hits), (decoded_scroll, scroll)):
        for _ in range(count):
            row = struct.unpack_from("<Q4f", packet, offset)
            if not row[0] or not all(math.isfinite(value) for value in row[1:]):
                raise AssertionError("Packet input rectangle lost its finite retained identity")
            collection.append(row)
            offset += struct.calcsize("<Q4f")
    if offset != len(packet):
        raise AssertionError("Packet has truncated fields or unparsed trailing bytes")
    return {"texture_paths": paths, "sprites": sprites, "hits": decoded_hits,
            "scroll": decoded_scroll}


def wire_rectangle(row: tuple) -> tuple:
    return (row[0], *struct.unpack("<4f", struct.pack("<4f", *row[1:])))


def captured_clip_xyxy(target: dict) -> tuple:
    box = target["clippedBounds"]
    # Capture rectangles use XYWH; the packet and compiler hit lists use XYXY.
    return box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]


def remove_generated(directory: Path, build: Path) -> dict:
    absolute = directory.resolve(strict=True)
    if absolute.parent != build or not absolute.name.startswith("pull-down-compositor-"):
        raise RuntimeError("Generated cleanup target escaped the owned Build directory")
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    descendants = list(absolute.rglob("*"))
    for path in [*absolute.parents, absolute, *descendants]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise RuntimeError("Generated cleanup encountered a reparse point")
    files, unique = [], {}
    for path in sorted(descendants):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            continue
        identity = [info.st_dev, info.st_ino] if info.st_ino else None
        row = {**artifact(path), "file_identity": identity, "link_count": info.st_nlink}
        files.append(row)
        unique[tuple(identity) if identity else (str(path),)] = info.st_size
    shutil.rmtree(absolute)
    if absolute.exists() or any(Path(row["path"]).exists() for row in files):
        raise RuntimeError("Generated compositor artifacts survived guarded removal")
    for row in files:
        row["result"] = "REMOVED_ABSENT"
    return {"directory": str(absolute), "directory_absent": True, "files": files,
            "file_count": len(files), "logical_bytes_removed": sum(row["bytes"] for row in files),
            "unique_file_content_bytes_removed": sum(unique.values()),
            "all_file_identities_available": all(row["file_identity"] is not None for row in files),
            "physical_allocation_or_volume_free_space_measured": False}


def verify_component() -> dict:
    fault = suppress_own_fault_ui()
    source_paths = {name: path for name, (path, _) in FROZEN.items()}
    source_paths.update(harness=Path(__file__).resolve(), inline_icons=INLINE_ICONS)
    before = {name: artifact(path) for name, path in source_paths.items()}
    for name, (_, expected) in FROZEN.items():
        if before[name]["sha256"] != expected:
            raise AssertionError("Frozen compositor input changed before execution: " + name)
    snapshots = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))["snapshots"]
    if len(snapshots) != 5:
        raise AssertionError("Exactly five existing Lua captures are required")
    original_snapshots = copy.deepcopy(snapshots)
    inline = json.loads(INLINE_ICONS.read_text(encoding="utf-8"))["icons"]
    checks = 0

    def check(value, message):
        nonlocal checks
        if not value:
            raise AssertionError(message)
        checks += 1

    build = (PROJECT / "Build").resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix="pull-down-compositor-", dir=build)).resolve(strict=True)
    rows, rejected, sources = [], [], {}
    cleanup = None
    error = None

    def compiler():
        result = Compiler(GAME, directory, context="load-menu", inline_colors={}, inline_icons=inline)
        for path, digest in result.context_sources.items():
            if str(path) in sources and sources[str(path)] != digest:
                raise AssertionError("Original UI source changed between compiler instances")
            sources[str(path)] = digest
        return result

    def reject(name, candidate, message):
        instance = compiler()
        try:
            instance.compile(candidate)
        except ValueError as caught:
            check(message in str(caught), name + " failed for an unrelated reason: " + str(caught))
            rejected.append({"case": name, "error": str(caught)})
        else:
            raise AssertionError(name + " accepted a changed original input contract")
        check(instance.unchanged(), name + " changed an original UI source")

    try:
        # Keep the full screen's unresolved boundary visible. This rejection is
        # not replaced by the successful projection and is never called a pass
        # for the full LoadMenu.
        reject("full_load_menu_unmeasured_autocheck", copy.deepcopy(snapshots[0]),
               "Production control lacks resolved style dimensions: CheckBox/AutoCheck")
        try:
            centered_button_text_bounds((0, 0, 200, 24), 40, 25, (0, 0))
        except ValueError as caught:
            check("does not fit" in str(caught), "Generic caption guard failed for an unrelated reason")
        else:
            raise AssertionError("Generic 25-high caption was accepted in an unrelated 24-high cell")
        for snapshot, (name, packet_bytes, hit_count, sprite_count) in zip(snapshots, EXPECTED):
            candidate = project_widget(snapshot)
            candidate_before = copy.deepcopy(candidate)
            widget = candidate["pullDowns"][0]
            instance = compiler()
            packet = instance.compile(candidate)
            parsed = packet_sections(packet, directory)
            check(len(packet) == packet_bytes, name + " packet byte count differs from the reviewed capture")
            check(len(instance.hits) == hit_count and len(instance.sprites) == sprite_count,
                  name + " input or sprite count differs from the reviewed capture")
            expected_hits = [(target["key"], *captured_clip_xyxy(target)) for target in candidate["inputTargets"]]
            check(instance.hits == expected_hits, name + " hit order/key/clip differs from the actual Lua capture")
            check(parsed["hits"] == [wire_rectangle(row) for row in expected_hits],
                  name + " serialized hit rectangles differ from the captured float32 wire values")
            check(parsed["sprites"] == sprite_count, name + " packet sprite header disagrees with composition")
            expected_scroll = sorted((target["key"], *captured_clip_xyxy(target)) for target in candidate["scrollTargets"])
            check(instance.scroll_regions == expected_scroll,
                  name + " scroll source/clip differs from the captured owning panel")
            check(parsed["scroll"] == [wire_rectangle(row) for row in expected_scroll],
                  name + " serialized scroll identities or clips changed")
            nodes = {node["key"]: node for node in economic_walk(candidate["tree"])}
            chrome = [node for node in nodes.values() if node.get("kind") in ("UpButton", "DownButton")
                      and node.get("scrollPanelChromeOwnerKey") == widget["scrollPanelKey"] and not node["hidden"]]
            check(len(chrome) == (2 if widget["overflow"] else 0),
                  name + " lost the original outside-anchored scroll buttons")
            for node in chrome:
                target = next(row for row in candidate["inputTargets"] if row["key"] == node["key"])
                target_rect = captured_clip_xyxy(target)
                painted = [sprite for sprite in instance.sprites if sprite[1] == node["key"]]
                check(bool(painted) and any(intersect(tuple(sprite[6:10]), tuple(sprite[10:14]))[2] >
                                           intersect(tuple(sprite[6:10]), tuple(sprite[10:14]))[0] and
                                           intersect(tuple(sprite[6:10]), tuple(sprite[10:14]))[3] >
                                           intersect(tuple(sprite[6:10]), tuple(sprite[10:14]))[1] for sprite in painted),
                      name + " outside scroll button has hits but no visible painted pixels: " + node["kind"])
                check(all(intersect(tuple(sprite[10:14]), target_rect) == target_rect for sprite in painted),
                      name + " outside scroll button paint was clipped by its own content panel: " + node["kind"])
            entry_labels = [label for label in instance.labels
                            if label.get("original_cell_linebox_overhang_candidate") == 1]
            check(bool(entry_labels) is widget["opened"], name + " line-box candidate escaped its visible original entries")
            font_texture_indices = {index for index, path in enumerate(instance.textures)
                                    if any(path == sheet["path"] for font in instance.font_records
                                           if font["font_id"] == "TwCenMT22" for sheet in font["sheets"])}
            for label in entry_labels:
                node = nodes[label["key"]]
                check(node["originalDataKind"] == "InstanceData" and
                      node["sourceAttributes"]["Size"] == "200.24" and
                      node["sourceAttributes"]["Style"] == "ZoomButton" and
                      node["height"] == 24 and label["font"] == "TwCenMT22" and label["bounds"][3] == 25 and
                      label["retail_text_alignment_verified"] is False and
                      label["retail_pixel_equivalence_verified"] is False,
                      name + " rewrote the original cell/font or claimed retail alignment")
                font = instance.fonts[(label["font"], label["style"])]
                check(layout_text(label["plain_text"], font).height == 25,
                      name + " replaced the original GGXML line-box metric")
                cell = rect((node["x"], node["y"], node["width"], node["height"]))
                panel = nodes[widget["scrollPanelKey"]]
                expected_clip = intersect(intersect(cell, rect((panel["x"], panel["y"], panel["width"], panel["height"]))),
                                          (0, 0, 1920, 1080))
                glyphs = [sprite for sprite in instance.sprites if sprite[1] == node["key"]
                          and sprite[0] in font_texture_indices]
                check(all(tuple(sprite[10:14]) == expected_clip for sprite in glyphs),
                      name + " original entry glyphs escaped their cell/scroll clipping")
                if expected_clip[2] > expected_clip[0] and expected_clip[3] > expected_clip[1]:
                    check(bool(glyphs), name + " visible original entry lost its caption glyphs")
            check(candidate == candidate_before and snapshots == original_snapshots,
                  name + " composition changed the Lua captures or readonly projection")
            check(instance.unchanged(), name + " composition changed an original UI/font/atlas source")
            rows.append({"state": name, "packet_bytes": len(packet), "packet_sha256": hashlib.sha256(packet).hexdigest(),
                         "hits": len(instance.hits), "sprites": len(instance.sprites),
                         "scroll_regions": len(instance.scroll_regions), "entry_caption_candidates": len(entry_labels),
                         "exact_capture_input_order_and_bounds": True, "retail_pixel_alignment_verified": False})

        def mutate(case):
            value = project_widget(snapshots[1])
            widget = value["pullDowns"][0]
            nodes = {node["key"]: node for node in economic_walk(value["tree"])}
            if case == "style_source_hash":
                widget["originalStyleSource"]["sha256"] = "0" * 64
            elif case == "overlay_source_owner":
                nodes[widget["popupKey"]]["ownerPullDownKey"] += 1
            elif case == "dismissal_source_owner":
                value["inputTargets"][0]["ownerPullDownKey"] += 1
            else:
                node = nodes[widget["entryKeys"][0]]
                if case == "unscoped_linebox":
                    node["originalDataKind"] = "UnregisteredInstance"
                elif case == "rewritten_original_entry_cell":
                    node["sourceAttributes"]["Size"] = "200,25"
                else:
                    raise AssertionError("Unknown mutation case")
            return value

        for case, message in (
            ("style_source_hash", "PullDown style provenance differs"),
            ("overlay_source_owner", "PullDown composite lost an original style block: popupKey"),
            ("dismissal_source_owner", "PullDown dismissal is not the source-bound root viewport barrier"),
            ("unscoped_linebox", "Original GridButton text does not fit its retained control bounds"),
            ("rewritten_original_entry_cell", "PullDown caption differs from the original 200x24 ZoomButton cell"),
        ):
            reject(case, mutate(case), message)
        check(snapshots == original_snapshots, "Negative cases changed an immutable Lua capture")
    except Exception as caught:
        error = caught
    finally:
        try:
            cleanup = remove_generated(directory, build)
        except Exception as caught:
            if error is None:
                error = caught
        changed = [name for name, path in source_paths.items() if artifact(path) != before[name]]
        if changed and error is None:
            error = AssertionError("Compositor changed its immutable inputs: " + ", ".join(changed))
    report = {"schema": 1, "status": "PASS_PULL_DOWN_SUBTREE_COMPOSITION_ONLY" if error is None else "FAIL_COMPOSITOR_COMPONENT",
              "created_utc": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "source_artifacts_before": before,
              "source_artifacts_after": {name: artifact(path) for name, path in source_paths.items()},
              "original_ui_sources": sources, "fault_ui_suppression": fault,
              "states": rows, "rejected_cases": rejected, "cleanup": cleanup,
              "full_load_menu_verified": False, "full_screen_blocker": "Original AutoCheck dimensions/behavior remain unmeasured",
              "retail_pixel_alignment_verified": False, "native_game_or_window_executed": False,
              "gamecore_or_host_executed": False, "existing_lua_captures_reexecuted": False,
              "snapshot_copies_created": False}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if error is None:
        path = EVIDENCE / "compositor.json"
    else:
        report["error"] = type(error).__name__ + ": " + str(error)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        path = EVIDENCE / "attempts" / run_id / "compositor_failure.json"
        path.parent.mkdir(parents=True, exist_ok=False)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    if error is not None:
        raise RuntimeError(str(error) + "; diagnostic receipt: " + str(path)) from error
    return {"status": report["status"], "checks": checks, "states": rows,
            "negative_cases": len(rejected), "generated_files_removed": cleanup["file_count"],
            "generated_logical_bytes_removed": cleanup["logical_bytes_removed"],
            "full_load_menu_verified": False, "receipt": artifact(path)}


if __name__ == "__main__":
    print(json.dumps(verify_component(), ensure_ascii=False))
