"""Independent file-only check of the current prepared pair and source closure."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import retained_host_runtime_input as retained
import retained_menu_suite_host_input as menu
from collect_baseline import pe_header

BUILD = '20261104T131943Z_deb06f03ff1f'
RUN = '20261104T132911Z_4f194ae38472'
REPORT_SHA = 'd6e679c92bcfc767b55b46e3b766777b7ffcc6513b19c9c36072c6e760150681'
PROFILE_SHA = '5e18e7edeec1e2ed98beb8c09997672a7ee6b0145f7c9ab3e8314fc878536a15'
HOST_SHA = 'c21bba2e433974300507230f4478d19d3a0d098e2cee72420066b81b2016b18a'
SDK_SHA = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def ref(path):
    path=Path(path).absolute()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path))


def main():
    output=STAGE/'prepared_runtime_verification.json'
    if output.exists():raise ValueError('Inspect the existing independent proof')
    profile=STAGE/'pair_preparation'/BUILD/'prepared_profile.json'
    report=PROJECT/'evidence/ui_window_host'/BUILD/'build_result.json'
    runtime=PROJECT/'Build/InteractiveGameRuntime'/RUN
    request_path=PROJECT/'evidence/interactive_game'/RUN/'request.json'
    materialization=PROJECT/'evidence/game_menu/menu_runtime_ui_followup/pair_preparation'/BUILD/'materialization/result.json'
    assert digest(profile)==PROFILE_SHA and digest(report)==REPORT_SHA
    build,request,result=read(report),read(request_path),read(materialization)
    assert result['run_id']==RUN and result['host_build_id']==BUILD
    assert result['native_attempts']==0 and not result['host_or_sdk_executed'] and not result['guard_denials']
    assert result['new_game_only'] and not result['default_promoted'] and not result['full_engine_goal_complete']
    assert request['menu_host_preparation_scope']['actual_current_source_closure_verified']
    assert not request['menu_host_preparation_scope']['cross_bundle_load_allowed']
    assert request['frozen_python_support_import_closure']['module_count']==6
    assert not request['frozen_python_support_import_closure']['live_project_tools_fallback']
    assert len(request['runtime_inputs'])==24
    backend=[]
    for row in request['runtime_inputs']:
        path=Path(row['path']);assert path.is_relative_to(runtime) and digest(path)==row['sha256']
        backend.append(ref(path))
    assert digest(runtime/'ZeroSisHost_x64.exe')==HOST_SHA
    assert digest(runtime/'CvGameCoreDLL_Expansion2_x64.dll')==SDK_SHA
    assert pe_header(runtime/'ZeroSisHost_x64.exe')['architecture']=='x64'
    assert pe_header(runtime/'CvGameCoreDLL_Expansion2_x64.dll')['architecture']=='x64'
    files=retained._Files(check_metadata=True)
    files.verify(build['reviewed_preflight'])
    reviewed=files.json(build['reviewed_preflight'])
    files.verify(reviewed['source_manifest'])
    for row in build['current_source_inputs']:files.verify(row)
    frozen=menu.frozen_rows(build)
    for row in frozen.values():files.verify(row)
    sidecar=menu.validate_required_sidecars(PROJECT,BUILD,read(profile)['required_sidecar'],files)
    assert sidecar['file_count']==154
    for row in request['required_host_sidecar_validation']['verified_files']:files.verify(row)
    files.finish()
    expected={Path(row['path']).relative_to(runtime).as_posix() for row in request['runtime_inputs']}
    expected.update('UIFrontEnd/'+row['relative_path'] for row in request['required_host_sidecars']['files'])
    expected.update(['Play.ps1','Resume.ps1','interactive_ui_support/support_manifest.json',
        'interactive_ui_support/assets/inline_icons.json','interactive_ui_support/assets/prepared.json',
        'interactive_ui_support/tools/found_value_runtime_options.py'])
    expected.update('interactive_ui_support/tools/'+name for name in request['interactive_ui_support_inventory']['tools'])
    actual=set()
    for directory,names,leaves in os.walk(runtime,followlinks=False):
        for name in [*names,*leaves]:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
        for name in leaves:actual.add((Path(directory)/name).relative_to(runtime).as_posix())
    assert len(expected)==len(actual)==189 and actual==expected
    for forbidden in ['sessions','settings','driver_result.json','__pycache__']:assert not(runtime/forbidden).exists()
    for path in runtime.rglob('*'):assert path.suffix not in ('.pyc','.pyo')
    retired=read(STAGE/'pair_preparation'/BUILD/'typed_retirement.json')
    assert len(retired['retired'])==6 and all(not Path(row['path']).exists() for row in retired['retired'])
    proof=dict(schema='zerosis.replay_calendar_legend.prepared_pair.v1',
        utc=datetime.now(timezone.utc).isoformat(),status='PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED',
        build_id=BUILD,run_id=RUN,runtime_directory=str(runtime),physical_file_paths=len(actual),
        backend_inputs=backend,sidecar_files=154,frozen_python_modules=6,
        current_source_inputs_verified=len(build['current_source_inputs']),frozen_inputs_verified=len(frozen),
        source_manifest=reviewed['source_manifest'],reviewed_preflight=build['reviewed_preflight'],
        independent_verifier=ref(Path(__file__).absolute()),profile=ref(profile),build_result=ref(report),
        request=ref(request_path),materialization=ref(materialization),host=ref(runtime/'ZeroSisHost_x64.exe'),
        gamecore=ref(runtime/'CvGameCoreDLL_Expansion2_x64.dll'),native_attempts=0,
        native_host_sdk_window_gpu_executed=False,new_game_only=True,cross_bundle_load_allowed=False,
        default_or_global_registration_changed=False,full_engine_goal_complete=False)
    with output.open('x',encoding='utf8') as stream:json.dump(proof,stream,indent=2);stream.write('\n')
    print(json.dumps({k:proof[k] for k in ('status','build_id','run_id','physical_file_paths','current_source_inputs_verified','frozen_inputs_verified','native_attempts')}))


if __name__=='__main__':main()
