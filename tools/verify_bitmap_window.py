"""Build and retain owned GPU-window/capture/input/lifetime checks for BitmapWindow."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess

from collect_baseline import PROJECT
from native_build import environment_for, run

VS=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
OWNED={
    "renderer_header":PROJECT/"Source/Presentation/BitmapRenderer.h",
    "renderer":PROJECT/"Source/Presentation/BitmapRenderer.cpp",
    "window_header":PROJECT/"Source/Presentation/BitmapWindow.h",
    "editor_input_header":PROJECT/"Source/Presentation/BitmapEditorInput.h",
    "window":PROJECT/"Source/Presentation/BitmapWindow.cpp",
    "test":PROJECT/"Tests/bitmap_window.cpp",
    "verifier":Path(__file__).resolve(),
}
LIBRARIES=("d2d1.lib","d3d11.lib","dxgi.lib","windowscodecs.lib","ole32.lib","user32.lib","gdi32.lib","wer.lib","imm32.lib")
# The unchanged 167 presenter and 35 transport assertions, plus 32 editor-refresh/focus assertions.
EXPECTED_COMPONENT_CHECKS=234
EXPECTED_WINDOW_COM_APARTMENTS=10
_ERROR_MODE_FLAGS=0x0001|0x0002|0x8000

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def allocate():
    build_root=PROJECT/"Build/BitmapWindow"; evidence_root=PROJECT/"evidence/bitmap_window"
    build_root.mkdir(parents=True,exist_ok=True); evidence_root.mkdir(parents=True,exist_ok=True)
    for _ in range(10):
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+secrets.token_hex(6)
        build,evidence=build_root/run_id,evidence_root/run_id
        try: build.mkdir(exist_ok=False); evidence.mkdir(exist_ok=False); return run_id,build,evidence
        except FileExistsError: continue
    raise RuntimeError("Could not allocate a unique BitmapWindow run ID")

def dependencies(document:Path,source:Path)->list[Path]:
    root=json.loads(document.read_text(encoding="utf-8")); root=root.get("Data",root)
    if not isinstance(root,dict) or not isinstance(root.get("Includes"),list):
        raise RuntimeError("MSVC sourceDependencies output is malformed")
    paths=[]; seen=set()
    for raw in [root.get("Source",str(source)),*root["Includes"]]:
        if not isinstance(raw,str) or not raw: raise RuntimeError("Invalid compiler dependency path")
        path=Path(raw)
        if not path.is_absolute(): path=source.parent/path
        path=path.resolve(strict=True); key=str(path).casefold()
        if key not in seen: seen.add(key); paths.append(path)
    return paths

def compile_binary(compiler:str,env:dict,build:Path,name:str,sources:list[Path],optimization:str):
    linker=shutil.which("link.exe",path=env.get("PATH"))
    if not linker: raise RuntimeError("MSVC linker is unavailable")
    common=["/nologo","/std:c++14","/EHsc","/W4","/WX",optimization,"/MD","/fp:strict",
            "/DWIN32","/D_WIN32_WINNT=0x0A00","/DNOMINMAX","/DWIN32_LEAN_AND_MEAN",
            "/DZEROSIS_BITMAP_WINDOW_DIAGNOSTICS"]
    objects=[]; tus=[]; output=[]
    for i,source in enumerate(sources):
        obj=build/f"{name}_{i}.obj"; rsp=build/f"{name}_{i}.rsp"; dep=build/f"{name}_{i}.sourceDependencies.json"
        flags=[*common,"/c",f'"{source}"',f'/Fo"{obj}"',f'/sourceDependencies "{dep}"']
        rsp.write_text("\n".join(flags)+"\n",encoding="utf-8",newline="\n")
        compiled=run([compiler,f"@{rsp}"],cwd=build,env=env,timeout=180)
        text=(compiled.stdout+compiled.stderr).decode("mbcs",errors="replace")
        log=build/f"{name}_{i}.compile.log"; log.write_text(text,encoding="utf-8",newline="\n"); output.append(text)
        if compiled.returncode or re.search(r"\bwarning\s+C\d+",text,re.I):
            raise RuntimeError(f"{name} compile failed/warned ({compiled.returncode}):\n{text[-5000:]}")
        if not obj.is_file() or not dep.is_file(): raise RuntimeError("Compiler omitted object/dependency output")
        deps=dependencies(dep,source); objects.append(obj)
        tus.append({"source":str(source),"source_sha256":sha(source),"response":str(rsp),"response_sha256":sha(rsp),
                    "arguments":flags,"object":str(obj),"object_sha256":sha(obj),"dependency_document":str(dep),
                    "dependency_document_sha256":sha(dep),"dependencies":[str(p) for p in deps],
                    "compile_log":str(log),"compile_log_sha256":sha(log)})
    exe=build/f"{name}.exe"; link_rsp=build/f"{name}.link.rsp"
    link_flags=[*(f'"{obj}"' for obj in objects),f'/OUT:"{exe}"',"/INCREMENTAL:NO","/MACHINE:X64","/Brepro",
                "/WX","/OPT:REF","/OPT:ICF","/SUBSYSTEM:CONSOLE","/VERBOSE:LIB",*LIBRARIES]
    link_rsp.write_text("\n".join(link_flags)+"\n",encoding="utf-8",newline="\n")
    linked=run([linker,f"@{link_rsp}"],cwd=build,env=env,timeout=180)
    link_text=(linked.stdout+linked.stderr).decode("mbcs",errors="replace")
    link_log=build/f"{name}.link.log"; link_log.write_text(link_text,encoding="utf-8",newline="\n"); output.append(link_text)
    if linked.returncode or re.search(r"\bwarning\s+(?:C|LNK)\d+",link_text,re.I):
        raise RuntimeError(f"{name} link failed/warned ({linked.returncode}):\n{link_text[-5000:]}")
    loaded={}
    for line in link_text.splitlines():
        for lib in LIBRARIES:
            match=re.search(r"([A-Za-z]:\\.*?"+re.escape(lib)+r")",line,re.I)
            if match:
                path=Path(match.group(1).strip('" ').replace('\\\\','\\'))
                if path.is_file(): loaded.setdefault(path.name.casefold(),path.resolve())
    if set(loaded)!={x.casefold() for x in LIBRARIES}:
        raise RuntimeError(f"Could not identify all resolved libraries: {loaded}")
    record={"optimization":optimization,"compiler":str(Path(compiler).resolve()),"compiler_sha256":sha(Path(compiler).resolve()),
            "linker":str(Path(linker).resolve()),"linker_sha256":sha(Path(linker).resolve()),
            "link_response":str(link_rsp),"link_response_sha256":sha(link_rsp),"link_arguments":link_flags,
            "link_log":str(link_log),"link_log_sha256":sha(link_log),
            "resolved_libraries":{k:{"path":str(v),"sha256":sha(v)} for k,v in loaded.items()},
            "translation_units":tus,"executable":str(exe),"executable_sha256":sha(exe)}
    return record,"\n".join(output)

def freeze_dependencies(records:list[dict],frozen:Path):
    all_paths={}
    for record in records:
        for tu in record["translation_units"]:
            for raw in tu["dependencies"]:
                path=Path(raw).resolve(strict=True); all_paths.setdefault(str(path).casefold(),path)
    copied=[]; before={}
    for path in sorted(all_paths.values(),key=lambda p:str(p).casefold()):
        digest=sha(path); before[str(path)]=digest
        try: path.relative_to(frozen.resolve()); target=path
        except ValueError:
            key=hashlib.sha256(str(path).casefold().encode()).hexdigest()[:20]
            target=frozen/"dependencies"/f"{key}_{path.name}"; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
        if sha(target)!=digest: raise RuntimeError(f"Compiler dependency freeze differs: {path}")
        copied.append({"original_path":str(path),"sha256":digest,"frozen_path":str(target),"frozen_sha256":sha(target)})
    return copied,before

def run_owned_test(argv:list[str],cwd:Path,env:dict,timeout:int,on_start=None)->dict:
    """Run one owned child with OS fault UI suppressed and exact exit evidence retained."""
    kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel32.SetErrorMode.argtypes=[ctypes.c_uint]
    kernel32.SetErrorMode.restype=ctypes.c_uint
    previous=kernel32.SetErrorMode(_ERROR_MODE_FLAGS)
    process=None; timed_out=False; cleanup=None
    try:
        process=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        pid=process.pid
        if on_start is not None: on_start(pid)
        try:
            stdout,stderr=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            process.terminate()
            try:
                stdout,stderr=process.communicate(timeout=5)
                cleanup="terminated_owned_pid"
            except subprocess.TimeoutExpired:
                process.kill()
                stdout,stderr=process.communicate(timeout=5)
                cleanup="killed_owned_pid_after_terminate_timeout"
        rc=process.returncode
        return {"pid":pid,"returncode":rc,"returncode_hex":f"0x{rc & 0xffffffff:08X}" if rc is not None else None,
                "timed_out":timed_out,"cleanup":cleanup,
                "stdout":stdout.decode("utf-8",errors="replace").replace("\r\n","\n"),
                "stderr":stderr.decode("utf-8",errors="replace").replace("\r\n","\n")}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        kernel32.SetErrorMode(previous)

def prepared_file(raw:str,root:Path)->Path:
    """Require a regular file beneath the owned root, without reparse ancestors."""
    path=Path(raw)
    if not path.is_absolute(): raise RuntimeError(f"Prepared path is not absolute: {raw}")
    try: relative=path.relative_to(root)
    except ValueError: raise RuntimeError(f"Prepared path escapes its root: {raw}") from None
    if '..' in relative.parts: raise RuntimeError(f"Prepared path traverses its root: {raw}")
    current=root
    for part in ('',*relative.parts):
        if part: current=current/part
        info=current.lstat()
        if current.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise RuntimeError(f"Prepared path has a reparse point: {current}")
    if not path.is_file() or path.resolve(strict=True)!=path:
        raise RuntimeError(f"Prepared path is not a confined regular file: {raw}")
    return path

def validate_prepared_build(run_id:str,report_sha256:str)->dict:
    """Attest a compile-only bundle without copying, compiling or executing it."""
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}',run_id):
        raise RuntimeError('Invalid prepared build ID')
    if not re.fullmatch(r'[0-9a-f]{64}',report_sha256):
        raise RuntimeError('A lowercase SHA-256 of the prepared build report is required')
    root=PROJECT.resolve(strict=True)
    build=root/'Build/BitmapWindow'/run_id
    report=prepared_file(str(root/'evidence/bitmap_window'/run_id/'conformance.json'),root)
    raw=report.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report_sha256:
        raise RuntimeError('Prepared build report SHA-256 differs')
    document=json.loads(raw)
    if (document.get('schema')!='zerosis.bitmap_window_conformance.v1' or
        document.get('run_id')!=run_id or
        document.get('status')!='BITMAP_WINDOW_TEST_BINARIES_BUILT_NOT_EXECUTED' or
        document.get('build_only_requested') is not True or
        document.get('native_test_executed') is not False or document.get('test_runs')!=[] or
        document.get('expected_native_checks')!=EXPECTED_COMPONENT_CHECKS or
        document.get('native_checks_completed')!=0 or
        document.get('native_window_acceptance_complete') is not False or
        document.get('source_inputs_unchanged') is not True or document.get('error') is not None):
        raise RuntimeError('Prepared build is not an intact, unexecuted compile-only result')
    before=document.get('source_hashes_before')
    if not isinstance(before,dict) or set(before)!=set(OWNED) or before!=document.get('source_hashes_after'):
        raise RuntimeError('Prepared source seals are missing or inconsistent')
    checked={str(report).casefold():report_sha256}
    def check(raw_path,digest,scope=build):
        if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
            raise RuntimeError('Invalid prepared file SHA-256')
        path=prepared_file(raw_path,scope)
        key=str(path).casefold()
        if key in checked and checked[key]!=digest: raise RuntimeError(f'Conflicting prepared seals: {path}')
        if sha(path)!=digest: raise RuntimeError(f'Prepared file SHA-256 differs: {path}')
        checked[key]=digest
        return path
    frozen=document.get('frozen_inputs',{})
    if set(frozen)!=set(OWNED): raise RuntimeError('Prepared owned-source list differs')
    for name,row in frozen.items():
        path=check(row['path'],row['sha256'])
        if row['sha256']!=before[name] or path!=build/'frozen'/OWNED[name].relative_to(PROJECT):
            raise RuntimeError(f'Prepared source identity differs: {name}')
        if name!='verifier':
            check(str(OWNED[name]),before[name],root)
    deps=document.get('compiler_dependencies')
    if not isinstance(deps,list) or not deps or document.get('source_dependency_count')!=len(deps):
        raise RuntimeError('Prepared dependency list is missing or inconsistent')
    dep_seals={}
    for row in deps:
        key=str(Path(row['original_path'])).casefold()
        if key in dep_seals or row['sha256']!=row['frozen_sha256']:
            raise RuntimeError('Prepared dependency seals are duplicated or inconsistent')
        check(row['frozen_path'],row['sha256'])
        dep_seals[key]=row['sha256']
    before_deps=document.get('compiler_dependency_hashes_before',{})
    if (before_deps!=document.get('compiler_dependency_hashes_after') or
        {str(Path(k)).casefold():v for k,v in before_deps.items()}!=dep_seals):
        raise RuntimeError('Prepared dependency before/after seals differ')
    libraries=document.get('resolved_libraries',{})
    if set(libraries)!={name.casefold() for name in LIBRARIES}:
        raise RuntimeError('Prepared library set differs')
    for name,row in libraries.items():
        if row['sha256']!=row['frozen_sha256']: raise RuntimeError(f'Prepared library seals differ: {name}')
        check(row['frozen_path'],row['sha256'])
    builds=document.get('builds',{})
    if set(builds)!={'O2','Od'}: raise RuntimeError('Both prepared optimization modes are required')
    all_tu_dependencies=set()
    for label,rec in builds.items():
        if rec.get('optimization')!='/'+label or '/MACHINE:X64' not in rec.get('link_arguments',[]):
            raise RuntimeError(f'Prepared optimization or x64 link contract differs: {label}')
        executable=check(rec['executable'],rec['executable_sha256'])
        if executable!=build/label/f'bitmap_window_{label}.exe':
            raise RuntimeError(f'Prepared executable identity differs: {label}')
        for field in ('link_response','link_log'): check(rec[field],rec[field+'_sha256'])
        if (set(rec.get('resolved_libraries',{}))!=set(libraries) or
            any(row['sha256']!=libraries[name]['sha256'] for name,row in rec['resolved_libraries'].items())):
            raise RuntimeError(f'Prepared linked libraries differ: {label}')
        tus=rec.get('translation_units',[])
        expected_sources={str(Path(frozen[name]['path'])).casefold():before[name] for name in ('test','window','renderer')}
        if len(tus)!=3 or {str(Path(tu['source'])).casefold():tu['source_sha256'] for tu in tus}!=expected_sources:
            raise RuntimeError(f'Prepared translation units differ: {label}')
        for tu in tus:
            source=check(tu['source'],tu['source_sha256'])
            for field in ('response','object','dependency_document','compile_log'): check(tu[field],tu[field+'_sha256'])
            closure={str(Path(p)).casefold() for p in tu['dependencies']}
            if str(source).casefold() not in closure or not closure<=set(dep_seals):
                raise RuntimeError(f'Prepared translation-unit dependency closure differs: {label}')
            all_tu_dependencies.update(closure)
    if all_tu_dependencies!=set(dep_seals): raise RuntimeError('Prepared dependency closure is not exact')
    if sha(report)!=report_sha256: raise RuntimeError('Prepared report changed during validation')
    return {'run_id':run_id,'report':str(report),'report_sha256':report_sha256,'build_root':str(build),
            'conformance':document,'checked_file_count':len(checked),'current_component_sources_match':True,
            'verifier_changed_since_build':sha(OWNED['verifier'])!=before['verifier']}

def run_component_test(rec:dict,label:str,build:Path,env:dict,evidence:Path,result:dict,checkpoint):
    """Use the identical native acceptance gate for new and prepared binaries."""
    opt="/"+label
    # Native retained PNG paths must stay below the fixture's Win32
    # path limit even when metadata evidence is nested more deeply.
    artifacts=build/"test_inputs"; artifacts.mkdir(parents=True,exist_ok=False)
    attempt={"optimization":opt,"status":"ATTEMPTING","pid":None,"returncode":None,
             "returncode_hex":None,"timed_out":False,"cleanup":None,
             "real_user_click_verified":False,"synthetic_messages_posted":True}
    result["test_runs"].append(attempt); checkpoint()
    test=run_owned_test([rec["executable"],"--artifact-dir",str(artifacts)],cwd=build,env=env,timeout=60,
                        on_start=lambda pid:(attempt.update({"pid":pid}),result.update({'native_test_executed':True}),checkpoint()))
    attempt.update({k:test[k] for k in ("pid","returncode","returncode_hex","timed_out","cleanup")})
    output=test["stdout"]+test["stderr"]
    log=evidence/f"test_{label}.log"; log.write_text(output,encoding="utf-8",newline="\n")
    descriptor="hidden owned GPU HWND, PNG and retained-scene capture, resize, one-shot COM lifetime, owner-thread checks, and isolated input queue"
    stdout_lines=test["stdout"].splitlines()
    pass_lines=[line for line in stdout_lines if line.startswith("PASS|")]
    pass_match=re.fullmatch(r"PASS\|(\d+)\|"+re.escape(descriptor),pass_lines[0]) if len(pass_lines)==1 else None
    # Default-off tests deliberately exercise ignored editing keys.
    # Preserve and validate those existing native diagnostics rather
    # than treating them as a second test-result record.
    other_stdout=[line for line in stdout_lines if not line.startswith("PASS|")]
    if any(not re.fullmatch(r"UI_WINDOW_KEY_IGNORED=\d+\|\d+",line) for line in other_stdout):
        raise RuntimeError(f"{label} component emitted unexpected stdout before its PASS record")
    expected_checks=int(pass_match.group(1)) if pass_match else None
    if expected_checks!=EXPECTED_COMPONENT_CHECKS:
        raise RuntimeError(f"{label} component suite reported {expected_checks} checks; expected {EXPECTED_COMPONENT_CHECKS}")
    if test["stderr"].count("WINDOW_COM|initialize|")!=test["stderr"].count("WINDOW_COM|uninitialize|") or test["stderr"].count("WINDOW_COM|initialize|")!=EXPECTED_WINDOW_COM_APARTMENTS:
        raise RuntimeError(f"{label} COM apartment init/uninit markers are unbalanced or unexpected:\n{test['stderr']}")
    gpu_marker="GPU_SCENE_TESTS_PASS|retained_target|png_reference|alpha_clip_uv_order|input_generation|resize|legacy_transition"
    gpu_pass=gpu_marker in output
    prepared_marker="PREPARED_GPU_FRAME_TESTS_PASS|prepare_before_hwnd|same_device_overlay|alpha_composition|commit_consumes|failure_atomicity|hit_generation|retained_resize|no_pending_rejected"
    prepared_pass=prepared_marker in output
    refresh_marker="PREPARED_GPU_REFRESH_TESTS_PASS|same_geometry|failure_preservation|candidate_consumption|input_generation|pixel_scroll_hits"
    refresh_pass=refresh_marker in output
    text_marker="UNICODE_TEXT_INPUT_TESTS_PASS|explicit_opt_in|korean_committed_scalars|surrogate_validation|edit_keys|focus_lifetime|scene_generation|ime_reentry|composition_key_ownership"
    text_pass=text_marker in output
    editor_marker="EDITOR_REFRESH_INPUT_TESTS_PASS|rapid_packet_wait|repeated_edits|original_generations|same_editor_surrogate|owner_focus_rejection|terminal_geometry_barrier|bounded_queue"
    editor_pass=editor_marker in output
    attempt.update({"status":test["stdout"].strip() if test["returncode"]==0 and pass_match and gpu_pass and prepared_pass and refresh_pass and text_pass and editor_pass else "FAILED",
                    "checks":expected_checks,"com_init_markers":test["stderr"].count("WINDOW_COM|initialize|"),
                    "gpu_scene_test_marker":gpu_marker if gpu_pass else None,
                    "prepared_gpu_frame_test_marker":prepared_marker if prepared_pass else None,
                    "prepared_gpu_refresh_test_marker":refresh_marker if refresh_pass else None,
                    "unicode_text_input_test_marker":text_marker if text_pass else None,
                    "editor_refresh_input_test_marker":editor_marker if editor_pass else None,
                    "com_uninit_markers":test["stderr"].count("WINDOW_COM|uninitialize|"),
                    "wer_ui_suppression":"WerSetFlags(WER_FAULT_REPORTING_NO_UI) in test process",
                    "log":{"path":str(log),"sha256":sha(log)},
                    "retained_scene_pngs":[{"path":str(p),"sha256":sha(p),"size":p.stat().st_size}
                                              for p in artifacts.glob("*_scene.png")],
                    "retained_auxiliary_pngs":[{"path":str(p),"sha256":sha(p),"size":p.stat().st_size}
                                              for p in artifacts.glob("*_wrong_size.png")],
                    "retained_gpu_frame_pngs":[{"path":str(p),"sha256":sha(p),"size":p.stat().st_size}
                                              for p in artifacts.glob("*_frame_*.png")],
                    "retained_gpu_scene_pngs":[{"path":str(p),"sha256":sha(p),"size":p.stat().st_size}
                                              for p in artifacts.glob("*_gpu_*.png")],
                    "retained_gpu_refresh_pngs":[{"path":str(p),"sha256":sha(p),"size":p.stat().st_size}
                                                 for p in artifacts.glob("*_refresh_*.png")]})
    checkpoint()
    if test["returncode"] or not pass_match or not gpu_pass or not prepared_pass or not refresh_pass or not text_pass or not editor_pass:
        raise RuntimeError(f"{label} hidden-window tests failed ({test['returncode_hex']} pid={test['pid']} timeout={test['timed_out']}):\n{output[-4000:]}")
    if len(attempt['retained_gpu_frame_pngs']) != 5 or len(attempt['retained_auxiliary_pngs']) != 1:
        raise RuntimeError(f"{label} omitted retained scene update/failure/empty or wrong-size PNG evidence")
    if len(attempt['retained_gpu_scene_pngs'])!=15:
        raise RuntimeError(f"{label} omitted retained texture/reference/capture/resize/failure or prepared-frame GPU-scene evidence")
    if len(attempt['retained_gpu_refresh_pngs'])!=18:
        raise RuntimeError(f"{label} omitted prepared-refresh old/candidate/failure/new-frame evidence")

def prepared_main(args)->int:
    try:
        prepared=validate_prepared_build(args.prepared_build,args.build_report_sha256)
    except Exception as error:
        print(json.dumps({'status':'BITMAP_WINDOW_PREPARED_BUILD_REJECTED','run_id':args.prepared_build,
                          'native_test_executed':False,'error':str(error)},ensure_ascii=False))
        return 1
    if args.validate_only:
        print(json.dumps({k:v for k,v in prepared.items() if k!='conformance'} |
                         {'status':'BITMAP_WINDOW_PREPARED_BUILD_VALIDATED_NOT_EXECUTED',
                          'native_test_executed':False,'native_checks_completed':0,
                          'expected_native_checks':EXPECTED_COMPONENT_CHECKS,
                          'native_window_acceptance_complete':False,
                          'runtime_environment_and_physical_ime_verified':False},ensure_ascii=False))
        return 0
    run_id,build_root,evidence=allocate()
    result={**prepared['conformance'],'run_id':run_id,'status':'RUNNING',
            'build_only_requested':False,'native_test_executed':False,'test_runs':[],
            'source_hashes_before':{name:sha(path) for name,path in OWNED.items()},
            'source_hashes_after':None,'source_inputs_unchanged':False,
            'prepared_build_id':prepared['run_id'],'prepared_build_report':prepared['report'],
            'prepared_build_report_sha256':prepared['report_sha256'],
            'prepared_inputs_checked':prepared['checked_file_count'],
            'compiled_source_hashes':prepared['conformance']['source_hashes_before'],
            'verifier_changed_since_build':prepared['verifier_changed_since_build'],
            'current_verifier_sha256':sha(OWNED['verifier']),
            'scope':'existing compiled x64 component binaries; shared native window/GPU/synthetic-input gate',
            'claim':'Component only; physical IME and full game acceptance remain separate',
            'native_checks_completed':0,'native_window_acceptance_complete':False,'error':None}
    report=evidence/'conformance.json'
    def checkpoint():
        temp=report.with_suffix('.json.tmp')
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        temp.replace(report)
    checkpoint()
    try:
        env=os.environ.copy(); env.pop('ZEROSIS_FOUND_VALUE_CPU_TRACE',None)
        for label in ('O2','Od'):
            # Recheck both binaries and their sealed inputs immediately before each child.
            current=validate_prepared_build(args.prepared_build,args.build_report_sha256)
            rec=current['conformance']['builds'][label]
            artifacts_build=build_root/label; artifacts_build.mkdir(exist_ok=False)
            run_component_test(rec,label,artifacts_build,env,evidence,result,checkpoint)
        validate_prepared_build(args.prepared_build,args.build_report_sha256)
        after={name:sha(path) for name,path in OWNED.items()}
        if after!=result['source_hashes_before']: raise RuntimeError('BitmapWindow sources changed during execution')
        result.update({'status':'BITMAP_WINDOW_COMPONENT_PASS','source_hashes_after':after,
                       'source_inputs_unchanged':True,'native_checks_completed':EXPECTED_COMPONENT_CHECKS,
                       'native_window_acceptance_complete':True})
    except Exception as error:
        result.update({'status':'BITMAP_WINDOW_COMPONENT_FAILED','error':str(error),
                       'source_hashes_after':{name:sha(path) for name,path in OWNED.items() if path.is_file()}})
    checkpoint()
    print(json.dumps({'status':result['status'],'run_id':run_id,'report':str(report),
                      'report_sha256':sha(report),'error':result['error']},ensure_ascii=False))
    return 0 if result['status']=='BITMAP_WINDOW_COMPONENT_PASS' else 1

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--build-only',action='store_true',
                        help='Compile/link both test binaries and seal inputs without executing tests or creating windows')
    mode.add_argument('--prepared-build',metavar='RUN_ID',
                      help='Reuse an attested compile-only bundle instead of compiling another copy')
    parser.add_argument('--build-report-sha256',
                        help='Required exact SHA-256 of the prepared compile-only conformance report')
    parser.add_argument('--validate-only',action='store_true',
                        help='Validate --prepared-build without allocating artifacts or running native code')
    args=parser.parse_args()
    if args.prepared_build is not None and args.build_report_sha256 is None:
        parser.error('--prepared-build requires --build-report-sha256')
    if args.prepared_build is None and (args.validate_only or args.build_report_sha256 is not None):
        parser.error('--validate-only and --build-report-sha256 require --prepared-build')
    if args.prepared_build is not None: return prepared_main(args)
    missing=[str(p) for p in OWNED.values() if not p.is_file()]
    if missing: raise RuntimeError("BitmapWindow source missing: "+", ".join(missing))
    before={name:sha(path) for name,path in OWNED.items()}; run_id,build_root,evidence=allocate()
    frozen=build_root/"frozen"; frozen_owned={}
    for name,path in OWNED.items():
        target=frozen/path.relative_to(PROJECT); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
        if sha(target)!=before[name]: raise RuntimeError(f"Frozen source differs: {name}")
        frozen_owned[name]=target
    result={"schema":"zerosis.bitmap_window_conformance.v1","run_id":run_id,"status":"RUNNING",
             "scope":"hidden_owned_GPU_HWND_PNG_and_retained_scene_capture_resize_input_generations_failure_atomicity_legacy_transitions_prepared_GPU_frame_composition_geometry-preserving_refresh_synthetic_Unicode_transport_bounded_same_editor_queue_and_owned_HWND_focus_only","gamecore_loaded":False,"sdk_linked":False,
            "wpr_capture_started":False,"stage_promoted":False,"mods_written":False,
            "real_user_click_verified":False,"source_hashes_before":before,"source_hashes_after":None,
            "frozen_inputs":{k:{"path":str(v),"sha256":sha(v)} for k,v in frozen_owned.items()},
            "builds":{},"test_runs":[],"compiler_dependencies":[],"resolved_libraries":{},"error":None}
    result['build_only_requested']=args.build_only
    result['native_test_executed']=False
    if args.build_only:
        result['status']='BUILDING_NOT_EXECUTED'
        result['scope']='x64 O2/Od component-test compile/link and input hashes only; no native test or window execution'
    report=evidence/"conformance.json"
    def checkpoint():
        temp=report.with_suffix(".json.tmp")
        with temp.open("w",encoding="utf-8",newline="\n") as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2,sort_keys=True); stream.write("\n")
        temp.replace(report)
    checkpoint()
    try:
        records=[]
        for opt in ("/O2","/Od"):
            label=opt[1:]; build=build_root/label; build.mkdir()
            env,compiler=environment_for(VS,"x64",build); env.pop("ZEROSIS_FOUND_VALUE_CPU_TRACE",None)
            rec,_=compile_binary(compiler,env,build,f"bitmap_window_{label}",
                                  [frozen_owned["test"],frozen_owned["window"],frozen_owned["renderer"]],opt)
            records.append(rec)
            result["builds"][label]=rec
            checkpoint()
            if args.build_only:
                continue
            run_component_test(rec,label,build,env,evidence,result,checkpoint)
        deps,dep_before=freeze_dependencies(records,frozen)
        dep_after={p:sha(Path(p)) for p in dep_before}
        if dep_before!=dep_after: raise RuntimeError("Compiler dependency changed during test build")
        libs={}
        for rec in records:
            for name,row in rec["resolved_libraries"].items():
                if name in libs and libs[name]["sha256"]!=row["sha256"]: raise RuntimeError(f"Library differs across builds: {name}")
                source=Path(row["path"]); target=frozen/"libraries"/source.name; target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists(): shutil.copy2(source,target)
                if sha(target)!=row["sha256"]: raise RuntimeError(f"Frozen library differs: {name}")
                libs[name]={"original_path":str(source),"sha256":row["sha256"],"frozen_path":str(target),"frozen_sha256":sha(target)}
        after={name:sha(path) for name,path in OWNED.items()}
        if before!=after: raise RuntimeError("BitmapWindow sources changed during build")
        result.update({"status":"BITMAP_WINDOW_TEST_BINARIES_BUILT_NOT_EXECUTED" if args.build_only else "BITMAP_WINDOW_COMPONENT_PASS","source_hashes_after":after,
                       "source_inputs_unchanged":True,"compiler_dependencies":deps,
                       "compiler_dependency_hashes_before":dep_before,"compiler_dependency_hashes_after":dep_after,
                       "resolved_libraries":libs,"source_dependency_count":len(deps),
                       "instance_lifetime_contract":"one Create attempt per window; Create, all instance calls, and destruction on the same owner thread",
                       "gpu_scene_contract":"retained BGRA8 scene target; hidden HWND; texture/reference pixel comparison, alpha/clip/UV/order samples, hit generation, failed replacement preservation, resize, legacy-to-GPU transitions, prepared same-device candidate composition, and geometry-preserving prepared-frame refresh with input retention",
                       "wrong_thread_destruction":"fail-fast guard; not invoked by this component test",
                       "claim":"GPU presenter/window/capture component only; no Civ V desktop screen capture or human input"})
        if args.build_only:
            result.update({'expected_native_checks':EXPECTED_COMPONENT_CHECKS,
                           'native_checks_completed':0,'native_window_acceptance_complete':False,
                           'claim':'Test binaries built and inputs sealed only; native 234 checks, GPU/window behavior and physical IME remain pending'})
    except Exception as error:
        result["status"]="BITMAP_WINDOW_BUILD_FAILED" if args.build_only else "BITMAP_WINDOW_COMPONENT_FAILED"; result["error"]=str(error)
        result["source_hashes_after"]={k:sha(v) for k,v in OWNED.items() if v.is_file()}
    checkpoint()
    print(json.dumps({"status":result["status"],"run_id":run_id,"report":str(report),
                      "report_sha256":sha(report),"error":result["error"]},ensure_ascii=False))
    return 0 if result["status"] in ("BITMAP_WINDOW_COMPONENT_PASS","BITMAP_WINDOW_TEST_BINARIES_BUILT_NOT_EXECUTED") else 1

if __name__=="__main__": raise SystemExit(main())
