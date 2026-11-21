"""Plan/apply a bounded file-only presentation overlay to one fresh audited run."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, base64, gzip, hashlib, json, os, sys
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path[:0] = [str(PROJECT / 'tools'), str(STAGE)]
import build_exit_confirm_host as common
from menu_suite_storage import storage
from verify_assets import EXPECTED, HOST, SDK
import prune_superseded_runtime_artifacts as deletion

BASE = STAGE / 'base_preparation_retry01/20261115T093013Z_23c5037b12b9/materialization/result.json'
OLD = PROJECT / 'Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db'
ORIGINAL = PROJECT / 'evidence/world_terrain_original/phase6/compiled_asset_binding.json'
OUT = STAGE / 'overlay'
DELETER_SHA = 'e7dc5a356deba20add2482c4109f5e78775b48480c5ea81e483289e97f3b3678'
assert hashlib.sha256((PROJECT / 'tools/prune_superseded_runtime_artifacts.py').read_bytes()).hexdigest() == DELETER_SHA


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def ref(path):
    return common.artifact(Path(path).absolute())


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def same(expected, *, links=True):
    actual = ref(expected['path'])
    keys = ['bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes'] + (['links'] if links else [])
    assert all(actual[key] == expected[key] for key in keys), expected['path']
    return actual


def ordinary_bound(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    assert path.is_relative_to(root) and path != root
    for parent in (path, *path.parents):
        if parent.exists():
            assert not parent.lstat().st_file_attributes & 0x400
    return path


def plan():
    assert not (OUT / 'plan.json').exists()
    base = read(BASE)
    assert base['status'] == 'PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED'
    assert base['native_attempts'] == 0 and base['new_game_only'] and not base['host_or_sdk_executed']
    assert base['host_build_id'] == '20261115T093013Z_23c5037b12b9' and base['host']['sha256'] == HOST and base['gamecore']['sha256'] == SDK
    run = base['run_id']
    root = PROJECT / 'Build/InteractiveGameRuntime' / run
    assert run == '20261115T101941Z_99b3c393ee9a' and not (root / 'sessions').exists()
    assert not (root / 'WorldAssets').exists() and not list(root.glob('interactive-ui-*.json'))
    request = Path(base['request']['path'])
    assert request == PROJECT / 'evidence/interactive_game' / run / 'request.json'
    assert ref(request)['sha256'] == base['request']['sha256']
    document = read(request)
    assert len(document['runtime_inputs']) == 24 and document['smoke'] is False and document['resume_from'] is None
    current = read(ORIGINAL)
    packages = {}
    for role, (name, digest, magic) in EXPECTED.items():
        source = ref(current['packages'][role]['path'])
        assert source['sha256'] == digest and source['file_attributes'] == 32
        with Path(source['path']).open('rb') as stream:
            assert stream.read(8) == magic
        target = ordinary_bound(root / name, root)
        assert source['file_identity'][0] == root.stat().st_dev
        packages[role] = dict(source=source, target_path=str(target), method='hardlink',
            read_only=False, immutability_policy='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE')
    support_names = ['interactive_ui_support/assets/prepared.json', 'interactive_ui_support/assets/inline_icons.json']
    support_names += ['interactive_ui_support/tools/' + path.name for path in sorted((OLD / 'interactive_ui_support/tools').glob('*.py'))]
    assert len(support_names) == 8
    support = []
    for name in support_names:
        source, target = ref(OLD / name), ref(root / name)
        assert source['sha256'] == target['sha256'] and source['bytes'] == target['bytes']
        assert source['file_attributes'] == target['file_attributes'] == 32 and target['links'] == 1
        assert source['file_identity'] != target['file_identity'] and source['file_identity'][0] == target['file_identity'][0]
        support.append(dict(source=source, target=target, method='hardlink', relative_path=name))
    controls = [dict(relative_path=name, artifact=ref(path)) for name, path in (
        ('request.json', request), ('bundle.manifest', root / 'bundle.manifest'), ('Play.ps1', root / 'Play.ps1'))]
    assert all(row['artifact']['links'] == 1 and row['artifact']['file_attributes'] == 32 for row in controls)
    old_terrain = ref(root / 'terrain-assets.bin')
    assert old_terrain['sha256'] == '2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13'
    value = dict(schema='zerosis.phase7.runtime_overlay.plan.v1', status='REVIEWED_EXACT_FILE_ONLY_OVERLAY',
        run_id=run, runtime_directory=str(root), base_result=ref(BASE), compiled_asset_binding=ref(ORIGINAL),
        controls=controls, base_terrain=old_terrain, packages=packages, shared_support=support,
        validator_source=ref(STAGE / 'verify_assets.py'), adapter_source=ref(Path(__file__)),
        native_execution_allowed=False, default_or_registration_changed=False, new_game_only=True)
    write_new(OUT / 'plan.json', value)
    print(json.dumps(dict(status=value['status'], plan=ref(OUT / 'plan.json'), packages=5, duplicate_support_files=8)))


class Boundary:
    def __init__(self, root, request):
        self.root, self.request = root, request
        self.denied = []
        self.native_attempts = 0

    def write_path(self, path):
        if isinstance(path, int):
            return
        path = Path(os.fsdecode(path)).absolute()
        if path == self.request or path.is_relative_to(self.root) or path.is_relative_to(OUT):
            return
        self.denied.append(str(path))
        raise PermissionError('Overlay write escaped its fresh runtime/evidence scope')

    def audit(self, event, args):
        if event.startswith(('subprocess.', 'socket.', 'winreg.')) or event in ('os.system', 'os.startfile', 'ctypes.dlopen'):
            self.native_attempts += 1
            self.denied.append(event)
            raise PermissionError('Native/process/network/registry operation forbidden during file overlay')
        if event == 'open':
            mode, flags = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                self.write_path(args[0])
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            self.write_path(args[0])
        elif event in ('os.rename', 'os.replace'):
            self.write_path(args[0]);self.write_path(args[1])
        elif event == 'os.link':
            self.write_path(args[1])


def apply(expected_plan_sha):
    assert ref(OUT / 'plan.json')['sha256'] == expected_plan_sha
    value = read(OUT / 'plan.json')
    assert not (OUT / 'result.json').exists() and not (OUT / 'base_snapshot.json.gz').exists()
    for row in [value['base_result'], value['compiled_asset_binding'], value['validator_source'], value['adapter_source']]:
        same(row)
    root = Path(value['runtime_directory'])
    request = PROJECT / 'evidence/interactive_game' / value['run_id'] / 'request.json'
    assert not (root / 'sessions').exists()
    for row in value['controls']:
        same(row['artifact'])
    document = read(request)
    for row in value['packages'].values():
        same(row['source'])
    for row in value['shared_support']:
        same(row['source']);same(row['target'])
    same(value['base_terrain'])
    # All required modules/codecs are initialized before the write/native guard.
    snapshot = dict(schema='zerosis.phase7.base_runtime_snapshot.v1', run_id=value['run_id'], runtime_directory=str(root),
        base_result=value['base_result'], files=[dict(relative_path=row['relative_path'], artifact=row['artifact'],
            data_base64=base64.b64encode(Path(row['artifact']['path']).read_bytes()).decode('ascii')) for row in value['controls']],
        original_terrain_materialization=next(row for row in document['materializations'] if Path(row['target']).name == 'terrain-assets.bin'))
    boundary = Boundary(root, request)
    sys.addaudithook(boundary.audit)
    snapshot_path = OUT / 'base_snapshot.json.gz'
    snapshot_path.write_bytes(gzip.compress((json.dumps(snapshot, indent=2) + '\n').encode(), mtime=0))
    removed, packages, shared = [], {}, []
    allowed_deletions = {row['target']['path'] for row in value['shared_support']} | {value['base_terrain']['path']}

    def retire(row):
        path = ordinary_bound(row['path'], root)
        assert str(path) in allowed_deletions
        same(row)
        recorded = dict(row, allocated_bytes=storage.allocated(path))
        deletion.unlink_without_attribute_changes(path)
        assert not path.exists()
        removed.append(recorded)

    def link(source, target):
        target = ordinary_bound(target, root)
        assert not target.exists()
        same(source, links=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source['path'], target)
        actual = ref(target)
        assert all(actual[k] == source[k] for k in ('bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes'))
        same(source, links=False)
        return dict(source=source, target=actual, method='hardlink', read_only=bool(actual['file_attributes'] & 1),
            immutability_policy='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE')

    for row in value['shared_support']:
        retire(row['target'])
        shared.append(link(row['source'], row['target']['path']))
    retire(value['base_terrain'])
    for role, row in value['packages'].items():
        packages[role] = link(row['source'], row['target_path'])
    validator = root / 'WorldAssets/verify_assets.py'
    validator.write_bytes(Path(value['validator_source']['path']).read_bytes())
    manifest = dict(schema='zerosis.world_assets.runtime_binding.v1', runtime_directory=str(root),
        host=ref(root / 'ZeroSisHost_x64.exe'), gamecore=ref(root / 'CvGameCoreDLL_Expansion2_x64.dll'),
        packages={role:dict(relative_path=EXPECTED[role][0], bytes=row['target']['bytes'], sha256=row['target']['sha256']) for role, row in packages.items()},
        validator=dict(relative_path='WorldAssets/verify_assets.py', bytes=validator.stat().st_size, sha256=ref(validator)['sha256']),
        original_compiled_binding=value['compiled_asset_binding'], native_execution_verified=False)
    manifest_path = root / 'WorldAssets/assets.manifest.json'
    write_new(manifest_path, manifest)
    original_manifest = base64.b64decode(next(row['data_base64'] for row in snapshot['files'] if row['relative_path'] == 'bundle.manifest')).decode('utf8')
    lines = original_manifest.splitlines()
    assert lines[0] == 'ZEROSIS_HOST_BUNDLE_V4' and sum(line.startswith('terrain-assets.bin|') for line in lines) == 1
    lines = ['terrain-assets.bin|' + EXPECTED['terrain'][1] if line.startswith('terrain-assets.bin|') else line for line in lines]
    (root / 'bundle.manifest').write_text('\n'.join(lines) + '\n', encoding='utf8')
    manifest_ref = ref(manifest_path)
    env = {'ZEROSIS_FOG_ASSETS':'fog-assets.bin', 'ZEROSIS_WATER_ASSETS':'water-assets.bin',
           'ZEROSIS_WATER_SURFACE_ASSETS':'water-lean-assets.bin', 'ZEROSIS_LIGHTING_ASSETS':'lighting-assets.bin'}
    prefix = "$ErrorActionPreference = 'Stop'\n" + ''.join(
        "$env:" + name + " = Join-Path $PSScriptRoot 'WorldAssets\\" + leaf + "'\n" for name, leaf in env.items())
    prefix += "& 'C:\\Python314\\python.exe' -B -X utf8 (Join-Path $PSScriptRoot 'WorldAssets\\verify_assets.py') --root $PSScriptRoot --manifest (Join-Path $PSScriptRoot 'WorldAssets\\assets.manifest.json') --manifest-sha256 " + manifest_ref['sha256'] + "\n"
    prefix += "if ($LASTEXITCODE -ne 0) { throw 'Isolated presentation asset verification failed' }\n"
    original_play = base64.b64decode(next(row['data_base64'] for row in snapshot['files'] if row['relative_path'] == 'Play.ps1')).decode('utf8')
    (root / 'Play.ps1').write_text(prefix + original_play, encoding='utf8', newline='')

    def refresh(row):
        now = ref(row['path'])
        return {key:now.get(key, item) for key, item in row.items()}

    for row in document['runtime_inputs']:
        name = Path(row['path']).name
        if name in ('terrain-assets.bin', 'bundle.manifest'):
            row.update(refresh(row))
        if name == 'terrain-assets.bin':
            row['source'] = packages['terrain']['source']['path']
    document['launcher'] = refresh(document['launcher'])
    for name in ('play', 'selected'):
        document['launcher_control_metadata'][name] = refresh(document['launcher_control_metadata'][name])
    document['materializations'] = [row for row in document['materializations'] if Path(row['target']).name != 'terrain-assets.bin']
    for role, row in packages.items():
        document['materializations'].append(dict(sha256=row['target']['sha256'], size=row['target']['bytes'], source=row['source']['path'],
            cache=None, target=row['target']['path'], cache_method='not-used-direct-existing-input', materialization_method='hardlink',
            read_only=False, immutability_policy='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE'))
    terrain_manifest = Path(packages['terrain']['source']['path']).with_name('terrain-assets.manifest.json')
    document['terrain_assets'] = dict(package=ref(root / 'terrain-assets.bin'), source_manifest=ref(terrain_manifest),
        preparer=ref(PROJECT / 'tools/civ5_original_terrain_assets.py'), package_format='ZSTERR02', originals_unchanged=True,
        originals_checked_during_preparation=False, validation_scope='SHA_PINNED_V2_PACKAGE_REUSED_NO_RETAIL_READ',
        reused_from_compiled_binding=value['compiled_asset_binding'])
    document['presentation_asset_binding'] = manifest_ref
    document['presentation_asset_overlay'] = dict(schema='zerosis.phase7.request_overlay.v1', base_result=value['base_result'],
        base_snapshot=ref(snapshot_path), packages=packages, shared_support=shared, launcher_prefix=prefix,
        supersedes_base_runtime_image=True, native_attempts=0, default_or_registration_changed=False, new_game_only=True)
    request.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    cleanup = dict(status='PASS_EXACT_FRESH_DUPLICATES_AND_OLD_TERRAIN_ALIAS_RETIRED', retired_files=len(removed), files=removed,
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in removed if row['links'] == 1),
        shared_link_payload_bytes_freed=0, source_attributes_modified=False, originals_or_old_runtimes_deleted=False)
    write_new(OUT / 'cleanup_result.json', cleanup)
    assert not boundary.denied and boundary.native_attempts == 0
    result = dict(schema='zerosis.phase7.runtime_asset_integration.v1', status='PASS_LATEST_ATTESTED_PAIR_AND_FIVE_ASSETS_FILE_ONLY',
        utc=datetime.now(timezone.utc).isoformat(), run_id=value['run_id'], runtime_directory=str(root),
        plan=ref(OUT / 'plan.json'), base_result=value['base_result'], base_snapshot=ref(snapshot_path),
        request=ref(request), asset_manifest=manifest_ref, launcher=ref(root / 'Play.ps1'), launcher_prefix=prefix,
        host=manifest['host'], gamecore=manifest['gamecore'], packages=packages, shared_support=shared,
        backend_manifest=ref(root / 'bundle.manifest'), validator=ref(validator), cleanup_receipt=ref(OUT / 'cleanup_result.json'),
        supersedes_base_runtime_image=True, new_game_only=True, native_attempts=0, guard_denials=boundary.denied,
        default_or_registration_changed=False, source_engine_changes=0, host_rebuilds=0, additional_asset_payload_copies=0)
    write_new(OUT / 'result.json', result)
    print(json.dumps(dict(status=result['status'], run_id=value['run_id'], direct_asset_links=5, shared_support_files=8, native_attempts=0)))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['plan', 'apply'])
    cli.add_argument('--plan-sha256')
    args = cli.parse_args()
    plan() if args.action == 'plan' else apply(args.plan_sha256)
