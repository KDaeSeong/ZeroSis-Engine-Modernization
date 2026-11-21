"""Pure line dispatch execution and actual C++14 renderer TU compilation only.

Never executes a Host, SDK, WIC/D2D/D3D renderer, window, GPU or game. Existing
packet formats and immutable asset payloads are inspected without modification.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from native_build import environment_for,run
from menu_replay_legend_assets import artifact,preflight,MANIFEST
from menu_suite_storage import storage


def stable(row):
    return tuple(row[key] for key in ('path','bytes','sha256','file_identity','mtime_ns','file_attributes'))


def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01')
    args=cli.parse_args(argv)
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Attempt must be a canonical owned label')
    base=PROJECT/'evidence/game_menu/replay_scroll_graph'
    stage=base/'lines'/args.attempt;build=PROJECT/'Build/SceneLineContract'/args.attempt
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True)
    receipt=stage/'result.json'
    if receipt.exists():raise ValueError('Preserve the existing result; select a new explicit attempt')
    sources=[PROJECT/('Source/Presentation/'+name) for name in
        ('BitmapRenderer.h','BitmapRenderer.cpp','BitmapWindow.cpp','WorldViewRenderer.cpp','SceneLineContract.h')]
    sources += [Path(__file__),PROJECT/'Tests/scene_line_contract.cpp']
    before=[artifact(path) for path in sources]
    assets=json.loads(MANIFEST.read_text('utf8'));protected=[artifact(MANIFEST)]+[artifact(row['path']) for row in assets['files']]
    if protected[0]['sha256']!='eb5408e1aeb55ed8469c2fb313f18beb82eb8bab3c2cc9456f60c3b7a1a3d9a1':raise ValueError('Frozen V3 manifest changed')
    if preflight()['file_count']!=154:raise ValueError('Frozen V3 source inventory changed')
    backups={}
    for path in sources[:4]:
        relative=path.relative_to(PROJECT).as_posix();pattern=relative.replace('/','__')+'.*.gz'
        matches=list((base/'source_before').glob(pattern))
        if len(matches)!=1:raise ValueError('Exact changed-file backup is missing or ambiguous')
        backups[path.name]=gzip.decompress(matches[0].read_bytes()).decode('utf8').replace('\r\n','\n')
    actual_renderer=sources[1].read_text('utf8')
    def parser(text):return text[text.index('bool ParseSceneBytes('):text.index('\nstd::uint32_t ReadU32(',text.index('bool ParseSceneBytes('))]
    if parser(backups['BitmapRenderer.cpp'])!=parser(actual_renderer):raise ValueError('Immutable V1/V2 packet parser bytes changed')
    report=dict(schema='zerosis.scene_line.controlled_component.v1',attempt=args.attempt,
        native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,gpu_execution=False,
        actual_renderer_or_wic_d2d_d3d_executed=False,inputs_before=before,
        immutable_assets_before=protected,packet_parser_source_byte_identical=True,
        cpp_dialect='c++14',actual_translation_units_compile_only=[],owned_intermediate_cleanup=[])
    cleanup=['SceneLineContract.obj','SceneLineContract.map','compile.rsp','read_build_environment.cmd']
    try:
        compiled=build_cxx14('SceneLineContract',build,stage,PROJECT/'Tests/scene_line_contract.cpp',[PROJECT/'Source/Presentation'])
        report['pure_fixture_build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        if imports.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Pure helper imports a renderer or unexpected DLL')
        report['pure_fixture_imported_dlls']=names
        result=run([compiled['path']],cwd=build,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report['pure_fixture']=json.loads(result.stdout)
        environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',build)
        for name in ('BitmapRenderer','BitmapWindow','WorldViewRenderer'):
            source=PROJECT/'Source/Presentation'/(name+'.cpp');obj=build/(name+'.obj');response=build/(name+'.compile.rsp')
            cleanup += [obj.name,response.name]
            flags=['/nologo','/c','/std:c++14','/source-charset:windows-1252','/EHsc','/W4','/WX','/O2','/fp:strict','/MT',
                   '/DNOMINMAX','/DWIN32_LEAN_AND_MEAN','/D_WIN32_WINNT=0x0A00',f'"{source}"',f'/Fo"{obj}"']
            response.write_text('\n'.join(flags)+'\n',encoding='utf8')
            compiled_tu=run([compiler,'@'+str(response)],cwd=build,env=environment,timeout=180)
            output=(compiled_tu.stdout+compiled_tu.stderr).decode('mbcs',errors='replace')
            log=stage/('compile_actual_'+name+'_x64_cxx14.txt');log.write_text(output,encoding='utf8')
            if compiled_tu.returncode or re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',output,re.I):
                raise ValueError('Actual translation unit failed or emitted warnings: '+name+'\n'+output[:3500])
            report['actual_translation_units_compile_only'].append(dict(source=artifact(source),compiler=compiler,
                compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),flags=flags,response=artifact(response),
                object=artifact(obj),log=artifact(log),compiler_warnings=0,no_link_or_renderer_execution=True))
        report['inputs_after']=[artifact(path) for path in sources]
        if [stable(row) for row in report['inputs_after']]!=[stable(row) for row in before]:raise ValueError('Owned production sources changed during controlled verification')
        current_protected=[artifact(row['path']) for row in protected]
        if [stable(row) for row in current_protected]!=[stable(row) for row in protected]:raise ValueError('Immutable pack or manifest changed during fixture')
        report.update(status='PASS_SCENE_LINE_PURE_DISPATCH_AND_ACTUAL_TU_COMPILE_ONLY',immutable_assets_preserved=True,
            no_packet_or_asset_profile_changes=True,compiler_and_linker_warnings=0)
    except Exception as error:
        report.update(status='FAIL_SCENE_LINE_CONTROLLED_COMPONENT',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Cleanup target escaped exact private component intermediates')
            row=dict(artifact(path),allocated_bytes=storage.allocated(path));path.unlink()
            row['result']='DELETED_EXACT_OWNED_REGENERABLE_LINE_COMPONENT_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],pure_checks=report['pure_fixture']['checks'],
        actual_translation_units=len(report['actual_translation_units_compile_only']),report=str(receipt),
        removed_intermediates=len(report['owned_intermediate_cleanup']))))
    return 0


if __name__=='__main__':raise SystemExit(main())
