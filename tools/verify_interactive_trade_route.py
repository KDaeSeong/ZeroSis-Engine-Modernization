"""Independently verify one actual Civ V SDK TradeRoute overview smoke run.

This verifier consumes immutable Host/driver evidence only. It does not launch
the Host or game, alter result.json, or claim retail-pixel/full-UI equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from collect_baseline import PROJECT, digest
import render_ui_popup
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts

EVIDENCE = PROJECT / "evidence/interactive_game"
RUNTIME_ROOT = PROJECT / "Build/InteractiveGameRuntime"
RUN_ID = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}\Z")
HOST_SOURCE_NAMES = ("InteractiveGameLoop.h", "UiPopupContext.h", "UiScene.lua",
                     "TradeRouteSmokeFixture.h", "TradeRoutePresentation.h")
HOST_SOURCE_FREEZE_ROOTS = {
    "InteractiveGameLoop.h": "include_roots/project",
    "UiPopupContext.h": "include_roots/project",
    "UiScene.lua": "project",
    "TradeRouteSmokeFixture.h": "include_roots/project",
    "TradeRoutePresentation.h": "include_roots/project",
}
NATIVE_INPUT_SOURCE_PATHS = {
    "BitmapWindow.h": ("Source\\Presentation\\BitmapWindow.h", "include_roots/project"),
    "BitmapWindow.cpp": ("Source\\Presentation\\BitmapWindow.cpp", "include_roots/project"),
    "UiInputDispatch.h": ("Source\\Host\\UiInputDispatch.h", "include_roots/project"),
    "UiPopupContext.h": ("Source\\Host\\UiPopupContext.h", "include_roots/project"),
    "UiPresentationInput.lua": ("Source\\Presentation\\UiPresentationInput.lua", "project"),
}
COMPONENT_RESULT = PROJECT / "evidence/trade_route_icon_fix/20261008T161342Z/layout-component/result.json"
COMPONENT_SNAPSHOT = PROJECT / "evidence/trade_route_icon_fix/20261008T161342Z/layout-component/snapshot.json"
FIXTURE = PROJECT / "Tests/trade_route_scene.lua"
VERIFIER = Path(__file__).resolve()

ORIGINAL_SOURCES = {
    "TradeRouteOverview.lua": "f52d8d95bbcdb768383d4503787a42be6eb5439d681408716c5d5dae34cf6652",
    "TradeRouteOverview.xml": "4b0d1d604a49a96be481fbbeb6a36f863f1ab6a3ea3685be4da58d77516275cd",
    "TradeRouteHelpers.lua": "ab741a40fbdb1413d5d31afa9cf37afd977777d030b2e6d852e93a91c866327f",
}
TAB_TARGETS = {
    "TabButtonYourTR": "YourTR",
    "TabButtonAvailableTR": "AvailableTR",
    "TabButtonTRWithYou": "TRWithYou",
}
SORT_TARGETS = {
    "Domain", "FromOwnerHeader", "FromCityHeader", "ToOwnerHeader", "ToCityHeader",
    "FromGPT", "ToGPT", "ToFood", "ToProduction", "FromReligion", "ToReligion",
    "FromScience", "ToScience", "TurnsLeft",
}
REQUIRED_TARGETS = set(TAB_TARGETS) | SORT_TARGETS | {"CloseButton"}
EXPECTED_ACTIONS = [
    (1, "InternationalTradeRoutes", "control"),
    (2, "FromGPT", "control"),
    (3, "FromGPT", "control"),
    (4, "TabButtonAvailableTR", "control"),
    (6, "TabButtonTRWithYou", "control"),
    (7, "TabButtonYourTR", "control"),
    (8, "KEY_RETURN", "key"),
    (9, "CloseButton", "control"),
    (10, "InternationalTradeRoutes", "control"),
    (11, "KEY_ESCAPE", "key"),
]


class VerificationError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise VerificationError(message)


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


def compiled_host_source(build_id: str, name: str, row: dict) -> Path:
    """Resolve a source row only when it is the exact frozen input for this Host build."""
    require(name in HOST_SOURCE_NAMES, f"Unexpected compiled Host source {name}")
    return compiled_build_source(build_id, row, f"Source\\Host\\{name}",
                                 HOST_SOURCE_FREEZE_ROOTS[name])


def compiled_build_source(build_id: str, row: dict, relative_path: str,
                          freeze_root: str) -> Path:
    """Bind any inspected source to one exact builder freeze root and lineage."""
    require(RUN_ID.fullmatch(build_id) is not None,
            "Host build ID is not an immutable timestamp/hash identity")
    original_source = PROJECT / relative_path.replace("\\", "/")
    build_root = PROJECT / "Build/UiWindowHost" / build_id
    frozen_root_path = build_root / "frozen" / freeze_root
    expected_path = frozen_root_path / relative_path.replace("\\", "/")
    recorded_original = row.get("original_source")
    require(row.get("relative_path") == relative_path and
            isinstance(recorded_original, str) and
            Path(recorded_original).resolve(strict=False) == original_source.resolve(strict=False),
            f"Build source {relative_path} does not preserve its project-relative original lineage")
    require(build_root.is_dir() and frozen_root_path.is_dir(),
            f"Build source {relative_path} has no frozen root for build {build_id}")
    path_value = row.get("path")
    require(isinstance(path_value, str), f"Frozen build source {relative_path} lacks its path")
    path = Path(path_value)
    require(path.resolve(strict=False) == expected_path.resolve(strict=False) and path.is_file() and
            path.stat().st_size == row.get("bytes") and digest(path) == row.get("sha256"),
            f"Host build does not pin the hash-verified frozen source {relative_path}")
    return path.resolve(strict=False)


def validate_native_input_source_contract(texts: dict[str, str]) -> None:
    """Validate the frozen native-to-Lua input enum, wheel conversion, and consume path."""
    require(set(texts) == set(NATIVE_INPUT_SOURCE_PATHS),
            "Native input source evidence is incomplete")
    markers = {
        "BitmapWindow.h": ("KeyDown=0", "ControlClick=1", "Scroll=4"),
        "BitmapWindow.cpp": (
            "kPrototypeScrollPixelsPerNotch = 48.0f",
            "-static_cast<float>(wheelDelta)*(kPrototypeScrollPixelsPerNotch/static_cast<float>(WHEEL_DELTA))",
            "BitmapInputKind::Scroll,key,0,logicalX,logicalY,sceneGeneration_,delta",
        ),
        "UiInputDispatch.h": (
            "KeyDown=1, LeftClick=2, PointerMove=3, Scroll=4",
            'exportName="DispatchLeftClick"', 'exportName="DispatchScroll"',
        ),
        "UiPopupContext.h": (
            "BitmapInputKind::ControlClick:request.kind=UiInputKind::LeftClick;request.key=event.controlKey",
            "BitmapInputKind::KeyDown:request.kind=UiInputKind::KeyDown;request.key=event.virtualKey",
            "BitmapInputKind::Scroll:",
            "request.kind=UiInputKind::Scroll;request.key=event.controlKey;request.delta=event.scrollDelta",
        ),
        "UiPresentationInput.lua": (
            "panel:SetScrollValue(math.max(0,math.min(maximum,current+delta)))",
            "return true",
        ),
    }
    for name, required in markers.items():
        scoped_text = texts[name]
        if name == "UiPresentationInput.lua":
            prefix = "function ZeroSisUi.DispatchScroll"
            require(prefix in scoped_text, "Frozen UiPresentationInput.lua lacks its DispatchScroll body")
            scoped_text = scoped_text.split(prefix, 1)[1].split("\nend", 1)[0]
        compact = re.sub(r"\s+", "", scoped_text)
        require(all(re.sub(r"\s+", "", marker) in compact for marker in required),
                f"Frozen native input contract changed in {name}")


def frozen_native_input_sources(build_id: str, sources: dict[str, dict]) -> dict[str, dict]:
    required_names = set(NATIVE_INPUT_SOURCE_PATHS)
    require(required_names <= sources.keys(), "Host build omits frozen native input sources")
    texts, proof = {}, {}
    for name, (relative_path, freeze_root) in NATIVE_INPUT_SOURCE_PATHS.items():
        path = compiled_build_source(build_id, sources[name], relative_path, freeze_root)
        texts[name] = path.read_text(encoding="utf-8")
        proof[name] = {"path": str(path), "sha256": digest(path)}
    validate_native_input_source_contract(texts)
    return proof


def validate_compiled_host_source_contract(name: str, text: str) -> None:
    """Check each frozen input for the responsibility it actually owns."""
    if name == "InteractiveGameLoop.h":
        markers = ("INTERACTIVE_TRADE_ROUTE_ACTION", "INTERACTIVE_TRADE_ROUTE_WHEEL",
                   "INTERACTIVE_TRADE_ROUTE_COMPLETE", "PostTradeRouteWheel")
        require(all(marker in text for marker in markers),
                "Compiled game loop lacks the recorded TradeRoute input/wheel contract")
    elif name == "UiPopupContext.h":
        markers = ("INTERACTIVE_TRADE_ROUTE_SHOWN", "INTERACTIVE_TRADE_ROUTE_INPUT",
                   "BUTTONPOPUP_TRADE_ROUTE_OVERVIEW")
        require(all(marker in text for marker in markers),
                "Compiled popup context lacks original TradeRoute dispatch/observation")
    elif name == "UiScene.lua":
        # The generic retained scene exports provenance and control state. The original
        # layout filename and TRInstance identity are checked against the captured
        # snapshot/generated asset proof, not expected as literals in this Lua module.
        markers = ("hasRetainedTradeRouteUi", "rowTemplate=assert(provenance.rowTemplate",
                   "originalLayoutXml=assert(provenance.originalLayoutXml",
                   "originalLayoutLua=assert(provenance.originalLayoutLua",
                   "originalHelpersLua=assert(provenance.originalHelpersLua")
        require(all(marker in text for marker in markers),
                "Compiled Lua scene source lacks retained TradeRoute provenance exports")
    elif name == "TradeRouteSmokeFixture.h":
        # City userdata is exposed to the fixture's Lua fragment as `from` and `to`;
        # the C++ fixture source itself does not contain FromCity:/ToCity: expressions.
        markers = ("from:GetID()", "to:GetID()", "from:GetOwner()", "to:GetOwner()",
                   "GetTradeRoutesToYou()", "GetTradeRoutesAvailable()", "UNITAI_UNKNOWN",
                   "SetUnitAIType(fixtureAI)", "for _,unit in ipairs({inA,inB}) do",
                   "MISSION_ESTABLISH_TRADE_ROUTE", "ResponsePushMission")
        require(all(marker in text for marker in markers),
                "Compiled TradeRoute fixture lacks real SDK getters and mission contract")
    elif name == "TradeRoutePresentation.h":
        markers = ("ZEROSIS_TRADE_ROUTE_PRESENTATION_V1", "SDK:TradeVisuals",
                   "worldRouteRenderingImplemented", "directionKnown", "plots")
        require(all(marker in text for marker in markers),
                "Compiled presentation source lacks the bounded SDK callback-copy contract")
    else:
        require(False, f"Unexpected compiled Host source contract {name}")


def generated_map(result: dict, runtime: Path) -> tuple[dict[str, list[Path]], set[Path]]:
    rows = result.get("generated_files")
    require(isinstance(rows, list), "Run result omits its generated-file inventory")
    session_root = (runtime / "sessions").resolve(strict=True)
    by_name: dict[str, list[Path]] = {}
    paths: set[Path] = set()
    for row in rows:
        path = artifact_ref(row, label="generated session artifact")
        require(path.is_relative_to(session_root), "Generated artifact escaped the run-private session")
        require(path not in paths, "Generated-file inventory duplicates a path")
        paths.add(path)
        by_name.setdefault(path.name, []).append(path)
    actual = {path.resolve(strict=True) for path in session_root.rglob("*") if path.is_file()}
    require(actual == paths, "Generated-file inventory does not exactly cover the session tree")
    return by_name, paths


def unique_generated(by_name: dict[str, list[Path]], filename: str) -> Path:
    matches = by_name.get(filename, [])
    require(len(matches) == 1, f"Expected one generated {filename}, found {len(matches)}")
    return matches[0]


def trade_route_frame_manifest(snapshot_path: Path, folder_ref: str,
                               generated_paths: set[Path], session_root: Path) -> Path:
    """Resolve a frame manifest only through the hash-verified run inventory."""
    folder = Path(folder_ref).resolve(strict=False)
    require(folder.is_dir() and folder.is_relative_to(session_root.resolve(strict=False)) and
            snapshot_path.parent == folder.parent and snapshot_path.stem == folder.name,
            "TradeRoute frame folder does not identify its exact generated snapshot")
    manifest_path = (folder / "scene_manifest.json").resolve(strict=False)
    require(manifest_path.is_file() and manifest_path in generated_paths,
            "TradeRoute frame scene_manifest.json is not a SHA-verified generated artifact")
    return manifest_path


def verify_frozen_support(request: dict, run_evidence: Path, runtime: Path) -> dict:
    tool_names = {"interactive_ui_driver.py", "render_ui_popup.py", "ui_pixel_scene.py",
                  "ui_bitmap_fonts.py", "civ5_ui_assets.py"}
    record_path = artifact_ref(request.get("interactive_ui_support"),
                               exact=run_evidence / "interactive_ui_support.json",
                               label="frozen UI support record")
    record = load_json(record_path, "frozen UI support record")
    inventory = request.get("interactive_ui_support_inventory")
    require(isinstance(inventory, dict) and set(record.get("tools", {})) == tool_names and
            set(inventory.get("tools", {})) == tool_names,
            "Request does not pin the exact interactive UI tool set")
    support_root = (runtime / "interactive_ui_support").resolve(strict=True)
    manifest_ref = record.get("frozen_support_manifest", {})
    manifest_path = artifact_ref(manifest_ref, label="frozen support manifest")
    manifest_inventory = inventory.get("frozen_support_manifest", {})
    require(manifest_path == (support_root / "support_manifest.json").resolve(strict=True) and
            manifest_ref.get("sha256") == manifest_inventory.get("sha256"),
            "Frozen support manifest differs from the immutable run request")
    manifest = load_json(manifest_path, "frozen support manifest")
    require(set(manifest.get("tools", {})) == tool_names,
            "Frozen support manifest has an incomplete tool set")
    tools_proof = {}
    for name in sorted(tool_names):
        row, request_row = record["tools"][name], inventory["tools"][name]
        frozen, source = row.get("frozen", {}), row.get("source", {})
        request_frozen, request_source = request_row.get("frozen", {}), request_row.get("source", {})
        path = artifact_ref(frozen, label=f"frozen UI tool {name}")
        require(path == (support_root / "tools" / name).resolve(strict=True) and
                frozen.get("sha256") == request_frozen.get("sha256") == source.get("sha256") ==
                request_source.get("sha256") == digest(path) and
                Path(source.get("original_path", "")).resolve(strict=True) ==
                Path(request_source.get("original_path", "")).resolve(strict=True) and
                manifest.get("tools", {}).get(name, {}).get("sha256") == digest(path),
                f"Frozen UI tool {name} lost source, request, or manifest hash provenance")
        tools_proof[name] = {"path": str(path), "sha256": digest(path),
                             "original_path": source["original_path"],
                             "original_sha256": source["sha256"]}
    catalog_proof = {}
    for key, filename in (("inline_icons", "inline_icons.json"),
                          ("asset_preparation_provenance", "prepared.json")):
        row, request_row = record.get(key, {}), inventory.get(key, {})
        frozen, source = row.get("frozen", {}), row.get("source", {})
        request_frozen, request_source = request_row.get("frozen", {}), request_row.get("source", {})
        path = artifact_ref(frozen, label=f"frozen UI catalog {filename}")
        require(path == (support_root / "assets" / filename).resolve(strict=True) and
                frozen.get("sha256") == request_frozen.get("sha256") == source.get("sha256") ==
                request_source.get("sha256") == digest(path) and
                Path(source.get("original_path", "")).resolve(strict=True) ==
                Path(request_source.get("original_path", "")).resolve(strict=True) and
                manifest.get(key, {}).get("sha256") == digest(path),
                f"Frozen UI catalog {filename} lost source, request, or manifest hash provenance")
        catalog_proof[key] = {"path": str(path), "sha256": digest(path),
                              "original_path": source["original_path"],
                              "original_sha256": source["sha256"]}
    return {"record": {"path": str(record_path), "sha256": digest(record_path)},
            "manifest": {"path": str(manifest_path), "sha256": digest(manifest_path)},
            "tools": tools_proof, "catalogs": catalog_proof}


def verify_sdk_inventory(path: Path, expected_owner: int, expected_turn: int) -> dict:
    inventory = load_json(path, "real SDK TradeRoute inventory")
    require(inventory.get("schema") == "ZEROSIS_TRADE_ROUTE_SDK_INVENTORY_V1" and
            inventory.get("activePlayer") == expected_owner and inventory.get("turn") == expected_turn and
            type(inventory.get("elapsed")) is int and inventory["elapsed"] >= 0,
            "SDK inventory root does not prove its versioned active-player/turn/getter contract")
    source = json.dumps(inventory.get("source"), ensure_ascii=False, sort_keys=True)
    require(all(name in source for name in ("GetTradeRoutes", "GetTradeRoutesToYou", "GetTradeRoutesAvailable")),
            "SDK inventory source does not identify all three actual player getters")
    names = ("outbound", "inbound", "available")
    rows_proof = {}
    for name in names:
        rowset = inventory.get(name)
        require(isinstance(rowset, list) and len(rowset) >= 2,
                f"Real SDK {name} getter did not yield the required two nonempty rows")
        normalized = []
        for row in rowset:
            required = {"fromOwner", "toOwner", "fromCityId", "toCityId",
                        "fromCityUserdataResolved", "toCityUserdataResolved", "domain", "turnsLeft",
                        "fromCityWrapperType", "fromCityNativeInstanceType",
                        "toCityWrapperType", "toCityNativeInstanceType",
                        "fromCityName", "toCityName", "fromGPT", "toGPT", "toFood", "toProduction",
                        "fromScience", "toScience", "toReligion", "toPressure", "fromReligion",
                        "fromPressure", "fromTourism", "toTourism",
                        "fromCivilizationType", "toCivilizationType"}
            require(isinstance(row, dict) and set(row) == required,
                    f"SDK {name} row does not preserve its exact native route/userdata fields")
            int_fields = ("fromOwner", "toOwner", "fromCityId", "toCityId", "domain", "turnsLeft",
                          "fromGPT", "toGPT", "toFood", "toProduction", "fromScience", "toScience",
                          "toReligion", "toPressure", "fromReligion", "fromPressure", "fromTourism", "toTourism",
                          "fromCivilizationType", "toCivilizationType")
            require(all(type(row.get(field)) is int for field in int_fields) and
                    row["fromCityId"] >= 0 and row["toCityId"] >= 0 and
                    row["fromCityUserdataResolved"] is True and row["toCityUserdataResolved"] is True and
                    row["fromCityWrapperType"] == row["toCityWrapperType"] == "table" and
                    row["fromCityNativeInstanceType"] == row["toCityNativeInstanceType"] == "userdata" and
                    isinstance(row["fromCityName"], str) and row["fromCityName"] and
                    isinstance(row["toCityName"], str) and row["toCityName"],
                    f"SDK {name} row does not prove real city userdata IDs, names, and numeric getter values")
            if name in ("outbound", "available"):
                require(row["fromOwner"] == expected_owner,
                        f"SDK {name} getter returned a row outside the active player's origin scope")
            else:
                require(row["toOwner"] == expected_owner and row["fromOwner"] != row["toOwner"],
                        "SDK inbound getter returned a row outside actual foreign-origin/active-destination scope")
            normalized.append({"from": row["fromCityName"], "to": row["toCityName"],
                               "from_owner": row["fromOwner"], "to_owner": row["toOwner"],
                               "from_city_id": row["fromCityId"], "to_city_id": row["toCityId"],
                               "from_gpt": row["fromGPT"], "domain": row["domain"],
                               "turns_left": row["turnsLeft"], "city_userdata_resolved": True})
        rows_proof[name] = normalized
    return {"schema": inventory["schema"], "source": inventory["source"],
            "active_player": inventory["activePlayer"], "turn": inventory["turn"],
            "elapsed_turns": inventory["elapsed"],
            "routes": rows_proof}


def verify_trade_route_presentation(path: Path, sdk_inventory: dict, label: str) -> dict:
    presentation = load_json(path, label)
    require(set(presentation) == {"schema", "source", "worldRouteRenderingImplemented",
                                  "popupRoute", "routes"} and
            presentation.get("schema") == "ZEROSIS_TRADE_ROUTE_PRESENTATION_V1" and
            presentation.get("source") == "SDK:TradeVisuals" and
            presentation.get("worldRouteRenderingImplemented") is False and
            presentation.get("popupRoute") is None,
            f"{label} does not prove SDK-only route presentation with no popup selection or world rendering")
    routes = presentation.get("routes")
    require(isinstance(routes, list), f"{label} routes must be an array")

    # Validate owner IDs against the exact SDK macro definitions instead of
    # assuming that a particular player (or map location) owns these routes.
    owner_header = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvDLLUtilDefines.h"
    require(owner_header.is_file(), "SDK player-count definition header is missing")
    owner_header_text = owner_header.read_text(encoding="utf-8")
    civ_match = re.search(r"^\s*#define\s+MAX_CIV_PLAYERS\s+\((\d+)\)\s*$", owner_header_text, re.M)
    total_match = re.search(r"^\s*#define\s+MAX_PLAYERS\s+\(MAX_CIV_PLAYERS\s*\+\s*(\d+)\)\s*$",
                            owner_header_text, re.M)
    require(civ_match is not None and total_match is not None,
            "SDK player-count macros no longer have the expected explicit numeric definitions")
    max_players = int(civ_match.group(1)) + int(total_match.group(1))

    expected_by_owner: dict[int, int] = {}
    sdk_rows = sdk_inventory["routes"]["outbound"] + sdk_inventory["routes"]["inbound"]
    for row in sdk_rows:
        owner = row["from_owner"]
        require(type(owner) is int and 0 <= owner < max_players,
                "Real SDK active route inventory has an invalid origin owner")
        expected_by_owner[owner] = expected_by_owner.get(owner, 0) + 1
    require(len(routes) >= len(sdk_rows) and sdk_rows,
            f"{label} has fewer live SDK route records than outbound plus inbound inventory")

    seen_indexes: set[int] = set()
    observed_by_owner: dict[int, int] = {}
    for route in routes:
        require(isinstance(route, dict) and set(route) ==
                {"index", "player", "type", "directionKnown", "forwards", "plots"},
                f"{label} route record does not match the exact callback-copy schema")
        index, owner, route_type = route.get("index"), route.get("player"), route.get("type")
        require(type(index) is int and index >= 0 and index not in seen_indexes,
                f"{label} contains an invalid, temporary, or duplicate SDK route index")
        require(type(owner) is int and 0 <= owner < max_players,
                f"{label} contains an invalid SDK player owner")
        require(type(route_type) is int and 0 <= route_type <= 2 and
                route.get("directionKnown") is True and type(route.get("forwards")) is bool,
                f"{label} does not retain a valid SDK type and known direction")
        plots = route.get("plots")
        require(isinstance(plots, list) and 1 <= len(plots) <= 256 and
                all(isinstance(point, list) and len(point) == 2 and
                    all(type(coord) is int and coord >= 0 for coord in point) for point in plots),
                f"{label} path must contain 1..256 nonnegative integer SDK plot coordinates")
        seen_indexes.add(index)
        observed_by_owner[owner] = observed_by_owner.get(owner, 0) + 1

    require(all(observed_by_owner.get(owner, 0) >= count
                for owner, count in expected_by_owner.items()),
            f"{label} route owners contradict the real outbound/inbound SDK inventory")
    return {"path": str(path), "sha256": digest(path), "schema": presentation["schema"],
            "source": presentation["source"], "world_route_rendering_implemented": False,
            "popup_route": None, "route_count": len(routes),
            "sdk_inventory_route_count": len(sdk_rows),
            "expected_route_counts_by_sdk_owner": expected_by_owner,
            "observed_route_counts_by_sdk_owner": observed_by_owner,
            "route_indexes_nonnegative_unique": True, "directions_known": True,
            "callback_paths_validated": True,
            "sdk_player_definitions": {"path": str(owner_header), "sha256": digest(owner_header),
                                       "max_civ_players": int(civ_match.group(1)),
                                       "max_players": max_players}}


def rows(pattern: str, output: str, label: str) -> list[tuple[str, ...]]:
    found = re.findall(pattern, output, re.M)
    require(found, f"Host stdout omits {label}")
    return found


def parse_trade_route_ui_frames(output: str) -> list[tuple[str, ...]]:
    """Parse the eight-field Host frame line, including its explicit context field."""
    pattern = (r"^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(trade-route)\|"
               r"(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$")
    return rows(pattern, output, "TradeRoute retained UI frames")


def snapshots_between_action_generations(snapshots: list[dict], lower: int, upper: int) -> list[dict]:
    """Select post-input retained frames up through the next action's target generation.

    Host actions record the generation used to post the input. A resulting frame
    may publish at the next generation, and the following action then targets
    that same generation; therefore the upper bound is inclusive.
    """
    require(type(lower) is int and type(upper) is int and lower < upper,
            "TradeRoute transition window has invalid action generations")
    return [proof for proof in snapshots
            if type(proof.get("generation")) is int and lower < proof["generation"] <= upper]


def walk(node: object):
    if not isinstance(node, dict):
        return
    yield node
    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            yield from walk(child)


def control_nodes(snapshot: dict, control_id: str) -> list[dict]:
    return [node for node in walk(snapshot.get("tree")) if
            (node.get("attributes", {}).get("ID") if isinstance(node.get("attributes"), dict)
             else node.get("id")) == control_id]


def validate_trade_route_tab_geometry_fixture(fixture: object) -> None:
    require(isinstance(fixture, dict) and fixture.get("columnHeadersDoNotOverlapTabs") is True,
            "TradeRoute component fixture does not prove column headers begin below all three tabs")


def validate_trade_route_scroll_target(scroll_targets: object, main_scroll: object) -> None:
    """Verify the full ScrollPanel record copied into TradeRoute snapshot metadata."""
    scroll_keys = {"key", "id", "event", "orientation", "bounds", "clippedBounds", "scrollY",
                   "contentHeight", "viewportHeight", "maximumScroll"}
    expected_keys = scroll_keys | {"visible", "disabled"}
    require(isinstance(scroll_targets, list) and len(scroll_targets) == 1 and
            isinstance(scroll_targets[0], dict) and set(scroll_targets[0]) == expected_keys and
            isinstance(main_scroll, dict) and set(main_scroll) == scroll_keys,
            "TradeRoute snapshot does not retain exactly the original MainScroll input target")
    target = scroll_targets[0]
    require(target.get("visible") is True and target.get("disabled") is False and
            all(target.get(key) == main_scroll.get(key) for key in scroll_keys) and
            target.get("id") == "MainScroll" and target.get("event") == "Scroll" and
            target.get("orientation") == "vertical",
            "TradeRoute native MainScroll target differs from its retained metadata geometry/state")


def verify_component() -> dict:
    result_path, snapshot_path = COMPONENT_RESULT, COMPONENT_SNAPSHOT
    result = load_json(result_path, "TradeRoute component result")
    snapshot = load_json(snapshot_path, "TradeRoute component snapshot")
    require(result.get("status") == "PASS_TRADE_ROUTE_ORIGINAL_LUA_COMPONENT_ONLY" and
            result.get("evidence_scope", "").startswith("mocked component") and
            result.get("verified", {}).get("retail_sdk_bindings_native_dispatch_renderer_pixels_live_game") is False,
            "TradeRoute fixture evidence is not the declared component-only PASS")
    validate_trade_route_tab_geometry_fixture(result.get("fixture"))
    source_hashes = result.get("original_source_sha256")
    require(isinstance(source_hashes, dict) and all(source_hashes.get(name) == expected
                                                   for name, expected in ORIGINAL_SOURCES.items()),
            "TradeRoute component report does not pin exact installed stock source hashes")
    impl = result.get("implementation_sha256", {})
    require(isinstance(impl, dict) and impl.get("fixture") == digest(FIXTURE),
            "TradeRoute component fixture source changed after its recorded verification")
    require(result.get("snapshot_sha256") == digest(snapshot_path) and
            snapshot.get("contextName") == "TradeRoute" and snapshot.get("popupKind") == "TradeRoute",
            "TradeRoute component snapshot identity/hash differs from its report")
    stock_paths = {
        "TradeRouteOverview.xml": render_ui_popup.GAME / "Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml",
        "TradeRouteOverview.lua": render_ui_popup.GAME / "Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua",
        "TradeRouteHelpers.lua": render_ui_popup.GAME / "Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua",
    }
    stock_proof = {}
    for name, expected_hash in ORIGINAL_SOURCES.items():
        path = stock_paths[name]
        require(path.is_file() and digest(path) == expected_hash,
                f"Installed stock source hash differs for {name}")
        stock_proof[name] = {"path": str(path), "sha256": expected_hash}
    return {"result": str(result_path), "result_sha256": digest(result_path),
            "snapshot": str(snapshot_path), "snapshot_sha256": digest(snapshot_path),
            "original_source_sha256": source_hashes,
            "installed_stock_sources": stock_proof,
            "fixture": str(FIXTURE), "fixture_sha256": digest(FIXTURE)}


def verify_trade_snapshot(path: Path, expected_player: int, expected_tab: str | None = None) -> dict:
    snapshot = load_json(path, "live TradeRoute UI snapshot")
    require(snapshot.get("active") is True and snapshot.get("hasRetainedPopupUi") is True and
            snapshot.get("contextName") == "TradeRoute" and snapshot.get("popupKind") == "TradeRoute" and
            snapshot.get("timerSemaphore") == 1 and snapshot.get("timerSemaphores", 1) == 1,
            "Live snapshot does not show the original modal TradeRoute context with its timer held")
    meta = snapshot.get("tradeRoute")
    require(isinstance(meta, dict) and meta.get("modal") is True and meta.get("timerSemaphore") == 1 and
            meta.get("rowTemplate") == "TRInstance" and meta.get("rowSelectionPresent") is False,
            "Live TradeRoute source/template/modal metadata is incomplete or invented")
    source_records = {
        "TradeRouteOverview.xml": meta.get("originalLayoutXml"),
        "TradeRouteOverview.lua": meta.get("originalLayoutLua"),
        "TradeRouteHelpers.lua": meta.get("originalHelpersLua"),
    }
    source_suffixes = {
        "TradeRouteOverview.xml": "/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml",
        "TradeRouteOverview.lua": "/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua",
        "TradeRouteHelpers.lua": "/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua",
    }
    require(all(isinstance(source_records[name], dict) and
                source_records[name].get("sha256", "").lower() == ORIGINAL_SOURCES[name] and
                source_records[name].get("path", "").replace("\\", "/").endswith(source_suffixes[name])
                for name in ORIGINAL_SOURCES),
            "Live TradeRoute snapshot does not preserve exact stock XML/Lua/helper provenance")
    if "activePlayer" in meta:
        require(meta["activePlayer"] == expected_player, "TradeRoute metadata player differs from actual SDK owner")
    selected_tab = meta.get("selectedTab")
    if expected_tab is not None:
        require(selected_tab == expected_tab, f"TradeRoute tab should be {expected_tab}, got {selected_tab!r}")
    stack = control_nodes(snapshot, "MainStack")
    require(len(stack) == 1, "Original MainStack is missing or duplicated")
    children = stack[0].get("children", [])
    require(isinstance(children, list), "Original MainStack child list is malformed")
    row_values = []
    for child in children:
        ids = {node.get("id") for node in walk(child)}
        if not ({"FromCity", "ToCity"} <= ids):
            continue
        from_nodes, to_nodes = control_nodes({"tree": child}, "FromCity"), control_nodes({"tree": child}, "ToCity")
        require(len(from_nodes) == len(to_nodes) == 1, "A live route row has duplicated or missing city labels")
        from_text, to_text = from_nodes[0].get("text"), to_nodes[0].get("text")
        require(isinstance(from_text, str) and from_text and isinstance(to_text, str) and to_text,
                "A live route row does not contain actual city labels")
        row_values.append({"from": from_text, "to": to_text})
    require(row_values, "Live TradeRoute tab has no retained route rows")
    targets = snapshot.get("inputTargets")
    require(isinstance(targets, list), "TradeRoute snapshot omits its native callback target inventory")
    require(len(targets) == len(REQUIRED_TARGETS) and all(isinstance(target, dict) and
            target.get("event") == "LeftClick" and target.get("visible") is True and
            target.get("disabled") is False for target in targets),
            "TradeRoute callback target metadata includes hidden, disabled, or non-stock entries")
    ids = [target.get("id") for target in targets]
    require(len(ids) == len(set(ids)) and set(ids) == REQUIRED_TARGETS,
            "Visible TradeRoute callback targets do not contain the exact stock three-tab/14-sort/close set")
    require(meta.get("visibleRowCount") == len(row_values),
            "TradeRoute visibleRowCount does not equal the retained original route rows")
    scroll_targets = snapshot.get("scrollTargets")
    scroll = meta.get("mainScroll")
    scroll_keys = {"key", "id", "event", "orientation", "bounds", "clippedBounds", "scrollY",
                   "contentHeight", "viewportHeight", "maximumScroll"}
    validate_trade_route_scroll_target(scroll_targets, scroll)
    require(isinstance(scroll, dict) and set(scroll) == scroll_keys and
            scroll.get("id") == "MainScroll" and scroll.get("event") == "Scroll" and
            scroll.get("orientation") == "vertical" and type(scroll.get("key")) is int and
            isinstance(scroll.get("bounds"), dict) and isinstance(scroll.get("clippedBounds"), dict) and
            all(type(scroll.get(key)) in (int, float) for key in
                ("scrollY", "contentHeight", "viewportHeight", "maximumScroll")) and
            scroll["maximumScroll"] == max(0, scroll["contentHeight"] - scroll["viewportHeight"]) and
            0 <= scroll["scrollY"] <= scroll["maximumScroll"],
            "Live MainScroll metadata lacks the exact stock vertical target and geometry")
    return {"path": str(path), "sha256": digest(path), "selected_tab": selected_tab,
            "rows": row_values, "input_target_ids": sorted(ids), "scroll": scroll}


def verify_trade_route_tab_caption_proof(snapshot: dict, manifest: dict) -> dict:
    """Bind the three original Button captions and separated headers to one retained frame."""
    tab_ids = set(TAB_TARGETS)
    tree = snapshot.get("tree")
    require(isinstance(tree, dict), "TradeRoute caption snapshot omits its retained tree")
    nodes = list(walk(tree))
    visible_ids: set[int] = set()

    def mark_visible(node: dict, parent_visible: bool = True) -> None:
        shown = parent_visible and node.get("hidden") is False
        if node.get("id") in tab_ids and shown:
            visible_ids.add(node.get("key"))
        for child in node.get("children", []):
            if isinstance(child, dict):
                mark_visible(child, shown)

    mark_visible(tree)
    tabs = [node for node in nodes if node.get("id") in tab_ids]
    require(len(tabs) == len(tab_ids) and {node.get("id") for node in tabs} == tab_ids,
            "TradeRoute snapshot omits or duplicates an original tab control")
    by_key = {}
    for node in tabs:
        key = node.get("key")
        require(type(key) is int and key > 0 and key not in by_key,
                "TradeRoute tab has a missing or duplicate retained key")
        by_key[key] = node

    labels_list = manifest.get("labels")
    geometry_list = manifest.get("geometry")
    require(type(labels_list) is list and type(geometry_list) is list,
            "TradeRoute frame manifest omits label or geometry evidence")
    labels = {}
    for row in labels_list:
        require(type(row) is dict and type(row.get("key")) is int and row["key"] not in labels,
                "TradeRoute frame manifest has malformed or duplicate label keys")
        labels[row["key"]] = row
    geometry: dict[int, list[dict]] = {}
    for row in geometry_list:
        require(type(row) is dict and type(row.get("key")) is int and
                isinstance(row.get("kind"), str) and isinstance(row.get("id"), str),
                "TradeRoute frame manifest has malformed geometry rows")
        geometry.setdefault(row["key"], []).append(row)

    targets_list = snapshot.get("inputTargets")
    require(type(targets_list) is list, "TradeRoute snapshot omits callback hit geometry")
    targets = {}
    for target in targets_list:
        require(type(target) is dict and type(target.get("key")) is int and
                target["key"] not in targets,
                "TradeRoute snapshot has malformed or duplicate callback targets")
        targets[target["key"]] = target

    def rect(value: object, what: str) -> tuple[float, float, float, float]:
        if type(value) is list and len(value) == 4:
            require(all(type(part) in (int, float) for part in value),
                    f"TradeRoute {what} bounds are missing or malformed")
            result = tuple(float(part) for part in value)
        else:
            require(type(value) is dict and all(type(value.get(name)) in (int, float)
                    for name in ("x", "y", "width", "height")),
                    f"TradeRoute {what} bounds are missing or malformed")
            result = tuple(float(value[name]) for name in ("x", "y", "width", "height"))
        require(result[2] > 0 and result[3] > 0,
                f"TradeRoute {what} bounds have no positive area")
        return result

    def contains(outer: tuple[float, float, float, float],
                 inner: tuple[float, float, float, float]) -> bool:
        return (inner[0] >= outer[0] and inner[1] >= outer[1] and
                inner[0] + inner[2] <= outer[0] + outer[2] and
                inner[1] + inner[3] <= outer[1] + outer[3])

    tab_bottoms = []
    proofs = []
    for control_id, node in sorted(((node["id"], node) for node in tabs)):
        key = node["key"]
        attrs, source = node.get("attributes"), node.get("sourceAttributes")
        require(key in visible_ids and type(attrs) is dict and type(source) is dict and
                attrs.get("ID") == control_id and source.get("ID") == control_id and
                isinstance(source.get("String"), str) and source["String"] and
                attrs.get("String") == source.get("String") and
                isinstance(node.get("text"), str) and node["text"].strip(),
                f"Original {control_id} Button identity or source caption is missing/changed")
        button = rect({name: node.get(name) for name in ("x", "y", "width", "height")},
                      f"{control_id} control")
        target, label = targets.get(key), labels.get(key)
        candidates = [row for row in geometry.get(key, [])
                      if row.get("kind") == "Button" and row.get("id") == control_id and
                      row.get("style_decoration") is False and row.get("input_target") is True]
        require(len(candidates) == 1,
                f"Original {control_id} has no unique non-decoration input-target Button geometry")
        geo = candidates[0]
        require(target is not None and target.get("id") == control_id and
                target.get("event") == "LeftClick" and target.get("visible") is True and
                target.get("disabled") is False,
                f"Original {control_id} callback target does not match its retained Button")
        target_bounds = rect(target.get("bounds"), f"{control_id} hit target")
        geo_bounds = geo.get("bounds") if geo is not None else None
        require(target_bounds == button and geo_bounds == list(button) and
                geo.get("input_target") is True,
                f"Original {control_id} hit geometry changed in the compiled frame")
        require(label is not None and label.get("text") == node["text"] and
                type(label.get("glyph_count")) is int and label["glyph_count"] > 0 and
                label.get("text_control") == "Button" and
                label.get("text_control_id") == control_id and
                label.get("retail_text_alignment_verified") is False,
                f"Original {control_id} Button caption has no compiled glyph proof")
        label_bounds = rect(label.get("bounds"), f"{control_id} caption")
        require(contains(button, label_bounds),
                f"Original {control_id} caption is clipped outside its button bounds")
        tab_bottoms.append(button[1] + button[3])
        proofs.append({"id": control_id, "key": key, "text": node["text"],
                       "source_string": source["String"], "glyph_count": label["glyph_count"],
                       "button_bounds": list(button), "caption_bounds": list(label_bounds),
                       "hit_geometry_unchanged": True})

    header_ids = {"Domain", "FromOwnerHeader", "FromCityHeader", "ToOwnerHeader", "ToCityHeader",
                  "FromGPT", "ToGPT", "ToFood", "ToProduction", "FromReligion", "ToReligion",
                  "FromScience", "ToScience", "TurnsLeft"}
    headers = [node for node in nodes if node.get("id") in header_ids and
               node.get("kind") == "Button"]
    require(len(headers) == 14 and {node.get("id") for node in headers} == header_ids,
            "TradeRoute snapshot omits or duplicates an original sortable header Button")
    header_bounds = [rect({name: node.get(name) for name in ("x", "y", "width", "height")},
                          f"{node['id']} header") for node in headers]
    require(all(bounds[1] >= max(tab_bottoms) for bounds in header_bounds),
            "TradeRoute column header geometry overlaps the original tab row")
    scene = manifest.get("trade_route_scene")
    require(type(scene) is dict and scene.get("retail_pixels_verified") is False and
            manifest.get("retail_pixel_equivalence_verified", False) is False,
            "TradeRoute caption proof must retain the renderer's explicit non-retail-pixel boundary")
    return {"captions": proofs, "header_top_y": min(bounds[1] for bounds in header_bounds),
            "tab_bottom_y": max(tab_bottoms), "headers_below_tabs": True,
            "retail_pixel_equivalence_verified": False}


def parse_from_gpt_display(text: object, raw_hundredths: int) -> float:
    """Parse stock #.# display text and bind it to the SDK's hundredths value."""
    require(isinstance(text, str), "Original FromGPT label is not text")
    if not text.strip():
        require(raw_hundredths == 0, "Blank FromGPT label disagrees with its nonzero SDK scalar")
        return 0.0
    match = re.fullmatch(r"\s*([+-]?\d+(?:[.,]\d)?)\s*", text)
    require(match is not None, f"Original FromGPT display is not one localized number: {text!r}")
    displayed = float(match.group(1).replace(",", "."))
    raw_value = raw_hundredths / 100.0
    # The stock localization key is `{1_Num: number #.#}`. It rounds the
    # hundredths SDK scalar to one displayed decimal place; permit half a tenth.
    require(abs(displayed - raw_value) <= 0.0500001,
            f"Displayed FromGPT {displayed} does not represent SDK hundredths {raw_hundredths}")
    return displayed


