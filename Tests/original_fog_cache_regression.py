"""Reuse the original production ground-cache CPU suite with only its output roots redirected."""
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
from menu_suite_storage import storage

STAGE=PROJECT/'evidence/world_terrain_original/phase2/cache_cpu'
BUILD=PROJECT/'Build/OriginalFogCache/current'


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def main():
    assert not STAGE.exists() and not BUILD.exists(),'Inspect the existing owned regression rather than repeating it'
    inputs=[PROJECT/name for name in ('Tests/original_fog_cache_regression.py','Tests/world_terrain_reuse.py',
        'Tests/world_terrain_reuse.cpp','Source/Presentation/WorldViewRenderer.h','Source/Presentation/WorldTerrainReuse.h',
        'Source/Presentation/OriginalFogModel.h','Source/Presentation/OriginalFogState.h')]
    before=[common.artifact(path) for path in inputs]
    assert before[-2]['sha256']=='e4c8fa8ac04bb9a4ef08b6135071b596db551ee5e2a9c5db822cd15a8a80b8f9'
    assert before[-1]['sha256']=='333281ef4e4b76b8f8404a0fa4b6355a3feff1f440484e24c43b7397b2a83a5b'
    dto=inputs[3].read_text('utf8');cache=inputs[4].read_text('utf8')
    assert re.search(r'std::wstring\s+fogAssetsPath\s*;\s*double\s+fogAnimationSeconds\s*=\s*0\.0\s*;',dto)
    assert 'fogAssetsPath' not in cache and 'fogAnimationSeconds' not in cache
    # Exactly these two output globals are redirected. The original suite,
    # sources, compiler options, dependency gate, console and cleanup stay intact.
    original.STAGE=STAGE;original.BUILD=BUILD
    original.main()
    after=[common.artifact(path) for path in inputs];assert before==after
    result=json.loads((STAGE/'result.json').read_text('utf8'))
    cleanup=json.loads((STAGE/'cleanup_result.json').read_text('utf8'))
    assert result['status']=='PASS_ACTUAL_PRODUCTION_HEADER_CPU_CACHE_TESTS'
    assert {name.lower() for name in result['imported_dlls']}=={'kernel32.dll'}
    assert result['build']['cpp_dialect']=='c++14' and result['build']['compiler_and_linker_warnings']==0
    assert not BUILD.exists() and result['retained_test_executable'] is False
    assert result['native_host_sdk_clr_hwnd_gpu_audio_or_game_executed'] is False
    receipt=dict(schema='zerosis.original_fog.production_cache_regression.v1',
        status='PASS_UNCHANGED_PRODUCTION_CACHE_CPU_SUITE_ON_CURRENT_FOG_DTO',
        driver=after[0],inputs_before=before,inputs_after=after,
        original_test=after[1],original_console_source=after[2],current_dto=after[3],
        overrides={'STAGE':str(STAGE),'BUILD':str(BUILD)},
        original_result=common.artifact(STAGE/'result.json'),original_cleanup=common.artifact(STAGE/'cleanup_result.json'),
        checks=result['checks'],compiler_and_linker_warnings=0,imported_dlls=result['imported_dlls'],
        verified_dto_tail=['std::wstring fogAssetsPath','double fogAnimationSeconds=0.0'],
        cache_ignores_supplemental_fog_path_and_clock=True,
        metadata_ownership='Original suite exercises real TerrainFrame picking/centres/projected spans, returned metadata move, failed publication and owned payload release',
        scope='Compile existing CPU suite against the latest DTO; no Host or GPU rendering or actual frame-cache performance claim',
        deleted_files=cleanup['retired_files'],deleted_logical_bytes=sum(row['bytes'] for row in cleanup['files']),
        released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'],
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'regression_result.json',receipt)
    print(json.dumps(dict(status=receipt['status'],checks=receipt['checks'],driver_sha256=after[0]['sha256'],
        result=str(STAGE/'regression_result.json'),deleted_files=receipt['deleted_files'],
        released_unique_allocated_bytes=receipt['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
