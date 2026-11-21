"""Retire superseded private component runs and generated review copies.

Preview first, then apply that exact ledger. Current runtime dependencies, the
newest component baseline, sources, tools, tests and all saved games survive.
This is the 2026-10-05 cleanup baseline, not an unattended deletion policy.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'evidence/storage_cleanup/20261005T130800Z_6219606ef78e/plan.json'
OUT = ROOT / 'evidence/storage_cleanup_components'
RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{10,12}')
STAMP = re.compile(r'\d{8}T\d{6}Z')
# Exact successful baselines; refresh them before retiring any newer work.
TIMESTAMP_FAMILIES = {
    'native_granny_bridge': {
        'groups': ('Build/GrannyAnimationBridge', 'evidence/granny_animation_bridge'),
        'keep': '20261005T113900Z', 'report_group': 'evidence/granny_animation_bridge',
        'report': 'report.json', 'status': 'PASS_NATIVE_GRANNY_C_ABI_X64'},
    'world_terrain_and_gpu_publication': {
        'groups': ('Build/terrain_renderer_validation',),
        'keep': '20261005T125302Z', 'report_group': 'Build/terrain_renderer_validation',
        'report': 'manifest.json', 'status': 'PASS_COMPONENT_CONTRACT'},
    'original_unit_animation': {
        'groups': ('Build/UnitAnimation', 'evidence/unit_animation'),
        'keep': '20261005T124200Z', 'report_group': 'evidence/unit_animation',
        'report': 'report.json', 'status': 'PASS_UNIT_ANIMATION'},
    'granny_curve_sample': {
        'groups': ('Build/GrannyAnimationProbe', 'evidence/granny_animation'),
        'keep': '20261005T105701Z', 'report_group': 'evidence/granny_animation',
        'report': 'report.json', 'status': 'PASS_PUBLIC_CURVE_SAMPLE_X64'},
}
PAIRS = {
    'SaveRestoreSDK': 'save_restore_sdk', 'ExploreSDK': 'explore_sdk',
    'CitySiteSDK': 'city_site_sdk', 'CitySiteSdkCommit': 'city_site_sdk_commit',
    'CitySiteScoreBridgeBoundary': 'city_site_score_bridge',
    'FoundValueSharedScores': 'found_value_shared_scores',
    'FoundValueSharedBridge': 'found_value_shared_bridge',
    'FoundValueScoreBridge': 'found_value_score_bridge', 'FoundValueSDK': 'found_value_sdk',
    'FoundValueSdkCapture': 'found_value_sdk_capture',
    'FoundValueSharedSdkCapture': 'found_value_shared_sdk_capture',
    'FoundValueCpuCapture': 'found_value_cpu_capture',
    'CitySiteCpuCapture': 'city_site_cpu_capture',
    'BitmapRenderer': 'bitmap_renderer', 'LocalUnitCommands': 'local_unit_commands',
    'LocalUnitSelection': 'local_unit_selection',
    'LocalCityDecisionCommands': 'local_city_decision_commands',
    'LocalFoundMission': 'local_found_mission',
    'LocalFoundSessionGuards': 'local_found_session_guards',
    'UiInputDispatch': 'ui_input_dispatch', 'UiPopupFailure': 'ui_popup_failure',
    'UiPopupPixels': 'ui_popup_pixels', 'UiPresentationInput': 'ui_presentation_input',
}
EVIDENCE_ONLY = ('ui_scene_component', 'host_combat_presentation', 'city_site_scores',
                 'found_value_sdk_runtime', 'local_unit_selection', 'local_unit_commands',
                 'research_command_guard', 'ui_snapshot_json_component', 'city_site_runtime',
                 'city_site_cpu_trace', 'city_site_trace_parser', 'city_site_cpu_capture_regressions',
                 'found_value_comparator', 'found_value_default_environment', 'extended_turns')
STAGES = ('Bootstrap', 'Construction', 'DatabaseCache', 'DatabaseLoader', 'DatabasePostprocess',
          'Debug', 'FileSystem', 'FractalNumeric', 'GameCore_x64', 'GCLifecycle', 'GlobalsCleanup',
          'HostBinding', 'HostExceptionBoundary', 'InfoCleanup', 'Localization', 'LocalizationICU',
          'LocalizationValues', 'Logging', 'LuaBorrowed', 'LuaEnums', 'LuaFractal', 'LuaRegistration',
          'StartupOwners', 'WorldBuilderMapBridge', 'WorldBuilderMapFiles', 'WorldBuilderMapObject',
          'WorldBuilderModData', 'WorldBuilderTypes')
NESTED = ('evidence/interactive_game/validators',)
REPORTS = ('build_result.json', 'conformance.json', 'result.json', 'report.json')

spec = importlib.util.spec_from_file_location('primary_pruner', ROOT / 'tools/prune_superseded_runtime_artifacts.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
require = P.require


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def runs(root):
    return {p.name: p for p in root.iterdir() if p.is_dir() and RUN.fullmatch(p.name)} if root.is_dir() else {}


def report_paths(directory):
    return [directory / name for name in REPORTS if (directory / name).is_file()]


_indexed_protected = None
_protected_ancestors = set()


def overlaps(path, protected):
    global _indexed_protected, _protected_ancestors
    if protected is not _indexed_protected:
        _indexed_protected = protected
        _protected_ancestors = set(protected)
        for item in protected:
            for ancestor in item.parents:
                _protected_ancestors.add(ancestor)
                if ancestor == ROOT:
                    break
    return path in _protected_ancestors or any(p in protected for p in path.parents)


def allowed(path):
    path = P.boundary(path)
    parts = path.relative_to(ROOT).parts
    ok = len(parts) == 3 and RUN.fullmatch(parts[2]) and (
        (parts[0] == 'Build' and parts[1] in PAIRS) or
        (parts[0] == 'evidence' and parts[1] in {*PAIRS.values(), *EVIDENCE_ONLY, 'new_game', 'first_turn'}))
    ok = ok or (len(parts) == 2 and parts[0] == 'Stage' and parts[1] in STAGES)
    ok = ok or path.relative_to(ROOT).as_posix() in NESTED
    ok = ok or (parts[:3] == ('evidence', 'bootstrap', 'static_initialization') and
                len(parts) == 4 and re.fullmatch(r'(GameCore|Database|Localization)_[0-9a-f]{16}_disassembly\.(log|json)', parts[3]))
    timestamp_groups = {group for family in TIMESTAMP_FAMILIES.values() for group in family['groups']}
    ok = ok or (len(parts) == 3 and STAMP.fullmatch(parts[2]) and '/'.join(parts[:2]) in timestamp_groups)
    require(ok, 'Outside reviewed component scope: ' + str(path))
    return path


def hashes(paths):
    cache, result = {}, {}
    for path in sorted(paths):
        info = P.regular(P.boundary(path))
        key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if key not in cache:
            cache[key] = P.digest(path)
        result[str(path)] = cache[key]
    return result


def plan():
    P.no_active_host()
    base = read(BASE)
    require(base['latest_host_build'] == P.BUILD and base['latest_runtime_pair'] == P.LATEST,
            'Runtime retention baseline changed; review before reuse')
    seeds = [Path(s) for s in base['seed_documents']]
    families = [(ROOT / 'Build' / b, ROOT / 'evidence' / e) for b, e in PAIRS.items()]
    families += [(ROOT / 'evidence' / e,) for e in EVIDENCE_ONLY if e not in PAIRS.values()]
    latest, possible = {}, set()
    for family in families:
        members = {p.name: p for group in family for p in runs(group).values()}
        if not members:
            continue
        newest = max(members)
        latest['|'.join(str(x.relative_to(ROOT)) for x in family)] = newest
        for group in family:
            for name, directory in runs(group).items():
                if name == newest:
                    seeds.extend(report_paths(directory))
                else:
                    possible.add(directory)
    for family in TIMESTAMP_FAMILIES.values():
        newest = family['keep']
        report = ROOT / family['report_group'] / newest / family['report']
        require(read(report)['status'] == family['status'], 'Timestamp baseline is not successful: ' + str(report))
        seeds.append(report)
        latest['|'.join(family['groups'])] = newest
        for group in family['groups']:
            directory = ROOT / group
            if not directory.is_dir():
                continue
            for child in directory.iterdir():
                if not child.is_dir() or not STAMP.fullmatch(child.name):
                    continue
                require(child.name <= newest, 'Newer component needs refreshed retention baseline: ' + str(child))
                if child.name != newest:
                    possible.add(child)
    seeds.append(ROOT / 'evidence/bootstrap/static_initialization/inventory.json')
    protected, documents = P.closure(seeds)
    print(json.dumps({'phase': 'dependency_closure', 'files': len(protected), 'documents': len(documents)}), flush=True)
    # Protect every file in the newest component runs, including raw ETL traces.
    for family, newest in latest.items():
        for group in family.split('|'):
            directory = ROOT / group / newest
            if directory.is_dir():
                for path, _ in P.inventory(directory):
                    protected[str(path)] = None
    for directory in ('Source', 'Tests', 'tools'):
        for path, _ in P.inventory(ROOT / directory):
            protected[str(path)] = None
    for area in ('Build', 'evidence'):
        for path in (ROOT / area).rglob('*.zssave'):
            protected[str(P.boundary(path))] = None
    print(json.dumps({'phase': 'current_sources_and_saves', 'files': len(protected)}), flush=True)
    # Old failed new-game/first-turn reports are replaced by the retained pair.
    for group in ('new_game', 'first_turn'):
        possible.update(runs(ROOT / 'evidence' / group).values())
    for rel in NESTED:
        path = ROOT / rel
        if path.is_dir():
            possible.add(path)
    static = ROOT / 'evidence/bootstrap/static_initialization'
    possible.update(p for p in static.iterdir() if re.fullmatch(
        r'(GameCore|Database|Localization)_[0-9a-f]{16}_disassembly\.(log|json)', p.name))
    stage_review = []
    for name in STAGES:
        path = ROOT / 'Stage' / name
        manifest = path / 'review_bundle.json'
        if not manifest.is_file():
            continue
        data = read(manifest)
        rows = data.get('files', [])
        require(rows and all(isinstance(row, dict) and row.get('source') for row in rows),
                'Unmapped review copy: ' + str(path))
        for row in rows:
            source = P.boundary(Path(row['source']))
            target = P.boundary(Path(row['path']))
            require(target.is_relative_to(path) and source.is_file() and target.is_file(),
                    'Review copy source/target missing or outside directory')
            require(P.digest(target) == row['sha256'], 'Review copy was edited: ' + str(target))
            if not source.is_relative_to(ROOT / 'Stage'):
                protected[str(source)] = None
        possible.add(path)
        stage_review.append({'path': str(path.relative_to(ROOT)), 'status': data.get('status'),
                             'mapped_files': len(rows), 'sources_exist': True, 'copy_hashes_match_manifest': True})
    print(json.dumps({'phase': 'review_copies_checked', 'groups': len(stage_review)}), flush=True)
    keep = {Path(p) for p in protected}
    targets = sorted(allowed(p) for p in possible if not overlaps(p, keep))
    require(targets, 'No superseded component artifacts remain')
    for i, path in enumerate(targets):
        require(not any(path.is_relative_to(q) or q.is_relative_to(path) for q in targets[:i]),
                'Overlapping cleanup targets')
    output = OUT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    output.mkdir(parents=True)
    protected = hashes(keep)
    protected_file = output / 'protected.json.gz'
    with gzip.open(protected_file, 'wt', encoding='utf8') as f:
        json.dump(protected, f, separators=(',', ':'))
    print(json.dumps({'phase': 'protected', 'files': len(protected), 'documents': len(documents)}), flush=True)
    ledger = output / 'retired-files.jsonl.gz'
    rows, count, total, identities = [], 0, 0, {}
    with gzip.open(ledger, 'wt', encoding='utf8') as f:
        for i, target in enumerate(targets):
            n = size = 0
            items = P.inventory(target) if target.is_dir() else [(target, P.regular(target))]
            for path, info in items:
                key = (info.st_dev, info.st_ino)
                item = identities.setdefault(key, {'links': info.st_nlink, 'count': 0, 'stored': P.stored(path)})
                item['count'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'bytes': info.st_size, 'sha256': P.digest(path),
                       'mtime_ns': info.st_mtime_ns, 'device': info.st_dev, 'file_id': info.st_ino}
                f.write(json.dumps(row, separators=(',', ':')) + '\n')
                n += 1
                size += info.st_size
            rows.append({'path': str(target.relative_to(ROOT)), 'is_directory': target.is_dir(), 'files': n, 'bytes': size})
            count += n
            total += size
            if (i + 1) % 50 == 0:
                print(json.dumps({'phase': 'inventory', 'targets': i + 1, 'files': count}), flush=True)
    result = {'status': 'PREVIEW_ONLY', 'root': str(ROOT), 'files': count, 'logical_bytes': total,
              'estimated_reclaimable_bytes': sum(v['stored'] for v in identities.values() if v['links'] == v['count']),
              'targets': rows, 'retained_latest': latest, 'stage_review': stage_review,
              'protected_count': len(protected), 'baseline': {'path': str(BASE), 'sha256': P.digest(BASE)},
              'protected': {'path': str(protected_file), 'sha256': P.digest(protected_file)},
              'ledger': {'path': str(ledger), 'sha256': P.digest(ledger)},
              'script_sha256': P.digest(Path(__file__)),
              'historical_raw_evidence_retired': True, 'source_and_user_saves_preserved': True}
    destination = output / 'plan.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'plan': str(destination), 'files': count, 'targets': len(rows),
                      'gib': round(total / 2**30, 4)}, ensure_ascii=False), flush=True)


def verify_protected(protected):
    actual = hashes({Path(p) for p in protected})
    require(actual == protected, 'Protected source/runtime/save content changed')


def apply(path):
    P.no_active_host()
    path = P.boundary(path)
    require(path.is_relative_to(OUT) and path.name == 'plan.json', 'Plan outside cleanup reports')
    output = path.parent / 'cleanup.json'
    require(not output.exists(), 'Plan already started; do not replay')
    plan = read(path)
    require(plan['status'] == 'PREVIEW_ONLY' and plan['root'] == str(ROOT), 'Wrong plan root/status')
    require(plan['script_sha256'] == P.digest(Path(__file__)), 'Cleanup script changed after review')
    for key in ('ledger', 'protected', 'baseline'):
        p = P.boundary(Path(plan[key]['path']))
        require(P.digest(p) == plan[key]['sha256'], 'Cleanup input changed')
    targets = [allowed(ROOT / row['path']) for row in plan['targets']]
    with gzip.open(plan['protected']['path'], 'rt', encoding='utf8') as f:
        protected = json.load(f)
    keep = {Path(p) for p in protected}
    require(not any(overlaps(p, keep) for p in targets), 'Protected files intersect targets')
    verify_protected(protected)
    result = {'status': 'REMOVING', 'plan_sha256': P.digest(path), 'removed_files': 0, 'removed_logical_bytes': 0,
              'protected_hashes_verified_before': True, 'errors': []}
    def checkpoint():
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    checkpoint()
    try:
        with gzip.open(plan['ledger']['path'], 'rt', encoding='utf8') as f:
            for line in f:
                row = json.loads(line)
                p = P.boundary(ROOT / row['path'])
                require(any(p == t or p.is_relative_to(t) for t in targets), 'File outside exact targets')
                info = P.regular(p)
                require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                        (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), 'Retired file identity changed')
                require(P.digest(p) == row['sha256'], 'Retired content changed')
                P.unlink_without_attribute_changes(p)
                require(not p.exists(), 'Retired file remains')
                result['removed_files'] += 1
                result['removed_logical_bytes'] += row['bytes']
                if result['removed_files'] % 1000 == 0:
                    checkpoint()
                    print(json.dumps({'phase': 'delete', 'files': result['removed_files'], 'planned': plan['files']}), flush=True)
        for row, target in zip(plan['targets'], targets):
            if row['is_directory']:
                for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
                    require(not files, 'Unplanned file remains in target')
                    P.boundary(Path(current)).rmdir()
            require(not target.exists(), 'Retired target remains')
        verify_protected(protected)
        require(result['removed_files'] == plan['files'], 'Deletion count differs')
        result.update(status='PASS_SUPERSEDED_COMPONENT_RETIREMENT', protected_hashes_verified_after=True,
                      removed_targets=len(targets), source_and_user_saves_preserved=True)
    except Exception as e:
        result['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
        result['errors'].append(type(e).__name__ + ': ' + str(e))
        raise
    finally:
        checkpoint()
        print(json.dumps({**result, 'report': str(output)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', type=Path)
    args = parser.parse_args()
    apply(args.apply) if args.apply else plan()
