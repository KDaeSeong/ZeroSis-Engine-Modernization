"""Execute the current-pointer reader with fake queries; compile Window TU only.

The console fixture extracts the exact production reader, mapping and hit-test
bodies and resolves cursor/window calls to C++ fakes. No production HWND, Host,
SDK, renderer, cursor query or GPU path is linked or executed.
"""
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
from menu_replay_legend_assets import artifact
from menu_suite_storage import storage
from native_build import environment_for,run

BASE=PROJECT/'evidence/game_menu/replay_hover_frame'
SOURCE=PROJECT/'Source/Presentation'


def block(text,token):
    if text.count(token)!=1:raise ValueError('Production extraction is missing or ambiguous: '+token)
    first=text.index(token);brace=text.index('{',first);depth=0
    for end in range(brace,len(text)):
        if text[end]=='{':depth+=1
        elif text[end]=='}':
            depth-=1
            if not depth:return text[first:end+1]
    raise ValueError('Unclosed production block: '+token)


def declaration(text,token):
    value=block(text,token)
    if text[text.index(value)+len(value)]!=';':raise ValueError('Unexpected production declaration terminator')
    return value+';'


def stable(row):
    return tuple(row[key] for key in ('path','bytes','sha256','file_identity','mtime_ns','file_attributes'))


def prepare_extraction(directory):
    header=(SOURCE/'BitmapWindow.h').read_text('utf8');cpp=(SOURCE/'BitmapWindow.cpp').read_text('utf8')
    backups={}
    for name in ('BitmapWindow.h','BitmapWindow.cpp'):
        matches=list((BASE/'source_before').glob('Source__Presentation__'+name+'.*.gz'))
        if len(matches)!=1:raise ValueError('Exact pre-edit changed-file backup missing: '+name)
        backups[name]=gzip.decompress(matches[0].read_bytes()).decode('utf8').replace('\r\n','\n')
    tokens=['BitmapDisplayRect BitmapWindow::ComputeDisplayRect(',
            'bool BitmapWindow::MapClientPointToLogical(',
            'std::uint64_t BitmapWindow::HitTestLogicalPoint(',
            'BitmapInputEvent BitmapWindow::CurrentPointerInput() const']
    functions=[block(cpp,token) for token in tokens]
    for token in tokens[:3]:
        if block(cpp,token)!=block(backups['BitmapWindow.cpp'],token):raise ValueError('Existing mapping/hit-test body changed')
    queue='void BitmapWindow::QueuePointerMove('
    if block(cpp,queue)!=block(backups['BitmapWindow.cpp'],queue):raise ValueError('Existing queued pointer semantics changed')
    def mouse(text):return text[text.index('    case WM_MOUSEMOVE:'):text.index('    case WM_MOUSEWHEEL:')]
    if mouse(cpp)!=mouse(backups['BitmapWindow.cpp']):raise ValueError('Existing native mouse move/leave message path changed')
    if cpp.replace(functions[-1]+'\n\n','',1)!=backups['BitmapWindow.cpp']:raise ValueError('Window implementation diff exceeds the new const reader')
    for token in ('enum class BitmapInputKind :','struct BitmapInputEvent {','struct BitmapDisplayRect {'):
        if declaration(header,token)!=declaration(backups['BitmapWindow.h'],token):raise ValueError('Existing public input/display declaration changed')
    if header.count('BitmapInputEvent CurrentPointerInput() const;')!=1:raise ValueError('Current pointer API is missing or not const')
    declarations='\n'.join(declaration(header,token) for token in ('enum class BitmapInputKind :','struct BitmapInputEvent {','struct BitmapDisplayRect {'))
    fixture='''namespace ZeroSisPresentation {
'''+declarations+'''
constexpr std::uint32_t kLogicalWidth=1920,kLogicalHeight=1080;
class BitmapWindow final {
public:
    DWORD ownerThreadId_=17;std::uint64_t sceneGeneration_=9;
    bool productionPointerInputEnabled_=true;HWND hwnd_=123;bool closing_=false;
    std::uint32_t logicalWidth_=1920,logicalHeight_=1080;
    std::vector<HitRecord> hits_;PixelHitMap pixelHits_;std::vector<BitmapInputEvent> pending_;
    bool captureSentinel=true,trackingSentinel=true,overflowSentinel=false;
    BitmapInputEvent CurrentPointerInput() const;
    static BitmapDisplayRect ComputeDisplayRect(std::uint32_t,std::uint32_t);
    static bool MapClientPointToLogical(std::uint32_t,std::uint32_t,std::int32_t,std::int32_t,float*,float*);
    std::uint64_t HitTestLogicalPoint(float,float,bool* uiHit=nullptr) const;
};
'''+ '\n'.join(functions)+'\n}\n'
    target=directory/'bitmap_current_pointer_actual.inc';target.write_text(fixture,encoding='ascii')
    return dict(verbatim_function_sha256={token:hashlib.sha256(value.encode()).hexdigest() for token,value in zip(tokens,functions)},
        production_event_declaration_sha256=hashlib.sha256(declaration(header,'struct BitmapInputEvent {').encode()).hexdigest(),
        generated_fixture=artifact(target),existing_mapping_hit_queue_and_move_leave_bodies_identical=True,
        implementation_diff_only_new_const_reader=True,comparison_newlines='CRLF normalized to LF')