def verify_wheel_result(maximum_scroll: object, before: dict,
                        after: dict | None, consumed: bool) -> str:
    """Verify Lua's ScrollPanel dispatch, which consumes valid input even at a boundary."""
    require(type(maximum_scroll) in (int, float) and maximum_scroll >= 0,
            "MainScroll maximumScroll is not a nonnegative number")
    require(isinstance(before, dict) and before.get("maximumScroll") == maximum_scroll,
            "AvailableTR scroll range changed across the wheel boundary proof")
    if maximum_scroll == 0:
        require(consumed,
                "TradeRoute ScrollPanel did not consume valid wheel input with no overflow")
        if after is not None:
            require(after.get("maximumScroll") == 0 and after.get("scrollY") == before.get("scrollY"),
                    "Non-overflowing MainScroll changed its offset after consumed wheel input")
        return "consumed_without_overflow"

    require(consumed,
            "TradeRoute wheel input was not consumed despite MainScroll content overflow")
    require(isinstance(after, dict),
            "TradeRoute had scrollable content but emitted no post-wheel AvailableTR frame")
    require(after.get("maximumScroll") == maximum_scroll,
            "AvailableTR scroll range changed across the wheel dispatch")
    before_y = before.get("scrollY")
    after_y = after.get("scrollY")
    require(type(before_y) in (int, float) and type(after_y) in (int, float),
            "MainScroll frame has invalid scrollY geometry")
    if after_y != before_y:
        return "moved"
    at_top = before_y <= 0
    at_bottom = before_y >= maximum_scroll
    require(at_top or at_bottom,
            "Wheel event did not move content despite remaining scroll range away from a boundary")
    return "already_at_top_boundary" if at_top else "already_at_bottom_boundary"


