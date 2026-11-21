"""Attest current LoadMenu data in a linked PE without loading native code.

Original Lua and every scene/addendum retain their raw UTF-8 BOM and newline
bytes. Only the preparer's explicit LF glue is added. XML is parsed normally,
then its prepared constant data is serialized by the documented Lua-value
format; original XML bytes have a separate hash check. No Lua is evaluated.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
KITS = Path(r"C:\Program Files (x86)\Windows Kits")
B3 = "20261014T110906Z_a60e98e7bde6"
FROZEN = {
    "Source/Host/UiScene.lua": "7c445d81244a1106b4145dfc149a09513578201f6e7ba279d652702b1c9e701c",
    "Source/Presentation/UiPresentationInput.lua": "eb39a22efe774b37fd6033a36aead66ef7c233c25a3b28975fd448cff3806730",
    "Source/Host/UiPopupContext.h": "b824147111989365fa0863914b2f3ed734f015b4161558c2aca06e6eddc7b5ba",
    "Source/Host/UiLoadMenuContract.h": "1b267f2206493c6a07f14079121f4536fe0a6e6f5bcd9eef67a29cfe6a8654c0",
}
ADDENDA = (
    ("City", "UiCityView.lua"), ("Unit", "UiUnitPanel.lua"),
    ("SocialPolicy", "UiSocialPolicy.lua"), ("Economic", "UiEconomicOverview.lua"),
    ("ActionInfo", "UiActionInfoPanel.lua"), ("Notification", "UiNotificationPanel.lua"),
)
ORIGINAL = {
    "LoadMenu": "Assets/UI/FrontEnd/LoadMenu.lua",
    "LoadMenuLayout": "Assets/UI/FrontEnd/LoadMenu.xml",
    "InstanceManager": "Assets/UI/InstanceManager.lua",
    "IconSupport": "Assets/UI/IconSupport.lua",
    "SupportFunctions": "Assets/UI/SupportFunctions.lua",
    "UniqueBonuses": "Assets/UI/FrontEnd/GameSetup/UniqueBonuses.lua",
    "MapUtilities": "Assets/Gameplay/Lua/MapUtilities.lua",
    "InfoTooltipInclude": "Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua",
    "FLuaVector": "Assets/Gameplay/Lua/FLuaVector.lua",
}
TUS = {"host_main", "window", "renderer", "world_renderer", "terrain_renderer"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def safe(path):
    path = Path(os.path.abspath(path))
    require(any(path.is_relative_to(root) for root in (PROJECT, GAME / "Assets", GAME / "Resource", VS, KITS)),
            "Read escaped the static asset/source/build roots")
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for ancestor in [*reversed(path.parents), path]:
        metadata = ancestor.lstat()
        require(not stat.S_ISLNK(metadata.st_mode) and
                not getattr(metadata, "st_file_attributes", 0) & reparse,
                "Read encountered a symlink or reparse point: " + str(ancestor))
    require(path.is_file(), "Expected a regular input file: " + str(path))
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Inputs:
    def __init__(self):
        self.seals = {}
        self.ranges = []

    def read(self, path):
        path = safe(path)
        data = path.read_bytes()
        seal = {"bytes": len(data), "sha256": digest(data)}
        key = str(path)
        require(key not in self.seals or self.seals[key] == seal, "Input changed during verification: " + key)
        self.seals[key] = seal
        return data

    def ref(self, row, expected=None):
        require(type(row) is dict and isinstance(row.get("path"), str), "Missing artifact reference")
        path = Path(row["path"])
        require(expected is None or norm(path) == norm(expected), "Artifact path lineage differs")
        data = self.read(path)
        require(digest(data) == row.get("sha256"), "Artifact hash differs: " + str(path))
        require("bytes" not in row or len(data) == row["bytes"], "Artifact size differs: " + str(path))
        return data

    def document(self, path):
        return json.loads(self.read(path).decode("utf-8-sig"))

    def finish(self):
        for path, before in self.seals.items():
            data = safe(path).read_bytes()
            require({"bytes": len(data), "sha256": digest(data)} == before, "Input changed after verification: " + path)
        for row in self.ranges:
            with safe(row["pack_path"]).open("rb") as stream:
                stream.seek(row["offset"])
                raw = stream.read(row["bytes"])
            require(len(raw) == row["bytes"] and digest(raw) == row["sha256"], "Selected static archive entry changed")
        return self.seals


def lua_value(value):
    """The preparer's ASCII constant-data format, without a Lua VM or eval."""
    if isinstance(value, str):
        return '"' + "".join(chr(b) if 32 <= b < 127 and b not in (34, 92) else "\\%03d" % b
                             for b in value.encode("utf-8")) + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        require(math.isfinite(value), "Non-finite prepared layout value")
        return repr(value)
    if isinstance(value, list):
        return "{" + ",".join(lua_value(item) for item in value) + "}"
    if isinstance(value, dict):
        def key(item):
            require(isinstance(item, str) or type(item) is int and item >= 0, "Unsupported constant table key")
            return "[" + lua_value(item) + "]"
        return "{" + ",".join(key(k) + "=" + lua_value(v) for k, v in
                              sorted(value.items(), key=lambda row: (type(row[0]).__name__, row[0]))) + "}"
    raise RuntimeError("Unsupported constant layout type")


