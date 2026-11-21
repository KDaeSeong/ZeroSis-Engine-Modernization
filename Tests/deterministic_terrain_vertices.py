"""Run only the bounded x64 CPU vertex component; never load the Host or SDK."""
from pathlib import Path
import argparse, gzip, hashlib, json, os, re, sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase10/multicore'
sys.path[:0]=[str(PROJECT/'tools')]
import build_exit_confirm_host as common
from native_build import environment_for, run
from menu_suite_storage import storage

def read_inputs():
    files=set();todo=[PROJECT/'Tests/deterministic_terrain_vertices.cpp',Path(__file__).absolute()]
    while todo:
        path=todo.pop()
        if path in files:continue
        files.add(path)
        for name in re.findall(r'^\s*#include\s+"([^"]+)"',path.read_text('utf8'),re.M):
            options=[path.parent/name,PROJECT/'Source/Presentation'/name]
            found=next((p.absolute() for p in options if p.is_file()),None)
            assert found is not None,name
            assert found.is_relative_to(PROJECT/'Source/Presentation'),str(found)
            todo.append(found)
    return [common.artifact(path) for path in sorted(files)]

def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=1);stream.write('\n')

def main(attempt):
    assert re.fullmatch(r'[0-9]{2}',attempt)
    out=STAGE/('parallel_attempt'+attempt);assert not out.exists(),'Use a fresh attempt after inspecting a failure'
    out.mkdir(parents=True);work=out/'parallel_work';work.mkdir()
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    before=read_inputs();write_new(out/'parallel_started.json',dict(inputs=before,host_gamecore_clr_hwnd_gpu_audio_executed=False))
    environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',work)
    records=[]
    for mode,flag in [('optimized','/O2'),('unoptimized','/Od')]:
        exe=work/('parallel_terrain_'+mode+'.exe');obj=exe.with_suffix('.obj');mapfile=exe.with_suffix('.map');rsp=exe.with_suffix('.rsp')
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',flag,'/fp:strict','/MT','/DNOMINMAX','/DWIN32_LEAN_AND_MEAN',
            '/I"'+str(PROJECT/'Source/Presentation')+'"','"'+str(PROJECT/'Tests/deterministic_terrain_vertices.cpp')+'"',
            '/Fo"'+str(obj)+'"','/Fe"'+str(exe)+'"']
        links=['/INCREMENTAL:NO','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MACHINE:X64','/MAP:'+str(mapfile)]
        with rsp.open('x',encoding='utf8') as stream:stream.write('\n'.join(flags)+'\n')
        compiled=run([compiler,'@'+str(rsp),'/link',*links],cwd=work,env=environment,timeout=60)
        text=(compiled.stdout+compiled.stderr).decode('mbcs',errors='replace')
        log=out/('parallel_compile_'+mode+'.txt')
        with log.open('x',encoding='utf8') as stream:stream.write(text)
        assert compiled.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',text,re.I),'Component compile failed: '+str(log)
        exe_ref=common.artifact(exe)
        dependencies=run([Path(compiler).with_name('dumpbin.exe'),'/dependents',exe],cwd=work,env=environment,timeout=20)
        assert dependencies.returncode==0
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',dependencies.stdout.decode('mbcs',errors='replace'),re.M)))
        assert {name.lower() for name in libraries}=={'kernel32.dll'},libraries
        executed=run([exe],cwd=work,env=environment,timeout=30)
        stdout=executed.stdout.decode('ascii');stderr=executed.stderr.decode('ascii')
        raw=out/('parallel_output_'+mode+'.json')
        write_new(raw,dict(returncode=executed.returncode,stdout=stdout,stderr=stderr,console_component=exe_ref,imported_dlls=libraries))
        match=re.search(r'PASS_PARALLEL_TERRAIN checks=(\d+) vertices=(\d+) useful_parallel_vertex_jobs=(\d+) vertex_digest=([0-9a-f]{16}) max_workers=4 runtime_executed=0\s*\Z',stdout)
        assert executed.returncode==0 and not stderr and match,'Component execution failed: '+str(raw)
        records.append(dict(mode=mode,compiler=common.artifact(compiler),flags=flags+['/link']+links,executable=exe_ref,
            compile_log=common.artifact(log),output=common.artifact(raw),imported_dlls=libraries,checks=int(match[1]),
            compared_vertices=int(match[2]),useful_parallel_vertex_jobs=int(match[3]),vertex_digest=match[4],
            original_scalar_case_signatures=dict(re.findall(r'SCALAR_CASE key=([a-zA-Z0-9_]+) signature=([0-9a-f]{16})',stdout))))
    cross_differences=[key for key in records[0]['original_scalar_case_signatures'] if
        records[0]['original_scalar_case_signatures'][key]!=records[1]['original_scalar_case_signatures'][key]]
    # Both binaries already compared every worker result with their own original
    # scalar body. Preserve the observed legacy scalar compiler dependence only
    # under directed down/up rounding; default production cases must also match
    # across O2/Od. This is not a cross-compiler claim for all floating modes.
    assert set(cross_differences)<= {'round8192','round16384'},'Default O2/Od scalar signatures differ: '+','.join(cross_differences)
    after=read_inputs();assert before==after,'Component inputs changed during verification'
    write_new(out/'parallel_component_result.json',dict(status='PASS_USEFUL_TERRAIN_VERTEX_CPP14_PARALLEL_FIXED_ORDER_BIT_IDENTITY',
        inputs_before=before,inputs_after=after,modes=records,cpp_dialect='c++14',floating_point='/fp:strict; x64 MXCSR captured per dispatch and restored per worker',
        default_scalar_cross_optimization_identical=True,worker_bit_identity_scope='Every 44-byte output equals the original scalar body from the same build, including all four owner rounding modes',
        original_scalar_nondefault_cross_optimization_differences={key:{row['mode']:row['original_scalar_case_signatures'][key] for row in records} for key in cross_differences},
        verified=['Full 44-byte vertex identity against pre-change scalar body; worker 0/2/4',
            'Persistent pool grow/reuse; each lane computes useful 65x65 normal/weights/height vertices',
            'Unknown NaN isolation, canonical map chunk bounds, material slot integrity and immutable inputs',
            'Four owner rounding modes with FTZ/DAZ; caller control preserved',
            'Lowest-index worker exception, recovery, wrong-owner rejection, empty/small/oversized batches',
            'Injected launch failures after 0/1/2/3 threads; join and complete serial fallback'],
        bounded_vertex_payload_bytes=65*65*44,max_persistent_threads_per_owner=4,source_atlas_or_table_clones=0,
        runtime_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,physical_core_overlap_verified=False,
        gameplay_determinism_or_performance_verified=False,production_call_site_integration_pending_root=True))
    owned=[]
    for path in sorted(work.iterdir()):
        assert path.is_file() and path.suffix in ('.cmd','.rsp','.obj','.exe','.map'),str(path)
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
        row['allocated_bytes']=storage.allocated(path);owned.append(row)
    write_new(out/'parallel_cleanup_plan.json',dict(status='EXACT_OWNED_COMPONENT_INTERMEDIATES',files=owned,protected_inputs=after))
    for row in owned:
        actual=common.artifact(row['path']);assert all(actual[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not list(work.iterdir());work.rmdir()
    write_new(out/'parallel_cleanup_result.json',dict(status='PASS_EXACT_OWNED_COMPONENT_INTERMEDIATES_REMOVED',files=owned,
        released_logical_bytes=sum(row['bytes'] for row in owned),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in owned),source_or_runtime_deleted=False))
    print(json.dumps(dict(status='PASS_USEFUL_TERRAIN_VERTEX_CPP14_PARALLEL_FIXED_ORDER_BIT_IDENTITY',attempt=attempt,
        modes=[{k:r[k] for k in ('mode','checks','compared_vertices','useful_parallel_vertex_jobs','vertex_digest')} for r in records],
        cleanup_files=len(owned),released_allocated_bytes=sum(row['allocated_bytes'] for row in owned))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    try:main(args.attempt)
    except Exception as error:
        path=STAGE/('parallel_attempt'+args.attempt)/'parallel_failure.json'
        if path.parent.exists() and not path.exists():write_new(path,dict(status='FAILED_COMPONENT_ATTEMPT_RETAINED_FOR_REVIEW',error=repr(error),runtime_executed=False))
        raise
