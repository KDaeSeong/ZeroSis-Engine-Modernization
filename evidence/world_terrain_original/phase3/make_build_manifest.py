"""Freeze the water source/component closure while reusing terrain and fog data."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    previous=PROJECT/'evidence/world_terrain_original/phase2/host_build/source_manifest_retry01.json'
    paths={common.key(row['path']):Path(row['path']) for row in json.loads(previous.read_text('utf8'))['sources']}
    names=['evidence/world_terrain_original/phase3/'+name for name in (
        'requirements.json','calibration_notes.json','make_build_manifest.py','review_build_plan.py',
        'assets/completion.json','assets/discovery.json','package_tests/attempt1/result.json',
        'model/current_model.json','model/cpu/result.json','state/current_state.json',
        'bridge/completion.json','bridge/attempt2/result.json','cache_cpu/regression_result.json',
        'semantics/sdk_river_contract.json','semantics/shader_semantics.json','semantics/coast_text_contract.json',
        'shader/current.json','shader/attempt03/result.json','review/integration_review.json')]
    names+=['tools/civ5_original_water_assets.py']
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Source/Presentation').glob('OriginalWater*')]
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Tests').glob('original_water*')]
    for name in names:
        path=PROJECT/name;assert path.is_file(),name;paths[common.key(path)]=path
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    prefix=PROJECT/'Build/UiWindowHost/20261115T000000Z_000000000000/frozen/project'
    assert all(len(str(prefix/Path(row['path']).relative_to(PROJECT)))<260 for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    output=STAGE/'host_build/source_manifest.json';assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    value=dict(schema='zerosis.original_water.phase3.source_manifest.v1',sources=rows,previous_manifest=common.artifact(previous),
        added_or_refreshed=names,catalog_count=74,water_package_sha256='2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc',
        native_execution=False,default_or_registration_changed=False,
        deployment='Compile/link explicit water candidate only; reuse terrain and fog packages; current/default runtime unchanged.')
    with output.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_WATER_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))
if __name__=='__main__':main()
