"""Production package->DTO->placement->global atlas CPU integration on40x24; no native game APIs."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase1/pipeline_tests'
PACKAGE=PROJECT/'Build/OriginalTerrainAssets/02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8/terrain-assets.bin'
PACKAGE_SHA='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',type=int,default=0);args=cli.parse_args()
    assert 0<=args.attempt<=9
    stage=ROOT/('current' if args.attempt==0 else f'retry{args.attempt:02d}');build=stage/'work'
    assert not stage.exists(),'Inspect the existing owned pipeline attempt before retrying'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build.mkdir()
    names=['Source/Presentation/OriginalTerrainModel.h','Source/Presentation/OriginalTerrainPackage.h',
        'Source/Presentation/OriginalTerrainBinding.h','Source/Presentation/OriginalTerrainGeometry.h',
        'Source/Presentation/OriginalTerrainSha256.h','Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/WorldCameraControls.h','Source/Presentation/BitmapRenderer.h',
        'Tests/original_terrain_pipeline.cpp','Tests/original_terrain_pipeline.py']
    before=[common.artifact(PROJECT/name) for name in names];package_before=common.artifact(PACKAGE)
    assert package_before['sha256']==PACKAGE_SHA and package_before['bytes']<128*1024**2
    assert before[0]['sha256']=='8152cd67c7e1e7eae59f28c901383df2e055a8350e3ebd2770a8000031677113'
    write_new(stage/'started.json',dict(inputs=before,package=package_before,large_package_copies=0,
        map_dimensions=[40,24],revealed_region=[19,10,3,3],timeout_seconds=90,self_process_memory_limit_bytes=384*1024**2,
        own_peak_memory_api='KERNEL32!K32GetProcessMemoryInfo on GetCurrentProcess only',
        host_sdk_clr_hwnd_gpu_audio_or_game_execution=False))
    compiled=build_cxx14('original_terrain_pipeline',build,stage,PROJECT/'Tests/original_terrain_pipeline.cpp',
        [PROJECT/'Source/Presentation'])
    imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names_dll=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imported.returncode==0 and {name.lower() for name in names_dll}=={'kernel32.dll'},names_dll
    executable=common.artifact(compiled['path']);started=time.perf_counter()
    output=run([compiled['path'],PACKAGE],cwd=build,timeout=90)
    wall_seconds=time.perf_counter()-started;stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii')
    (stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_PIPELINE (.+)\s*',stdout)
    assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
    metrics={}
    for field in match[1].split():
        name,value=field.split('=',1);metrics[name]=value if name.endswith('_sha') else int(value)
    assert (metrics['width'],metrics['height'],metrics['revealed'])==(2560,1536,9)
    assert metrics['elapsed_ms']<=85000 and metrics['peak_working_set']<=metrics['memory_limit']==384*1024**2
    assert metrics['peak_commit']<=metrics['memory_limit']
    after=[common.artifact(PROJECT/name) for name in names];package_after=common.artifact(PACKAGE)
    for old,new in zip(before+[package_before],after+[package_after]):
        assert all(old[k]==new[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes'))
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);row['allocated_bytes']=storage.allocated(path)
        assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after,protected_package=package_after))
    for row in rows:
        current=common.artifact(row['path']);assert all(current[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_PIPELINE_CONSOLE_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),large_package_copies=0)
    write_new(stage/'cleanup_result.json',cleanup)
    result=dict(schema='zerosis.original_terrain_pipeline.cpu_integration.v1',status='PASS_REAL_PACKAGE_40X24_CPU_PIPELINE',
        metrics=metrics,subprocess_wall_seconds=wall_seconds,package=package_before,inputs_before=before,inputs_after=after,
        package_after=package_after,build=compiled,executed_console=executable,imported_dlls=names_dll,
        scenarios=['Real112MB package SHA/records/parser -> 299piece library -> captured960cells -> placement -> global64texels/hex atlas',
            '951hidden plots have terrain/continent/hills/mountain/water/natural-wonder changed; matching cells, placements, random consumption, material/height/mask arrays unchanged',
            'Only visible flags change on9revealed plots; terrain cells, placements and atlas remain identical',
            'Every3,932,160texel has finite height; unknown texels carry material255 and height0',
            'At most two full atlases retained; measured own-console peak working set/commit remain within384MiB'],
        independent_tile_pick_geometry_test='Separate controlled geometry test; this test does not equate material-row IDs with tile IDs.',
        cleanup=common.artifact(stage/'cleanup_result.json'),report_label='규칙 동등, 배치 동등은 미검증',
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_or_retail_layout_parity_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],metrics=metrics,wall_seconds=round(wall_seconds,3),
        cleanup_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'],large_package_copies=0)))

if __name__=='__main__':main()