def verify_trade_route_dispatches(decoded_inputs: list[dict], action_by_stage: dict,
                                  wheel_key: int) -> None:
    """Compare native UiInputKind records to the requested original controls/actions."""
    expected = [
        (2, action_by_stage[2]["value"], 0.0),
        (2, action_by_stage[3]["value"], 0.0),
        (2, action_by_stage[4]["value"], 0.0),
        (4, wheel_key, 48.0),
        (2, action_by_stage[6]["value"], 0.0),
        (2, action_by_stage[7]["value"], 0.0),
        (1, 13, 0.0),
        (2, action_by_stage[9]["value"], 0.0),
        (1, 27, 0.0),
    ]
    observed = [(event["kind"], event["key"], event["delta"]) for event in decoded_inputs]
    require(observed == expected,
            "Native dispatch kind/key/delta differs from requested TradeRoute callback, wheel, Return, Close, or Escape")
    require(all(event["consumed"] for event in decoded_inputs) and
            all(event["active"] and event["timer_held"] for event in decoded_inputs[:7]) and
            all(not event["active"] and not event["timer_held"] for event in decoded_inputs[7:]),
            "TradeRoute input consumption or modal timer lifecycle differs across callback, close, and Escape stages")


def verify_from_gpt_rows(snapshot_proof: dict, sdk_routes: list[dict], ascending: bool) -> dict:
    """Tie every visible YourTR row to its SDK route and verify both scalar orders."""
    snap = load_json(Path(snapshot_proof["path"]), "FromGPT sorted snapshot")
    stacks = control_nodes(snap, "MainStack")
    require(len(stacks) == 1, "FromGPT sort snapshot has no unique original MainStack")
    rendered = []
    for row in stacks[0].get("children", []):
        from_nodes = control_nodes({"tree": row}, "FromCity")
        to_nodes = control_nodes({"tree": row}, "ToCity")
        if not from_nodes and not to_nodes:
            continue
        require(len(from_nodes) == len(to_nodes) == 1,
                "A FromGPT sort row has duplicated or missing city labels")
        from_name, to_name = from_nodes[0].get("text"), to_nodes[0].get("text")
        require(isinstance(from_name, str) and from_name and isinstance(to_name, str) and to_name,
                "A FromGPT sort row has an empty city name")
        matches = [route for route in sdk_routes
                   if route.get("from") == from_name and route.get("to") == to_name]
        require(len(matches) == 1,
                f"Visible route {from_name!r} -> {to_name!r} does not identify one SDK route")
        route = matches[0]
        from_gpt = control_nodes({"tree": row}, "FromGPT")
        to_gpt = control_nodes({"tree": row}, "ToGPT")
        require(len(from_gpt) == len(to_gpt) == 1,
                "A FromGPT sort row has duplicated or missing original yield labels")
        raw = route.get("from_gpt")
        require(type(raw) is int, "SDK route FromGPT scalar is not an integer hundredths value")
        displayed = parse_from_gpt_display(from_gpt[0].get("text"), raw)
        rendered.append({"from": from_name, "to": to_name,
                         "from_owner": route["from_owner"], "to_owner": route["to_owner"],
                         "from_city_id": route["from_city_id"], "to_city_id": route["to_city_id"],
                         "sdk_from_gpt_hundredths": raw, "sdk_from_gpt": raw / 100.0,
                         "displayed_from_gpt_text": from_gpt[0].get("text"),
                         "displayed_from_gpt": displayed})
    route_pairs = [(route.get("from"), route.get("to")) for route in sdk_routes]
    rendered_pairs = [(row["from"], row["to"]) for row in rendered]
    require(len(rendered) == len(sdk_routes) and len(set(rendered_pairs)) == len(rendered_pairs) and
            set(rendered_pairs) == set(route_pairs),
            "Displayed FromGPT rows do not map one-to-one onto the outbound SDK inventory")
    raw_values = [row["sdk_from_gpt_hundredths"] for row in rendered]
    displayed_values = [row["displayed_from_gpt"] for row in rendered]
    expected_raw = sorted(raw_values, reverse=not ascending)
    expected_displayed = sorted(displayed_values, reverse=not ascending)
    direction = "ascending" if ascending else "descending"
    require(raw_values == expected_raw,
            f"Original SDK FromGPT hundredths are not {direction}: {raw_values}")
    require(displayed_values == expected_displayed,
            f"Original displayed FromGPT values are not {direction}: {displayed_values}")
    return {"direction": direction, "rows": rendered,
            "sdk_raw_hundredths_monotonic": True, "displayed_values_monotonic": True,
            "displayed_values": displayed_values, "sdk_raw_hundredths": raw_values,
            "distinct_displayed_values": len(set(displayed_values)),
            "strict_reordering_claimed": False}