def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01');args=cli.parse_args(argv)
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Use a bounded explicit owned attempt label')
    stage=BASE/'pointer_sampling'/args.attempt;build=PROJECT/'Build/BitmapCurrentPointerSampling'/args.attempt
    receipt=stage/'result.json'
    if receipt.exists() or build.exists():raise ValueError('Inspect existing outputs; do not replay a used attempt')
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=False)
    inputs=[SOURCE/'BitmapWindow.h',SOURCE/'BitmapWindow.cpp',SOURCE/'BitmapRenderer.h',SOURCE/'BitmapPointerPress.h',
        PROJECT/'Tests/bitmap_current_pointer.cpp',Path(__file__)]
    before=[artifact(path) for path in inputs]
    report=dict(schema='zerosis.bitmap.current_pointer.controlled.v1',attempt=args.attempt,inputs_before=before,
        api='BitmapInputEvent BitmapWindow::CurrentPointerInput() const',
        native_host_sdk_hwnd_cursor_query_or_gpu_executed=False,actual_window_translation_unit_executed=False,
        cpp_dialect='c++14',compile_recipe_sha256=hashlib.sha256(inspect.getsource(build_cxx14).encode()).hexdigest(),
        scope='Verbatim production reader/mapping/hit-test functions with fake read-only OS queries; actual Window TU compiled only.',
        owned_intermediate_cleanup=[])
    cleanup=['bitmap_current_pointer_actual.inc','BitmapCurrentPointerSampling.obj','BitmapCurrentPointerSampling.map',
        'compile.rsp','read_build_environment.cmd','BitmapWindow.obj','BitmapWindow.compile.rsp']
    try:
        if any(any(value>127 for value in path.read_bytes()) for path in inputs):raise ValueError('Owned production/test sources must stay ASCII/windows-1252 compatible')
        report['production_extraction']=prepare_extraction(build)
        compiled=build_cxx14('BitmapCurrentPointerSampling',build,stage,PROJECT/'Tests/bitmap_current_pointer.cpp',[SOURCE,build])
        report['pure_fixture_build']=compiled
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Pure cursor fixture imported native window/rendering APIs: '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path']],cwd=build,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report['pure_fixture']=json.loads(result.stdout)
        environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',build)
        source=SOURCE/'BitmapWindow.cpp';obj=build/'BitmapWindow.obj';response=build/'BitmapWindow.compile.rsp'
        flags=['/nologo','/c','/std:c++14','/source-charset:windows-1252','/EHsc','/W4','/WX','/O2','/fp:strict','/MT',
            '/DNOMINMAX','/DWIN32_LEAN_AND_MEAN','/D_WIN32_WINNT=0x0A00',f'"{source}"',f'/Fo"{obj}"']
        response.write_text('\n'.join(flags)+'\n',encoding='utf8')
        result=run([compiler,'@'+str(response)],cwd=build,env=environment,timeout=180)
        output=(result.stdout+result.stderr).decode('mbcs',errors='replace');log=stage/'compile_actual_BitmapWindow_x64_cxx14.txt';log.write_text(output,encoding='utf8')
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+|\uacbd\uace0\s+[A-Z]+\d+',output,re.I):raise ValueError('Actual Window TU compile failed or emitted warnings: '+output[:2500])
        report['actual_window_translation_unit_compile_only']=dict(source=artifact(source),response=artifact(response),object=artifact(obj),log=artifact(log),
            compiler=compiler,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),flags=flags,warnings=0,linked_or_executed=False)
        report['inputs_after']=[artifact(path) for path in inputs]
        if [stable(row) for row in report['inputs_after']]!=[stable(row) for row in before]:raise ValueError('Owned pointer sources changed during controlled verification')
        report.update(status='PASS_CURRENT_POINTER_FAKE_QUERY_EXECUTION_AND_ACTUAL_WINDOW_COMPILE_ONLY',compiler_and_linker_warnings=0)
    except Exception as error:
        report.update(status='FAIL_CURRENT_POINTER_CONTROLLED_COMPONENT',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Pointer intermediate cleanup escaped its exact private build leaf')
            row=dict(artifact(path),allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Pointer cleanup candidate identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_POINTER_SAMPLING_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['pure_fixture']['checks'],samples=report['pure_fixture']['samples'],
        actual_window_translation_units_compiled=1,report=str(receipt),removed_intermediates=len(report['owned_intermediate_cleanup']),
        intermediate_allocated_bytes_removed=report['intermediate_allocated_bytes_removed'])))
    return 0


if __name__=='__main__':raise SystemExit(main())
