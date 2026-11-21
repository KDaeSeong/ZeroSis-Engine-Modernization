"""Build a private shared-Lua host candidate with the bitmap-window presenter."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys

from collect_baseline import PROJECT, digest, pe_header
from native_build import checked_run, environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
BUILD_ROOT = PROJECT / "Build/UiWindowHost"
EVIDENCE_ROOT = PROJECT / "evidence/ui_window_host"
SDK_ROOT = PROJECT / "Source/SDK_BNW_x64"
PROJECT_INCLUDE_DIRS = [PROJECT / "Source/Host", PROJECT / "Source/Porting", PROJECT / "Tests"]
SDK_INCLUDE_RELS = [
    Path("CvGameCoreDLL_Expansion2"), Path("CvGameCoreDLLUtil/include"),
    Path("CvGameDatabase/include"), Path("CvLocalization/include"),
    Path("CvWorldBuilderMap/include"), Path("FirePlace/include"),
    Path("FirePlace/include/FireWorks"), Path("ThirdPartyLibs/Lua51/include"),
]
PROVIDER_REPORTS = {
    "database": PROJECT / "evidence/database/candidate/build_result.json",
    "localization": PROJECT / "evidence/localization/provider/build_result.json",
    "shared_lua": PROJECT / "evidence/shared_lua_runtime/build_result.json",
    "streams": PROJECT / "evidence/streams/provider/build_result.json",
    "temp_heap": PROJECT / "evidence/temp_heap/build_result.json",
}
OWNED = {
    "host_main": PROJECT / "Source/Host/HostMain.cpp",
    "host_run": PROJECT / "Source/Host/HostRun.h",
    "host_services": PROJECT / "Source/Host/HostServices.h",
    "ui_input_dispatch": PROJECT / "Source/Host/UiInputDispatch.h",
    "ui_save_menu_contract": PROJECT / "Source/Host/UiSaveMenuContract.h",
    "native_save_catalog": PROJECT / "Source/Host/NativeSaveCatalog.h",
    "ui_window_presentation": PROJECT / "Source/Host/UiWindowPresentation.h",
    "ui_popup_context": PROJECT / "Source/Host/UiPopupContext.h",
    "ui_audio_playback": PROJECT / "Source/Host/UiAudioPlayback.h",
    "ui_snapshot_json": PROJECT / "Source/Host/UiSnapshotJson.h",
    "ui_popup_assets_generated": PROJECT / "Source/Host/UiPopupAssets.generated.h",
    "ui_scene": PROJECT / "Source/Host/UiScene.lua",
    "ui_city_view_addon": PROJECT / "Source/Presentation/UiCityView.lua",
    "ui_unit_panel_addon": PROJECT / "Source/Presentation/UiUnitPanel.lua",
    "ui_action_info_panel_addon": PROJECT / "Source/Presentation/UiActionInfoPanel.lua",
    "ui_notification_panel_addon": PROJECT / "Source/Presentation/UiNotificationPanel.lua",
    "ui_social_policy_addon": PROJECT / "Source/Presentation/UiSocialPolicy.lua",
    "ui_economic_overview_addon": PROJECT / "Source/Presentation/UiEconomicOverview.lua",
    "production_command_guard": PROJECT / "Source/Host/ProductionCommandGuard.lua",
    "research_command_guard": PROJECT / "Source/Host/ResearchCommandGuard.lua",
    "popup_asset_preparer": PROJECT / "tools/prepare_ui_popup_assets.py",
    "ui_font_profile_helper": PROJECT / "tools/ui_font_profile.py",
    "ui_font_profile_manifest": PROJECT / "Source/Assets/UI/font_input_profile.json",
    "ui_asset_codec": PROJECT / "tools/civ5_ui_assets.py",
    "ui_presentation_input_addon": PROJECT / "Source/Presentation/UiPresentationInput.lua",
    "window_header": PROJECT / "Source/Presentation/BitmapWindow.h",
    "editor_input_header": PROJECT / "Source/Presentation/BitmapEditorInput.h",
    "window": PROJECT / "Source/Presentation/BitmapWindow.cpp",
    "renderer_header": PROJECT / "Source/Presentation/BitmapRenderer.h",
    "renderer": PROJECT / "Source/Presentation/BitmapRenderer.cpp",
    "world_state": PROJECT / "Source/Host/WorldViewState.h",
    "interactive_session": PROJECT / "Source/Host/InteractiveGameSession.h",
    "interactive_ui_session": PROJECT / "Source/Host/InteractiveUiSession.h",
    "interactive_loop": PROJECT / "Source/Host/InteractiveGameLoop.h",
    "trade_route_smoke_fixture": PROJECT / "Source/Host/TradeRouteSmokeFixture.h",
    "social_policy_smoke_fixture": PROJECT / "Source/Host/SocialPolicySmokeFixture.h",
    "economic_overview_smoke_fixture": PROJECT / "Source/Host/EconomicOverviewSmokeFixture.h",
    "trade_route_presentation": PROJECT / "Source/Host/TradeRoutePresentation.h",
    "trade_route_fixture_probe": PROJECT / "Source/Host/TradeRouteFixtureProbe.h",
    "world_renderer_header": PROJECT / "Source/Presentation/WorldViewRenderer.h",
    "world_renderer": PROJECT / "Source/Presentation/WorldViewRenderer.cpp",
    "terrain_renderer_header": PROJECT / "Source/Presentation/WorldTerrainRenderer.h",
    "terrain_renderer": PROJECT / "Source/Presentation/WorldTerrainRenderer.cpp",
    "unit_assets_header": PROJECT / "Source/Presentation/WorldUnitAssets.h",
    "unit_animation_header": PROJECT / "Source/Animation/UnitAnimation.h",
    "granny_animation_abi": PROJECT / "Source/Animation/GrannyAnimationBridge.h",
    "builder": Path(__file__).resolve(),
    "host_builder": PROJECT / "tools/build_native_host.py",
}
TRANSLATION_UNITS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")
SYSTEM_LIBRARIES = ("d2d1.lib", "d3d11.lib", "d3dcompiler.lib", "dxgi.lib", "windowscodecs.lib", "ole32.lib", "user32.lib", "gdi32.lib", "wer.lib", "dwrite.lib", "imm32.lib")
ALLOWED_IMPORTS = {
    "kernel32.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "zerosisdatabase_x64.dll", "zerosislocalization_x64.dll", "bcrypt.dll",
    "zerosislua51_x64.dll", "d2d1.dll", "windowscodecs.dll", "ole32.dll",
    "user32.dll", "gdi32.dll", "wer.dll", "d3d11.dll", "dxgi.dll", "dwrite.dll",
    "d3dcompiler_47.dll", "imm32.dll",
}


def allocate() -> tuple[str, Path, Path]:
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
        build = BUILD_ROOT / identifier
        evidence = EVIDENCE_ROOT / identifier
        try:
            build.mkdir(exist_ok=False)
            evidence.mkdir(exist_ok=False)
            return identifier, build, evidence
        except FileExistsError:
            continue
    raise RuntimeError("Could not allocate a unique UI-window host build ID")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def checked_frozen_path(path: Path, root: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    absolute.relative_to(Path(os.path.abspath(root)))
    for part in [*reversed(absolute.parents), absolute]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeError(f'Frozen input path contains a reparse point: {part}')
    return absolute


def regular_frozen_path(path: Path, root: Path):
    absolute = checked_frozen_path(path, root)
    info = absolute.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f'Frozen input is not a regular file: {absolute}')
    return info


def frozen_identity(info) -> tuple:
    # Creating another hardlink changes link count, not content or attributes.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            getattr(info, 'st_file_attributes', 0))


class FrozenInputReuse:
    """Reuse only attested build snapshots; never hardlink mutable live inputs."""

    def __init__(self, report_path: Path, donor_root: Path, target_root: Path, build_id: str):
        self.donor_root = donor_root
        self.target_root = target_root
        self.index: dict[tuple[str, int], Path] = {}
        self.used: dict[tuple[int, int], dict] = {}
        regular_frozen_path(report_path, report_path.parent)
        self.report_path = report_path
        before = digest(report_path)
        self.report_sha256 = before
        report = read_json(report_path)
        if (report.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or
                report.get('build_id') != build_id or digest(report_path) != before):
            raise RuntimeError('Frozen-input donor report is not a stable successful build')
        rows = [*report.get('compiler_inputs', []), *report.get('sources', []),
                *report.get('provider_inputs', []), *report.get('system_libraries', []),
                *report.get('provider_reports', {}).values(), *report.get('build_tools', [])]
        if report.get('ui_assets'):
            rows.append(report['ui_assets'])
        for row in rows:
            path = Path(row['path'])
            info = regular_frozen_path(path, donor_root)
            sha = row['sha256']
            if not re.fullmatch('[0-9a-f]{64}', sha) or info.st_size != row['bytes']:
                raise RuntimeError(f'Invalid frozen donor receipt: {path}')
            self.index.setdefault((sha, info.st_size), path)
        self.summary = {'donor_build_id': build_id, 'donor_report_path': str(report_path),
                        'donor_report_sha256': before, 'hardlinked_files': 0,
                        'hardlinked_bytes': 0, 'copied_files': 0, 'copied_bytes': 0,
                        'donor_content_and_metadata_preserved': False}

    def create(self, source: Path, target: Path, sha: str, size: int) -> str | None:
        checked_frozen_path(target, self.target_root)
        donor = self.index.get((sha, size))
        method = None
        if donor is not None:
            root = self.donor_root if donor.is_relative_to(self.donor_root) else self.target_root
            info = regular_frozen_path(donor, root)
            source_info = source.stat()
            if (info.st_dev, info.st_ino) == (source_info.st_dev, source_info.st_ino):
                raise RuntimeError('Frozen donor aliases the mutable source')
            if info.st_size != size or digest(donor) != sha:
                raise RuntimeError(f'Frozen donor no longer matches its receipt: {donor}')
            identity = (info.st_dev, info.st_ino)
            used = self.used.setdefault(identity, {'path': donor, 'root': root, 'sha256': sha,
                                                   'identity': frozen_identity(info),
                                                   'links_before': info.st_nlink, 'added_links': 0})
            if frozen_identity(info) != used['identity']:
                raise RuntimeError(f'Frozen donor metadata changed: {donor}')
            if info.st_dev == target.parent.stat().st_dev:
                os.link(donor, target)
                used['added_links'] += 1
                result = regular_frozen_path(target, self.target_root)
                if frozen_identity(result) != frozen_identity(info):
                    raise RuntimeError('Hardlinked frozen input changed identity')
                method = 'hardlink-attested-frozen-input'
                self.summary['hardlinked_files'] += 1
                self.summary['hardlinked_bytes'] += size
        if method is None:
            # Exclusive publication also protects against accidental overwrites.
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            shutil.copystat(source, target)
            self.summary['copied_files'] += 1
            self.summary['copied_bytes'] += size
        self.index.setdefault((sha, size), target)
        return str(donor) if method is not None else None

    def verify(self) -> None:
        if digest(self.report_path) != self.report_sha256:
            raise RuntimeError('Frozen-input donor report changed during compilation')
        for row in self.used.values():
            info = regular_frozen_path(row['path'], row['root'])
            if (frozen_identity(info) != row['identity'] or digest(row['path']) != row['sha256'] or
                    info.st_nlink != row['links_before'] + row['added_links']):
                raise RuntimeError(f'Frozen donor changed during compilation: {row["path"]}')
        self.summary['donor_content_and_metadata_preserved'] = True


FROZEN_INPUT_REUSE: FrozenInputReuse | None = None


def freeze_artifact(source: Path, target: Path) -> dict:
    source = source.resolve(strict=True)
    if FROZEN_INPUT_REUSE is not None:
        checked_frozen_path(target, FROZEN_INPUT_REUSE.target_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        raise RuntimeError(f'Frozen target already exists: {target}')
    before = digest(source)
    source_info = source.stat()
    reused_from = None
    if FROZEN_INPUT_REUSE is None:
        shutil.copy2(source, target)
    else:
        reused_from = FROZEN_INPUT_REUSE.create(source, target, before, source_info.st_size)
    after = digest(source)
    frozen = digest(target)
    if before != after or before != frozen or frozen_identity(source.stat()) != frozen_identity(source_info):
        raise RuntimeError(f"Frozen input changed while copying: {source}")
    row = {"original_path": str(source), "path": str(target), "sha256": frozen,
           "bytes": target.stat().st_size, "materialization": 'hardlink' if reused_from else 'copy'}
    if reused_from:
        row['reused_from_path'] = reused_from
    return row


def parse_dependencies(document: Path) -> list[Path]:
    root = json.loads(document.read_text(encoding="utf-8-sig"))
    data = root.get("Data", root)
    if not isinstance(data, dict) or not isinstance(data.get("Includes"), list):
        raise RuntimeError("MSVC sourceDependencies output is malformed")
    raw = [data.get("Source"), *data["Includes"]]
    rows: list[Path] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str) or not value:
            raise RuntimeError("MSVC reported an invalid compiler dependency path")
        path = Path(value)
        if not path.is_absolute():
            path = document.parent / path
        path = path.resolve(strict=True)
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            rows.append(path)
    return rows


def include_directories(env: dict[str, str]) -> tuple[list[Path], list[Path]]:
    system = []
    for raw in env.get("INCLUDE", "").split(";"):
        raw = raw.strip().strip('"')
        if raw:
            path = Path(raw).resolve(strict=True)
            if str(path).casefold() not in {str(p).casefold() for p in system}:
                system.append(path)
    sdk = [(SDK_ROOT / relative).resolve(strict=True) for relative in SDK_INCLUDE_RELS]
    return sdk, system


def owning_root(path: Path, roots: list[tuple[str, Path]]) -> tuple[str, Path, Path]:
    candidates = []
    for name, root in roots:
        try:
            relative = path.relative_to(root)
            candidates.append((len(str(root)), name, root, relative))
        except ValueError:
            pass
    if not candidates:
        raise RuntimeError(f"Compiler dependency is outside configured frozen roots: {path}")
    _, name, root, relative = max(candidates, key=lambda row: row[0])
    return name, root, relative


def freeze_dependency_closure(paths: list[Path], roots: list[tuple[str, Path]], frozen: Path) -> list[dict]:
    records = []
    seen: set[str] = set()
    for source in paths:
        name, _, relative = owning_root(source, roots)
        target = frozen / name / relative
        key = str(target).casefold()
        if key in seen:
            continue
        seen.add(key)
        row = freeze_artifact(source, target)
        row["root_name"] = name
        row["relative_path"] = str(relative)
        records.append(row)
    return records


def artifact_report(path: Path) -> dict:
    result = read_json(path)
    check_artifacts(result)
    return result


def resolve_system_libraries(env: dict[str, str], frozen: Path) -> tuple[list[Path], list[dict]]:
    search = [Path(p.strip().strip('"')).resolve() for p in env.get("LIB", "").split(";") if p.strip()]
    outputs: list[Path] = []
    records: list[dict] = []
    for name in SYSTEM_LIBRARIES:
        found = next((directory / name for directory in search if (directory / name).is_file()), None)
        if found is None:
            raise RuntimeError(f"Could not resolve required x64 system library: {name}")
        target = frozen / "libraries" / name
        record = freeze_artifact(found, target)
        record["name"] = name
        records.append(record)
        outputs.append(target)
    return outputs, records


def check_trade_route_lua_syntax() -> dict:
    # C++ compilation does not parse its embedded Lua. Use the exact shared
    # Lua 5.1 provider to reject invalid chunks before allocating a big build.
    import ctypes
    provider = artifact_report(PROVIDER_REPORTS['shared_lua'])
    library = provider['lua_dll']
    library_path = Path(library['path']).resolve(strict=True)
    if digest(library_path) != library['sha256']:
        raise RuntimeError('Shared Lua provider changed before embedded-script syntax validation')
    source = OWNED['trade_route_smoke_fixture'].read_text(encoding='utf8')
    chunks = re.findall(r'R"lua\((.*?)\)lua"', source, re.S)
    if len(chunks) != 3 or not chunks[1].rstrip().endswith('local connection='):
        raise RuntimeError('Trade-route embedded Lua assembly changed; review its syntax preflight')
    assembled = {'inventory': chunks[0], 'fresh_setup': 'local fixtureAI=0\n' + chunks[1] + '0' + chunks[2]}
    probe_source = OWNED['trade_route_fixture_probe'].read_text(encoding='utf8')
    probe_chunks = re.findall(r'R"lua\((.*?)\)lua"', probe_source, re.S)
    if len(probe_chunks) != 4:
        raise RuntimeError('Trade-route diagnostic Lua changed; review its syntax preflight')
    assembled.update({f'probe_{index}': value for index, value in enumerate(probe_chunks)})
    lua = ctypes.CDLL(str(library_path))
    lua.luaL_newstate.argtypes = []; lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]; lua.lua_close.restype = None
    for name, text in assembled.items():
        state = lua.luaL_newstate()
        if not state:
            raise RuntimeError('Cannot allocate the embedded Lua syntax-check state')
        try:
            data = text.encode('utf8')
            if lua.luaL_loadbuffer(state, data, len(data), name.encode('ascii')):
                error = lua.lua_tolstring(state, -1, None)
                raise RuntimeError('Trade-route embedded Lua syntax failed: ' + error.decode('utf8', errors='replace'))
        finally:
            lua.lua_close(state)
    return {'status': 'PASS_LUA51_SYNTAX_ONLY', 'fixture_header_sha256': digest(OWNED['trade_route_smoke_fixture']),
            'probe_header_sha256': digest(OWNED['trade_route_fixture_probe']),
            'lua_provider': library, 'chunks': list(assembled), 'scripts_executed': False}


def main() -> int:
    global FROZEN_INPUT_REUSE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-frozen-build', help='Successful prior host build ID whose attested inputs may be hardlinked')
    args = parser.parse_args()
    if args.reuse_frozen_build and not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.reuse_frozen_build):
        parser.error('Invalid frozen donor build ID')
    trade_route_syntax = check_trade_route_lua_syntax()
    # Lua runs from the generated C++ script catalog, not from the retained
    # source copies. Refresh that catalog before sealing either input so a
    # successful C++ build cannot silently execute an older Lua adapter.
    preparation_command = [sys.executable, '-B', '-X', 'utf8',
                           str(PROJECT / 'tools/prepare_ui_popup_assets.py')]
    preparation = subprocess.run(preparation_command, cwd=PROJECT, capture_output=True)
    if preparation.returncode != 0:
        raise RuntimeError('UI script catalog preparation failed: ' +
                           preparation.stderr.decode('utf8', errors='replace')[-8000:])
    missing = [str(path) for path in OWNED.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Required UI-window host input is missing: " + ", ".join(missing))

    identifier, build, evidence = allocate()
    (evidence / 'ui_asset_preparation.stdout.log').write_bytes(preparation.stdout)
    (evidence / 'ui_asset_preparation.stderr.log').write_bytes(preparation.stderr)
    frozen = build / "frozen"
    source_before = {key: digest(path) for key, path in OWNED.items()}
    prepared_ui = PROJECT / "evidence/ui_popup/assets/prepared.json"
    report: dict = {
        "trade_route_lua_syntax": trade_route_syntax,
        "schema": "zerosis.ui_window_host_build.v1", "status": "BUILDING_NOT_EXECUTED",
        "build_id": identifier, "executable": None, "gamecore_loaded": False,
        "sdk_linked": False, "stage_updated": False, "mods_updated": False,
        "host_runtime_executed": False, "source_hashes_before": source_before,
        "source_hashes_after": None, "sources": [], "compiler_inputs": [],
        "provider_reports": {}, "provider_inputs": [], "system_libraries": [],
        "ui_assets": None, "error": None,
        "ui_asset_preparation": {"command": preparation_command, "returncode": preparation.returncode,
                                 "stdout": artifact(evidence / 'ui_asset_preparation.stdout.log'),
                                 "stderr": artifact(evidence / 'ui_asset_preparation.stderr.log')},
    }
    build_report = evidence / "build_result.json"

    def checkpoint() -> None:
        temp = build_report.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        temp.replace(build_report)

    checkpoint()
    try:
        if args.reuse_frozen_build:
            FROZEN_INPUT_REUSE = FrozenInputReuse(
                EVIDENCE_ROOT / args.reuse_frozen_build / 'build_result.json',
                BUILD_ROOT / args.reuse_frozen_build / 'frozen', frozen, args.reuse_frozen_build)
            report['frozen_input_reuse'] = FROZEN_INPUT_REUSE.summary
        frozen_sources = {}
        for key, source in OWNED.items():
            relative = source.relative_to(PROJECT)
            target = frozen / "project" / relative
            row = freeze_artifact(source, target)
            row["role"] = key
            frozen_sources[key] = target
            report["sources"].append(row)

        provider_rows = {}
        expected_provider_status = {
            "database": "SDK_DATABASE_X64_COMPONENT_BUILT",
            "localization": "SDK_LOCALIZATION_X64_CANDIDATE_BUILT",
            "shared_lua": "SHARED_LUA_RUNTIME_CANDIDATE_BUILT",
            "streams": "X64_STREAM_PROVIDER_BUILT_NOT_YET_ACCEPTED",
            "temp_heap": "TEMP_HEAP_PROVIDERS_BUILT",
        }
        for key, source in PROVIDER_REPORTS.items():
            provider = artifact_report(source)
            if provider.get("status") != expected_provider_status[key]:
                raise RuntimeError(f"Unexpected provider report status for {key}: {provider.get('status')!r}")
            target = frozen / "provider_reports" / f"{key}.json"
            row = freeze_artifact(source, target)
            report["provider_reports"][key] = row
            provider_rows[key] = provider

        if provider_rows["shared_lua"].get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
            raise RuntimeError("The selected shared Lua runtime is not a built candidate")
        libraries = [
            provider_rows["database"]["library"], provider_rows["localization"]["library"],
            provider_rows["shared_lua"]["lua_library"], provider_rows["streams"]["library"],
            *provider_rows["temp_heap"]["x64"]["libraries"],
        ]
        check_artifacts(libraries)
        frozen_libraries = []
        for index, item in enumerate(libraries):
            source = Path(item["path"]).resolve(strict=True)
            target = frozen / "libraries" / f"{index:02d}_{source.name}"
            row = freeze_artifact(source, target)
            if row["sha256"] != item["sha256"]:
                raise RuntimeError(f"Provider import library changed after its report was written: {source}")
            row["role"] = f"provider_{index}"
            frozen_libraries.append(target)
            report["provider_inputs"].append(row)

        env, compiler_text = environment_for(VS, "x64", build)
        compiler = Path(compiler_text).resolve(strict=True)
        env["VSLANG"] = "1033"
        sdk_include, system_include = include_directories(env)
        project_root = PROJECT.resolve(strict=True)
        sdk_root = SDK_ROOT.resolve(strict=True)
        roots = [("project", project_root), ("sdk", sdk_root)]
        roots.extend((f"system_{index:02d}", path) for index, path in enumerate(system_include))
        system_libraries, system_library_records = resolve_system_libraries(env, frozen)
        report["system_libraries"] = system_library_records
        if prepared_ui.is_file():
            report["ui_assets"] = freeze_artifact(prepared_ui, frozen / "ui_assets" / "prepared.json")

        common = [
            "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict",
            "/source-charset:windows-1252", "/external:W0", "/DWIN32", "/DNDEBUG",
            "/DFINAL_RELEASE", "/D_CRT_SECURE_NO_WARNINGS", "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
            "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING", "/D_WIN32_WINNT=0x0A00", "/DNOMINMAX",
            "/DWIN32_LEAN_AND_MEAN", "/DZEROSIS_SHARED_LUA_RUNTIME=1", "/DLUA_BUILD_AS_DLL",
            "/DZEROSIS_NEW_GAME_TRACE=1", "/DZEROSIS_UI_WINDOW_PRESENTATION=1",
            "/DZEROSIS_WORLD_TERRAIN=1",
        ]
        include_flags = [f'/external:I"{path}"' for path in sdk_include]
        include_flags += [f'/I"{path}"' for path in PROJECT_INCLUDE_DIRS]
        preliminary = build / "dependency_discovery"
        preliminary.mkdir()
        source_paths = [OWNED[key] for key in TRANSLATION_UNITS]
        discovery_docs: dict[str, Path] = {}
        discovery_records = []
        dependencies_by_tu: dict[str, list[Path]] = {}
        for index, (key, source) in enumerate(zip(TRANSLATION_UNITS, source_paths)):
            tu_dir = preliminary / f"tu_{index:02d}_{key}"
            tu_dir.mkdir()
            tu_obj = tu_dir / "obj"
            tu_obj.mkdir()
            tu_doc = tu_dir / f"{key}.sourceDependencies.json"
            tu_rsp = tu_dir / f"{key}.discover.rsp"
            tu_common = ["/std:c++17" if key == "terrain_renderer" and flag == "/std:c++14" else
                         "/source-charset:utf-8" if key == "world_renderer" and flag == "/source-charset:windows-1252" else flag for flag in common]
            flags = [*tu_common, *include_flags, "/c", f'"{source}"', f'/Fo"{tu_obj.as_posix()}/"',
                     f'/sourceDependencies "{tu_doc}"']
            tu_rsp.write_text("\n".join(flags) + "\n", encoding="utf-8", newline="\n")
            result = run([str(compiler), f"@{tu_rsp}"], cwd=tu_dir, env=env, timeout=300)
            tu_log = evidence / f"dependency_discovery_{key}.log"
            tu_log.write_bytes(result.stdout + result.stderr)
            output = tu_log.read_bytes().decode("mbcs", errors="replace")
            discovery_records.append({
                "translation_unit": key, "response": artifact(tu_rsp), "log": artifact(tu_log),
                "dependency_report": artifact(tu_doc) if tu_doc.is_file() else None,
                "returncode": result.returncode, "objects": [artifact(path) for path in tu_obj.glob("*.obj")],
            })
            if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
                raise RuntimeError(f"Dependency discovery failed or warned for {key}: " + output[-5000:])
            dependencies_by_tu[key] = parse_dependencies(tu_doc)
            discovery_docs[key] = tu_doc
        report["dependency_discovery"] = {"translation_units": discovery_records}
        checkpoint()
        dependencies = []
        seen_dependencies: set[str] = set()
        for key in TRANSLATION_UNITS:
            for path in dependencies_by_tu[key]:
                identity = str(path).casefold()
                if identity not in seen_dependencies:
                    seen_dependencies.add(identity)
                    dependencies.append(path)
        frozen_deps = freeze_dependency_closure(dependencies, roots, frozen / "include_roots")
        by_original = {row["original_path"].casefold(): row for row in frozen_deps}
        if len(by_original) != len(dependencies):
            raise RuntimeError("Compiler dependency closure has duplicate or unmapped inputs")
        report["compiler_inputs"] = frozen_deps

        mirrored_project = frozen / "include_roots/project"
        mirrored_sdk = frozen / "include_roots/sdk"
        frozen_sdk_includes = [mirrored_sdk / relative for relative in SDK_INCLUDE_RELS]
        frozen_project_includes = [mirrored_project / path.resolve().relative_to(project_root)
                                   for path in PROJECT_INCLUDE_DIRS]
        frozen_system_includes = [frozen / "include_roots" / f"system_{index:02d}"
                                  for index, _ in enumerate(system_include)]
        final_env = dict(env)
        final_env["INCLUDE"] = ";".join(str(path) for path in frozen_system_includes)
        frozen_sources_final = {}
        for key in TRANSLATION_UNITS:
            original = OWNED[key].resolve(strict=True)
            row = by_original.get(str(original).casefold())
            if row is None:
                raise RuntimeError(f"Primary source is absent from compiler closure: {original}")
            frozen_sources_final[key] = Path(row["path"])
        final_dir = build / "final"
        final_dir.mkdir()
        final_docs: dict[str, Path] = {}
        final_responses: dict[str, Path] = {}
        final_compile_records = []
        objects_by_tu: dict[str, Path] = {}
        for index, key in enumerate(TRANSLATION_UNITS):
            tu_dir = final_dir / f"tu_{index:02d}_{key}"
            tu_dir.mkdir()
            object_dir = tu_dir / "obj"
            object_dir.mkdir()
            final_doc = tu_dir / f"{key}.sourceDependencies.json"
            response = tu_dir / f"{key}.compile.rsp"
            final_docs[key] = final_doc
            final_responses[key] = response
            tu_common = ["/std:c++17" if key == "terrain_renderer" and flag == "/std:c++14" else
                         "/source-charset:utf-8" if key == "world_renderer" and flag == "/source-charset:windows-1252" else flag for flag in common]
            flags = [*tu_common, *(f'/external:I"{p}"' for p in frozen_sdk_includes),
                     *(f'/I"{p}"' for p in frozen_project_includes),
                     *(f'/I"{p}"' for p in frozen_system_includes), "/c",
                     f'"{frozen_sources_final[key]}"', f'/Fo"{object_dir.as_posix()}/"',
                     f'/sourceDependencies "{final_doc}"']
            response.write_text("\n".join(flags) + "\n", encoding="utf-8", newline="\n")
            result = run([str(compiler), f"@{response}"], cwd=tu_dir, env=final_env, timeout=300)
            log = evidence / f"compile_{key}.log"
            log.write_bytes(result.stdout + result.stderr)
            output = log.read_bytes().decode("mbcs", errors="replace")
            final_compile_records.append({"translation_unit": key, "response": artifact(response),
                                          "log": artifact(log), "returncode": result.returncode,
                                          "dependency_report": artifact(final_doc) if final_doc.is_file() else None})
            if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
                raise RuntimeError(f"Final frozen-input compile failed or warned for {key}: " + output[-6000:])
            final_deps = parse_dependencies(final_doc)
            # parse_dependencies and freeze_dependency_closure already resolve
            # every original path. Reuse that checked identity map rather than
            # repeating filesystem resolution for every pair of includes.
            expected = {str(Path(by_original[str(dep).casefold()]["path"]).resolve()).casefold()
                        for dep in dependencies_by_tu[key]}
            actual = {str(path).casefold() for path in final_deps}
            if actual != expected:
                raise RuntimeError(f"Final {key} compile consumed a different dependency closure")
            tu_objects = list(object_dir.glob("*.obj"))
            if len(tu_objects) != 1:
                raise RuntimeError(f"Expected one private object for {key}, found {len(tu_objects)}")
            objects_by_tu[key] = tu_objects[0]
        objects = [objects_by_tu[key] for key in TRANSLATION_UNITS]
        compile_log = evidence / "compile.log"
        compile_log.write_text("Per-translation-unit compilation passed without warnings.\n", encoding="utf-8")
        final_doc = final_docs["host_main"]
        response = final_responses["host_main"]
        report["final_compilation"] = {"translation_units": final_compile_records}
        output_exe = final_dir / "ZeroSisHost_x64.exe"
        map_file = final_dir / "ZeroSisHost_x64.map"
        link = shutil.which("link.exe", path=env.get("PATH"))
        if not link:
            raise RuntimeError("MSVC linker is unavailable")
        link_rsp = final_dir / "link.rsp"
        link_flags = [*(f'"{p}"' for p in objects), *(f'"{p}"' for p in frozen_libraries),
                      *(f'"{p}"' for p in system_libraries), f'/OUT:"{output_exe}"',
                      f'/MAP:"{map_file}"', "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro",
                      "/WX", "/OPT:REF", "/OPT:ICF", "/SUBSYSTEM:CONSOLE"]
        link_rsp.write_text("\n".join(link_flags) + "\n", encoding="utf-8", newline="\n")
        link_result = run([link, f"@{link_rsp}"], cwd=final_dir, env=final_env, timeout=300)
        link_log = evidence / "link.log"
        link_log.write_bytes(link_result.stdout + link_result.stderr)
        link_text = link_log.read_bytes().decode("mbcs", errors="replace")
        if link_result.returncode or re.search(r"\bwarning\s+LNK\d+", link_text, re.I):
            raise RuntimeError("Private host link failed or warned: " + link_text[-6000:])
        dumpbin = compiler.with_name("dumpbin.exe")
        imports_result = checked_run([dumpbin, "/dependents", output_exe], cwd=final_dir, env=final_env)
        imports_log = evidence / "imports.log"
        imports_log.write_bytes(imports_result.stdout + imports_result.stderr)
        imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$",
                             imports_result.stdout.decode("ascii", errors="replace"), re.M | re.I)
        unknown = [name for name in imports if name.casefold() not in ALLOWED_IMPORTS and
                   not name.casefold().startswith("api-ms-win-crt-")]
        if not imports or unknown or "zerosislua51_x64.dll" not in {name.casefold() for name in imports}:
            raise RuntimeError("Private host import audit failed: " + repr({"imports": imports, "unknown": unknown}))

        source_after = {key: digest(path) for key, path in OWNED.items()}
        if source_before != source_after:
            raise RuntimeError("Owned host, presenter, or builder input changed during compilation")
        provider_after = {key: digest(path) for key, path in PROVIDER_REPORTS.items()}
        provider_expected = {key: row["sha256"] for key, row in report["provider_reports"].items()}
        if provider_after != provider_expected:
            raise RuntimeError("A provider report changed during the isolated host build")
        dependency_hashes_after = {}
        for row in frozen_deps:
            original = Path(row["original_path"]).resolve(strict=True)
            current = digest(original)
            if current != row["sha256"]:
                raise RuntimeError(f"Compiler dependency changed after it was frozen: {original}")
            dependency_hashes_after[str(original)] = current
        if report["ui_assets"] and digest(prepared_ui) != report["ui_assets"]["sha256"]:
            raise RuntimeError("Prepared UI asset report changed during the host build")
        if FROZEN_INPUT_REUSE is not None:
            FROZEN_INPUT_REUSE.verify()

        source_rows = []
        source_row_keys: set[str] = set()
        for row in frozen_deps:
            path = Path(row["path"])
            try:
                relative = path.relative_to(mirrored_project)
            except ValueError:
                continue
            if str(relative).replace("/", "\\").casefold().startswith(("source\\host\\", "source\\presentation\\")):
                source_rows.append({"original_source": row["original_path"], "path": str(path),
                                    "sha256": row["sha256"], "bytes": row["bytes"],
                                    "relative_path": str(relative)})
                source_row_keys.add(str(Path(row["original_path"]).resolve()).casefold())
        # Preserve explicit Host/presentation contract inputs even when they are Lua metadata
        # or generated headers not directly reached by the C++ include graph.
        for key, original in OWNED.items():
            if key in ("builder", "host_builder"):
                continue
            frozen_path = frozen_sources[key]
            identity = str(original.resolve()).casefold()
            if identity in source_row_keys:
                continue
            if original.parent.name.casefold() not in ("host", "presentation"):
                continue
            source_rows.append({"original_source": str(original.resolve()), "path": str(frozen_path),
                                "sha256": digest(frozen_path), "bytes": frozen_path.stat().st_size,
                                "relative_path": str(original.resolve().relative_to(PROJECT.resolve()))})
            source_row_keys.add(identity)
        source_names = [Path(row["path"]).name.casefold() for row in source_rows]
        if len(source_names) != len(set(source_names)):
            raise RuntimeError("Host snapshot sources contain duplicate basenames that the runner cannot materialize safely")
        report.update({
            "status": "UI_WINDOW_HOST_CANDIDATE_BUILT",
            "source_hashes_after": source_after,
            "provider_report_hashes_after": provider_after,
            "source_inputs_unchanged": True,
            "provider_inputs_unchanged": True,
            "sources": source_rows,
            "compiler": artifact(compiler),
            "compiler_version": "MSVC x64, C++14, /O2, /MD",
            "linker": artifact(Path(link).resolve(strict=True)),
            "dumpbin": artifact(dumpbin.resolve(strict=True)),
            "toolchain": {"target": "x64", "language": "C++14", "optimization": "/O2",
                          "runtime": "/MD", "brepro": True, "pch_used": False},
            "response": artifact(response),
            "dependency_report": artifact(final_doc),
            "dependency_discovery_reports": {key: artifact(path) for key, path in discovery_docs.items()},
            "final_dependency_reports": {key: artifact(path) for key, path in final_docs.items()},
            "compile_log": artifact(compile_log),
            "link_response": artifact(link_rsp),
            "link_log": artifact(link_log),
            "map": artifact(map_file),
            "executable": {**artifact(output_exe), "pe": pe_header(output_exe)},
            "imports": {"dependencies": imports, "log": artifact(imports_log)},
            "libraries": report["provider_inputs"] + report["system_libraries"],
            "shared_lua_build": report["provider_reports"]["shared_lua"],
            "window_sources": [row for row in source_rows if "Source\\Presentation\\" in row["original_source"]],
            "system_include_roots": [str(path) for path in system_include],
            "system_library_names": list(SYSTEM_LIBRARIES),
            "build_tools": [
                next(row for row in report["sources"] if row["role"] == "builder"),
                next(row for row in report["sources"] if row["role"] == "host_builder"),
            ],
            "definitions": ["ZEROSIS_SHARED_LUA_RUNTIME=1", "LUA_BUILD_AS_DLL",
                            "ZEROSIS_NEW_GAME_TRACE=1", "ZEROSIS_UI_WINDOW_PRESENTATION=1", "ZEROSIS_WORLD_TERRAIN=1"],
            "compiler_dependency_count": len(frozen_deps),
            "compiler_dependency_live_hashes_after": dependency_hashes_after,
            "gamecore_loaded": False, "sdk_linked": False, "stage_updated": False,
            "mods_updated": False, "host_runtime_executed": False,
            "scope": "private shared-Lua host plus bitmap presenter build only; no SDK link/build or GameCore execution",
        })
        checkpoint()
    except Exception as error:
        report["status"] = "UI_WINDOW_HOST_BUILD_FAILED"
        report["error"] = str(error)
        report["source_hashes_after"] = {key: digest(path) for key, path in OWNED.items() if path.is_file()}
        checkpoint()
        print(json.dumps({"status": report["status"], "build_id": identifier,
                          "report": str(build_report), "error": report["error"]}, ensure_ascii=False), flush=True)
        return 1

    checkpoint()
    print(json.dumps({"status": report["status"], "build_id": identifier,
                      "report": str(build_report), "report_sha256": digest(build_report),
                      "executable": report["executable"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