def sdk_state_identity(data: bytes, label: str) -> tuple[int, int, int, int]:
    try:
        fields = data.decode("utf-8", errors="strict").splitlines()[0].split("|")
        require(len(fields) == 5 and fields[0] == "G", f"{label} lacks the SDK Game identity row")
        turn, elapsed, active, plots = map(int, fields[1:])
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise VerificationError(f"{label} has a malformed SDK Game identity row") from exc
    require(turn >= 0 and elapsed >= 0 and 0 <= active < 64 and plots > 0,
            f"{label} SDK Game identity is outside its limits")
    return turn, elapsed, active, plots


def verified_runtime_bundle(request: dict, runtime: Path, label: str) -> tuple[Path, Path, dict[str, dict]]:
    """Verify the complete immutable runtime input set and its constructed bundle manifest."""
    inputs = request.get("runtime_inputs")
    require(isinstance(inputs, list) and inputs,
            f"{label} request omits runtime inputs")
    by_name: dict[str, dict] = {}
    for row in inputs:
        require(isinstance(row, dict) and isinstance(row.get("path"), str),
                f"{label} runtime input row is malformed")
        path = artifact_ref(row, label=f"{label} runtime input")
        require(path.parent == runtime.resolve(strict=True) and path.is_relative_to(runtime.resolve(strict=True)),
                f"{label} runtime input escaped its private directory")
        require(path.name not in by_name, f"{label} runtime input inventory duplicates {path.name}")
        by_name[path.name] = row
    require("ZeroSisHost_x64.exe" in by_name and "bundle.manifest" in by_name,
            f"{label} runtime does not pin both Host and bundle manifest")
    manifest = runtime / "bundle.manifest"
    expected = "ZEROSIS_HOST_BUNDLE_V4\n" + "".join(
        f"{name}|{row['sha256']}\n" for name, row in by_name.items() if name != "bundle.manifest")
    try:
        actual = manifest.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise VerificationError(f"{label} bundle manifest is unreadable") from exc
    require(actual == expected, f"{label} bundle manifest differs from its runtime input hashes")
    return Path(by_name["ZeroSisHost_x64.exe"]["path"]).resolve(strict=True), manifest.resolve(strict=True), by_name


