"""Pin the plane/contour/optics build closure, reusing all preceding asset packages."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
def main():
    previous=PROJECT/'evidence/world_terrain_original/phase3/host_build/source_manifest.json'
    paths={common.key(row['path']):Path(row['path']) for row in json.loads(previous.read_text('utf8'))['sources']}
    names=['evidence/world_terrain_original/phase4/'+name for name in (
        'requirements.json','calibration_notes.json','make_build_manifest.py','review_build_plan.py','unit_refactor_receipt.json',
        'assets/lean_completion.json','assets/lean_format.json','assets/lean_result.json','package_tests/attempt1/result.json',
        'model/current_surface.json','model/cpu_retry01/result.json','optics/current.json','optics/cpu_retry01/result.json',
        'semantics/optics_contract.json','pipeline/cpu/result.json','cache_cpu/regression_result.json',
        'shader/completion.json','shader/attempt01/source_seal.json','shader/attempt01/result.json','review/integration_review.json')]
    names+=['tools/civ5_original_water_lean_assets.py','Source/Presentation/WorldTerrainUnits.inc']
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Source/Presentation').glob('OriginalWater*')]
    names+=[path.relative_to(PROJECT).as_posix() for path in (PROJECT/'Tests').glob('original_water*')]
    for name in names:
        path=PROJECT/name;assert path.is_file(),name;paths[common.key(path)]=path
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    prefix=PROJECT/'Build/UiWindowHost/20261115T000000Z_000000000000/frozen/project'
    assert all(len(str(prefix/Path(row['path']).relative_to(PROJECT)))<260 for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    output=STAGE/'host_build/source_manifest.json';assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    value=dict(schema='zerosis.water_surface.phase4.source_manifest.v1',sources=rows,previous_manifest=common.artifact(previous),
        added_or_refreshed=names,catalog_count=74,lean_package_sha256='69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7',
        native_execution=False,default_or_registration_changed=False,
        deployment='Compile/link fixed-plane/contour/LEAN/refraction candidate only; no game runtime/default promotion.')
    with output.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_SURFACE_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))
if __name__=='__main__':main()
