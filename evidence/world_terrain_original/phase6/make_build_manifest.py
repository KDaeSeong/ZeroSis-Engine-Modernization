"""Freeze the normal/shadow/specular source closure, reusing all existing asset packs."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def main():
    previous = PROJECT / 'evidence/world_terrain_original/phase5/host_build/source_manifest.json'
    paths = {common.key(row['path']): Path(row['path']) for row in json.loads(previous.read_text('utf8'))['sources']}
    names = ['evidence/world_terrain_original/phase6/' + name for name in (
        'requirements.json', 'calibration_notes.json', 'make_build_manifest.py', 'review_build_plan.py',
        'semantics/retail_cache_bindings.py', 'semantics/retail_cache_bindings.json', 'semantics/composite/result.json',
        'field_cpu/current.json', 'field_cpu/cpu/result.json', 'field_cpu/lighting_api/cpu/result.json',
        'pipeline/cpu01/result.json', 'review/material_asset_reuse_audit.json',
        'review/material_sampler/attempt01/result.json', 'review/field_shader/attempt02/result.json',
        'review/wrap_fix_reseal.json', 'review/integration_review.json', 'review/asset_integration_review.json',
        'review/asset_review_reissue_seal.json', 'review/component_completion.json', 'review/build_tools_update.json',
        'shader/completion.json', 'shader/source_seal.json')]
    names += [path.relative_to(PROJECT).as_posix() for path in (PROJECT / 'Source/Presentation').glob('OriginalLightingField*')]
    names += ['Source/Presentation/OriginalTerrainMaterialSampler.h']
    names += [path.relative_to(PROJECT).as_posix() for pattern in ('original_lighting_field*', 'original_terrain_material_sampler*')
              for path in (PROJECT / 'Tests').glob(pattern)]
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
    value = dict(schema='zerosis.original_lighting_fields.phase6.source_manifest.v1', sources=rows,
        previous_manifest=common.artifact(previous), added_or_refreshed=names, catalog_count=74,
        new_asset_packages=0, retained_cpu_texture_clone_bytes=0, native_execution=False,
        default_or_registration_changed=False,
        deployment='Actual compile/link normal/macro-shadow/final-specular candidate only; no game runtime or default promotion.')
    with output.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_LIGHTING_FIELD_SOURCE_MANIFEST', sources=len(rows), artifact=common.artifact(output))))


if __name__ == '__main__':
    main()
