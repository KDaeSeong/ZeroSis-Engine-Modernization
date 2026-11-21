"""Verify exactly one production map edge: session180 + name100 wchar.

Runs only a compiler and an isolated file-only console fixture. The Host,
GameCore, SDK, CLR, window and GPU are never loaded. Production is not edited.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program,run
from menu_suite_storage import storage

def api_path(path):
    absolute=str(path.absolute())
    return Path(absolute if absolute.startswith('\\\\?\\') else '\\\\?\\'+absolute)

def seal(path):
    native=api_path(path);info=storage.ordinary(native)
    return dict(path=str(path),sha256=storage.digest(native),allocated_bytes=storage.allocated(native),**storage.metadata(info))

def cleanup(root):
    expected=(PROJECT/'Build/MenuMapLongPathComponent/current/fixtures').absolute()
    if root.absolute()!=expected:raise RuntimeError('Cleanup escaped the exact owned long-path fixture')
    directories=[];files=[];pending=[root]
    while pending:
        directory=pending.pop()
        if getattr(api_path(directory).lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Reparse point in fixture ancestry')
        directories.append(directory)
        for path in directory.iterdir():
            native=api_path(path)
            if getattr(native.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Fixture reparse leaf is not owned')
            if native.is_dir():pending.append(path)
            else:
                if native.stat().st_nlink!=1:raise RuntimeError('Unexpected fixture hardlink')
                files.append((path,seal(path)))
    result=[]
    for path,row in files:
        native=api_path(path);info=storage.ordinary(native)
        if [info.st_dev,info.st_ino]!=row['file_identity'] or storage.digest(native)!=row['sha256']:
            raise RuntimeError('Long-path fixture changed after cleanup observation')
        native.unlink();row['result']='DELETED_EXACT_OWNED_FILE_FIXTURE';result.append(row)
    for path in sorted(directories,key=lambda value:len(value.parts),reverse=True):path.rmdir()
    return result

def main():
    build=PROJECT/'Build/MenuMapLongPathComponent/current';evidence=PROJECT/'evidence/game_menu/offline_menu_suite/map_catalog/long_path'
    build.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    fixtures=build/'fixtures';fixtures.mkdir(exist_ok=True)
    if list(fixtures.iterdir()):raise RuntimeError('Prior long-path fixture data is preserved; refusing overwrite')
    inputs=[Path(__file__),Path(__file__).with_suffix('.cpp'),PROJECT/'Tests/menu_map_catalog.cpp',
            PROJECT/'Source/Host/NativeMapCatalog.h',PROJECT/'Source/Host/MenuMapDocument.h',PROJECT/'Source/Host/UiMapMenuContract.h']
    before=[seal(path) for path in inputs]
    report={'schema':'zerosis.menu_map_catalog.long_path.v1','scope':'ONLY_SESSION180_NAME100_SAVE_LIST_OVERWRITE_DELETE','inputs_before':before,'production_sources_edited':False}
    try:
        result=build_program(name='MenuMapLongPathComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=build,evidence=evidence,
            source=Path(__file__).with_suffix('.cpp'),includes=[PROJECT/'Source/Host'],extra_link=['bcrypt.lib'])
        imported=run([Path(result['compiler']).with_name('dumpbin.exe'),'/dependents',result['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)),key=str.lower)
        if imported.returncode or not names or {name.lower() for name in names}-{'kernel32.dll','bcrypt.dll'}:
            raise RuntimeError('Unexpected file-component dependency: '+repr(names))
        report.update(build=result,imported_dlls=names)
        completed=run([result['path'],fixtures],cwd=build,timeout=30)
        if completed.returncode:raise RuntimeError((completed.stdout+completed.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(completed.stdout.decode('utf8')))
        after=[seal(path) for path in inputs]
        if [(x['bytes'],x['sha256']) for x in before]!=[(x['bytes'],x['sha256']) for x in after]:
            raise RuntimeError('Production/test source changed during the bounded long-path fixture')
        report['inputs_after']=after
    except Exception as error:
        report.update(status='FAIL_LONG_PATH_FIXTURE',error=str(error));raise
    finally:
        if fixtures.exists():report['fixture_cleanup']=cleanup(fixtures)
        removed=[]
        for name in ('MenuMapLongPathComponent.obj','MenuMapLongPathComponent.map','compile.rsp','read_build_environment.cmd'):
            path=build/name
            if not path.exists():continue
            if path.absolute().parent!=build.absolute() or path.stat().st_nlink!=1:
                raise RuntimeError('Intermediate left its exact owned scope')
            row=seal(path);path.unlink();row['result']='DELETED_OWNED_REGENERABLE_INTERMEDIATE';removed.append(row)
        report['intermediate_cleanup']=removed
        (evidence/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({key:report[key] for key in ('status','session_wchars','target_wchars','save','list','overwrite','delete','save_winerror','list_winerror','delete_winerror')}))

if __name__=='__main__':main()
