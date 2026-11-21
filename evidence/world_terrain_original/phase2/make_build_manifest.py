"""Pin the current phase-two source/check closure without copying shared assets."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--retry',action='store_true');args=cli.parse_args()
    previous=PROJECT/'evidence/world_terrain_original/phase1/host_build/source_manifest2.json'
    paths={common.key(row['path']):Path(row['path']) for row in json.loads(previous.read_text('utf8'))['sources']}
    names=['evidence/world_terrain_original/phase2/'+name for name in (
        'requirements.json','calibration_notes.json','make_build_manifest.py','review_build_plan.py',
        'assets/completion.json','assets/format.json','package_tests/attempt1/result.json',
        'model/current_model.json','model/model_contract.json','state/cpu/result.json',
        'cache_cpu/result.json','cache_cpu/regression_result.json','review/integration_asset_review.json','review/exact_distance_followup.json',
        'shader/attempt01/result.json','shader/attempt03/result.json','shader/current.json')]
    names+=['tools/civ5_original_fog_assets.py']
    if args.retry:names+=['evidence/world_terrain_original/phase2/review/integration_asset_review_retry01.json']
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Source/Presentation').glob('OriginalFog*')]
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Tests').glob('original_fog*')]
    for name in names:
        path=PROJECT/name;assert path.is_file(),name;paths[common.key(path)]=path
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    # Compiler paths include this prefix. Reject long paths before creating a frozen tree.
    prefix=PROJECT/'Build/UiWindowHost/20261115T000000Z_000000000000/frozen/project'
    assert all(len(str(prefix/Path(row['path']).relative_to(PROJECT)))<260 for row in rows)
    output=STAGE/('host_build/source_manifest_retry01.json' if args.retry else 'host_build/source_manifest.json')
    assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    value=dict(schema='zerosis.original_fog.phase2.source_manifest.v1',sources=rows,
        previous_manifest=common.artifact(previous),added_or_refreshed=names,catalog_count=74,
        terrain_package_sha256='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8',
        fog_package_sha256='42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc',
        native_execution=False,default_or_registration_changed=False,
        deployment='Compile/link explicit opt-in candidate only; reuse V2 terrain, add one supplemental fog package; current runtime not promoted.')
    with output.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))

if __name__=='__main__':main()