def verify_resume_lineage(run_id: str, request: dict, result: dict, output: str,
                          run_evidence: Path, runtime: Path, build: dict,
                          build_path: Path, host_path: Path, attempt: dict,
                          current_generated: dict[str, list[Path]],
                          source_chain: frozenset[str] = frozenset()) -> dict:
    """Independently bind a resumed TradeRoute run to its accepted source checkpoint."""
    resume = request.get("resume_from")
    require(isinstance(resume, dict), "Resumed TradeRoute request lacks checkpoint lineage")
    source_id = resume.get("run_id")
    require(isinstance(source_id, str) and RUN_ID.fullmatch(source_id) is not None and source_id != run_id,
            "TradeRoute checkpoint source ID is invalid or self-referential")
    require(source_id not in source_chain,
            "TradeRoute checkpoint lineage contains a cycle")
    require(result.get("resume_from_run") == source_id and
            result.get("checkpoint_input_unchanged") is True and
            result.get("semantic_restore_equal") is True and
            result.get("fresh_process_restore_verified") is True,
            "Runner did not report the exact resumed source and successful checkpoint checks")

    source_evidence = EVIDENCE / source_id
    source_request_path = source_evidence / "request.json"
    source_result_path = source_evidence / "result.json"
    source_request = load_json(source_request_path, "TradeRoute checkpoint source request")
    source_result = load_json(source_result_path, "TradeRoute checkpoint source result")
    require(source_request.get("run_id") == source_result.get("run_id") == source_id and
            source_request.get("trade_route_smoke") is True and
            source_result.get("trade_route_requested") is True,
            "Checkpoint source is not the identified TradeRoute smoke run")
    check_artifacts(source_request)
    check_artifacts(source_result)
    source_proof = verify_run(source_id, _resume_chain=source_chain | {run_id})
    require(source_proof.get("status") == "PASS_INTERACTIVE_TRADE_ROUTE_NATIVE_SDK_SMOKE",
            "Checkpoint source did not independently pass the actual TradeRoute verifier")

    frozen_source_result = artifact_ref(
        resume.get("run_result"), exact=run_evidence / "resume-source-result.json",
        label="frozen TradeRoute source result")
    require(frozen_source_result.read_bytes() == source_result_path.read_bytes() and
            digest(frozen_source_result) == digest(source_result_path),
            "Frozen source result does not byte-match the selected source run")
    source_result_request = artifact_ref(source_result.get("request"), exact=source_request_path,
                                         label="checkpoint source request reference")
    require(source_result_request.read_bytes() == source_request_path.read_bytes(),
            "Checkpoint source result points to different request bytes")

    source_runtime = (RUNTIME_ROOT / source_id).resolve(strict=True)
    require(Path(source_request.get("cwd", "")).resolve(strict=True) == source_runtime and
            source_request.get("run_id") == source_id and
            runtime.resolve(strict=True) == (RUNTIME_ROOT / run_id).resolve(strict=True) and
            source_runtime != runtime.resolve(strict=True),
            "Checkpoint and resumed Host processes do not use distinct exact private runtimes")
    source_build_path = artifact_ref(source_request.get("provenance", {}).get("host_build"),
                                     label="checkpoint source Host build report")
    # Each run freezes its own evidence copy of the build report. Bind the
    # source copy by verified bytes, not by pathname: identical report content
    # at the source/current run evidence roots is the same pinned build.
    require(digest(source_build_path) == digest(build_path) and
            source_result.get("status", "").endswith("PASS") and
            source_result.get("returncode") == 0 and source_result.get("timed_out") is False and
            source_result.get("runtime_inputs_unchanged") is True,
            "Checkpoint source does not use the same successful sealed Host build")
    source_host_path, source_manifest_path, source_inputs = verified_runtime_bundle(
        source_request, source_runtime, "Checkpoint source")
    current_host_path, current_manifest_path, current_inputs = verified_runtime_bundle(
        request, runtime, "Resumed TradeRoute")
    host_sha = build.get("executable", {}).get("sha256")
    require(source_host_path == (source_runtime / "ZeroSisHost_x64.exe").resolve(strict=True) and
            current_host_path == host_path.resolve(strict=True) and
            digest(source_host_path) == digest(current_host_path) == host_sha and
            digest(source_manifest_path) == digest(current_manifest_path),
            "Checkpoint and resumed runtimes do not pin the same Host bytes and bundle manifest")

    source_attempt_path = artifact_ref(source_result.get("attempt"),
                                       exact=source_evidence / "attempt.json",
                                       label="checkpoint source Host attempt")
    source_attempt = load_json(source_attempt_path, "checkpoint source Host attempt")
    require(source_attempt.get("status") == "FINISHED" and source_attempt.get("returncode") == 0 and
            source_attempt.get("timed_out") is False and
            source_attempt.get("pid") == source_result.get("driver_pid"),
            "Checkpoint source Host process lacks a finished distinct attempt record")
    require(type(source_result.get("pid")) is int and type(result.get("pid")) is int and
            type(source_result.get("driver_pid")) is int and type(result.get("driver_pid")) is int and
            source_result["pid"] != result["pid"] and
            source_result["driver_pid"] != result["driver_pid"] and
            attempt.get("pid") == result.get("driver_pid") and
            attempt.get("pid") != source_attempt.get("pid"),
            "Checkpoint source and resume are not distinct Host/driver processes")

    source_output_path = artifact_ref(source_result.get("stdout"), exact=source_evidence / "stdout.log",
                                      label="checkpoint source Host stdout")
    source_output = source_output_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    source_saves = rows(r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$", source_output,
                        "checkpoint source native saves")
    source_turns = rows(r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$", source_output,
                        "checkpoint source final human turn")
    require(len(source_saves) >= 2 and len(source_turns) == 1 and
            source_result.get("native_saves") == [list(row) for row in source_saves] and
            source_result.get("next_human_turn") == [list(source_turns[0])] and
            int(source_saves[-1][0]) == int(source_turns[0][0]),
            "Checkpoint source raw save/turn logs differ from its result or final turn")
    source_generated, _ = generated_map(source_result, source_runtime)
    source_save_path = Path(source_saves[-1][1]).resolve(strict=True)
    source_state_path = source_save_path.parent / "play-final-state.txt"
    checkpoint_source = artifact_ref(resume.get("checkpoint_source"), exact=source_save_path,
                                     label="source native checkpoint")
    checkpoint_source_state = artifact_ref(
        resume.get("checkpoint_source_state"), exact=source_state_path,
        label="source final semantic state")
    require(source_save_path in source_generated.get(source_save_path.name, []) and
            source_state_path in source_generated.get("play-final-state.txt", []) and
            checkpoint_source_state.parent == checkpoint_source.parent and
            digest(checkpoint_source) == digest(source_save_path) == resume["checkpoint_source"].get("sha256") and
            digest(checkpoint_source_state) == resume["checkpoint_source_state"].get("sha256"),
            "Checkpoint save/state are not hash-verified artifacts from the source save session")

    checkpoint_input = artifact_ref(resume.get("checkpoint_input"),
                                    exact=runtime / "checkpoint-input.zssave",
                                    label="private copied checkpoint input")
    expected_state = artifact_ref(resume.get("expected_state"),
                                  exact=run_evidence / "checkpoint-state.txt",
                                  label="frozen expected checkpoint state")
    require(digest(checkpoint_input) == digest(checkpoint_source) ==
            resume["checkpoint_input"].get("sha256") and
            expected_state.read_bytes() == checkpoint_source_state.read_bytes() and
            digest(expected_state) == resume["expected_state"].get("sha256"),
            "Private checkpoint input or expected state differs from the source save/session")
    source_identity = sdk_state_identity(checkpoint_source_state.read_bytes(), "Source final state")
    require(source_identity[0] == int(source_saves[-1][0]) == resume.get("turn"),
            "Source checkpoint turn differs between state, save marker, and resume request")

    initial_state = unique_generated(current_generated, "play-initial-state.txt")
    roundtrip_save = unique_generated(current_generated, "play-restored-checkpoint.zssave")
    require(initial_state.read_bytes() == expected_state.read_bytes() == checkpoint_source_state.read_bytes(),
            "Resumed process initial SDK state is not byte-identical to the checkpoint session")
    require(digest(checkpoint_input) == resume["checkpoint_input"].get("sha256"),
            "Copied checkpoint input changed after runner publication")

    restore_path_rows = rows(r"^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$", output,
                             "native restore checkpoint path")
    restore_identity = rows(r"^INTERACTIVE_RESTORE_IDENTITY=(\d+)\|(\d+)\|(\d+)\|(\d+)$",
                            output, "native restore identity")
    sections_equal = rows(r"^INTERACTIVE_RESTORE_SECTIONS_EQUAL=(\d+)\|(\d+)$",
                          output, "native restore section comparison")
    changed_pattern = r"^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$"
    changed_rows = [tuple(row) for row in re.findall(changed_pattern, output, re.M)]
    changed_marker_lines = [line for line in output.splitlines()
                            if line.startswith("INTERACTIVE_RESTORE_SECTION_CHANGED=")]
    idle = rows(r"^INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=(true)$", output,
                "restored idle-state check")
    identity = source_identity
    require(restore_path_rows == [str(checkpoint_input)] and
            len(restore_identity) == len(sections_equal) == len(idle) == 1 and
            tuple(map(int, restore_identity[0])) == (*identity[:3], 133) and idle == ["true"],
            "Raw native restore markers do not identify this checkpoint and unchanged startup state")
    require(len(changed_marker_lines) == len(changed_rows),
            "Native restore section-change marker is malformed")

    manifest_path = current_manifest_path
    source_db = source_save_path.parent / "Civ5SavedGameDatabase.db"
    current_db = initial_state.parent / "Civ5SavedGameDatabase.db"
    source_inventory = {path.resolve(strict=True) for paths in source_generated.values() for path in paths}
    current_inventory = {path.resolve(strict=True) for paths in current_generated.values() for path in paths}
    require(source_db.resolve(strict=True) in source_inventory and current_db.resolve(strict=True) in current_inventory,
            "Checkpoint source or resumed session omits its generated embedded SDK database")
    archive_expected = (1, 0, identity[0], identity[1], identity[2], 64, 64, 133)
    source_archive = inspect_save(source_save_path, source_manifest_path, source_db,
                                  expected=archive_expected)
    map_dimensions = source_archive.get("sdk_map_dimensions")
    require(isinstance(map_dimensions, list) and len(map_dimensions) == 2 and
            all(type(value) is int and value > 0 for value in map_dimensions),
            "Source checkpoint lacks independently inspected SDK map dimensions")
    source_start_rows = rows(
        r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$",
        source_output, "checkpoint source SDK startup")
    start_rows = rows(r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$",
                      output, "restored SDK startup")
    require(len(source_start_rows) == len(start_rows) == 1 and
            tuple(map(int, source_start_rows[0][2:])) == tuple(map_dimensions) and
            tuple(map(int, start_rows[0])) == (identity[0], identity[2], *map_dimensions),
            "Restored Host startup differs from checkpoint state or inspected SDK map dimensions")

    copied_archive = inspect_save(checkpoint_input, manifest_path, source_db,
                                  expected=archive_expected)
    roundtrip_archive = inspect_save(roundtrip_save, manifest_path, current_db,
                                     expected=archive_expected)
    source_sections = {(row["kind"], row["index"]): row["sha256"] for row in source_archive["sections"]}
    copied_sections = {(row["kind"], row["index"]): row["sha256"] for row in copied_archive["sections"]}
    roundtrip_sections = {(row["kind"], row["index"]): row["sha256"] for row in roundtrip_archive["sections"]}
    require(len(source_sections) == len(copied_sections) == len(roundtrip_sections) == 133 and
            source_sections == copied_sections and source_sections.keys() == roundtrip_sections.keys(),
            "Checkpoint archive section identities or copied archive bytes differ")
    changed_sections = sorted(key for key in source_sections if source_sections[key] != roundtrip_sections[key])
    require(all(key == (3, 0) for key in changed_sections),
            "Restore roundtrip changed a native save section outside the SDK Game reload section")
    equal_count = 133 - len(changed_sections)
    require(sections_equal == [(str(equal_count), "133")] and
            [tuple(map(int, row)) for row in changed_rows] == changed_sections,
            "Native restore section markers differ from independent source/roundtrip archive comparison")

    next_turn_rows = rows(r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$", output,
                          "post-restore human turn")
    require(len(next_turn_rows) == 1 and int(next_turn_rows[0][0]) == identity[0] + 1 and
            result.get("next_human_turn") == [list(next_turn_rows[0]),],
            "Resumed TradeRoute process did not reach exactly the next human turn")
    final_state = unique_generated(current_generated, "play-final-state.txt")
    final_identity = sdk_state_identity(final_state.read_bytes(), "Resumed final state")
    require(final_identity[0] == int(next_turn_rows[0][0]) and final_identity[2] == identity[2],
            "Resumed final SDK state does not retain its actual next-turn identity")
    save_rows = rows(r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$", output,
                     "post-restore native resaves")
    require(len(save_rows) >= 2 and result.get("native_saves") == [list(row) for row in save_rows] and
            all(int(row[0]) == final_identity[0] for row in save_rows),
            "Resumed run did not record repeated native saves at its actual next turn")
    resaved_archives = []
    for turn_text, path_text in save_rows:
        save_path = Path(path_text).resolve(strict=True)
        require(save_path in current_inventory,
                "Post-restore native save is absent from the current generated-file inventory")
        resaved = inspect_save(
            save_path, manifest_path, save_path.parent / "Civ5SavedGameDatabase.db",
            expected=(1, 0, final_identity[0], final_identity[1], final_identity[2], 64, 64, 133))
        require(resaved.get("sdk_map_dimensions") == map_dimensions,
                "Post-restore SDK save map dimensions differ from the source checkpoint")
        resaved_archives.append(resaved)

    return {
        "source_run_id": source_id,
        "source_trade_route_status": source_proof["status"],
        "source_result": {"path": str(source_result_path), "sha256": digest(source_result_path)},
        "frozen_source_result": {"path": str(frozen_source_result), "sha256": digest(frozen_source_result)},
        "source_runtime": str(source_runtime), "resumed_runtime": str(runtime.resolve(strict=True)),
        "source_host_sha256": digest(source_host_path), "resumed_host_sha256": digest(current_host_path),
        "source_bundle_manifest_sha256": digest(source_manifest_path),
        "resumed_bundle_manifest_sha256": digest(current_manifest_path),
        "source_pid": source_result["pid"], "resumed_pid": result["pid"],
        "source_driver_pid": source_result["driver_pid"], "resumed_driver_pid": result["driver_pid"],
        "checkpoint_source": {"path": str(checkpoint_source), "sha256": digest(checkpoint_source)},
        "checkpoint_input": {"path": str(checkpoint_input), "sha256": digest(checkpoint_input)},
        "source_state": {"path": str(checkpoint_source_state), "sha256": digest(checkpoint_source_state)},
        "expected_state": {"path": str(expected_state), "sha256": digest(expected_state)},
        "initial_state": {"path": str(initial_state), "sha256": digest(initial_state)},
        "restore_identity": list(identity), "restore_sections_equal": equal_count,
        "restore_section_changes": [list(row) for row in changed_sections],
        "source_archive": source_archive, "copied_archive": copied_archive,
        "restore_roundtrip_archive": roundtrip_archive,
        "resaved_archives": resaved_archives,
        "post_restore_turn": final_identity[0], "startup_state_byte_equal": True,
        "native_reload_delta_limited_to_game_section": True,
        "sdk_game_reload_metadata_semantics_verified": False,
        "limitations": [
            "The Game section is compared byte-for-byte only; a permitted (3,0) delta is not independently parsed as reload metadata or RNG equivalence."
        ],
    }


