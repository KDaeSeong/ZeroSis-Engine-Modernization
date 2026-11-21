"""Retire the terminal pre-link attempt and record a separate reviewed plan input."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
from menu_suite_storage import storage


def main():
    output=STAGE/'host_build/permission_resolution.json'
    assert not output.exists()
    failed=STAGE/'host_build/attempts/cfdc8ecde3404a86a0de/failure.json'
    value=json.loads(failed.read_text('utf8'))
    identifier='20261105T113537Z_cfdc8ecde340'
    assert value['status']=='FAILED_DO_NOT_REPLAY' and value['build_id']==identifier
    assert value['error_type']=='PermissionError' and '[WinError 5]' in value['detail']
    assert not value['materialized'] and not value['completed_translation_units']
    assert len(value['commands'])==6 and len(value['discovery'])==5 and not value['denied_operations']
    assert not value['host_sdk_clr_window_gpu_or_dll_executed']
    root=(PROJECT/'Build/UiWindowHost'/identifier).absolute()
    assert root.parent==PROJECT/'Build/UiWindowHost' and root.is_relative_to(PROJECT/'Build')
    candidates=[];directories=[]
    for directory,names,leaves in os.walk(root,followlinks=False):
        here=Path(directory);assert not os.stat(here,follow_symlinks=False).st_file_attributes&0x400
        directories.append(here)
        for name in names:assert not os.stat(here/name,follow_symlinks=False).st_file_attributes&0x400
        for name in leaves:
            path=here/name;row=common.artifact(path);info=storage.ordinary(path)
            assert info.st_nlink==1 and path.suffix in ('.cmd','.rsp','.json') and path.is_relative_to(root)
            candidates.append(dict(**row,allocated_bytes=storage.allocated(path)))
    assert len(candidates)==11 and not any(root.rglob('*.exe')) and not any(root.rglob('*.obj'))
    for row in candidates:
        path=Path(row['path']);now=common.artifact(path)
        assert now=={k:v for k,v in row.items() if k!='allocated_bytes'}
        path.unlink();assert not path.exists()
        row['result']='DELETED_EXACT_TERMINAL_PRELINK_ATTEMPT_INTERMEDIATE'
    for directory in sorted(directories,key=lambda x:len(x.parts),reverse=True):
        assert directory.is_relative_to(root) and not any(directory.iterdir());directory.rmdir()
    assert not root.exists()
    receipt=dict(schema='zerosis.replay_scroll_graph.build_permission_resolution.v1',
        status='TERMINAL_FAILED_PLAN_NOT_REPLAYED_NEW_PLAN_REQUIRES_PROJECT_SCOPED_PERMISSION',
        failed_attempt=common.artifact(failed),failed_build_id=identifier,
        actual_completed_phases=['environment',*['discover_'+x for x in ('host_main','window','renderer','world_renderer','terrain_renderer')]],
        final_compiler_translation_units=0,host_image_created=False,
        reason='Windows refused a readonly retained-source hardlink. The same operation previously required an explicit scoped tool permission override.',
        next_action='Generate a distinct single-use plan including this immutable input; use scoped permission for exact compiler/linker-only build.',
        failed_output_cleanup=candidates,released_allocated_bytes=sum(x['allocated_bytes'] for x in candidates),
        failed_plan_replay_allowed=False,production_source_or_assets_changed=False,
        native_host_sdk_window_gpu_executed=False,full_engine_goal_complete=False)
    with output.open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=receipt['status'],deleted=len(candidates),released_allocated_bytes=receipt['released_allocated_bytes'],receipt=common.artifact(output))))


if __name__=='__main__':main()
