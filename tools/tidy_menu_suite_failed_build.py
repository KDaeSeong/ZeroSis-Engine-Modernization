"""Hash-locked, one-use removal of the terminal first failed menu build."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import stat

import menu_suite_storage as audit
from civ5_ui_assets import _unlink_font_target_without_attribute_changes

PROJECT=audit.PROJECT
STAGE=audit.STAGE/'host_build/failed_cleanup'
ROOT=PROJECT/'Build/UiWindowHost/20261101T065422Z_bd0504aac8ef'
FAILURE=audit.STAGE/'host_build/attempts/bd0504aac8efb981ffd5/failure.json'


def snapshot(path):
    info=audit.storage.ordinary(path)
    return dict(path=str(path),**audit.storage.metadata(info),sha256=audit.storage.digest(path),allocated_bytes=audit.storage.allocated(path))


def inventory():
    assert ROOT.is_absolute() and ROOT.parent==PROJECT/'Build/UiWindowHost'
    assert audit.storage.read(FAILURE)['status']=='FAILED_DO_NOT_REPLAY'
    assert not (ROOT/'final/ZeroSisHost_x64.exe').exists()
    rows=[]
    for directory,dirs,files in os.walk(ROOT):
        for name in dirs:
            assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT
        for name in files:
            path=Path(directory)/name
            assert path.suffix.lower() not in ('.zssave','.civ5save')
            rows.append(snapshot(path))
    return rows


def protected():
    ids={}
    for row in audit.storage.read(audit.STAGE/'protection_before.json')['protected_artifacts']:
        if Path(row['path']).suffix.lower() in ('.exe','.dll','.zssave'):
            value=snapshot(Path(row['path']))
            assert value['sha256']==row['sha256'] and value['file_identity']==row['file_identity']
            ids.setdefault(tuple(value['file_identity']),value)
    return list(ids.values())


def main():
    global ROOT,FAILURE,STAGE
    parser=argparse.ArgumentParser();parser.add_argument('--apply-plan-sha256');parser.add_argument('--failed-build-id');args=parser.parse_args()
    if args.failed_build_id:
        assert re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}',args.failed_build_id)
        matches=[path for path in (audit.STAGE/'host_build/attempts').glob('*/failure.json')
                 if audit.storage.read(path).get('build_id')==args.failed_build_id]
        assert len(matches)==1,'Only a recorded terminal failure can be retired'
        ROOT=PROJECT/'Build/UiWindowHost'/args.failed_build_id;FAILURE=matches[0]
        STAGE=audit.STAGE/'host_build'/('failed_cleanup_'+args.failed_build_id)
    plan_path=STAGE/'plan.json'
    if not args.apply_plan_sha256:
        rows=inventory();counts=Counter(tuple(row['file_identity']) for row in rows)
        unique={tuple(row['file_identity']):row for row in rows}
        value=dict(schema='zerosis.menu_suite.failed_build_retirement.v1',root=str(ROOT),
                   failure=snapshot(FAILURE),files=rows,protected=protected(),
                   logical_bytes=sum(row['bytes'] for row in rows),
                   expected_unique_allocated_release=sum(row['allocated_bytes'] for key,row in unique.items() if counts[key]==row['links']),
                   source_unchanged=True,Host_SDK_or_window_executed=False)
        audit.write_new(plan_path,value)
        print(json.dumps(dict(status='PLAN_READY',files=len(rows),logical_bytes=value['logical_bytes'],
                             expected_release=value['expected_unique_allocated_release'],plan_sha256=audit.storage.digest(plan_path))))
        return
    assert audit.storage.digest(plan_path)==args.apply_plan_sha256
    plan=audit.storage.read(plan_path)
    assert plan['root']==str(ROOT) and not (STAGE/'started.json').exists()
    assert audit.storage.digest(FAILURE)==plan['failure']['sha256']
    assert {row['path'] for row in inventory()}=={row['path'] for row in plan['files']}
    for row in plan['files']:
        assert snapshot(Path(row['path']))==row,row['path']
    for row in plan['protected']:
        now=snapshot(Path(row['path']))
        assert all(now[key]==row[key] for key in ('sha256','bytes','file_identity','mtime_ns','file_attributes'))
    audit.write_new(STAGE/'started.json',dict(plan_sha256=args.apply_plan_sha256,files=len(plan['files'])))
    deleted=[]
    try:
        for row in plan['files']:
            path=Path(row['path']);info=audit.storage.metadata(audit.storage.ordinary(path))
            # Other aliases from this same plan can reduce the link count.
            assert all(info[key]==row[key] for key in ('bytes','file_identity','mtime_ns','file_attributes'))
            assert audit.storage.digest(path)==row['sha256']
            _unlink_font_target_without_attribute_changes(path)
            assert not os.path.lexists(path)
            deleted.append(row['path'])
        directories=sorted((Path(directory) for directory,_,_ in os.walk(ROOT)),key=lambda p:len(p.parts),reverse=True)
        for directory in directories:
            assert directory.is_relative_to(ROOT) and not directory.is_symlink()
            directory.rmdir()
        for row in plan['protected']:
            now=snapshot(Path(row['path']))
            assert all(now[key]==row[key] for key in ('sha256','bytes','file_identity','mtime_ns','file_attributes','allocated_bytes'))
        audit.write_new(STAGE/'result.json',dict(status='PASS_EXACT_FAILED_BUILD_RETIRED',files_deleted=len(deleted),
                        logical_bytes_removed=plan['logical_bytes'],unique_allocated_bytes_released=plan['expected_unique_allocated_release'],
                        root_absent=not ROOT.exists(),protected_identities=len(plan['protected']),
                        unchanged_protected_bytes_ids_mtimes_attributes=True,source_or_runtime_or_saves_deleted=False))
        print(json.dumps(dict(status='PASS',files_deleted=len(deleted),released_bytes=plan['expected_unique_allocated_release'])))
    except BaseException as error:
        audit.write_new(STAGE/'partial_failure.json',dict(deleted=deleted,error_type=type(error).__name__,error=str(error)))
        raise


if __name__=='__main__':main()
