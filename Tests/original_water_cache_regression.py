"""Unchanged production ground-cache suite and separate actual DTO water/ground key checks."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
import world_terrain_reuse as original
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

STAGE=PROJECT/'evidence/world_terrain_original/phase3/cache_cpu'
BUILD=PROJECT/'Build/OriginalWaterCache/current'


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def key_console():
    stage=STAGE/'keys';build=PROJECT/'Build/OriginalWaterCache/keys'
    stage.mkdir();build.mkdir()
    compiled=build_cxx14('original_water_cache_keys',build,stage,PROJECT/'Tests/original_water_cache_keys.cpp',[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
    executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=30)
    stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii');(stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_WATER_CACHE_KEYS checks=(\d+)\s*',stdout)
    assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build);actual=common.artifact(path)
        assert all(actual[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
    write_new(stage/'cleanup_result.json',cleanup)
    result=dict(schema='zerosis.original_water.actual_key_separation_cpu.v1',status='PASS_ACTUAL_GROUND_AND_WATER_KEY_SEPARATION',
        checks=int(match[1]),build=compiled,executed_console=executable,imported_dlls=names,cleanup=common.artifact(stage/'cleanup_result.json'),
        retained_test_executable=False,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        mutation_policy=['River flags/active flow: ground reuse, water state invalidated.',
            'Visibility only: ground invalidated, water topology reused.',
            'Camera/zoom/seed: ground invalidated, water topology reused.',
            'Terrain/water/relief/exploration: both invalidated.',
            'Water asset path and animation clocks: neither detached state key changes; actual water package identity is a separate Root GPU cache dependency.',
            'Plot reorder: ground invalidated, canonical water topology reused.',
            'Owned snapshots survive source mutation; inactive edge flow values ignored.'])
    write_new(stage/'result.json',result);return result


def main():
    assert not STAGE.exists() and not BUILD.exists(),'Inspect the existing owned regression instead of repeating it'
    inputs=[PROJECT/name for name in ('Tests/original_water_cache_regression.py','Tests/original_water_cache_keys.cpp',
        'Tests/world_terrain_reuse.py','Tests/world_terrain_reuse.cpp','Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/OriginalWaterModel.h','Source/Presentation/OriginalWaterState.h')]
    before=[common.artifact(path) for path in inputs]
    assert before[-2]['sha256']=='75552fe2a8002772795c0fa6d14c396ee566615e826b4d627815bfc7b6b59ba4'
    assert before[-1]['sha256']=='1c064d632cc056f1de81204dbaaf000061ef5067c5cbb04abf3157e6eca8c6ee'
    dto=inputs[4].read_text('utf8');cache=inputs[5].read_text('utf8')
    assert re.search(r'std::wstring\s+waterAssetsPath\s*;\s*double\s+waterAnimationSeconds\s*=\s*0\.0\s*;',dto)
    assert all(name in dto for name in ('riverW','riverNW','riverNE','flowE','flowSE','flowSW','lake'))
    assert all(name not in cache for name in ('waterAssetsPath','waterAnimationSeconds','riverW','riverNW','riverNE','flowE','flowSE','flowSW'))
    original.STAGE=STAGE;original.BUILD=BUILD;original.main()
    original_result=json.loads((STAGE/'result.json').read_text('utf8'))
    assert original_result['status']=='PASS_ACTUAL_PRODUCTION_HEADER_CPU_CACHE_TESTS' and original_result['checks']==179
    joint=key_console();after=[common.artifact(path) for path in inputs];assert before==after
    cleanup=json.loads((STAGE/'cleanup_result.json').read_text('utf8'));joint_cleanup=json.loads((STAGE/'keys/cleanup_result.json').read_text('utf8'))
    result=dict(schema='zerosis.original_water.production_cache_regression.v1',status='PASS_UNCHANGED_PRODUCTION_CACHE_AND_ACTUAL_WATER_KEY_SPLIT',
        driver=after[0],key_console_source=after[1],inputs_before=before,inputs_after=after,
        original_tests_unmodified=True,overrides={'STAGE':str(STAGE),'BUILD':str(BUILD)},
        original_result=common.artifact(STAGE/'result.json'),key_result=common.artifact(STAGE/'keys/result.json'),
        ground_checks=original_result['checks'],key_checks=joint['checks'],checks=original_result['checks']+joint['checks'],
        compiler_and_linker_warnings=0,imported_dlls=joint['imported_dlls'],current_dto=after[4],
        model_and_state_sources_frozen=True,retained_test_executable=False,
        deleted_files=cleanup['retired_files']+joint_cleanup['deleted_files'],
        deleted_logical_bytes=sum(row['bytes'] for row in cleanup['files'])+joint_cleanup['deleted_logical_bytes'],
        released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes']+joint_cleanup['released_unique_allocated_bytes'],
        scope='CPU production headers, ground metadata ownership and water/ground key separation; Root GPU asset-cache dependency and native rendering remain separate verification',
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'regression_result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],ground_checks=result['ground_checks'],key_checks=result['key_checks'],
        driver_sha256=after[0]['sha256'],result=str(STAGE/'regression_result.json'),deleted_files=result['deleted_files'],
        released_unique_allocated_bytes=result['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
