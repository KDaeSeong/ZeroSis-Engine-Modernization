"""Execute owner input policies and compile the actual window TU without launching it."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from native_build import environment_for,run
from menu_replay_assets import artifact
from menu_suite_storage import storage


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01');cli.add_argument('--policy-only',action='store_true');args=cli.parse_args()
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Use a canonical owned attempt label')
    stage=PROJECT/'evidence/game_menu/replay_hover_frame/input_batch'/args.attempt
    build=PROJECT/'Build/MenuReplayInputBatch'/args.attempt
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True)
    receipt=stage/'result.json'
    if receipt.exists():raise ValueError('Preserve the existing result and choose a fresh explicit attempt')
    relatives=['Source/Host/MenuReplayInputBatch.h','Source/Presentation/BitmapKeyPolicy.h',
        'Source/Host/MenuLifecycleWindow.h','Source/Presentation/BitmapWindow.cpp','Source/Presentation/BitmapWindow.h',
        'Source/Presentation/BitmapRenderer.h','Source/Presentation/BitmapPointerPress.h',
        'Tests/menu_replay_input_batch.cpp','Tests/menu_replay_input_batch.py']
    sources=[PROJECT/name for name in relatives];before=[artifact(path) for path in sources]
    if any(any(value>127 for value in path.read_bytes()) for path in sources if path.suffix in ('.h','.cpp')):
        raise ValueError('Actual C++14/windows1252 sources must be ASCII')
    lifecycle=(PROJECT/relatives[2]).read_text('utf8');window=(PROJECT/relatives[3]).read_text('utf8')
    assert '#include "MenuReplayInputBatch.h"' in lifecycle
    branch=re.search(r'if\(page==Page::Replay && hooks\.replayInput && hooks\.replayInput\(input\)\)\{(.*?)\n            \}',lifecycle,re.S).group(1)
    assert 'ContinueHandledMenuReplayInputBatch(input,window.SceneGeneration(),0x300000000ull)' in branch
    assert 'continue;' in branch and branch.rstrip().endswith('break;')
    assert '#include "BitmapKeyPolicy.h"' in window
    assert 'ShouldQueueBitmapGameplayNavigationKey(gameplayInputEnabled_,static_cast<std::uint32_t>(wParam))' in window
    assert 'if(textInputEnabled_ && imeCompositionActive_)return DefWindowProcW' in window
    assert '((lParam&(1ll<<30))==0 || editingKey)' in window
    backups=[]
    base=PROJECT/'evidence/game_menu/replay_hover_frame/source_before'
    for rel in relatives[2:4]:
        matches=list(base.glob(rel.replace('/','__')+'.*.gz'))
        if len(matches)!=1:raise ValueError('Expected one original changed-file backup')
        raw=gzip.decompress(matches[0].read_bytes())
        assert hashlib.sha256(raw).hexdigest().startswith(matches[0].name.split('.')[-2])
        backups.append(dict(backup=artifact(matches[0]),original_bytes=len(raw),original_sha256=hashlib.sha256(raw).hexdigest()))
    report=dict(schema='zerosis.replay_hover_frame.input_batch.v1',attempt=args.attempt,inputs_before=before,
        changed_file_backup_evidence=backups,production_policy_call_sites_checked=True,
        compile_recipe_sha256=hashlib.sha256(inspect.getsource(build_cxx14).encode()).hexdigest(),
        native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,gpu_execution=False,
        owner_scope='Handled same-generation Replay PointerMove including zero/Back keys, Scroll and ControlDrag continue; click/key/modal/Back transitions retain the boundary.',
        keyboard_scope='Gameplay-enabled Home/End/PageUp/PageDown join the existing key whitelist; IME/editing gates unchanged.',
        original_map_wheel=dict(source='Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml:224',
            authored_wheel_steps=10,implemented=True,owner='MenuReplayView TurnScrollKey -> MenuReplayScrollModel::WheelTurn',
            evidence='evidence/game_menu/replay_season_wheel/retail_static_probe.json; Tests/menu_replay_scroll_model.py wheel goldens',
            batch_scope='TurnScrollKey is a replay-owned Scroll key, so each queued wheel message continues the same-generation batch one step at a time.'),
        owned_intermediate_cleanup=[])
    cleanup=['MenuReplayInputBatch.obj','MenuReplayInputBatch.map','compile.rsp','read_build_environment.cmd','BitmapWindow.obj','BitmapWindow.compile.rsp']
    try:
        compiled=build_cxx14('MenuReplayInputBatch',build,stage,PROJECT/'Tests/menu_replay_input_batch.cpp',
            [PROJECT/'Source/Host',PROJECT/'Source/Presentation'])
        report['pure_fixture_build']=compiled
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Pure input fixture imported an unexpected DLL: '+repr(names))
        report['pure_fixture_imported_dlls']=names
        checked=run([compiled['path']],cwd=build,timeout=30)
        if checked.returncode:raise ValueError((checked.stdout+checked.stderr).decode('utf8',errors='replace'))
        report['pure_fixture']=json.loads(checked.stdout)
        if not args.policy_only:
            environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',build)
            source=PROJECT/'Source/Presentation/BitmapWindow.cpp';obj=build/'BitmapWindow.obj';response=build/'BitmapWindow.compile.rsp'
            flags=['/nologo','/c','/std:c++14','/source-charset:windows-1252','/EHsc','/W4','/WX','/O2','/fp:strict','/MT',
                '/DNOMINMAX','/DWIN32_LEAN_AND_MEAN','/D_WIN32_WINNT=0x0A00',f'"{source}"',f'/Fo"{obj}"']
            response.write_text('\n'.join(flags)+'\n',encoding='utf8')
            result=run([compiler,'@'+str(response)],cwd=build,env=environment,timeout=180)
            output=(result.stdout+result.stderr).decode('mbcs',errors='replace');log=stage/'compile_actual_BitmapWindow_x64_cxx14.txt'
            log.write_text(output,encoding='utf8')
            if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',output,re.I):
                raise ValueError('Actual BitmapWindow compilation failed or emitted warnings: '+output[:3500])
            report['actual_window_translation_unit_compile_only']=dict(source=artifact(source),object=artifact(obj),
                compiler=compiler,flags=flags,response=artifact(response),log=artifact(log),compiler_warnings=0,no_link_or_window_execution=True)
        else:
            report['actual_window_translation_unit_compile_only']=dict(performed=False,reason='Window source is verified separately by the pointer-sampling fixture and final actual Host compilation.')
        report['inputs_after']=[artifact(path) for path in sources]
        if report['inputs_after']!=before:raise ValueError('Input-policy source changed during verification')
        report.update(status=('PASS_SDK_FREE_REPLAY_POINTER_BATCH_AND_KEY_POLICY' if args.policy_only else 'PASS_SDK_FREE_REPLAY_BATCH_KEY_POLICY_AND_ACTUAL_WINDOW_TU_COMPILE_ONLY'),compiler_and_linker_warnings=0)
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_BATCH_KEY_POLICY',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Unsafe exact input-policy cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Input cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_INPUT_COMPONENT_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in report['owned_intermediate_cleanup'])
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        with receipt.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],checks=report['pure_fixture']['checks'],report=str(receipt),
        removed_intermediates=len(report['owned_intermediate_cleanup']))))


if __name__=='__main__':raise SystemExit(main())
