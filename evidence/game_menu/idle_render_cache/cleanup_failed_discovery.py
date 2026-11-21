"""Retire only this resolved failed discovery's regenerable work files; keep its evidence."""
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

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)

def main():
    root=PROJECT/'Build/UiWindowHost/20261115T005316Z_09f703125edf'
    assert root.resolve()==root and root.is_relative_to((PROJECT/'Build/UiWindowHost').resolve())
    failure=json.loads((STAGE/'host_build/failed_discovery.json').read_text('utf8'))
    common.sealed(failure['compressed_backup']);common.sealed(failure['plan'])
    report_path=PROJECT/'evidence/ui_window_host/20261115T005626Z_256252d8abe3/build_result.json'
    report=json.loads(report_path.read_text('utf8'))
    assert common.artifact(report_path)['sha256']=='5e2c9f8232938e2cf89490dc7742780d2f8880db2a5b8e80f622e12108467008'
    assert not any(common.key(value).startswith(common.key(root)) for value in strings(report))
    rows=[];directories=[]
    for directory,names,leaves in os.walk(root,followlinks=False):
        assert not os.stat(directory,follow_symlinks=False).st_file_attributes&0x400
        directories.append(Path(directory))
        for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
        for name in leaves:
            path=Path(directory)/name
            assert path.is_relative_to(root) and path.suffix in ('.cmd','.rsp','.json')
            row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
            row['allocated_bytes']=storage.allocated(path);rows.append(row)
    assert len(rows)==11 and sum(row['bytes'] for row in rows)==228984
    plan=dict(schema='zerosis.idle_cache.failed_discovery_retirement.v1',root=str(root),files=rows,
        successful_build=common.artifact(report_path),retained_failure=common.artifact(STAGE/'host_build/failed_discovery.json'),
        reason='Resolved name-shadow warning: keep sealed plan, compressed failing source, compiler logs and diagnosis; retire only regenerable discovery work files.')
    output=STAGE/'failed_discovery_cleanup_plan.json';assert not output.exists()
    output.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
    for row in rows:
        current=common.artifact(row['path'])
        assert all(current[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    for directory in sorted(directories,key=lambda path:len(path.parts),reverse=True):directory.rmdir()
    result=dict(status='PASS_EXACT_RESOLVED_FAILED_DISCOVERY_WORK_REMOVED',root=str(root),files=rows,
        deleted_files=len(rows),deleted_directories=len(directories),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),user_sources_saves_or_default_changed=False)
    (STAGE/'failed_discovery_cleanup_result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ('status','deleted_files','deleted_directories','released_unique_allocated_bytes')}))

if __name__=='__main__':main()
