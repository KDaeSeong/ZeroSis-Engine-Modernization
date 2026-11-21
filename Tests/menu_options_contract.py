"""Retained preference regression, updated for explicit V3 migration."""
from __future__ import annotations
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_frontend_assets import artifact
from menu_suite_storage import storage
from native_build import run


def metadata(path):
    path=Path(path);info=storage.ordinary(path)
    return dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(path))


def main():
    # Preserve the unresolved old auxiliary console rather than replacing it.
    build=PROJECT/'Build/MenuOptionsComponent/reward_v3';stage=PROJECT/'evidence/game_menu/options_reward_popups/contract/legacy_contract_regression'
    build.mkdir(parents=True,exist_ok=True);stage.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).with_suffix('.cpp');inputs=[source,Path(__file__),PROJECT/'Source/Host/MenuOptionsContract.h',PROJECT/'Source/Host/MenuOptionsStore.h',PROJECT/'evidence/game_menu/options_reward_popups/migration_plan.json']
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14);signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()).hexdigest()[:20]
    evidence=stage/signature;receipt=evidence/'result.json';old_aux=PROJECT/'Build/MenuOptionsComponent/current/MenuOptionsComponent.exe';old_before=metadata(old_aux) if old_aux.exists() else None
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'))
        if old.get('status')=='PASS' and old.get('inputs_before')==before and artifact(old['build']['path'])['sha256']==old['build']['sha256']:
            print(json.dumps(dict(status='PASS',checks=old['checks'],report=str(receipt),reused_identical_inputs=True)));return 0
        raise ValueError('Existing legacy contract proof cannot be overwritten')
    evidence.mkdir();fixtures=build/('fixtures_'+signature)
    if fixtures.exists():raise ValueError('Owned legacy fixture directory contains prior data')
    fixtures.mkdir();report=dict(schema='zerosis.menu_options.v3_legacy_regression.v1',inputs_before=before,cpp_dialect='c++14',
        old_auxiliary_executable_before=old_before,new_output_reason='Preserve old current auxiliary with unresolved purpose; compile the updated C++14 regression in reward_v3 without copying any project or old binary.',
        legacy_v1_v2_literals_preserved=True,native_host_sdk_window_gpu_or_audio_executed=False,actual_owned_store_directory=str(fixtures),compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest())
    try:
        report['build']=build_cxx14('MenuOptionsComponent',build,evidence,source,[PROJECT/'Source/Host']);built=report['build']
        deps=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=build,timeout=30);names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',deps.stdout.decode('mbcs',errors='replace'),re.M)))
        if deps.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected legacy regression imports '+repr(names))
        report['component_imported_dlls']=names;completed=run([built['path'],str(fixtures)],cwd=build,timeout=30)
        if completed.returncode:raise RuntimeError((completed.stdout+completed.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(completed.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if before!=report['inputs_after']:raise ValueError('Legacy contract source changed during regression')
        report['old_auxiliary_executable_after']=metadata(old_aux) if old_aux.exists() else None
        if report['old_auxiliary_executable_after']!=old_before:raise ValueError('Preserved old auxiliary executable changed')
    except Exception as error:
        report.update(status='FAIL_V3_LEGACY_CONTRACT_REGRESSION',error=str(error));raise
    finally:
        cleanup=[];allowed={'menu-options.zssettings','menu-options.pending','menu-options.lock','protected-test-input.txt'};files=list(fixtures.iterdir())
        for path in files:
            if not path.is_file():raise ValueError('Unexpected legacy fixture directory')
            match=re.fullmatch(r'retired_(\d+)_(.+)',path.name);original=match.group(2) if match else path.name
            if original not in allowed:raise ValueError('Unexpected legacy fixture file')
            info=storage.ordinary(path);allocation=storage.allocated(path)
            aliases=[other for other in files if other.exists() and [os.stat(other,follow_symlinks=False).st_dev,os.stat(other,follow_symlinks=False).st_ino]==[info.st_dev,info.st_ino]]
            if info.st_nlink!=len(aliases):raise ValueError('Owned hardlink fixture has an unowned alias')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,
                file_allocation_before_unlink=allocation,allocated_bytes=allocation if info.st_nlink==1 else 0,original_test_scenario_path=str(fixtures/original),allocation_policy='Actual release counts only the final owned hardlink alias.')
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Legacy fixture changed before exact cleanup')
            path.unlink();row['result']='DELETED_EXACT_OWNED_LEGACY_PREFERENCE_FIXTURE';cleanup.append(row)
        if any(fixtures.iterdir()):raise ValueError('Legacy fixture cleanup did not empty directory')
        fixtures.rmdir()
        for name in ['MenuOptionsComponent.obj','MenuOptionsComponent.map','compile.rsp','read_build_environment.cmd']:
            path=build/name
            if not path.exists():continue
            row=metadata(path);info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Unsafe legacy compiler cleanup')
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Legacy compiler intermediate changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_LEGACY_CONTRACT_INTERMEDIATE';cleanup.append(row)
        report['owned_intermediate_cleanup']=cleanup;report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in cleanup);report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in cleanup)
        report['owned_unique_file_id_logical_bytes_removed']=sum(row['bytes'] for row in {tuple(row['file_identity']):row for row in cleanup}.values());report['owned_fixture_directory_removed']=not fixtures.exists()
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),cleaned_allocated_bytes=report['owned_intermediate_allocated_bytes_removed'],old_aux_preserved=True)));return 0


if __name__=='__main__':raise SystemExit(main())