def generated_catalog(data, targets):
    arrays, decoded = {}, {}
    for match in re.finditer(rb"^static const char ([A-Za-z_]\w*)\[\]=\r?\n(.*?);\r?$", data, re.M | re.S):
        name = match[1].decode("ascii")
        require(name not in arrays, "Duplicate generated array: " + name)
        length, pieces = 0, []
        for line in match[2].splitlines():
            require(re.fullmatch(rb'"(?:\\x[0-9a-f]{2}){0,64}"', line) is not None,
                    "Generated array is not the exact hexadecimal literal format")
            length += (len(line) - 2) // 4
            if name in targets:
                pieces.append(bytes.fromhex(line[1:-1].replace(b"\\x", b"").decode("ascii")))
        arrays[name] = length
        if name in targets:
            decoded[name] = b"".join(pieces)
    table = re.findall(rb"^static const Script scripts\[\]=\{\r?\n(.*?)^\};\r?$", data, re.M | re.S)
    require(len(table) == 1, "Generated script catalog table is missing or duplicated")
    names = []
    for line in table[0].splitlines():
        match = re.fullmatch(rb'\{"([A-Za-z_]\w*)",([A-Za-z_]\w*),sizeof\(([A-Za-z_]\w*)\)-1\},', line)
        require(match is not None and match[1] == match[2] == match[3], "Generated script registry row differs")
        name = match[1].decode("ascii")
        require(name in arrays and name not in names, "Generated registry array is missing or duplicated")
        names.append(name)
    require(set(targets) <= set(names), "Generated catalog omits required LoadMenu payloads")
    return arrays, decoded, names