def verify_run(run_id: str, _resume_chain: frozenset[str] = frozenset()) -> dict:
    require(RUN_ID.fullmatch(run_id) is not None, "Run ID is not an immutable timestamp/hash identity")
    require(run_id not in _resume_chain, "TradeRoute checkpoint lineage contains a cycle")
    run_evidence = EVIDENCE / run_id
    request_path, result_path = run_evidence / "request.json", run_evidence / "result.json"
    request, result = load_json(request_path, "TradeRoute request"), load_json(result_path, "TradeRoute result")
    require(request.get("run_id") == result.get("run_id") == run_id, "Request/result/run identity differs")
    check_artifacts(request)
    check_artifacts(result)
    artifact_ref(result.get("request"), exact=request_path, label="immutable run request")
    stdout_path = artifact_ref(result.get("stdout"), exact=run_evidence / "stdout.log", label="Host stdout")
    stderr_path = artifact_ref(result.get("stderr"), exact=run_evidence / "stderr.log", label="Host stderr")
    output = stdout_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    require(request.get("trade_route_smoke") is True and request.get("smoke") is True and
            request.get("decisions") is True and request.get("research_tree") is True and
            request.get("top_panel") is True and
            request.get("stage_or_mods_changed") is False,
            "Request is not the isolated TradeRoute + decisions + research-tree smoke profile")
    require(result.get("returncode") == 0 and result.get("timed_out") is False and
            result.get("runtime_inputs_unchanged") is True and result.get("failures") == [] and
            result.get("trade_route_sequence_verified") is True and result.get("status", "").endswith("PASS"),
            "Host/driver result is not a clean TradeRoute smoke PASS")
    require(not re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED",
                          output + "\n" + stderr), "Host/native/input failure marker is present")
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    require(runtime == (RUNTIME_ROOT / run_id).resolve(strict=True),
            "Request cwd is not the exact run-private runtime")
    host_rows = [row for row in request.get("runtime_inputs", [])
                 if isinstance(row, dict) and Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
    require(len(host_rows) == 1, "Request does not pin one exact x64 Host input")
    host_path = artifact_ref(host_rows[0], exact=runtime / "ZeroSisHost_x64.exe", label="runtime Host")
    for row in request.get("runtime_inputs", []):
        require(isinstance(row, dict), "Runtime input inventory contains a malformed entry")
        path = artifact_ref(row, label="runtime input")
        require(path.is_relative_to(runtime) and digest(path) == row.get("sha256"),
                f"Runtime input changed or escaped its immutable private runtime: {path.name}")
    build_ref = request.get("provenance", {}).get("host_build")
    build_path = artifact_ref(build_ref, label="Host build report")
    build = load_json(build_path, "Host build report")
    build_id = build.get("build_id")
    require(isinstance(build_id, str) and RUN_ID.fullmatch(build_id) is not None,
            "Host build report lacks its immutable build identity")
    build_root = (PROJECT / "Build/UiWindowHost" / build_id).resolve(strict=True)
    expected_executable = (build_root / "final/ZeroSisHost_x64.exe").resolve(strict=True)
    built_executable = build.get("executable", {})
    require(isinstance(built_executable, dict) and
            Path(built_executable.get("path", "")).resolve(strict=True) == expected_executable,
            "Host build executable does not belong to the exact recorded build root")
    require(build.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            build.get("source_inputs_unchanged") is True and
            digest(host_path) == host_rows[0].get("sha256") == build.get("executable", {}).get("sha256"),
            "Runtime Host does not match its pinned successful build report")
    sources = {Path(row.get("path", "")).name: row for row in build.get("sources", [])
               if isinstance(row, dict) and isinstance(row.get("path"), str)}
    require({"InteractiveGameLoop.h", "UiPopupContext.h", "UiScene.lua", "TradeRouteSmokeFixture.h",
             "TradeRoutePresentation.h"} <= sources.keys(),
            "Host build source closure omits TradeRoute integration sources")
    source_proof = {}
    for name in HOST_SOURCE_NAMES:
        path = compiled_host_source(build_id, name, sources[name])
        text = path.read_text(encoding="utf-8")
        validate_compiled_host_source_contract(name, text)
        source_proof[name] = {"path": str(path), "sha256": digest(path)}
    source_proof.update(frozen_native_input_sources(build_id, sources))
    require(digest(host_path) == host_rows[0].get("sha256"), "Runtime Host hash changed after result publication")
    attempt_path = artifact_ref(result.get("attempt"), exact=run_evidence / "attempt.json", label="Host attempt")
    attempt = load_json(attempt_path, "Host attempt")
    require(attempt.get("status") == "FINISHED" and attempt.get("returncode") == 0 and
            attempt.get("timed_out") is False and attempt.get("pid") == result.get("driver_pid", result.get("pid")),
            "Host process did not terminate cleanly under the recorded process identity")
    generated, generated_paths = generated_map(result, runtime)
    frozen_support = verify_frozen_support(request, run_evidence, runtime)

    shown = rows(r"^INTERACTIVE_TRADE_ROUTE_SHOWN=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|1$",
                 output, "original TradeRoute shown marker")
    require(len(shown) == 2, "TradeRoute popup must be shown exactly once initially and once after CloseButton")
    shown_values = [tuple(map(int, row)) for row in shown]
    require(shown_values[0] == shown_values[1], "TradeRoute reopen changed owner, popup data, or SDK turn")
    owner, data1, data2, turn = shown_values[0]
    require(data1 == -1 and data2 == -1, "Original TradeRoute popup data did not preserve -1/-1 defaults")
    start = rows(r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|", output, "actual GameCore startup marker")
    require(len(start) == 1 and int(start[0][1]) == owner,
            "Shown TradeRoute owner differs from actual SDK startup state")
    startup_turn = int(start[0][0])
    resumed = isinstance(request.get("resume_from"), dict)
    require(resumed or startup_turn == 0,
            "Fresh TradeRoute source run did not begin at the initial SDK turn")
    expected_turn = startup_turn if resumed else startup_turn + 1
    require(turn == expected_turn and
            result.get("fresh_process_restore_verified") is resumed,
            "TradeRoute turn does not follow the fresh-AI-turn or restored-startup contract")
    resume_lineage = verify_resume_lineage(
        run_id, request, result, output, run_evidence, runtime, build, build_path,
        host_path, attempt, generated, _resume_chain | {run_id}) if resumed else None

    action_rx = r"^INTERACTIVE_TRADE_ROUTE_ACTION=(\d+)\|([^|\r\n]+)\|(-?\d+)\|(\d+)\|(\d+)$"
    action_matches = [tuple(row) for row in re.findall(action_rx, output, re.M)]
    require([(int(a[0]), a[1]) for a in action_matches] == [(s, name) for s, name, _ in EXPECTED_ACTIONS],
            "Posted TradeRoute actions do not match the exact required stage/target order")
    actions = []
    for row, (_, expected_name, mode) in zip(action_matches, EXPECTED_ACTIONS):
        stage, name, value, generation, revision = row
        numeric = int(value)
        if mode == "control":
            require(numeric > 0, f"TradeRoute action {name} has no original control key")
        else:
            expected_vk = 13 if name == "KEY_RETURN" else 27
            require(numeric == expected_vk, f"TradeRoute {name} did not post its exact native virtual key")
        actions.append({"stage": int(stage), "id": name, "value": numeric,
                        "generation": int(generation), "ui_revision": int(revision)})
    action_by_stage = {row["stage"]: row for row in actions}
    require([row["generation"] for row in actions] == sorted(row["generation"] for row in actions) and
            [row["ui_revision"] for row in actions] == sorted(row["ui_revision"] for row in actions),
            "TradeRoute posted actions do not follow increasing retained scene generations/revisions")
    button_posts = [tuple(map(int, row)) for row in re.findall(
        r"^INTERACTIVE_SMOKE_BUTTON=(\d+)\|(\d+)\|(\d+)\|(\d+)$", output, re.M)]
    hwnd_posts = [(int(row[0]), int(row[1])) for row in re.findall(
        r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$", output, re.M)]
    for stage in (1, 2, 3, 4, 6, 7, 9, 10):
        action = action_by_stage[stage]
        button_match = [row for row in button_posts if row == (action["generation"], action["value"], 1, 0)]
        post_match = [row for row in hwnd_posts if row == (action["generation"], action["value"])]
        require(len(button_match) == len(post_match) == 1,
                f"TradeRoute stage {stage} original {action['id']} target was not posted to its recorded HWND frame")
    top_panel_inputs = [tuple(map(int, row)) for row in re.findall(
        r"^INTERACTIVE_TOP_PANEL_INPUT=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$", output, re.M)]
    for stage in (1, 10):
        action = action_by_stage[stage]
        matching = [row for row in top_panel_inputs if row[0] == action["generation"] and
                    row[1] == 1 and row[2] == action["value"] and row[4] == 1]
        require(len(matching) == 1 and action["value"] >= 1 << 51 and
                matching[0][2] - matching[0][3] == 1 << 51,
                f"TopPanel TradeRoute callback stage {stage} did not reverse-map its reserved input key")

    wheel = rows(r"^INTERACTIVE_TRADE_ROUTE_WHEEL=(\d+)\|(\d+)\|-120(?:\.0+)?$",
                 output, "native TradeRoute wheel posting")
    require(len(wheel) == 1, "TradeRoute run did not post exactly one native wheel event")
    inputs = rows(r"^INTERACTIVE_TRADE_ROUTE_INPUT=(\d+)\|(\d+)\|(-?[0-9]+(?:\.[0-9]+)?)\|([01])\|([01])\|([01])\|STATE_UNCHANGED$",
                  output, "actual TradeRoute input dispatches")
    require(len(inputs) == 9, "TradeRoute run must dispatch the exact nine-input callback/key/scroll sequence")
    decoded_inputs = [{"kind": int(k), "key": int(key), "delta": float(delta),
                       "consumed": bool(int(consumed)), "active": bool(int(active)),
                       "timer_held": bool(int(timer))} for k, key, delta, consumed, active, timer in inputs]
    require(all(row["consumed"] and row["active"] and row["timer_held"]
                for index, row in enumerate(decoded_inputs[:7]) if index != 3),
            "A TradeRoute callback/tab/sort/Return dispatch was not consumed while the modal popup remained active")
    require(decoded_inputs[-2]["active"] is False and decoded_inputs[-2]["timer_held"] is False and
            decoded_inputs[-1]["active"] is False and decoded_inputs[-1]["timer_held"] is False,
            "CloseButton/Escape did not both release the modal timer and close the TradeRoute popup")
    verify_trade_route_dispatches(decoded_inputs, action_by_stage, int(wheel[0][1]))
    action_positions = [match.start() for match in re.finditer(action_rx, output, re.M)]
    input_positions = [match.start() for match in re.finditer(
        r"^INTERACTIVE_TRADE_ROUTE_INPUT=", output, re.M)]
    shown_positions = [match.start() for match in re.finditer(
        r"^INTERACTIVE_TRADE_ROUTE_SHOWN=", output, re.M)]
    wheel_position = re.search(r"^INTERACTIVE_TRADE_ROUTE_WHEEL=", output, re.M).start()
    complete_position = re.search(r"^INTERACTIVE_TRADE_ROUTE_COMPLETE=", output, re.M).start()
    timeline = [action_positions[0], shown_positions[0], action_positions[1], input_positions[0],
                action_positions[2], input_positions[1], action_positions[3], input_positions[2],
                wheel_position, input_positions[3], action_positions[4], input_positions[4],
                action_positions[5], input_positions[5], action_positions[6], input_positions[6],
                action_positions[7], input_positions[7], action_positions[8], shown_positions[1],
                action_positions[9], input_positions[8], complete_position]
    require(timeline == sorted(timeline),
            "TradeRoute posted actions, shown/return events, native dispatches, or completion are out of order")

    ui_frames = parse_trade_route_ui_frames(output)
    require(ui_frames, "Host did not publish any retained TradeRoute snapshot frame")
    snapshots: list[dict] = []
    frame_ids = set()
    session_root = (runtime / "sessions").resolve(strict=True)
    for revision, generation, frame_turn, context, hwnd, device, snapshot_ref, folder_ref in ui_frames:
        require(int(frame_turn) == turn, "TradeRoute retained frame belongs to a different SDK turn")
        path = Path(snapshot_ref).resolve(strict=True)
        require(path in generated_paths, "TradeRoute UI frame references an unrecorded snapshot")
        manifest_path = trade_route_frame_manifest(path, folder_ref, generated_paths, session_root)
        manifest = load_json(manifest_path, "generated TradeRoute scene manifest")
        proof = verify_trade_snapshot(path, owner)
        proof["tab_caption_geometry"] = verify_trade_route_tab_caption_proof(
            load_json(path, "live TradeRoute UI snapshot"), manifest)
        proof["scene_manifest"] = {"path": str(manifest_path), "sha256": digest(manifest_path)}
        proof.update({"revision": int(revision), "generation": int(generation), "turn": int(frame_turn),
                      "hwnd": int(hwnd), "device": int(device)})
        snapshots.append(proof)
        frame_ids.add((int(hwnd), int(device)))
    top_frames = rows(r"^INTERACTIVE_TOP_PANEL_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$",
                      output, "retained TopPanel world frames")
    top_identity = {(int(row[4]), int(row[5])) for row in top_frames}
    require(len(frame_ids) == 1 and len(top_identity) == 1 and frame_ids == top_identity and
            all(hwnd and device for hwnd, device in frame_ids),
            "TradeRoute modal round-trip changed its owned HWND or GPU device")
    by_tab: dict[str, dict] = {}
    for tab in ("YourTR", "AvailableTR", "TRWithYou"):
        matches = [proof for proof in snapshots if proof["selected_tab"] == tab]
        require(matches, f"No live retained snapshot shows the {tab} tab")
        chosen = max(matches, key=lambda proof: proof["generation"])
        require(chosen["rows"], f"Live {tab} route list is empty")
        by_tab[tab] = chosen
    initial_route = [proof for proof in snapshots if action_by_stage[1]["generation"] < proof["generation"] <=
                     action_by_stage[2]["generation"]]
    require(initial_route and any(proof["selected_tab"] == "YourTR" for proof in initial_route),
            "Original TradeRoute popup did not initialize its default YourTR tab after the TopPanel callback")
    for stage, tab, next_stage in ((4, "AvailableTR", 6), (6, "TRWithYou", 7),
                                   (7, "YourTR", 8)):
        action = action_by_stage[stage]
        after = [proof for proof in snapshots if action["generation"] < proof["generation"] <=
                 action_by_stage[next_stage]["generation"] and proof["selected_tab"] == tab]
        require(after, f"Posted stock {tab} tab callback did not publish its own retained snapshot")
    return_open = [proof for proof in snapshots_between_action_generations(
        snapshots, action_by_stage[8]["generation"], action_by_stage[9]["generation"])
        if proof["selected_tab"] == "YourTR"]
    require(return_open, "Native Return did not leave the original TradeRoute modal open before CloseButton")
    require(not [proof for proof in snapshots if action_by_stage[9]["generation"] < proof["generation"] <
                 action_by_stage[10]["generation"]],
            "TradeRoute retained snapshot remained active after CloseButton closed the modal")
    reopened = snapshots_between_action_generations(
        snapshots, action_by_stage[10]["generation"], action_by_stage[11]["generation"])
    require(reopened and any(proof["selected_tab"] == "YourTR" for proof in reopened),
            "InternationalTradeRoutes did not reopen its original default YourTR tab before Escape")
    require(not [proof for proof in snapshots if proof["generation"] > action_by_stage[11]["generation"]],
            "TradeRoute retained snapshot remained active after Escape closed the reopened modal")

    sdk_inventory = verify_sdk_inventory(
        unique_generated(generated, "trade-route-before-inventory.json"), owner, turn)
    sort_results = []
    for stage, ascending in ((2, False), (3, True)):
        action = action_by_stage[stage]
        next_generation = action_by_stage[stage + 1]["generation"]
        candidates = [proof for proof in snapshots if action["generation"] < proof["generation"] <= next_generation and
                      proof["selected_tab"] == "YourTR"]
        require(candidates, f"No post-action YourTR snapshot follows FromGPT sort stage {stage}")
        sort_proof = verify_from_gpt_rows(min(candidates, key=lambda item: item["generation"]),
                                         sdk_inventory["routes"]["outbound"], ascending)
        sort_results.append({"stage": stage, "column": "FromGPT", **sort_proof})

    wheel_generation, scroll_key = map(int, wheel[0])
    require(action_by_stage[4]["generation"] < wheel_generation < action_by_stage[6]["generation"],
            "Native wheel event did not occur between AvailableTR and TRWithYou stages")
    scroll_snapshots = [load_json(Path(proof["path"]), "wheel snapshot") for proof in snapshots
                        if proof["generation"] == wheel_generation]
    require(scroll_snapshots, "Native wheel target generation has no retained TradeRoute snapshot")
    scroll = scroll_snapshots[0].get("tradeRoute", {}).get("mainScroll", {})
    require(scroll.get("key") == scroll_key, "Native wheel key did not match original MainScroll target")
    wheel_events = [event for event in decoded_inputs if event["kind"] == 4 and event["key"] == scroll_key and
                    event["delta"] == 48.0]
    require(len(wheel_events) == 1, "MainScroll did not receive exactly one converted +48 wheel dispatch")
    wheel_before_rows = [proof for proof in snapshots if proof["generation"] <= wheel_generation and
                         proof["selected_tab"] == "AvailableTR"]
    require(wheel_before_rows, "No original AvailableTR snapshot precedes the posted wheel event")
    wheel_before = max(wheel_before_rows, key=lambda proof: proof["generation"])["scroll"]
    wheel_after_rows = [proof for proof in snapshots_between_action_generations(
        snapshots, wheel_generation, action_by_stage[6]["generation"])
        if proof["selected_tab"] == "AvailableTR"]
    wheel_after = max(wheel_after_rows, key=lambda proof: proof["generation"])["scroll"] if wheel_after_rows else None
    wheel_result = verify_wheel_result(scroll.get("maximumScroll"), wheel_before, wheel_after,
                                       wheel_events[0]["consumed"])

    before_state = unique_generated(generated, "trade-route-before-state.txt")
    after_close = unique_generated(generated, "trade-route-returned-10-state.txt")
    after_escape = unique_generated(generated, "trade-route-returned-12-state.txt")
    inventories = [unique_generated(generated, name) for name in (
        "trade-route-before-inventory.json", "trade-route-returned-10-inventory.json",
        "trade-route-returned-12-inventory.json")]
    prepared_presentation = unique_generated(generated, "trade-route-prepared-presentation.json")
    presentations = [unique_generated(generated, name) for name in (
        "trade-route-before-presentation.json", "trade-route-returned-10-presentation.json",
        "trade-route-returned-12-presentation.json")]
    presentation_proofs = [verify_trade_route_presentation(path, sdk_inventory, path.name)
                           for path in presentations]
    require(presentations[0].read_bytes() == presentations[1].read_bytes() == presentations[2].read_bytes(),
            "TradeRoute open/close/reopen/Escape changed exact SDK callback presentation bytes")
    require(before_state.read_bytes() == after_close.read_bytes() == after_escape.read_bytes(),
            "TradeRoute open/close/reopen/Escape changed exact SDK state snapshot bytes")
    require(inventories[0].read_bytes() == inventories[1].read_bytes() == inventories[2].read_bytes(),
            "TradeRoute open/close/reopen/Escape changed the exact captured SDK inventory bytes")
    inventory_docs = [load_json(path, "actual SDK TradeRoute inventory") for path in inventories]
    require(inventory_docs[0] == inventory_docs[1] == inventory_docs[2],
            "TradeRoute roundtrip changed the exact SDK route inventory")
    for tab, inventory_key in (("YourTR", "outbound"), ("AvailableTR", "available"),
                               ("TRWithYou", "inbound")):
        live_pairs = {(row["from"], row["to"]) for row in by_tab[tab]["rows"]}
        sdk_pairs = {(row["from"], row["to"]) for row in sdk_inventory["routes"][inventory_key]}
        require(live_pairs == sdk_pairs and len(live_pairs) == len(by_tab[tab]["rows"]),
                f"Live original {tab} rows do not correspond to the same real SDK getter inventory")
    inventory_bytes_hash = hashlib.sha256(inventories[0].read_bytes()).hexdigest()
    complete = rows(r"^INTERACTIVE_TRADE_ROUTE_COMPLETE=(\d+)\|(-?\d+)\|STATE_UNCHANGED$",
                    output, "TradeRoute completion marker")
    require(len(complete) == 1 and int(complete[0][1]) == turn,
            "TradeRoute sequence did not complete at the original unchanged turn")
    for name in ("YourTR", "AvailableTR", "TRWithYou"):
        # Fixture evidence is tied to real inventory bytes separately; retained row labels must be populated.
        require(by_tab[name]["rows"], f"Original {name} tab has no runtime route row")

    return {
        "status": "PASS_INTERACTIVE_TRADE_ROUTE_NATIVE_SDK_SMOKE",
        "run_id": run_id,
        "host": {"build_report": str(build_path), "build_report_sha256": digest(build_path),
                 "host_path": str(host_path), "host_sha256": digest(host_path),
                 "source_hashes": source_proof},
        "component_fixture": verify_component(), "frozen_ui_support": frozen_support,
        "request": {"path": str(request_path), "sha256": digest(request_path)},
        "result": {"path": str(result_path), "sha256": digest(result_path)},
        "owner": owner, "startup_turn": startup_turn, "turn": turn,
        "turn_transition": "restored_startup" if resumed else "sdk_turn_completed_after_bounded_fixture",
        "resume_lineage": resume_lineage,
        "fixture_ai_role_override": {
            "scope": "two disposable player-1 inbound caravans in fresh fixture setup only",
            "unit_ai_type": "UNITAI_UNKNOWN",
            "mission_path": "SDK MISSION_ESTABLISH_TRADE_ROUTE via ResponsePushMission",
        },
        "popup_data": {"data1": data1, "data2": data2},
        "actions": actions, "input_dispatches": decoded_inputs, "sort_results": sort_results,
        "snapshots_by_tab": by_tab, "all_ui_frames": snapshots,
        "wheel": {"generation": wheel_generation, "main_scroll_key": scroll_key,
                  "delta": -120, "result": wheel_result,
                  "before_scroll_geometry": wheel_before,
                  "after_scroll_geometry": wheel_after, "posted_generation_geometry": scroll},
        "sdk_state": {"before_sha256": digest(before_state), "closed_sha256": digest(after_close),
                      "escape_sha256": digest(after_escape), "roundtrip_bytes_identical": True,
                      "inventory_sha256": inventory_bytes_hash,
                      "inventory_files": [str(path) for path in inventories],
                      "inventory_roundtrip_equal": True, "inventory_schema": sdk_inventory},
        "trade_route_presentation": {
            "prepared_artifact": {"path": str(prepared_presentation), "sha256": digest(prepared_presentation)},
            "before": presentation_proofs[0], "returned_10": presentation_proofs[1],
            "returned_12": presentation_proofs[2], "roundtrip_bytes_identical": True,
            "scope": "SDK TradeVisuals callback path and direction retention only",
            "world_route_rendering_implemented": False},
        "single_hwnd_and_gpu_device": True,
        "host_process_passed": True, "result_json_modified": False,
        "retail_pixel_equivalence_verified": False,
        "all_original_callbacks_supported": False,
        "full_original_ui_verified": False, "full_gameplay_verified": False,
        "human_input_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Immutable actual interactive-game run ID")
    args = parser.parse_args()
    if RUN_ID.fullmatch(args.run) is None:
        print("Run ID is not an immutable timestamp/hash identity", file=sys.stderr)
        return 2
    report_path = EVIDENCE / args.run / "trade_route_validation.json"
    if report_path.exists():
        print(f"Refusing to overwrite existing TradeRoute validation report: {report_path}", file=sys.stderr)
        return 2
    try:
        report = verify_run(args.run)
        document = {
            "status": report.pop("status"),
            "scope": "ACTUAL_X64_HOST_TRADE_ROUTE_MODAL_TABS_SORT_WHEEL_CLOSE_ESCAPE",
            "evidence": report,
            "limitations": [
                "The smoke uses posted HWND input, not human input.",
            "Only the three stock tabs, FromGPT sort direction, MainScroll wheel, Return, CloseButton, and Escape are exercised.",
            "No retail-game pixel capture or complete callback/UI coverage is claimed.",
            "For resumed runs, the permitted Game-section delta is byte-scoped; reload metadata and RNG semantic equivalence are not verified.",
            "TradeVisuals evidence proves copied SDK callback paths and directions only; world route rendering is not implemented.",
            "The bounded SDK route fixture is not evidence of all game states or complete gameplay.",
            ],
        }
    except Exception as exc:
        print(f"FAIL_INTERACTIVE_TRADE_ROUTE_VALIDATION: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with report_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError:
        print(f"Refusing to overwrite existing TradeRoute validation report: {report_path}", file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "run_id": args.run,
                      "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
