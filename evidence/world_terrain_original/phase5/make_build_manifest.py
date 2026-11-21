"""Pin the lighting source closure without duplicating content-addressed assets."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def main():
    previous = PROJECT / 'evidence/world_terrain_original/phase4/host_build/source_manifest.json'
    paths = {common.key(row['path']): Path(row['path']) for row in json.loads(previous.read_text('utf8'))['sources']}
    names = ['evidence/world_terrain_original/phase5/' + name for name in (
        'requirements.json', 'calibration_notes.json', 'make_build_manifest.py', 'review_build_plan.py',
        'semantics/lighting_contract.py', 'semantics/lighting_contract.json',
        'assets/completion.json', 'assets/format.json', 'assets/package_tests/attempt1/result.json',
        'lighting_cpu/current.json', 'lighting_cpu/cpu_retry01/result.json', 'pipeline/cpu01/result.json',
        'shader/completion.json', 'shader/source_seal.json', 'review/asset_pipeline_review.json',
        'review/build_tools_update.json')]
    names += ['tools/civ5_original_lighting_assets.py']
    names += [path.relative_to(PROJECT).as_posix() for path in (PROJECT / 'Source/Presentation').glob('OriginalLighting*')]
    names += [path.relative_to(PROJECT).as_posix() for path in (PROJECT / 'Tests').glob('original_lighting*')]
    for name in names:
        path = PROJECT / name
        assert path.is_file(), name
        paths[common.key(path)] = path
    rows = [common.artifact(path) for _, path in sorted(paths.items())]
    prefix = PROJECT / 'Build/UiWindowHost/20261115T000000Z_000000000000/frozen/project'
    assert all(len(str(prefix / Path(row['path']).relative_to(PROJECT))) < 260 for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json', 'current_progress.json') for row in rows)
    output = STAGE / 'host_build/source_manifest.json'
    assert not output.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    value = dict(schema='zerosis.original_lighting.phase5.source_manifest.v1', sources=rows,
                 previous_manifest=common.artifact(previous), added_or_refreshed=names, catalog_count=74,
                 lighting_package_sha256='d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424',
                 native_execution=False, default_or_registration_changed=False,
                 deployment='Actual compile/link lighting candidate only; no game runtime or default promotion.')
    with output.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_LIGHTING_SOURCE_MANIFEST', sources=len(rows), artifact=common.artifact(output))))


if __name__ == '__main__':
    main()
