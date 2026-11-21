"""Remove only five attested COFF objects and their build environment script."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re

import menu_suite_storage as audit
from civ5_ui_assets import _unlink_font_target_without_attribute_changes


def verify(row):
    info=audit.storage.metadata(audit.storage.ordinary(row['path']))
    assert all(info[key]==row[key] for key in ('bytes','file_identity','mtime_ns','file_attributes','links')),row['path']
    assert audit.storage.digest(row['path'])==row['sha256'],row['path']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args();path=args.plan.absolute()
    assert path.is_relative_to(audit.STAGE/'pair_preparation') and path.name=='cleanup_plan.json'
    assert audit.storage.digest(path)==args.sha256
    plan=audit.storage.read(path)
    assert plan['historical_object_refs_retired_after_verification'] is True and len(plan['candidates'])==6
    image=plan['retained_current_executable'];verify(image)
    root=Path(image['path']).parents[1];identifier=root.name
    assert root.parent==audit.PROJECT/'Build/UiWindowHost' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}',identifier)
    expected={audit.storage.key(root/f'final/tu_{i:02d}_{unit}/obj/{stem}.obj') for i,(unit,stem) in enumerate(zip(
        ('host_main','window','renderer','world_renderer','terrain_renderer'),
        ('HostMain','BitmapWindow','BitmapRenderer','WorldViewRenderer','WorldTerrainRenderer')))}
    expected.add(audit.storage.key(root/'read_build_environment.cmd'))
    assert expected=={audit.storage.key(row['path']) for row in plan['candidates']}
    verify(plan['independent_verification'])
    allocation=0
    for row in plan['candidates']:
        verify(row);assert row['links']==1
        allocation+=audit.storage.allocated(row['path'])
    audit.write_new(path.parent/'cleanup_started.json',dict(plan_sha256=args.sha256,build_id=identifier))
    deleted=[]
    try:
        for row in plan['candidates']:
            verify(row);_unlink_font_target_without_attribute_changes(Path(row['path']))
            assert not os.path.lexists(row['path']);deleted.append(row['path'])
        removed=[]
        for row in plan['candidates']:
            parent=Path(row['path']).parent
            if parent.name=='obj' and parent.is_relative_to(root) and not any(parent.iterdir()):parent.rmdir();removed.append(str(parent))
        verify(image)
        result=dict(schema='zerosis.menu_suite_host.cleanup_result.v1',status='PASS_EXACT_CURRENT_MENU_BUILD_INTERMEDIATE_CLEANUP',
                    build_id=identifier,plan_sha256=args.sha256,files_deleted=len(deleted),all_candidates_absent=True,
                    logical_bytes_removed=sum(row['bytes'] for row in plan['candidates']),allocated_bytes_released=allocation,
                    current_image_unchanged=True,protected_objects_or_sources_deleted=False,runtime_default_or_saves_deleted=False,
                    empty_object_directories_removed=removed,Host_SDK_window_or_GPU_executed=False)
        audit.write_new(path.parent/'cleanup_result.json',result)
        print(json.dumps({key:result[key] for key in ('status','build_id','files_deleted','allocated_bytes_released')}))
    except BaseException as error:
        audit.write_new(path.parent/'cleanup_partial_failure.json',dict(deleted=deleted,error_type=type(error).__name__,error=str(error)))
        raise


if __name__=='__main__':main()
