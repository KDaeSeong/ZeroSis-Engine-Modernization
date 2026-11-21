"""Execute current menu lifecycle method text in a small nonwindow API fixture.

This is not a Host build, real Lua/SDK execution, or game/runtime validation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import environment_for,run

BASE=PROJECT/'evidence/save_menu/20261013_original_screen'
CONTEXT=PROJECT/'Source/Host/UiPopupContext.h'
ROUTER=PROJECT/'Source/Host/InteractiveUiSession.h'
TEMPLATE=PROJECT/'Tests/save_menu_scope_lifecycle.cpp.in'
FAILURE=BASE/'native/attempts/20261013T120632Z_811f6cd8/probe_result.json'
FAILURE_SHA='69c4d304a85b5542e6d6825b733bb3f52479cc466ef9c17d754c96922b89cbfe'

def digest(value: bytes)->str:
    return hashlib.sha256(value).hexdigest()

def block(text: str,marker: str)->tuple[str,int,int]:
    start=text.index(marker)
    if text.find(marker,start+len(marker))>=0:raise AssertionError(f'Ambiguous marker: {marker}')
    opening=text.index('{',start);depth=0;i=opening;state='code'
    while i<len(text):
        c=text[i];nextc=text[i+1:i+2]
        if state=='line':
            if c=='\n':state='code'
        elif state=='comment':
            if c=='*' and nextc=='/':state='code';i+=1
        elif state in ('"',"'"):
            if c=='\\':i+=1
            elif c==state:state='code'
        else:
            if c=='/' and nextc=='/':state='line';i+=1
            elif c=='/' and nextc=='*':state='comment';i+=1
            elif c in ('"',"'"):state=c
            elif c=='{':depth+=1
            elif c=='}':
                depth-=1
                if depth==0:return text[start:i+1],start,i+1
        i+=1
    raise AssertionError(f'Unclosed function: {marker}')

def prepare(context_path: Path=CONTEXT)->tuple[str,list[dict]]:
    records=[]
    texts={CONTEXT:context_path.read_text(encoding='utf-8'),ROUTER:ROUTER.read_text(encoding='utf-8')}
    def extract(path: Path,marker: str)->str:
        value,start,end=block(texts[path],marker)
        records.append({'path':str(context_path if path==CONTEXT else path),'marker':marker,'first_line':texts[path].count('\n',0,start)+1,
            'last_line':texts[path].count('\n',0,end)+1,'source_text_sha256':digest(value.encode()),'chars':len(value)})
        return value
    context_markers=[
        'void Require() const {','void RequireLocalMenuPlayer(int owner,int turn){',
        'void RequireGameMenuOwner(){','void RequireSaveMenuOwner(){','void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){',
        'std::vector<SaveMenuRequest> TakeSaveMenuRequests(){','void Stop(){','void CloseInformationalPopup(){',
        'void Call(lua_CFunction function,void* argument){','void Fault() noexcept {','void RestoreGameMenuCursor() noexcept {',
        'void ReleaseWarResources(){','bool IsNotificationInputPanel() const {','void ApplyEconomicVisibility(bool initialize){','std::string EmbeddedEconomicSnapshots(){',
        'unsigned long SynchronousRandomSeed(){','static std::size_t Utf8Next(', 'static std::size_t Utf8Length(const char* text){',
        'std::string SnapshotText(){','std::string WriteSnapshot(const char* phase){']
    if 'void RequireOwnedMenuPlayer(){' in texts[CONTEXT]:context_markers.append('void RequireOwnedMenuPlayer(){')
    elif context_path==CONTEXT:raise AssertionError('Current source is missing the approved scope correction')
    context_methods=[extract(CONTEXT,m) for m in context_markers]
    router_methods=[extract(ROUTER,m) for m in ('void Require() const {','void Stop(){','bool HasEconomicContext() const {',
        'void DiscardIdleProduction(){','void StopEconomicContexts(){')]
    dispatch,start,end=block(texts[CONTEXT],'bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){')
    records.append({'path':str(context_path),'marker':'DispatchInput whole source reference (only exact common preamble and menu branches executed)',
        'first_line':texts[CONTEXT].count('\n',0,start)+1,'last_line':texts[CONTEXT].count('\n',0,end)+1,
        'source_text_sha256':digest(dispatch.encode()),'chars':len(dispatch),'scope':'MENU_BRANCHES_ONLY'})
    preamble=dispatch[dispatch.index('        Require();'):dispatch.index('        if(kind_==UiPopupKind::EconomicOverview){')]
    save_branch,save_start,save_end=block(dispatch,'        if(kind_==UiPopupKind::SaveMenu){')
    game_branch,game_start,game_end=block(dispatch,'        if(kind_==UiPopupKind::GameMenu){')
    for label,value,offset in [('input-preamble',preamble,dispatch.index(preamble)),('save-input-branch',save_branch,save_start),('game-input-branch',game_branch,game_start)]:
        records.append({'path':str(context_path),'marker':label,'first_line':texts[CONTEXT].count('\n',0,start+offset)+1,
            'source_text_sha256':digest(value.encode()),'chars':len(value),'scope':'EXACT_FRAGMENT_EXECUTED'})
    kind=texts[CONTEXT].split('enum class UiPopupKind',1)[1].split(';',1)[0]
    request=extract(CONTEXT,'struct GameMenuRequest final {')+';'
    input_text=(PROJECT/'Source/Host/UiInputDispatch.h').read_text(encoding='utf-8')
    input_kind='enum class UiInputKind'+input_text.split('enum class UiInputKind',1)[1].split(';',1)[0]+';'
    input_request=block(input_text,'struct UiInputRequest final {')[0]+';'
    tokens={'@KIND_ENUM@':'enum class UiPopupKind'+kind+';','@GAME_REQUEST@':request,'@INPUT_TYPES@':input_kind+'\n'+input_request,
        '@CONTEXT_METHODS@':'\n'.join(context_methods),'@ROUTER_METHODS@':'\n'.join(router_methods),
        '@INPUT_PREAMBLE@':preamble,'@SAVE_INPUT_BRANCH@':save_branch,'@GAME_INPUT_BRANCH@':game_branch}
    result=TEMPLATE.read_text(encoding='utf-8')
    for key,value in tokens.items():
        assert result.count(key)==1,key
        result=result.replace(key,value)
    assert not re.search(r'@[A-Z_]+@',result)
    assert '#define ZEROSIS_UI_WINDOW_PRESENTATION' not in result
    return result,records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vs',type=Path,default=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'))
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    evidence=BASE/'scope_lifecycle'/stamp; evidence.mkdir(parents=True,exist_ok=False)
    build=PROJECT/'Build/SaveMenuScope'/stamp;build.mkdir(parents=True,exist_ok=False)
    code,methods=prepare()
    inputs=[CONTEXT,ROUTER,TEMPLATE,Path(__file__).absolute(),PROJECT/'Source/Host/UiSaveMenuContract.h',PROJECT/'Source/Host/UiInputDispatch.h']
    hashes={str(p):digest(p.read_bytes()) for p in inputs}
    assert digest(FAILURE.read_bytes())==FAILURE_SHA
    source=evidence/'extracted_methods_fixture.cpp';source.write_text(code,encoding='utf-8')
    report={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','scope':'COMPONENT_ONLY_EXACT_METHOD_TEXT_WITH_SDK_SCRIPT_OS_IO_SUBSTITUTES',
        'not_proven':['Host compilation/link','actual Lua/SDK execution','actual HWND lifecycle','native named save/restore','retail game completion'],
        'host_built':False,'native_window_created':False,'game_launched':False,'installed_mods_or_saves_accessed':False,
        'whole_dispatch_input_executed':False,'method_text':methods,'inputs_before':hashes,'generated_fixture':{'path':str(source),'sha256':digest(source.read_bytes())},
        'immutable_failure':{'path':str(FAILURE),'sha256':FAILURE_SHA},'configurations':[]}
    env,compiler=environment_for(args.vs,'x64',build/'environment')
    report['compiler']={'path':compiler,'sha256':digest(Path(compiler).read_bytes())}
    try:
        for optimization in ('O2','Od'):
            directory=build/optimization;directory.mkdir();exe=directory/'scope.exe'
            command=[compiler,'/nologo','/std:c++14','/EHsc','/W4','/WX','/MT',f'/{optimization}','/utf-8',
                f'/I{PROJECT / "Source/Host"}',str(source),f'/Fo{directory / "scope.obj"}',f'/Fe{exe}',
                '/link','/INCREMENTAL:NO','/Brepro','/WX']
            compiled=run(command,cwd=directory,env=env,timeout=45)
            log=evidence/f'compile_{optimization}.log';log.write_bytes(compiled.stdout+compiled.stderr)
            if compiled.returncode:raise RuntimeError(f'Component compile failed: {log}')
            executed=run([exe],cwd=directory,env=env,timeout=15)
            output=executed.stdout+executed.stderr
            logrun=evidence/f'run_{optimization}.log';logrun.write_bytes(output)
            matched=re.search(rb'SAVE_MENU_SCOPE_COMPONENT_PASS=(\d+)\|(\d+)',executed.stdout)
            if executed.returncode or not matched:raise RuntimeError(f'Component failed: {logrun}')
            report['configurations'].append({'optimization':optimization,'returncode':executed.returncode,'cases':int(matched[1]),'checks':int(matched[2]),
                'exe_sha256':digest(exe.read_bytes()),'compile_log':str(log),'compile_log_sha256':digest(log.read_bytes()),
                'run_log':str(logrun),'run_log_sha256':digest(logrun.read_bytes()),'compiler_warnings':0})
        before=BASE/'source_before/stale_menu_scope/Source/Host/UiPopupContext.h'
        assert digest(before.read_bytes())=='55800ba1243f295298b937e3e008cd32897055aa51751bfa4bbf2038fac0d954'
        baseline_code,baseline_methods=prepare(before)
        baseline_source=evidence/'before_scope_methods_fixture.cpp';baseline_source.write_text(baseline_code,encoding='utf-8')
        directory=build/'before_O2';directory.mkdir();exe=directory/'scope_before.exe'
        compiled=run([compiler,'/nologo','/std:c++14','/EHsc','/W4','/WX','/MT','/O2','/utf-8',
            f'/I{PROJECT / "Source/Host"}',str(baseline_source),f'/Fo{directory / "scope.obj"}',f'/Fe{exe}',
            '/link','/INCREMENTAL:NO','/Brepro','/WX'],cwd=directory,env=env,timeout=45)
        log=evidence/'compile_before_O2.log';log.write_bytes(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(f'Before component compile failed: {log}')
        executed=run([exe],cwd=directory,env=env,timeout=15)
        logrun=evidence/'run_before_O2.log';logrun.write_bytes(executed.stdout+executed.stderr)
        expected=b'COMPONENT_ASSERTION_FAILED=Rejected stale child must become faulted'
        assert executed.returncode==1 and expected in executed.stderr,'Before correction did not reproduce the stale-scope failure'
        report['before_correction_reproduction']={'status':'EXPECTED_COMPONENT_FAILURE_REPRODUCED_NOT_GAME_RUNTIME',
            'returncode':executed.returncode,'expected_assertion':expected.decode(),'fixture_sha256':digest(baseline_source.read_bytes()),
            'exe_sha256':digest(exe.read_bytes()),'compile_log':str(log),'compile_log_sha256':digest(log.read_bytes()),
            'run_log':str(logrun),'run_log_sha256':digest(logrun.read_bytes()),'selected_method_text':baseline_methods}
        report['inputs_after']={str(p):digest(p.read_bytes()) for p in inputs}
        report['selected_method_text_after']=prepare()[1]
        assert report['selected_method_text_after']==methods,'Selected function text changed during component test'
        assert digest(FAILURE.read_bytes())==FAILURE_SHA,'Historical failure changed'
        report['status']='SAVE_MENU_SCOPE_NONWINDOW_COMPONENT_PASS'
    except Exception as error:
        report['status']='SAVE_MENU_SCOPE_NONWINDOW_COMPONENT_FAIL';report['error']=str(error)
        raise
    finally:
        # Only this invocation's regenerable binary/object/environment files.
        approved=(PROJECT/'Build/SaveMenuScope').absolute()
        assert build.absolute().parent==approved and stamp==build.name
        temporary_bytes=sum(p.stat().st_size for p in build.rglob('*') if p.is_file())
        shutil.rmtree(build)
        report['cleanup']={'path':str(build),'temporary_bytes_removed':temporary_bytes,'removed':not build.exists(),
            'retained':'Changed-file before copy, source fixture/template, extracted method unit, logs and receipt; no component binary'}
        path=evidence/'conformance.json';path.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':report['status'],'report':str(path),'sha256':digest(path.read_bytes()),
            'configurations':[(r['optimization'],r['cases'],r['checks']) for r in report['configurations']],
            'temporary_bytes_removed':temporary_bytes}))

if __name__=='__main__':main()
