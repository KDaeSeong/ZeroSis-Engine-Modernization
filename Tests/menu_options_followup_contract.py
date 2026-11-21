"""Build/run the SDK-free private options console fixture in its owned folder."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program, run
from menu_suite_storage import storage


def main():
    build = PROJECT/'Build/MenuOptionsFollowup/current'
    evidence = PROJECT/'evidence/game_menu/original_menu_followup/options'
    build.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    fixtures = build/'fixtures';fixtures.mkdir(exist_ok=True)
    if list(fixtures.iterdir()):raise RuntimeError('Dedicated component fixtures already contain data')
    source = PROJECT/'Tests/menu_options_contract.cpp'
    inputs = [source,PROJECT/'Source/Host/MenuOptionsContract.h',PROJECT/'Source/Host/MenuOptionsStore.h']
    before = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    result = build_program(name='MenuOptionsFollowup',architecture='x64',
        vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=build,
        evidence=evidence,source=source,includes=[PROJECT/'Source/Host'])
    completed = run([result['path'],fixtures],cwd=build,timeout=30)
    if completed.returncode:
        raise RuntimeError((completed.stdout+completed.stderr).decode('utf-8',errors='replace'))
    report = json.loads(completed.stdout.decode('utf-8'))
    if before != {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}:
        raise RuntimeError('Component source changed during its run')
    if list(fixtures.iterdir()):raise RuntimeError('Component left dedicated fixture data')
    fixtures.rmdir()
    cleanup = []
    for name in ('MenuOptionsFollowup.obj','MenuOptionsFollowup.map','compile.rsp','read_build_environment.cmd'):
        path = build/name
        if path.absolute().parent != build.absolute():raise RuntimeError('Cleanup escaped its exact owned folder')
        for ancestor in (path,*path.parents):
            if getattr(ancestor.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Reparse cleanup target rejected')
        info = storage.ordinary(path)
        if info.st_nlink != 1:raise RuntimeError('Hardlinked intermediate cleanup target rejected')
        row = dict(path=str(path),sha256=storage.digest(path),allocated_bytes=storage.allocated(path),
                   **storage.metadata(info))
        path.unlink();row['result']='DELETED_OWNED_REGENERABLE_INTERMEDIATE';cleanup.append(row)
    report.update(schema='zerosis.original_options.component.v2',build=result,source_sha256=before,
        private_schema='ZEROSIS_PRIVATE_MENU_OPTIONS_V3',legacy_v1_read_without_rewrite=True,legacy_v2_read_without_rewrite=True,
        migration_trigger='FIRST_SUCCESSFUL_CHANGED_COMMIT',unknown_version_bytes_preserved=True,
        classification='SDK_FREE_CONSOLE_ONLY_NO_HOST_SDK_HWND_GPU',intermediate_cleanup=cleanup)
    (evidence/'cpp_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','checks','classification')}))


if __name__ == '__main__':main()
