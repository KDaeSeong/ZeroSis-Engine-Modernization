"""Independently verify one actual Civ V SDK TopPanel world-overlay smoke run.

This is a narrow evidence verifier. It never launches the Host/game, mutates
the run's result.json, or upgrades private renderer captures into retail UI
equivalence claims.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

from collect_baseline import PROJECT, digest
from verify_world_builder_map_object import check_artifacts

EVIDENCE = PROJECT / "evidence/interactive_game"
RUNTIME_ROOT = PROJECT / "Build/InteractiveGameRuntime"
RUN_ID = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}\Z")
EXPECTED_HOST_BUILD = "20261007T205518Z_12228ee7e01b"
EXPECTED_HOST_SHA256 = "22ed4c0987fa3f320f9ebba963e3a80e9befd208faceea12ee1a7b0b268fa14c"
TOP_PANEL_KEY_BASE = 1 << 51
TOP_PANEL_KEY_LIMIT = 1 << 32
ORIGINAL_TOP_PANEL_SOURCES = {
    "TopPanel.xml": "2325da5a03ff39daca1910089891dbd709b916b56ad4470e85c215fd12b065ad",
    "TopPanel.lua": "e1fa9bbeb198fb85fe71b101b6f11ac048721551be5e9de10259bbf20c167aef",
}
FROZEN_UI_TOOLS = {
    "interactive_ui_driver.py", "render_ui_popup.py", "ui_pixel_scene.py",
    "ui_bitmap_fonts.py", "civ5_ui_assets.py",
}
COMPONENT_FIXTURE = PROJECT / "Tests/top_panel_scene.lua"


class VerificationError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise VerificationError(message)


def valid_top_panel_popup_request_branch(source_text: str) -> bool:
    """Accept the original fixed TechTree request or the exact expanded enum gate."""
    branch_start = source_text.find('if(std::strcmp(operation,"queueTopPanelPopup")==0){')
    branch_end = source_text.find('if(std::strcmp(operation,"isTouchScreen")==0)', branch_start)
    if branch_start < 0 or branch_end <= branch_start:
        return False
    branch = re.sub(r"\s+", "", source_text[branch_start:branch_end])
    direct_tech_tree = re.search(
        r"(?:new)?CvPopupInfo\(BUTTONPOPUP_TECH_TREE,-1,-1\)", branch) is not None
    exact_overview_gate = (
        "constinttype=Integer(state,2),data2=Integer(state,3);" in branch and
        "if((type!=static_cast<int>(BUTTONPOPUP_TECH_TREE)&&"
        "type!=static_cast<int>(BUTTONPOPUP_TRADE_ROUTE_OVERVIEW))||data2!=-1)" in branch and
        "newCvPopupInfo(static_cast<ButtonPopupTypes>(type),-1,-1)" in branch
    )
    return direct_tech_tree or exact_overview_gate


def artifact_ref(ref: object, *, exact: Path | None = None, label: str = "artifact") -> Path:
    require(isinstance(ref, dict), f"{label} reference is missing")
    check_artifacts(ref)
    path = Path(ref.get("path", "")).resolve(strict=True)
    require(path.is_file(), f"{label} is not a regular file")
    if exact is not None:
        require(path == exact.resolve(strict=True), f"{label} escaped its exact evidence path")
    return path


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Cannot read {label}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def generated_map(result: dict, runtime: Path) -> tuple[dict[str, list[Path]], set[Path]]:
    rows = result.get("generated_files")
    require(isinstance(rows, list), "Run result has no generated-file inventory")
    session_root = (runtime / "sessions").resolve(strict=True)
    files: dict[str, list[Path]] = {}
    paths: set[Path] = set()
    for row in rows:
        path = artifact_ref(row, label="generated session file")
        require(path.is_relative_to(session_root), "Generated evidence escaped the exact private session tree")
        require(path not in paths, "Generated-file inventory contains a duplicate path")
        paths.add(path)
        files.setdefault(path.name, []).append(path)
    actual = {p.resolve(strict=True) for p in session_root.rglob("*") if p.is_file()}
    require(actual == paths, "Generated-file inventory does not exactly cover the private session tree")
    return files, paths


def verify_frozen_ui(request: dict, run_evidence: Path, runtime: Path) -> dict:
    inventory = request.get("interactive_ui_support_inventory")
    require(isinstance(inventory, dict), "Request omits frozen UI support inventory")
    record_path = artifact_ref(request.get("interactive_ui_support"),
                               exact=run_evidence / "interactive_ui_support.json", label="UI support record")
    record = load_json(record_path, "UI support record")
    require(set(record.get("tools", {})) == FROZEN_UI_TOOLS and
            set(inventory.get("tools", {})) == FROZEN_UI_TOOLS,
            "Frozen UI support does not contain the exact required tool set")
    support_root = (runtime / "interactive_ui_support").resolve(strict=True)
    manifest_ref = record.get("frozen_support_manifest", {})
    request_manifest = inventory.get("frozen_support_manifest", {})
    manifest_path = artifact_ref(manifest_ref, label="frozen UI support manifest")
    require(manifest_path == (support_root / "support_manifest.json").resolve(strict=True) and
            manifest_ref.get("sha256") == request_manifest.get("sha256"),
            "Frozen UI support manifest path/hash differs from the immutable request")
    manifest = load_json(manifest_path, "frozen UI support manifest")
    require(set(manifest.get("tools", {})) == FROZEN_UI_TOOLS,
            "Frozen UI support manifest tool set differs")
    frozen_rows = {}
    for name in sorted(FROZEN_UI_TOOLS):
        row = record["tools"][name]
        request_row = inventory["tools"][name]
        frozen = row.get("frozen", {})
        request_frozen = request_row.get("frozen", {})
        source = row.get("source", {})
        request_source = request_row.get("source", {})
        frozen_path = artifact_ref(frozen, label=f"frozen UI tool {name}")
        require(frozen_path == (support_root / "tools" / name).resolve(strict=True) and
                frozen.get("sha256") == request_frozen.get("sha256") and
                source.get("sha256") == request_source.get("sha256") and
                Path(source.get("original_path", "")).resolve(strict=True) ==
                Path(request_source.get("original_path", "")).resolve(strict=True) and
                digest(frozen_path) == source.get("sha256") == frozen.get("sha256") and
                manifest.get("tools", {}).get(name, {}).get("sha256") == frozen.get("sha256"),
                f"Frozen UI tool {name} lost source, manifest, or byte-hash provenance")
        frozen_rows[name] = {"path": str(frozen_path), "sha256": digest(frozen_path),
                             "source_path": source["original_path"], "source_sha256": source["sha256"]}

    catalog_rows = {}
    for name, key in (("inline_icons.json", "inline_icons"),
                      ("prepared.json", "asset_preparation_provenance")):
        row = record.get(key, {})
        request_row = inventory.get(key, {})
        frozen = row.get("frozen", {})
        source = row.get("source", {})
        request_frozen = request_row.get("frozen", {})
        request_source = request_row.get("source", {})
        path = artifact_ref(frozen, label=f"frozen UI data {name}")
        require(path == (support_root / "assets" / name).resolve(strict=True) and
                frozen.get("sha256") == request_frozen.get("sha256") and
                source.get("sha256") == request_source.get("sha256") and
                Path(source.get("original_path", "")).resolve(strict=True) ==
                Path(request_source.get("original_path", "")).resolve(strict=True) and
                digest(path) == frozen.get("sha256") == source.get("sha256") and
                manifest.get(key, {}).get("sha256") == frozen.get("sha256"),
                f"Frozen UI data {name} lost source or hash provenance")
        catalog_rows[key] = {"path": str(path), "sha256": digest(path),
                             "source_path": source["original_path"], "source_sha256": source["sha256"]}
    return {"support_manifest": {"path": str(manifest_path), "sha256": digest(manifest_path)},
            "tools": frozen_rows, "catalogs": catalog_rows,
            "support_record": {"path": str(record_path), "sha256": digest(record_path)}}


def verify_host(request: dict, runtime: Path) -> dict:
    provenance = request.get("provenance")
    require(isinstance(provenance, dict) and "host_build" in provenance,
            "Request omits sealed Host build provenance")
    build_path = artifact_ref(provenance["host_build"], label="Host build report")
    build = load_json(build_path, "Host build report")
    check_artifacts(build)
    require(build.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            build.get("source_inputs_unchanged") is True and build.get("build_id") == EXPECTED_HOST_BUILD and
            build.get("executable", {}).get("sha256") == EXPECTED_HOST_SHA256,
            "Run does not use the exact accepted TopPanel Host build/hash")
    build_sources = {Path(row.get("path", "")).name: row for row in build.get("sources", [])
                     if isinstance(row, dict) and isinstance(row.get("path"), str)}
    required_source_tokens = {
        "InteractiveGameLoop.h": ("1ull<<51", "TopPanelKey(target.key)",
                                  "routed.controlKey=panelTarget?input.controlKey-kTopPanelKeyBase:0",
                                  "INTERACTIVE_TOP_PANEL_SCIENCE_TARGET",
                                  "CapturePreparedGpuFrame(png,&error)",
                                  "world-underlay.png",
                                  "OverlayPreparedGpuFrame(top,&error)",
                                  "CaptureFrame(directory+", "INTERACTIVE_TOP_PANEL_FRAME"),
        "InteractiveUiSession.h": ("CaptureTopPanel()", "topPanel_->Stop()"),
        "UiPopupContext.h": ("RefreshTopPanelLua", "queueTopPanelPopup"),
        "UiScene.lua": ("ZeroSisTopPanelRefresh", "ZeroSisTopPanelStop",
                        "flushTopPanelPopupRequest"),
        "BitmapWindow.cpp": ("ComputeDisplayRect", "D2D1_BITMAP_INTERPOLATION_MODE_NEAREST_NEIGHBOR",
                             "CaptureFrame(const std::wstring& png", "swapChain->GetBuffer(0",
                             "CopyResource(impl_->staging.Get(),backBuffer.Get())", "swapChain->Present(1,0)"),
    }
    require(required_source_tokens.keys() <= build_sources.keys(),
            "Accepted Host build source closure omits TopPanel native/Lua integration")
    source_hashes = {}
    for name, tokens in required_source_tokens.items():
        source_ref = build_sources[name]
        source_path = artifact_ref(source_ref, label=f"compiled Host source {name}")
        source_text = source_path.read_text(encoding="utf-8")
        require(all(token in source_text for token in tokens),
                f"Sealed Host source lacks the required TopPanel contract: {name}")
        if name == "UiPopupContext.h":
            require(valid_top_panel_popup_request_branch(source_text),
                    "TopPanel popup callback must preserve the original TechTree request or the exact TechTree/TradeRoute enum gate with Data2=-1")
        if name == "InteractiveGameLoop.h":
            require(source_text.index("world-underlay.png") <
                    source_text.index("OverlayPreparedGpuFrame(top,&error)") <
                    source_text.index("CaptureFrame(directory+") <
                    source_text.index("INTERACTIVE_TOP_PANEL_FRAME"),
                    "Host GPU capture does not follow TopPanel overlay and scene publication")
        if name == "BitmapWindow.cpp":
            render_start = source_text.index("bool BitmapWindow::RenderFrame(")
            draw_at = source_text.index("DrawBitmap(impl_->bitmap.Get()", render_start)
            capture_at = source_text.index("impl_->swapChain->GetBuffer(0", render_start)
            present_at = source_text.index("impl_->swapChain->Present(1,0)", render_start)
            require(draw_at < capture_at < present_at,
                    "BitmapWindow capture is not read back after drawing and before Present")
        source_hashes[name] = {"path": str(source_path), "sha256": digest(source_path)}
    runtime_rows = request.get("runtime_inputs")
    require(isinstance(runtime_rows, list), "Request has no immutable runtime input list")
    selected = [row for row in runtime_rows if Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
    require(len(selected) == 1, "Request must pin exactly one x64 Host executable")
    host_path = artifact_ref(selected[0], exact=runtime / "ZeroSisHost_x64.exe", label="runtime Host")
    require(digest(host_path) == EXPECTED_HOST_SHA256 and
            selected[0].get("sha256") == build["executable"]["sha256"],
            "Private runtime Host differs from the accepted Host build")
    require(request.get("cwd") == str(runtime) or Path(request.get("cwd", "")).resolve(strict=True) == runtime,
            "Request cwd differs from the exact run-specific runtime")
    return {"build_id": build["build_id"], "build_report": str(build_path),
            "build_report_sha256": digest(build_path), "host_executable": str(host_path),
            "host_executable_sha256": digest(host_path), "source_hashes": source_hashes}


def text_rows(output: str, marker: str, pattern: str) -> list[tuple[str, ...]]:
    found = re.findall(pattern, output, re.M)
    require(found, f"Missing {marker} evidence")
    return found


def find_control(node: object, control_id: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(node, dict):
        attrs = node.get("attributes")
        if isinstance(attrs, dict) and attrs.get("ID") == control_id:
            found.append(node)
        for child in node.get("children", []) if isinstance(node.get("children", []), list) else []:
            found.extend(find_control(child, control_id))
    return found


def verify_top_snapshot(path: Path, *, expected_player: int, pre_city: bool | None = None) -> dict:
    snapshot = load_json(path, "TopPanel snapshot")
    require(snapshot.get("contextName") == "TopPanel" and snapshot.get("popupKind") == "TopPanel" and
            snapshot.get("active") is True and snapshot.get("hasRetainedPopupUi") is True and
            snapshot.get("nonmodal") is True and snapshot.get("timerSemaphore") == 0 and
            snapshot.get("timerSemaphores") == 0,
            "TopPanel snapshot is not active with its nonmodal timer-zero contract")
    panel = snapshot.get("topPanel")
    require(isinstance(panel, dict) and panel.get("activePlayer") == expected_player and
            panel.get("nonmodal") is True and panel.get("timerSemaphores") == 0,
            "TopPanel metadata differs from the actual active SDK player/timer contract")
    info = find_control(snapshot.get("tree"), "TopPanelInfoStack")
    require(len(info) == 1, "Original TopPanelInfoStack is missing or duplicated in the retained XML tree")
    hidden = info[0].get("hidden") is True
    if pre_city is not None:
        require(hidden is pre_city, "Original TopPanelInfoStack visibility differs from the SDK city state")
    targets = snapshot.get("inputTargets")
    require(isinstance(targets, list), "TopPanel snapshot has no input target list")
    science = [row for row in targets if isinstance(row, dict) and row.get("id") == "SciencePerTurn"]
    if hidden:
        require(not science, "Hidden pre-city SciencePerTurn unexpectedly exposes a native input target")
    else:
        require(len(science) == 1 and science[0].get("event") == "LeftClick" and
                science[0].get("visible") is True,
                "Visible post-city SciencePerTurn lacks its exact original click target")
    turn = find_control(snapshot.get("tree"), "CurrentTurn")
    require(len(turn) == 1 and isinstance(turn[0].get("text"), str) and turn[0]["text"],
            "Original CurrentTurn control is missing its actual stock text")
    return {"snapshot": str(path), "snapshot_sha256": digest(path), "active_player": expected_player,
            "info_stack_hidden": hidden, "science_targets": len(science),
            "current_turn_text": turn[0]["text"]}


def png_header(path: Path, allowed_sizes: set[tuple[int, int]]) -> tuple[int, int]:
    raw = path.read_bytes()
    require(len(raw) >= 24 and raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR",
            f"Invalid PNG artifact: {path.name}")
    size = struct.unpack_from(">II", raw, 16)
    require(size in allowed_sizes, f"Unexpected PNG dimensions for {path.name}: {size}")
    return size


def decode_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Decode the simple non-interlaced 8-bit PNGs emitted by the UI renderer."""
    raw = path.read_bytes()
    require(raw[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG: {path.name}")
    offset, width, height, depth, color, compression, filtering, interlace = 8, 0, 0, 0, 0, 0, 0, 0
    compressed = bytearray()
    while offset + 12 <= len(raw):
        length = struct.unpack_from(">I", raw, offset)[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        require(end <= len(raw), f"Truncated PNG chunk: {path.name}")
        data = raw[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
        offset = end
    require(width > 0 and height > 0 and depth == 8 and color in (2, 6) and
            compression == filtering == interlace == 0,
            f"Unsupported PNG pixel format for exact comparison: {path.name}")
    channels = 3 if color == 2 else 4
    stride = width * channels
    packed = zlib.decompress(bytes(compressed))
    require(len(packed) == height * (stride + 1), f"Malformed PNG scanline data: {path.name}")
    rows = bytearray(height * stride)
    cursor = 0
    for y in range(height):
        filt = packed[cursor]
        cursor += 1
        scan = packed[cursor:cursor + stride]
        cursor += stride
        prior = rows[(y - 1) * stride:y * stride] if y else bytes(stride)
        out = rows[y * stride:(y + 1) * stride]
        for x in range(stride):
            left = out[x - channels] if x >= channels else 0
            above = prior[x]
            upper_left = prior[x - channels] if x >= channels else 0
            if filt == 0:
                predictor = 0
            elif filt == 1:
                predictor = left
            elif filt == 2:
                predictor = above
            elif filt == 3:
                predictor = (left + above) // 2
            elif filt == 4:
                p = left + above - upper_left
                pa, pb, pc = abs(p - left), abs(p - above), abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else above if pb <= pc else upper_left
            else:
                raise VerificationError(f"Unknown PNG filter {filt}: {path.name}")
            out[x] = (scan[x] + predictor) & 0xff
        rows[y * stride:(y + 1) * stride] = out
    if channels == 3:
        rgba = bytearray(width * height * 4)
        for i in range(width * height):
            rgba[4 * i:4 * i + 3] = rows[3 * i:3 * i + 3]
            rgba[4 * i + 3] = 255
        return width, height, bytes(rgba)
    return width, height, bytes(rows)


def verify_frame_links(output: str, result: dict, runtime: Path,
                       generated: dict[str, list[Path]], generated_paths: set[Path], active_player: int) -> dict:
    frame_pattern = r"^INTERACTIVE_TOP_PANEL_FRAME=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([^\r\n|]+)\|([^\r\n|]+)$"
    frames = [tuple(row) for row in re.findall(frame_pattern, output, re.M)]
    require(frames, "Host emitted no TopPanel frame markers")
    world_pattern = r"^INTERACTIVE_WORLD_FRAME=(\d+)\|(\d+)\|(\d+)\|\d+\|\d+\|(\d+)\|\d+\|[01]\|[12]$"
    world_frames = [tuple(map(int, row)) for row in re.findall(world_pattern, output, re.M)]
    require(world_frames, "Host emitted no owned world GPU frame markers")
    top_rows = []
    hwnds, devices = set(), set()
    by_sequence = {}
    by_generation = {}
    for seq_s, generation_s, turn_s, player_s, hwnd_s, device_s, snap_s, folder_s in frames:
        seq, generation, turn, player, hwnd, device = map(int, (seq_s, generation_s, turn_s, player_s, hwnd_s, device_s))
        require(seq not in by_sequence and generation not in by_generation,
                "Duplicate TopPanel scene sequence or generation")
        require(player == active_player and hwnd > 0 and device > 0,
                "TopPanel frame is detached from the actual player/HWND/GPU device")
        snapshot_path = Path(snap_s).resolve(strict=True)
        folder_path = Path(folder_s).resolve(strict=True)
        require(snapshot_path in generated_paths and folder_path.is_relative_to((runtime / "sessions").resolve(strict=True)),
                "TopPanel frame snapshot/folder escaped generated session evidence")
        require(snapshot_path.parent == folder_path.parent and snapshot_path.stem == f"play-ui-{seq}",
                "TopPanel frame sequence does not match its exact snapshot file")
        snapshot_info = verify_top_snapshot(snapshot_path, expected_player=active_player)
        world_match = [row for row in world_frames if row[1] == generation]
        require(len(world_match) == 1 and world_match[0][2] == turn and world_match[0][3] == device,
                "TopPanel overlay lacks a same-generation, same-turn, same-device world frame")
        revision = world_match[0][0]
        result_frame_rows = [row for row in result.get("frames", [])
                             if isinstance(row, list) and len(row) == 9 and row[1] == generation]
        require(len(result_frame_rows) == 1 and result_frame_rows[0][0] == revision and
                result_frame_rows[0][2] == turn and result_frame_rows[0][5] == device,
                "TopPanel frame log differs from the final run-result GPU frame inventory")
        gpu_rows = generated.get(f"play-scene-{revision}-gpu.png", [])
        require(len(gpu_rows) == 1, "TopPanel world generation lacks one unique real -gpu.png capture")
        gpu_path = gpu_rows[0]
        folder_files = {p.name: p for p in folder_path.iterdir() if p.is_file()}
        composed, underlay, packet, manifest = (folder_files.get(name) for name in
                                                ("composed.png", "world-underlay.png", "scene.packet", "scene_manifest.json"))
        require(all(p is not None for p in (composed, underlay, packet, manifest)),
                "TopPanel same-generation overlay lacks composed, underlay, packet, or manifest evidence")
        for p in (composed, underlay, packet, manifest):
            require(p.resolve(strict=True) in generated_paths, f"TopPanel overlay artifact is not in result inventory: {p.name}")
        require(png_header(gpu_path, {(1280, 720)}) == (1280, 720) and
                png_header(composed, {(1920, 1080)}) == (1920, 1080) and
                png_header(underlay, {(1920, 1080)}) == (1920, 1080),
                "TopPanel GPU or logical composition dimensions differ from the renderer contract")
        manifest_doc = load_json(manifest, "TopPanel scene manifest")
        snap_info = manifest_doc.get("snapshot", {})
        require(manifest_doc.get("context") == "top-panel" and
                Path(snap_info.get("path", "")).resolve(strict=True) == snapshot_path and
                snap_info.get("sha256") == digest(snapshot_path) and
                manifest_doc.get("snapshot_state_unchanged") is True,
                "Prepared TopPanel manifest is not tied to its exact immutable Host snapshot")
        sources = manifest_doc.get("original_context_sources")
        require(isinstance(sources, list), "TopPanel manifest omits original XML/Lua source provenance")
        source_map = {}
        for row in sources:
            src = Path(row.get("path", ""))
            name = src.name
            if name in ORIGINAL_TOP_PANEL_SOURCES:
                src = src.resolve(strict=True)
                require(row.get("sha256") == ORIGINAL_TOP_PANEL_SOURCES[name] and
                        digest(src) == row.get("sha256"),
                        f"Original TopPanel source hash differs: {name}")
                copies = [p for p in (folder_path / "source_ui").glob("*" + name) if p.is_file()]
                require(len(copies) == 1 and digest(copies[0]) == row["sha256"],
                        f"Frozen source mirror differs from the original TopPanel {name}")
                source_map[name] = {"source_path": str(src), "sha256": row["sha256"],
                                    "mirror": str(copies[0].resolve(strict=True))}
        require(set(source_map) == set(ORIGINAL_TOP_PANEL_SOURCES),
                "Prepared TopPanel manifest does not pin both original XML and Lua bytes")
        top_rows.append({"sequence": seq, "generation": generation, "turn": turn,
                         "snapshot": snapshot_info, "hwnd": hwnd, "device": device,
                         "gpu_frame": {"path": str(gpu_path), "sha256": digest(gpu_path),
                                       "revision": revision},
                         "overlay": {"composed": {"path": str(composed), "sha256": digest(composed)},
                                     "underlay": {"path": str(underlay), "sha256": digest(underlay)},
                                     "packet": {"path": str(packet), "sha256": digest(packet)},
                                     "manifest": {"path": str(manifest), "sha256": digest(manifest)},
                                     "composition_changed_pixels": None},
                         "original_sources": source_map})
        by_sequence[seq] = snapshot_info
        by_generation[generation] = snapshot_info
        hwnds.add(hwnd)
        devices.add(device)
    require(len(hwnds) == 1 and len(devices) == 1,
            "TopPanel frames replaced the single owned HWND or GPU device")
    return {"frames": top_rows, "sequence_snapshots": by_sequence,
            "generation_snapshots": by_generation, "hwnd": next(iter(hwnds)),
            "device": next(iter(devices))}


def verify_candidate_overlay_delta(frame: dict) -> int:
    """Measure candidate TopPanel pixels added over its exact captured world underlay."""
    overlay = frame["overlay"]
    composed_path = Path(overlay["composed"]["path"])
    underlay_path = Path(overlay["underlay"]["path"])
    cw, ch, composed = decode_png_rgba(composed_path)
    uw, uh, underlay = decode_png_rgba(underlay_path)
    require((cw, ch) == (uw, uh), "Same-generation composition dimensions differ")
    changed = sum(composed[pos:pos + 4] != underlay[pos:pos + 4]
                  for pos in range(0, len(composed), 4))
    require(changed > 0,
            "TopPanel software overlay did not change a pixel from its exact same-generation GPU underlay")
    overlay["composition_changed_pixels"] = changed
    return changed


def compare_gpu_capture_to_composed(gpu_path: Path, composed_path: Path) -> dict:
    """Compare the final Host backbuffer capture to the logical candidate composition.

    InteractiveGameLoop captures `play-scene-N-gpu.png` after committing the
    combined scene. BitmapWindow draws the committed logical bitmap to the
    1280x720 client with Direct2D nearest-neighbor sampling, then reads back the
    swap-chain backbuffer before Present. The other image is the Python candidate
    render of the same snapshot and world underlay; exact differences are measured.
    """
    gpu_size = png_header(gpu_path, {(1280, 720)})
    composed_size = png_header(composed_path, {(1920, 1080)})
    gw, gh, gpu = decode_png_rgba(gpu_path)
    cw, ch, composed = decode_png_rgba(composed_path)
    require((gw, gh) == gpu_size and (cw, ch) == composed_size and
            gw * ch == cw * gh,
            "GPU capture and composition do not share the same display aspect ratio")
    top_strip_rows = math.ceil(32 * gh / ch)
    differing = 0
    outside_top_strip = 0
    alpha_different = 0
    max_abs_rgb_delta = 0
    rgb_delta_values = [set(), set(), set()]
    min_x = min_y = None
    max_x = max_y = None
    for y in range(gh):
        source_y = int((y + 0.5) * ch / gh)
        for x in range(gw):
            source_x = int((x + 0.5) * cw / gw)
            gpu_offset = (y * gw + x) * 4
            composed_offset = (source_y * cw + source_x) * 4
            gpu_px = gpu[gpu_offset:gpu_offset + 4]
            composed_px = composed[composed_offset:composed_offset + 4]
            rgb_delta = tuple(gpu_px[c] - composed_px[c] for c in range(3))
            for channel, delta in enumerate(rgb_delta):
                rgb_delta_values[channel].add(delta)
                max_abs_rgb_delta = max(max_abs_rgb_delta, abs(delta))
            if gpu_px[3] != composed_px[3]:
                alpha_different += 1
            if gpu_px != composed_px:
                differing += 1
                if y >= top_strip_rows:
                    outside_top_strip += 1
                min_x = x if min_x is None else min(min_x, x)
                min_y = y if min_y is None else min(min_y, y)
                max_x = x if max_x is None else max(max_x, x)
                max_y = y if max_y is None else max(max_y, y)
    require(outside_top_strip == 0,
            "Final GPU capture differs from its scaled candidate composition outside the original 32px TopPanel bar")
    return {"final_host_gpu_capture": {"path": str(gpu_path), "sha256": digest(gpu_path),
                                       "width": gw, "height": gh,
                                       "capture_stage": "committed_scene_after_top_panel_overlay"},
            "composed_reference": {"path": str(composed_path), "sha256": digest(composed_path),
                                   "width": cw, "height": ch},
            "mapping": "Direct2D nearest-neighbor pixel-center sample from 1920x1080 to 1280x720",
            "top_panel_source_bar_height_logical": 32,
            "top_strip_rows_client": top_strip_rows,
            "different_pixels": differing,
            "matching_pixels": gw * gh - differing,
            "different_pixels_outside_top_panel_strip": outside_top_strip,
            "difference_bbox_client_inclusive": None if min_x is None else [min_x, min_y, max_x, max_y],
            "rgb_delta_gpu_minus_composed_per_channel": [sorted(values) for values in rgb_delta_values],
            "max_absolute_rgb_channel_delta": max_abs_rgb_delta,
            "alpha_different_pixels": alpha_different,
            "final_top_panel_gpu_capture_present": True,
            "exact_pixel_equivalence_to_candidate": differing == 0,
            "pixel_equivalence_status": "EXACT" if differing == 0 else "NOT_EXACT",
            "retail_pixel_equivalence_verified": False}


def verify_run(run_id: str) -> dict:
    require(RUN_ID.fullmatch(run_id) is not None, "Run ID is not an immutable timestamp/hash identity")
    run_evidence = EVIDENCE / run_id
    request_path, result_path = run_evidence / "request.json", run_evidence / "result.json"
    request = load_json(request_path, "interactive request")
    result = load_json(result_path, "interactive result")
    require(request.get("run_id") == run_id and result.get("run_id") == run_id,
            "Request/result identity differs from the run evidence directory")
    check_artifacts(request)
    check_artifacts(result)
    artifact_ref(result.get("request"), exact=request_path, label="run request")
    stdout_path = artifact_ref(result.get("stdout"), exact=run_evidence / "stdout.log", label="Host stdout")
    stderr_path = artifact_ref(result.get("stderr"), exact=run_evidence / "stderr.log", label="Host stderr")
    output = stdout_path.read_text(encoding="utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    require(request.get("top_panel") is True and request.get("smoke") is True and request.get("decisions") is True and
            request.get("stage_or_mods_changed") is False,
            "Request is not the isolated TopPanel + decisions smoke profile")
    require(result.get("returncode") == 0 and result.get("timed_out") is False and
            result.get("runtime_inputs_unchanged") is True and result.get("failures") == [] and
            result.get("decision_ui_sequence_verified") is True,
            "Actual Host/driver result is not clean or did not verify the TopPanel sequence")
    require(result.get("status", "").endswith("_PASS"), "Interactive run status is not PASS")
    require(not re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED",
                          output + "\n" + stderr), "Host/native/input failure marker is present")
    attempt_ref = artifact_ref(result.get("attempt"), exact=run_evidence / "attempt.json", label="Host attempt")
    attempt = load_json(attempt_ref, "Host process attempt")
    require(attempt.get("status") == "FINISHED" and attempt.get("returncode") == 0 and
            attempt.get("timed_out") is False and attempt.get("pid") == result.get("driver_pid", result.get("pid")),
            "Host process attempt did not end cleanly under its recorded process identity")
    runtime = (RUNTIME_ROOT / run_id).resolve(strict=True)
    require(Path(request.get("cwd", "")).resolve(strict=True) == runtime,
            "Interactive runtime cwd is not the exact run-private runtime")
    host_proof = verify_host(request, runtime)
    frozen_ui = verify_frozen_ui(request, run_evidence, runtime)
    fixture_path = COMPONENT_FIXTURE.resolve(strict=True)
    require(fixture_path.is_file(), "Component-only TopPanel fixture source is missing")
    fixture_proof = {"path": str(fixture_path), "sha256": digest(fixture_path),
                     "scope": "component_only_not_live_runtime_evidence"}
    verifier_path = Path(__file__).resolve(strict=True)
    verifier_proof = {"path": str(verifier_path), "sha256": digest(verifier_path)}
    generated_by_name, generated_paths = generated_map(result, runtime)

    started = text_rows(output, "INTERACTIVE_GAME_STARTED",
                        r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    require(len(started) == 1, "Actual GameCore startup marker is missing or duplicated")
    start_turn, active_player, _, _ = map(int, started[0])

    frame_proof = verify_frame_links(output, result, runtime, generated_by_name, generated_paths, active_player)
    top_frames = frame_proof["frames"]

    initial_state_rows = [p for p in generated_paths if p.name == "play-initial-state.txt"]
    before_state_rows = [p for p in generated_paths if p.name == "top-panel-before.txt"]
    tree_state_rows = [p for p in generated_paths if p.name == "top-panel-tree.txt"]
    returned_state_rows = [p for p in generated_paths if p.name == "top-panel-returned.txt"]
    require(len(initial_state_rows) == len(before_state_rows) == len(tree_state_rows) == len(returned_state_rows) == 1,
            "TopPanel smoke lacks unique initial/before/tree/returned SDK state snapshots")

    def active_city_count(snapshot_path: Path) -> int:
        rows = [line.split("|") for line in snapshot_path.read_text(encoding="utf-8").splitlines()
                if line.startswith(f"P|{active_player}|")]
        require(len(rows) == 1 and len(rows[0]) == 11,
                f"Malformed active-player row in SDK state snapshot: {snapshot_path.name}")
        return int(rows[0][6])

    initial_city_count = active_city_count(initial_state_rows[0])
    before_city_count = active_city_count(before_state_rows[0])
    require(initial_city_count >= 0 and before_city_count >= 1,
            "SDK state before SciencePerTurn does not prove an active-player city")
    is_new_game_foundation = initial_city_count == 0
    active_at_start = [row for row in top_frames if row["turn"] == start_turn and
                       not row["snapshot"]["info_stack_hidden"]]
    active_next_turn = [row for row in top_frames if row["turn"] == start_turn + 1 and
                        not row["snapshot"]["info_stack_hidden"]]
    require(active_at_start and active_next_turn,
            "TopPanel evidence lacks visible frames at the starting turn and the following turn")
    first_active_start = min(active_at_start, key=lambda row: row["sequence"])
    first_active_next = min(active_next_turn, key=lambda row: row["sequence"])
    if is_new_game_foundation:
        pre_city = [row for row in top_frames if row["turn"] == start_turn and
                    row["snapshot"]["info_stack_hidden"]]
        require(pre_city and min(row["sequence"] for row in pre_city) < first_active_start["sequence"],
                "New-game scene lacks its hidden pre-city TopPanel before founding the first city")
        scenario = "NEW_GAME_CITY_FOUNDATION"
        first_pre_city = min(pre_city, key=lambda row: row["sequence"])
    else:
        scenario = "RESTORED_OR_EXISTING_CITY_STATE"
        first_pre_city = None
    require(first_active_start["sequence"] < first_active_next["sequence"] and
            first_active_start["snapshot"]["current_turn_text"] !=
            first_active_next["snapshot"]["current_turn_text"],
            "Original TopPanel did not refresh its current-turn text on the following turn")
    transition_states = [path.read_bytes() for path in
                         (before_state_rows[0], tree_state_rows[0], returned_state_rows[0])]
    require(transition_states[0] == transition_states[1] == transition_states[2],
            "TechTree open/Escape roundtrip changed the exact SDK state snapshot bytes")

    science_targets = text_rows(output, "INTERACTIVE_TOP_PANEL_SCIENCE_TARGET",
                                r"^INTERACTIVE_TOP_PANEL_SCIENCE_TARGET=(\d+)\|(\d+)\|(-?\d+)$")
    require(len(science_targets) == 1, "TopPanel science target marker is missing or duplicated")
    global_key, generation, target_turn = map(int, science_targets[0])
    require(target_turn == start_turn,
            "Science test did not dispatch at the current nonmodal TopPanel starting-turn generation")
    require(global_key >= TOP_PANEL_KEY_BASE and global_key < TOP_PANEL_KEY_BASE + TOP_PANEL_KEY_LIMIT,
            "Science target is outside the reserved TopPanel input-key namespace")
    local_key = global_key - TOP_PANEL_KEY_BASE
    require(local_key > 0 and frame_proof["generation_snapshots"].get(generation) is not None,
            "Science global key does not map back to a retained local target and exact frame")
    science_snapshot = [row for row in top_frames if row["generation"] == generation]
    require(len(science_snapshot) == 1, "Science target generation is not a unique TopPanel frame")
    composition_changed_pixels = verify_candidate_overlay_delta(science_snapshot[0])
    gpu_composition = compare_gpu_capture_to_composed(
        Path(science_snapshot[0]["gpu_frame"]["path"]),
        Path(science_snapshot[0]["overlay"]["composed"]["path"]))
    snap_path = Path(science_snapshot[0]["snapshot"]["snapshot"])
    snap_doc = load_json(snap_path, "Science target TopPanel snapshot")
    local_targets = [row for row in snap_doc["inputTargets"] if isinstance(row, dict) and
                     row.get("key") == local_key and row.get("id") == "SciencePerTurn" and
                     row.get("event") == "LeftClick" and row.get("visible") is True]
    require(len(local_targets) == 1, "Namespaced science target does not reverse-map to original SciencePerTurn")

    posted = text_rows(output, "INTERACTIVE_SMOKE_POSTED",
                       r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    top_inputs = text_rows(output, "INTERACTIVE_TOP_PANEL_INPUT",
                           r"^INTERACTIVE_TOP_PANEL_INPUT=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$")
    posted_science = [tuple(map(int, row)) for row in posted if int(row[0]) == generation and int(row[1]) == global_key]
    routed_science = [tuple(map(int, row)) for row in top_inputs if int(row[0]) == generation and
                      int(row[2]) == global_key and int(row[3]) == local_key]
    require(len(posted_science) == 1 and len(routed_science) == 1 and
            routed_science[0][1] == 1 and routed_science[0][4] == 1,
            "Posted HWND science click did not route global key to its exact consumed local callback")
    bounds = local_targets[0].get("clippedBounds") or local_targets[0].get("bounds")
    require(isinstance(bounds, dict) and all(type(bounds.get(key)) in (int, float)
                                             for key in ("x", "y", "width", "height")),
            "Science target has no exact retained logical hit bounds")
    logical_x, logical_y = posted_science[0][2] * 1.5, posted_science[0][3] * 1.5
    require(bounds["x"] <= logical_x < bounds["x"] + bounds["width"] and
            bounds["y"] <= logical_y < bounds["y"] + bounds["height"],
            "Posted client coordinate is outside the original SciencePerTurn hit bounds")

    popup = text_rows(output, "INTERACTIVE_TOP_PANEL_POPUP",
                      r"^INTERACTIVE_TOP_PANEL_POPUP=(-?\d+)\|(-?\d+)\|(-?\d+)$")
    returned = text_rows(output, "INTERACTIVE_TOP_PANEL_SCIENCE_RETURNED",
                         r"^INTERACTIVE_TOP_PANEL_SCIENCE_RETURNED=(\d+)\|(-?\d+)\|STATE_UNCHANGED$")
    require(len(popup) == 1 and int(popup[0][0]) == active_player and
            int(popup[0][2]) == -1 and len(returned) == 1,
            "Science click did not queue exactly one original TechTree request with Data2=-1 and return marker")
    return_generation, return_turn = map(int, returned[0])
    require(return_turn == start_turn and generation < return_generation,
            "Native Escape return did not publish a later unchanged overlay at the starting turn")
    modal_requests = text_rows(output, "INTERACTIVE_UI_SCENE_REQUEST",
        r"^INTERACTIVE_UI_SCENE_REQUEST=(\d+)\|(research-tree)\|([^\r\n|]+)\|([^\r\n|]+)$")
    require(modal_requests, "Deferred science callback did not instantiate the original modal TechTree")
    modal_snapshots = []
    for _, _, path_text, _ in modal_requests:
        modal_path = Path(path_text).resolve(strict=True)
        require(modal_path in generated_paths, "Modal TechTree snapshot is not a recorded Host artifact")
        modal_doc = load_json(modal_path, "modal TechTree snapshot")
        if modal_doc.get("popupKind") == "ResearchTree":
            modal_snapshots.append(modal_doc)
    require(modal_snapshots and any(row.get("active") is True and row.get("timerSemaphore") == 1 and
                                    row.get("timerSemaphores", row.get("timerSemaphore")) == 1 and
                                    row.get("nonmodal") is not True
                                    for row in modal_snapshots),
            "Deferred science popup did not enter the original modal timer-held TechTree context")
    native_escape_rows = list(re.finditer(
        r"^INTERACTIVE_UI_NATIVE_KEY=(\d+)\|research-tree\|27\|1\|0$", output, re.M))
    matching_native_escape = [row for row in native_escape_rows
                              if generation < int(row[1]) < return_generation]
    require(len(matching_native_escape) == 1,
            "Science callback interval lacks one uniquely consumed ResearchTree Escape")
    key_generation = int(matching_native_escape[0][1])
    require(generation < key_generation < return_generation,
            "Science callback, native Escape, and returned TopPanel generations are out of order")
    native_dispatch = [tuple(map(int, row)) for row in re.findall(
        r"^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$", output, re.M)]
    preceding_key_inputs = [row for row in native_dispatch if row[0] == key_generation]
    require(preceding_key_inputs and preceding_key_inputs[-1] == (key_generation, 0, 0, 1),
            "TechTree Escape key has no matching consumed native KeyDown dispatch")
    escape_generation_frames = re.findall(
        r"^INTERACTIVE_UI_FRAME=\d+\|(\d+)\|\d+\|research-tree\|(\d+)\|(\d+)\|([^\r\n|]+)\|([^\r\n|]+)$", output, re.M)
    matching_escape_frames = [row for row in escape_generation_frames if int(row[0]) == key_generation]
    require(len(matching_escape_frames) == 1 and
            int(matching_escape_frames[0][1]) == frame_proof["hwnd"] and
            int(matching_escape_frames[0][2]) == frame_proof["device"],
            "Native Escape did not act on the same owned HWND and GPU device as the TopPanel")
    popup_type = int(popup[0][1])
    require(popup_type >= 0, "Deferred TechTree popup type is invalid")

    world_frames = result.get("frames")
    require(isinstance(world_frames, list) and world_frames, "Run result omits native GPU frame records")
    require(all(isinstance(row, list) and len(row) == 9 for row in world_frames) and
            len({row[5] for row in world_frames}) == 1,
            "Continuous run replaced the single owned GPU device")
    # verify_frame_links already binds each overlay to one INTERACTIVE_WORLD_FRAME
    # with the same generation, turn, HWND, and GPU device. The composition test
    # uses exact image-byte differences against the exact captured underlay; it
    # deliberately makes no pixel-percentage or retail-equivalence claim.
    return {"status": "PASS_INTERACTIVE_TOP_PANEL_NATIVE_SDK_SMOKE",
            "run_id": run_id, "host": host_proof, "frozen_ui_source": frozen_ui,
            "component_fixture": fixture_proof, "verifier": verifier_proof,
            "active_player": active_player, "startup_turn": start_turn,
            "scenario": scenario, "initial_active_player_city_count": initial_city_count,
            "active_city_before_science_count": before_city_count,
            "pre_city_hidden_frame": first_pre_city,
            "starting_turn_visible_frame": first_active_start,
            "next_turn_refreshed_frame": first_active_next,
            "science_dispatch": {"generation": generation, "global_key": global_key,
                                 "local_key": local_key, "posted_hwnd_click": posted_science[0],
                                 "consumed_input": routed_science[0], "popup_type": popup_type,
                                 "popup_data2": int(popup[0][2]),
                                 "returned_generation": return_generation,
                                 "native_escape_generation": key_generation},
            "sdk_state": {
                "initial": {"path": str(initial_state_rows[0]), "sha256": digest(initial_state_rows[0]),
                            "active_player_city_count": initial_city_count},
                "active_city_before_science": {"path": str(before_state_rows[0]),
                    "sha256": digest(before_state_rows[0]),
                    "active_player_city_count": before_city_count},
                "tech_tree": {"path": str(tree_state_rows[0]), "sha256": digest(tree_state_rows[0])},
                "returned": {"path": str(returned_state_rows[0]), "sha256": digest(returned_state_rows[0])},
                "tech_tree_roundtrip_bytes_identical": True},
            "top_panel_frames": top_frames, "single_hwnd_verified": True,
            "single_gpu_device_verified": True,
            "final_top_panel_gpu_capture_present": True,
            "top_panel_gpu_pixel_equivalence": gpu_composition["pixel_equivalence_status"],
            "science_generation_composition_changed_pixels": composition_changed_pixels,
            "science_generation_gpu_vs_composed": gpu_composition,
            "starting_turn_to_next_turn_data_refresh_verified": True,
            "host_process_passed": True, "result_json_modified": False,
            "tooltip_retail_placement_verified": False, "retail_pixel_equivalence_verified": False,
            "all_original_callbacks_supported": False, "full_original_ui_verified": False,
            "full_gameplay_verified": False, "human_input_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if RUN_ID.fullmatch(args.run_id) is None:
        print("Run ID is not an immutable timestamp/hash identity", file=sys.stderr)
        return 2
    run_evidence = EVIDENCE / args.run_id
    report_path = run_evidence / "top_panel_validation.json"
    if report_path.exists():
        print(f"Refusing to overwrite existing TopPanel validation report: {report_path}", file=sys.stderr)
        return 2
    try:
        report = verify_run(args.run_id)
        document = {"status": report.pop("status"),
                    "top_panel_visual_status": report["top_panel_gpu_pixel_equivalence"],
                    "scope": "ACTUAL_X64_HOST_TOP_PANEL_NONMODAL_OVERLAY_AND_SCIENCE_TECHTREE_RETURN",
                    "evidence": report,
                    "limitations": [
                        "The run used posted HWND input, not human input.",
                        "The final Host GPU capture is compared to the software candidate by exact pixel equality; any recorded top-strip differences mean the candidate is not exactly pixel-equivalent.",
                        "No retail game capture was provided, so original-game pixel equivalence remains unverified regardless of the candidate comparison.",
                        "Only the SciencePerTurn to TechTree callback is exercised; tooltip placement, other callbacks, and full UI coverage remain unverified.",
                        "One bounded SDK decision scenario is not evidence of complete game coverage.",
                    ]}
    except Exception as exc:
        document = {"status": "FAIL_INTERACTIVE_TOP_PANEL_VALIDATION", "run_id": args.run_id,
                    "failure": f"{type(exc).__name__}: {exc}", "result_json_modified": False,
                    "retail_pixel_equivalence_verified": False, "full_original_ui_verified": False,
                    "full_gameplay_verified": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    try:
        with report_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError:
        print(f"Refusing to overwrite existing TopPanel validation report: {report_path}", file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "run_id": args.run_id,
                      "report": str(report_path)}, ensure_ascii=False))
    return 0 if document["status"] == "PASS_INTERACTIVE_TOP_PANEL_NATIVE_SDK_SMOKE" else 1


if __name__ == "__main__":
    raise SystemExit(main())


