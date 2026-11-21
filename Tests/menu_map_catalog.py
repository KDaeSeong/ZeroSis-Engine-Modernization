"""Build and run the unchanged map catalog against isolated, owned file fixtures.

No Host, GameCore, SDK, CLR, HWND or GPU is loaded. Only a small console
component plus kernel32/bcrypt and compiler tools execute.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program, run
from menu_suite_storage import storage

def seal(path):
    info=storage.ordinary(path)
    return dict(path=str(path),sha256=storage.digest(path),allocated_bytes=storage.allocated(path),**storage.metadata(info))

def cleanup_fixtures(root):
    root=root.absolute();expected=(PROJECT/'Build/MenuMapCatalogComponent/current/fixtures').absolute()
    if root!=expected:raise RuntimeError('Fixture cleanup escaped the exact owned root')
    files=[];directories=[];pending=[root]
    while pending:
        directory=pending.pop()
        if getattr(directory.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Reparse point in owned fixture ancestry')
        directories.append(directory)
        for path in directory.iterdir():
            info=path.lstat()
            if getattr(info,'st_file_attributes',0)&0x400:raise RuntimeError('Fixture reparse point is not an owned regular leaf')
            if path.is_dir():pending.append(path)
            else:files.append((path,seal(path)))
    identities={}
    for path,row in files:
        info=path.stat();identities.setdefault((info.st_dev,info.st_ino),[]).append(path)
    for aliases in identities.values():
        if aliases[0].stat().st_nlink!=len(aliases):raise RuntimeError('Fixture has a hardlink outside its exact owned namespace')
    rows=[]
    for path,row in files:
        now=storage.ordinary(path)
        if ([now.st_dev,now.st_ino],now.st_size)!=(row['file_identity'],row['bytes']) or storage.digest(path)!=row['sha256']:
            raise RuntimeError('Fixture changed after cleanup observation')
        path.unlink();row['result']='DELETED_EXACT_OWNED_FIXTURE_LEAF';rows.append(row)
    for directory in sorted(directories,key=lambda path:len(path.parts),reverse=True):directory.rmdir()
    return rows

def main():
    build=PROJECT/'Build/MenuMapCatalogComponent/current';evidence=PROJECT/'evidence/game_menu/offline_menu_suite/map_catalog'
    build.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    fixtures=build/'fixtures';fixtures.mkdir(exist_ok=True)
    if list(fixtures.iterdir()):raise RuntimeError('Owned map fixture directory contains prior data; refusing overwrite')
    source=Path(__file__).with_suffix('.cpp')
    inputs=[source,PROJECT/'Source/Host/NativeMapCatalog.h',PROJECT/'Source/Host/MenuMapDocument.h',PROJECT/'Source/Host/UiMapMenuContract.h']
    before=[seal(path) for path in inputs]
    report={'schema':'zerosis.menu_map_catalog.component.v1','classification':'REAL_PRODUCTION_HEADER_CONSOLE_COMPONENT_ONLY_NO_HOST_SDK_CLR_HWND_GPU','inputs_before':before}
    completed=None
    try:
        result=build_program(name='MenuMapCatalogComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=build,evidence=evidence,
            source=source,includes=[PROJECT/'Source/Host'],extra_link=['bcrypt.lib'])
        dumpbin=Path(result['compiler']).with_name('dumpbin.exe')
        imports=run([dumpbin,'/dependents',result['path']],cwd=build,timeout=30)
        if imports.returncode:raise RuntimeError('Component import inspection failed')
        imported=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)),key=str.lower)
        if not imported or {name.lower() for name in imported}-{'kernel32.dll','bcrypt.dll'}:
            raise RuntimeError('Unexpected component import dependency: '+repr(imported))
        report.update(build=result,imported_dlls=imported)
        completed=run([result['path'],fixtures],cwd=build,timeout=30)
        if completed.returncode:raise RuntimeError((completed.stdout+completed.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(completed.stdout.decode('utf8')))
        after=[seal(path) for path in inputs]
        if [(x['sha256'],x['bytes']) for x in before]!=[(x['sha256'],x['bytes']) for x in after]:
            raise RuntimeError('Production/test sources changed during component execution')
        report['inputs_after']=after
    except Exception as error:
        report['status']='FAIL_COMPONENT';report['error']=str(error)
        raise
    finally:
        if fixtures.exists():report['fixture_cleanup']=cleanup_fixtures(fixtures)
        intermediates=[]
        for name in ('MenuMapCatalogComponent.obj','MenuMapCatalogComponent.map','compile.rsp','read_build_environment.cmd'):
            path=build/name
            if not path.exists():continue
            if path.absolute().parent!=build.absolute():raise RuntimeError('Intermediate cleanup escaped owned build directory')
            for ancestor in (path,*path.parents):
                if getattr(ancestor.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Reparse point in intermediate ancestry')
            if path.stat().st_nlink!=1:raise RuntimeError('Owned intermediate has untracked hardlinks')
            row=seal(path);path.unlink();row['result']='DELETED_OWNED_REGENERABLE_INTERMEDIATE';intermediates.append(row)
        report['intermediate_cleanup']=intermediates
        report['only_console_fixture_executed']=completed is not None
        (evidence/'cpp_tests.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({key:report[key] for key in ('status','checks','classification','imported_dlls','hardlink_fixture_executed')}))

if __name__=='__main__':main()