class PE:
    """Read file-backed AMD64 addresses; never map or load the image."""
    def __init__(self, data):
        self.data = data
        require(len(data) >= 64 and data[:2] == b"MZ", "PE DOS header is missing")
        offset = self.number(0x3C, "<I")
        require(data[offset:offset + 4] == b"PE\0\0", "PE signature is missing")
        require(self.number(offset + 4, "<H") == 0x8664, "PE is not AMD64")
        count, optional_size = self.number(offset + 6, "<H"), self.number(offset + 20, "<H")
        optional = offset + 24
        require(self.number(optional, "<H") == 0x20B and optional_size >= 128 and
                self.number(optional + 108, "<I") >= 2, "PE32+ import directory is unavailable")
        require(not self.number(offset + 22, "<H") & 0x2000, "Candidate is a DLL")
        require(0 < count <= 96, "PE section count is invalid")
        self.base = self.number(optional + 24, "<Q")
        self.sections = []
        for index in range(count):
            at = optional + optional_size + index * 40
            require(at + 40 <= len(data), "PE section table is truncated")
            name = data[at:at + 8].split(b"\0", 1)[0].decode("ascii")
            size, raw = self.number(at + 16, "<I"), self.number(at + 20, "<I")
            require(raw + size <= len(data), "PE raw section is truncated")
            self.sections.append({"name": name, "rva": self.number(at + 12, "<I"), "raw": raw,
                                  "size": size, "flags": self.number(at + 36, "<I")})
        self.import_rva, self.import_size = struct.unpack_from("<II", data, optional + 120)

    def number(self, offset, fmt):
        require(0 <= offset <= len(self.data) - struct.calcsize(fmt), "PE scalar is outside the image")
        return struct.unpack_from(fmt, self.data, offset)[0]

    def mapped(self, rva, size, readonly=False):
        matches = [row for row in self.sections if row["rva"] <= rva and
                   rva - row["rva"] + size <= row["size"]]
        require(len(matches) == 1, "PE address does not map to exactly one raw section")
        row = matches[0]
        if readonly:
            require(row["flags"] & 0x40000000 and not row["flags"] & 0xA0000000,
                    "UI catalog/payload is not in read-only non-executable PE data")
        return row["raw"] + rva - row["rva"], row

    def cstring(self, rva):
        at, row = self.mapped(rva, 1)
        end = self.data.find(b"\0", at, min(at + 4096, row["raw"] + row["size"]))
        require(end >= at, "PE catalog/import name is not terminated")
        return self.data[at:end]

    def occurrences(self, value):
        result = []
        for row in self.sections:
            if not row["flags"] & 0x40000000 or row["flags"] & 0xA0000000:
                continue
            end = row["raw"] + row["size"]
            at = self.data.find(value, row["raw"], end)
            while at >= 0:
                result.append((row["rva"] + at - row["raw"], at))
                at = self.data.find(value, at + 1, end)
        return result

    def imports(self):
        require(self.import_rva and self.import_size >= 20, "PE has no import directory")
        names = []
        for index in range(min(self.import_size // 20, 1024)):
            at, _ = self.mapped(self.import_rva + index * 20, 20)
            descriptor = struct.unpack_from("<5I", self.data, at)
            if not any(descriptor):
                return names
            names.append(self.cstring(descriptor[3]).decode("ascii").casefold())
        raise RuntimeError("PE import directory is not bounded and terminated")

    def catalog(self, names, lengths, payloads):
        candidates = None
        for name, payload in payloads.items():
            rows = set()
            for name_rva, _ in self.occurrences(name.encode("ascii") + b"\0"):
                for payload_rva, _ in self.occurrences(payload + b"\0"):
                    record = struct.pack("<QQQ", self.base + name_rva, self.base + payload_rva, len(payload))
                    rows.update(rva - names.index(name) * 24 for rva, _ in self.occurrences(record) if rva % 8 == 0)
            candidates = rows if candidates is None else candidates & rows
        require(candidates is not None and len(candidates) == 1, "PE lacks one actual shared name/payload/length catalog")
        base = candidates.pop()
        at, section = self.mapped(base, len(names) * 24, readonly=True)
        proof = {}
        for index, name in enumerate(names):
            name_va, payload_va, size = struct.unpack_from("<QQQ", self.data, at + index * 24)
            require(name_va >= self.base and payload_va >= self.base, "PE catalog has a foreign address")
            name_rva, payload_rva = name_va - self.base, payload_va - self.base
            self.mapped(name_rva, len(name) + 1, readonly=True)
            require(self.cstring(name_rva) == name.encode("ascii") and size == lengths[name],
                    "PE catalog name or exact payload length differs from the generated registry")
            payload_at, payload_section = self.mapped(payload_rva, size + 1, readonly=True)
            require(self.data[payload_at + size] == 0, "PE catalog payload is not terminated")
            if name in payloads:
                require(self.data[payload_at:payload_at + size] == payloads[name], "PE catalog points to different payload bytes")
                proof[name] = {"registry_index": index, "row_rva": base + index * 24,
                               "name_rva": name_rva, "payload_rva": payload_rva, "file_offset": payload_at,
                               "bytes": size, "sha256": digest(payloads[name]), "section": payload_section["name"]}
        return {"table_rva": base, "table_section": section["name"], "stride": 24,
                "entry_count": len(names), "exact_payloads": proof}


def strip_tree(node):
    return {"kind": node["kind"], "attributes": node["attributes"],
            "children": [strip_tree(child) for child in node["children"]]}


def xml_tree(node):
    return {"kind": node.tag, "attributes": dict(node.attrib), "children": [xml_tree(child) for child in node]}


def walk(node):
    yield node
    for child in node["children"]:
        yield from walk(child)


def checkbox_contract(inputs, tree, metadata):
    defaults = tree.get("controlDefaultSizes")
    require(type(defaults) is dict and set(defaults) == {"AutoCheck", "CloudCheck"} and
            defaults == metadata.get("checkbox_default_candidates"), "Prepared checkbox candidate metadata differs")
    nodes = {node["attributes"].get("ID"): node for node in walk(tree)}
    style_path = GAME / "Assets/UI/Styles.xml"
    style = ET.fromstring(inputs.read(style_path)).find("Button_16")
    require(style is not None and not list(style) and dict(style.attrib) ==
            {"Texture": "Assets/UI/Art/Controls/Checkbox.dds", "Size": "32,32"}, "Original checkbox style changed")
    packed = []
    for control, row in defaults.items():
        require(row["policy"] == "LOAD_MENU_BUTTON_16_DEFAULT_CANDIDATE_V1" and
                (row["width"], row["height"], row["frameCount"], row["style"]) == (32, 32, 4, "Button_16"),
                "Checkbox candidate size or policy changed")
        require(all(row[key] is False for key in
                    ("defaultBindingVerified", "retailGeometryVerified", "retailWidgetStateMappingVerified")),
                "Checkbox candidate claims unproved retail behavior")
        require(nodes[control]["kind"] == "CheckBox" and
                nodes[control]["attributes"] == row["controlSourceAttributes"] and
                row["sourceStyleAttributes"] == dict(style.attrib), "Original implicit checkbox declaration changed")
        inputs.ref(row["source"], style_path)
        inputs.ref(row["controlSource"], GAME / ORIGINAL["LoadMenuLayout"])
        require(row["atlas"] == {**row["atlas"], "width": 32, "height": 128, "cellWidth": 32,
                                "cellHeight": 32, "frameCount": 4} and
                re.fullmatch("[0-9a-f]{64}", row["atlas"]["sha256"]), "Checkbox atlas metadata changed")
        for key, expected_name in (("atlasSource", "checkbox.dds"), ("atlasIndexSource", "checkbox-index.dds")):
            reference = row[key]
            require(type(reference) is dict and reference["entry"].casefold() == expected_name,
                    "Checkbox atlas pair source is missing")
            pack = safe(reference["pack_path"])
            require(pack == GAME / "Resource/DX9/Expansion2UITextures.fpk",
                    "Checkbox atlas comes from another archive")
            require(type(reference["offset"]) is int and reference["offset"] >= 14 and
                    type(reference["bytes"]) is int and 0 < reference["bytes"] <= 16 * 1024 * 1024 and
                    reference["offset"] + reference["bytes"] <= pack.stat().st_size, "Invalid checkbox archive range")
            with pack.open("rb") as stream:
                stream.seek(reference["offset"])
                raw = stream.read(reference["bytes"])
            require(digest(raw) == reference["sha256"], "Original checkbox atlas bytes changed")
            inputs.ranges.append(reference)
            packed.append(reference)
    return {"policy": "LOAD_MENU_BUTTON_16_DEFAULT_CANDIDATE_V1", "controls": sorted(defaults),
            "atlas_entry_ranges_hash_checked": packed[:2], "decoded_pixel_hash_recomputed": False,
            "retail_binding_verified": False}


def verify_build(build_id):
    require(re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", build_id), "Invalid immutable build ID")
    inputs = Inputs()
    inputs.read(Path(__file__))
    scope_path = PROJECT / "evidence/load_menu/linked_candidate/scope.json"
    scope = inputs.document(scope_path)
    require(scope["schema"] == "ZEROSIS_CURRENT_LOAD_MENU_LINKED_CANDIDATE_SCOPE_V1" and
            scope["full_engine_goal_redefined"] is False, "Candidate scope does not preserve the full engine goal")
    for row in scope["protected_default_and_schema"].values():
        inputs.ref(row)
    inputs.ref(scope["existing_generated_header_recovery"])
    report_path = PROJECT / "evidence/ui_window_host" / build_id / "build_result.json"
    report = inputs.document(report_path)
    require(report["build_id"] == build_id and report["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT",
            "Candidate compilation/linking has not completed")
    require(report["source_inputs_unchanged"] is True and report["provider_inputs_unchanged"] is True and
            all(report[key] is False for key in
                ("gamecore_loaded", "sdk_linked", "stage_updated", "mods_updated", "host_runtime_executed")),
            "Build did not preserve its private compile/link scope")
    require(report["source_hashes_before"] == report["source_hashes_after"], "Owned source hash accounting differs")
    sources = {}
    frozen_root = PROJECT / "Build/UiWindowHost" / build_id / "frozen"
    for role, relative in (("builder", "tools/build_ui_window_host.py"),
                           ("popup_asset_preparer", "tools/prepare_ui_popup_assets.py"),
                           ("ui_asset_codec", "tools/civ5_ui_assets.py")):
        raw = inputs.read(PROJECT / relative)
        require(digest(raw) == report["source_hashes_before"][role] and
                inputs.read(frozen_root / "project" / relative) == raw,
                "Current preparer/codec/builder differs from the build's frozen input: " + role)
    for row in report["sources"]:
        name = Path(row["path"]).name
        require(name not in sources, "Duplicate frozen source basename")
        require(Path(os.path.abspath(row["path"])).is_relative_to(frozen_root), "Source escaped the selected frozen build")
        require(inputs.ref(row) == inputs.read(row["original_source"]), "Frozen owned source differs from current source: " + name)
        sources[name] = row
    current = {}
    for relative, expected in FROZEN.items():
        path = PROJECT / relative
        raw = inputs.read(path)
        require(digest(raw) == expected, "Current source differs from agreed LoadMenu freeze: " + relative)
        row = sources[path.name]
        require(norm(row["original_source"]) == norm(path), "Frozen source has wrong original lineage")
        current[path.name] = inputs.ref(row)
        require(current[path.name] == raw, "Candidate froze an older LoadMenu source: " + relative)
    by_original = {}
    for row in report["compiler_inputs"]:
        require(Path(os.path.abspath(row["path"])).is_relative_to(frozen_root), "Compiler input escaped its frozen build")
        original = inputs.read(row["original_path"])
        require(digest(original) == row["sha256"] and original == inputs.ref(row), "Compiler input changed")
        key = norm(row["original_path"])
        require(key not in by_original, "Duplicate compiler input identity")
        by_original[key] = norm(row["path"])
    discoveries = {row["translation_unit"]: row for row in report["dependency_discovery"]["translation_units"]}
    finals = {row["translation_unit"]: row for row in report["final_compilation"]["translation_units"]}
    require(set(discoveries) == set(finals) == TUS, "Wrong compiled translation-unit coverage")
    final_sets = {}
    for name in sorted(TUS):
        sets = []
        for row in (discoveries[name], finals[name]):
            require(row["returncode"] == 0, "Compilation failed")
            log = inputs.ref(row["log"]).decode("utf-8", errors="replace")
            require(not re.search(r"\bwarning\s+[A-Z]+\d+", log, re.I), "Compiler warning remains")
            document = json.loads(inputs.ref(row["dependency_report"]).decode("utf-8-sig"))
            data = document.get("Data", document)
            sets.append({norm(path) for path in (data["Source"], *data["Includes"])})
        require({by_original[path] for path in sets[0]} == sets[1], "Final compiler consumed another dependency closure")
        final_sets[name] = sets[1]
    required_headers = ("UiPopupContext.h", "UiLoadMenuContract.h", "UiPopupAssets.generated.h",
                        "NativeSaveCatalog.h", "SdkGameRestore.h", "InteractiveUiSession.h",
                        "InteractiveGameSession.h", "InteractiveGameLoop.h")
    require(set(name.casefold() for name in required_headers) <=
            {Path(path).name.casefold() for path in final_sets["host_main"]}, "Final Host omitted the new load/session contract")
    generated_path = PROJECT / "Source/Host/UiPopupAssets.generated.h"
    header_row = sources[generated_path.name]
    generated = inputs.ref(header_row)
    require(generated == inputs.read(generated_path) and
            by_original[norm(generated_path)] in final_sets["host_main"], "Final compiler missed the exact current generated header")
    prepared = json.loads(inputs.ref(report["ui_assets"]).decode("utf-8-sig"))
    require(prepared["status"] == "INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED",
            "UI preparation did not complete")
    require(inputs.ref(prepared["compiled_assets"], generated_path) == generated, "Prepared generated-header binding differs")
    inputs.ref(prepared["builder"], PROJECT / "tools/prepare_ui_popup_assets.py")
    assembled = b""
    segments = []
    omitted_prepared_fields = []
    for field, filename, glue in (
        ("host_ui_runtime", "UiScene.lua", b""),
        ("host_ui_input_addendum", "UiPresentationInput.lua", b"\n"),
        *(({"City": "host_ui_city_view_addendum", "Unit": "host_ui_unit_panel_addendum",
            "SocialPolicy": "host_ui_social_policy_addendum", "Economic": "host_ui_economic_overview_addendum",
            "ActionInfo": "host_ui_action_info_addendum", "Notification": "host_ui_notification_addendum"}[flag],
           filename, b"\nif hasRetained" + flag.encode("ascii") + b"Ui then\n") for flag, filename in ADDENDA),
    ):
        folder = "Host" if filename == "UiScene.lua" else "Presentation"
        source = inputs.read(PROJECT / "Source" / folder / filename)
        require(norm(sources[filename]["original_source"]) == norm(PROJECT / "Source" / folder / filename) and
                inputs.ref(sources[filename]) == source, "Scene/addendum source lineage is stale: " + filename)
        if field in prepared:
            require(inputs.ref(prepared[field], PROJECT / "Source" / folder / filename) == source,
                    "Prepared Scene/addendum provenance is stale: " + filename)
        else:
            # The preparer has always appended this module but omits its
            # report field. Its complete bytes remain mandatory in the scene.
            require(filename == "UiNotificationPanel.lua", "A required prepared source reference is missing: " + field)
            omitted_prepared_fields.append(field)
        assembled += glue
        segments.append({"source": filename, "offset": len(assembled), "bytes": len(source), "sha256": digest(source)})
        assembled += source
        if filename not in ("UiScene.lua", "UiPresentationInput.lua"):
            assembled += b"\nend\n"
    original_rows = {row["name"]: row for row in prepared["inputs"]}
    payloads = {"ZeroSisUiScene": assembled}
    for name, relative in ORIGINAL.items():
        row = original_rows[name]
        raw = inputs.ref(row["installed"], GAME / relative)
        require(inputs.ref(row["snapshot"]) == raw, "Original installed/snapshot bytes differ: " + name)
        if name != "LoadMenuLayout":
            payloads[name] = raw
    tree = deepcopy(prepared["xml_control_trees"]["LoadMenuLayout"])
    # JSON object keys lose the integer type used by the font schema. Restore
    # only glyphSets codepoints; never coerce arbitrary numeric-looking text.
    for glyph_set, glyphs in tree["fontMetrics"]["glyphSets"].items():
        require(all(re.fullmatch(r"0|[1-9][0-9]*", key) and 0 <= int(key) <= 0x10FFFF
                    for key in glyphs), "Prepared glyph-set codepoint key differs from its schema")
        tree["fontMetrics"]["glyphSets"][glyph_set] = {int(key): value for key, value in glyphs.items()}
    for font in tree["fontMetrics"]["fonts"].values():
        raw_font = inputs.read(GAME / font["ggxmlPath"])
        require(digest(raw_font) == font["sha256"], "Prepared font source differs from installed GGXML")
    original_xml = inputs.read(GAME / ORIGINAL["LoadMenuLayout"])
    require(strip_tree(tree) == xml_tree(ET.fromstring(original_xml)) and
            (tree["contextName"], tree["popupKind"]) == ("LoadMenu", "LoadMenu"), "Prepared layout rewrote original LoadMenu XML")
    load_metadata = prepared["load_menu"]
    require(all(load_metadata[key] == value for key, value in tree["loadMenu"].items()),
            "Prepared LoadMenu metadata differs from its compiled tree")
    for field, name in (("originalLua", "LoadMenu"), ("originalXml", "LoadMenuLayout"),
                        ("originalUniqueBonusesLua", "UniqueBonuses"), ("originalMapUtilitiesLua", "MapUtilities")):
        inputs.ref(tree["loadMenu"][field], GAME / ORIGINAL[name])
    checkbox = checkbox_contract(inputs, tree, load_metadata)
    payloads["LoadMenuLayout"] = ("ZeroSisUiLayout=" + lua_value(tree) + "\n").encode("ascii")
    lengths, arrays, names = generated_catalog(generated, payloads)
    require(all(arrays[name] == payload for name, payload in payloads.items()), "Generated catalog payload differs from exact source/prepared data")
    executable_path = PROJECT / "Build/UiWindowHost" / build_id / "final/ZeroSisHost_x64.exe"
    image = inputs.ref(report["executable"], executable_path)
    pe = PE(image)
    imports = pe.imports()
    require(set(imports) == {name.casefold() for name in report["imports"]["dependencies"]} and
            {"imm32.dll", "zerosislua51_x64.dll"} <= set(imports) and
            not any("gamecore" in name or "civilization" in name for name in imports), "Actual PE import table differs or imports retail/Core code")
    catalog = pe.catalog(names, lengths, payloads)
    scene_location = catalog["exact_payloads"]["ZeroSisUiScene"]
    for segment in segments:
        segment["pe_file_offset"] = scene_location["file_offset"] + segment["offset"]
        segment["pe_rva"] = scene_location["payload_rva"] + segment["offset"]
    link_log = inputs.ref(report["link_log"]).decode("utf-8", errors="replace")
    require(not re.search(r"\bwarning\s+LNK\d+", link_log, re.I), "Linker warning remains")
    link_response = inputs.ref(report["link_response"]).decode("utf-8-sig").splitlines()
    actual_objects = {norm(line.strip('"')) for line in link_response if line.casefold().endswith('.obj"')}
    expected_objects = {norm(PROJECT / "Build/UiWindowHost" / build_id / "final" /
                             ("tu_%02d_%s" % (index, name)) / "obj" /
                             ({"host_main": "HostMain", "window": "BitmapWindow", "renderer": "BitmapRenderer",
                               "world_renderer": "WorldViewRenderer", "terrain_renderer": "WorldTerrainRenderer"}[name] + ".obj"))
                        for index, name in enumerate(("host_main", "window", "renderer", "world_renderer", "terrain_renderer"))}
    require(actual_objects == expected_objects and
            {"/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"} <= set(link_response) and
            f'/OUT:"{executable_path}"' in link_response, "Link response does not use only this candidate's five final objects")
    inputs.ref(report["map"])
    seals = inputs.finish()
    return {"build_id": build_id, "build_report": {"path": str(report_path), **seals[str(report_path)]},
            "candidate_scope": {"path": str(scope_path), **seals[str(scope_path)]},
            "executable": report["executable"], "source_sha256": FROZEN, "inputs_unchanged": True,
            "read_input_count": len(seals),
            "read_input_seals_sha256": digest(json.dumps(seals, sort_keys=True).encode("utf-8")),
            "current_source_seals": {path: row for path, row in seals.items()
                                     if (Path(path).is_relative_to(PROJECT / "Source") or
                                         Path(path).is_relative_to(PROJECT / "Tests")) and
                                     "Assets" not in Path(path).parts and "SDK_BNW_x64" not in Path(path).parts},
            "translation_units": sorted(TUS), "exact_final_dependency_closure": True,
            "actual_pe_imports": imports, "pe_catalog": catalog, "scene_source_segments": segments,
            "checkbox_candidate": checkbox,
            "prepared_report_omits_reference_fields": omitted_prepared_fields,
            "byte_policy": "RAW_UTF8_BOM_AND_NEWLINES_PRESERVED; EXPLICIT_LF_SCENE_GLUE; XML_ET_ATTRIBUTES_AND_LUA_CONSTANT_SERIALIZATION",
            "native_binding_execution_verified": False, "retail_ui_verified": False,
            "acceptance": "PRIVATE_COMPILE_LINK_AND_EXACT_READ_ONLY_PE_UI_CATALOG_PAYLOAD_ONLY"}


def verify_b3_negative():
    try:
        verify_build(B3)
    except (RuntimeError, KeyError) as error:
        reason = str(error)
    else:
        raise RuntimeError("Historical B3 incorrectly passed current LoadMenu attestation")
    inputs = Inputs()
    report_path = PROJECT / "evidence/ui_window_host" / B3 / "build_result.json"
    report = inputs.document(report_path)
    sources = {Path(row["path"]).name: row for row in report["sources"]}
    old_header = inputs.ref(sources["UiPopupAssets.generated.h"])
    lengths, payloads, names = generated_catalog(old_header, {"ZeroSisUiScene"})
    missing = sorted({"LoadMenu", "LoadMenuLayout"} - set(names))
    require(missing == ["LoadMenu", "LoadMenuLayout"], "B3 no longer provides the expected missing-LoadMenu negative control")
    image = inputs.ref(report["executable"], PROJECT / "Build/UiWindowHost" / B3 / "final/ZeroSisHost_x64.exe")
    old_table = PE(image).catalog(names, lengths, payloads)
    inputs.ref(sources["UiScene.lua"])
    require(sources["UiScene.lua"]["sha256"] != FROZEN["Source/Host/UiScene.lua"], "B3 scene is not historical")
    inputs.finish()
    return {"build_id": B3, "rejected": True, "strict_candidate_rejection": reason,
            "actual_pe_catalog_checked": True, "actual_pe_catalog_missing": missing,
            "old_scene_sha256": sources["UiScene.lua"]["sha256"],
            "executable": report["executable"], "catalog_table_rva": old_table["table_rva"],
            "scope": "Valid historical PE/catalog, rejected as current LoadMenu acceptance"}


def write_evidence(filename, result):
    folder = PROJECT / "evidence/load_menu/linked_candidate"
    require(folder.is_dir(), "Candidate evidence directory is missing")
    for path in [*folder.parents, folder]:
        metadata = path.lstat()
        require(not stat.S_ISLNK(metadata.st_mode) and
                not getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
                "Evidence folder encountered a reparse point")
    output = folder / filename
    require(output.parent == folder and not output.exists(), "Attestation already exists or escaped its evidence directory")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    try:
        result = verify_build(args.build_id)
        negative = verify_b3_negative()
        # The old-image negative check must not leave a window for a current
        # source/image replacement before the accepted result is published.
        for path, expected in result["current_source_seals"].items():
            raw = safe(path).read_bytes()
            require(digest(raw) == expected["sha256"] and len(raw) == expected["bytes"],
                    "Current source changed while checking the historical negative control")
        for row in (result["executable"], result["build_report"]):
            require(digest(safe(row["path"]).read_bytes()) == row["sha256"], "Candidate changed before evidence publication")
    except Exception as error:
        failure = {"schema": "ZEROSIS_LOAD_MENU_LINKED_PE_CATALOG_ATTESTATION_V1", "status": "FAIL",
                   "build_id": args.build_id, "utc": datetime.now(timezone.utc).isoformat(),
                   "error_type": type(error).__name__, "error": str(error),
                   "verifier_sha256": digest(Path(__file__).read_bytes()),
                   "host_executed": False, "gamecore_loaded": False, "dll_loaded": False,
                   "hwnd_created": False, "binary_modified": False, "default_promoted": False}
        output = write_evidence("failure_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json", failure)
        print(json.dumps({"status": "FAIL", "error": str(error), "report": str(output)}))
        raise
    result.update(schema="ZEROSIS_LOAD_MENU_LINKED_PE_CATALOG_ATTESTATION_V1", status="PASS",
                  utc=datetime.now(timezone.utc).isoformat(), negative_control=negative,
                  verifier_sha256=digest(Path(__file__).read_bytes()),
                  host_executed=False, gamecore_loaded=False, dll_loaded=False, hwnd_created=False,
                  mods_or_user_saves_accessed=False, default_promoted=False, binary_modified=False)
    output = write_evidence("attestation_" + args.build_id + ".json", result)
    print(json.dumps({"status": "PASS", "build_id": args.build_id, "report": str(output),
                      "sha256": digest(output.read_bytes()), "payloads": len(result["pe_catalog"]["exact_payloads"]),
                      "host_executed": False, "native_binding_execution_verified": False}))


if __name__ == "__main__":
    main()
