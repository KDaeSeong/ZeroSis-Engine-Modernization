"""Current-header regressions using unchanged legacy C++ cases; never starts a renderer."""
from pathlib import Path
import argparse,ast,hashlib,json,os,re,struct,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path[:0]=[str(PROJECT/'Tests'),str(PROJECT/'tools')]
from original_water_shader import ref,write_new
from menu_replay_restoration import build_cxx14
from native_build import run

ROOT=Path(__file__).parent
TESTS=PROJECT/'Tests'
SRC=PROJECT/'Source/Presentation'
PINNED={
    'original_terrain_model.py':'e6db17b18bda3dc774ce110e05436123ae9f5dae6a1455916a5052ac47dd8f42',
    'original_terrain_model.cpp':'39c0f1e9870933e6fee5b51a193eb9249072cdabbef8dc2e93b723e898b5ff74',
    'original_terrain_geometry.cpp':'968f94cccb8310c6d29549941ca2ffaa747462efd4d2ec40be5c2c2d3a1eec35',
    'original_terrain_geometry.py':'d289f50246ac8c47f2a75cbffe249aad1d01b656bed5923d0d7d9c172ddd8b94'}
CASES={
    'model':[
        'RandomAndCoordinates: MSVCR90 sequence/shuffle bounds, independent Python FNV golden1/4/64/33000, negative cube/offset/source conversions, four orientations, malformed rejection.',
        'MapRules: terrain/hills/mountains/natural-wonder bits, ordinary features unchanged, unknown privacy and continent bounds.',
        'LibraryAndPlacement: read-only original299-piece fxsb RLE decode42,008,576pixels; malformed runs; greedy seed determinism/global RNG isolation; hidden atlas equality; T/H blend and default row3.',
        'MaterialsAndBlend: SurfaceNormal flat/unknown-neighbour input remains finite; normalized5x5 kernel and byte truncation; unknown NaN rejection-before-read; edge wrap; chunk top8 independent histogram/ties.',
        'MaterialsAndBlend: three-way projection expansion and0.9 boundary, MaterialUv .33/.66 scales; alpha^8 weighted squared diffuse/specular and height; zero/unknown blend guards.'
    ],
    'geometry':[
        'CoordinateRoundTrips: grid64/cube/offset/world, negative rows, both wrap axes and out-of-domain rejection.',
        'PolygonReference: independent six integer triangles per hex; boundary-inclusive picking owners and two distinct tile owners within one global triangle.',
        'InformationBoundary: hidden terrain/wonder/continent mutation leaves public cells, full atlas and heights invariant; poisoned unknown NaN remains unread; revealed invisible terrain retained.',
        'HeightsAndCache: known-only bilinear interpolation, malformed/nonfinite height rejection, seed/wonder/terrain cache invalidation.'
    ]}

def pinned_tests():
    rows=[ref(TESTS/name)for name in PINNED]
    assert all(r['sha256']==PINNED[Path(r['path']).name]for r in rows),'Legacy tests or golden generator changed; investigate instead of accepting a new baseline'
    return rows
def closure():
    found={};pending=[TESTS/'original_terrain_model.cpp',TESTS/'original_terrain_geometry.cpp']
    while pending:
        p=pending.pop().resolve()
        if p in found:continue
        assert p.is_relative_to(PROJECT.resolve())
        found[p]=ref(p)
        for name in re.findall(r'^\s*#\s*include\s*"([^"]+)"',p.read_text('utf8'),re.M):
            if name=='original_terrain_golden.h':continue
            choices=(p.parent/name,SRC/name);q=next((q for q in choices if q.is_file()),None)
            assert q is not None,(p,name)
            pending.append(q)
    return [found[p]for p in sorted(found)]
def golden_definition():
    p=TESTS/'original_terrain_model.py';assert ref(p)['sha256']==PINNED[p.name]
    text=p.read_text('utf8');tree=ast.parse(text)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in ('reference_shuffle','make_golden')]
    assert [n.name for n in nodes]==['reference_shuffle','make_golden']
    receipts=[dict(function=n.name,source_sha256=hashlib.sha256(ast.get_source_segment(text,n).encode('utf8')).hexdigest())for n in nodes]
    module=ast.Module(body=nodes,type_ignores=[]);namespace={'struct':struct}
    exec(compile(module,str(p)+'[two functions only]','exec'),namespace)
    return namespace['make_golden'],receipts
def library():
    p=PROJECT/'evidence/world_terrain_original/asset_inventory.json';d=json.loads(p.read_text('utf8'))
    path=Path(d['game_root'])/'Resource/Common/TerrainPiecesLibrary.fxsb';r=ref(path)
    assert r['sha256']=='86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a'and r['bytes']==27595584
    return path,r
def cleanup(work,stage,protected):
    rows=[]
    for p in sorted(work.iterdir()):
        assert p.is_file()and p.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
        row=ref(p);assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'asset_cleanup_plan.json',dict(directory=str(work),files=rows,protected_inputs=protected,exact_owned_leaves_only=True))
    assert work.resolve().is_relative_to(ROOT.resolve())
    for row in rows:assert ref(row['path'])==row;Path(row['path']).unlink()
    work.rmdir()
    result=stage/'asset_cleanup_result.json';write_new(result,dict(status='PASS_EXACT_OWNED_CPU_REGRESSION_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),released_unique_allocated_bytes=sum(r['allocated_bytes']for r in rows)))
    return ref(result)
def execute_case(kind,parent,protected,original_library):
    stage=parent/('asset_'+kind);stage.mkdir();work=stage/'work';work.mkdir()
    result=dict(kind=kind,cases=CASES[kind]);failure=None
    try:
        if kind=='model':
            make_golden,receipts=golden_definition();header=work/'original_terrain_golden.h'
            result['independent_golden']=make_golden(header);result['golden_function_extraction']=receipts;result['golden_header_before_cleanup']=ref(header)
        name='original_terrain_'+kind
        compiled=build_cxx14(name,work,stage,TESTS/(name+'.cpp'),[SRC,work]);result['build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=work,timeout=30)
        dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs'),re.M)))
        assert imports.returncode==0 and {d.lower()for d in dlls}=={'kernel32.dll'},dlls
        result['imported_dlls']=dlls;result['executed_console']=ref(compiled['path'])
        args=[compiled['path']]+([original_library]if kind=='model'else [])
        done=run(args,cwd=work,timeout=60);stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
        (stage/'asset_console.txt').write_text(stdout+stderr,encoding='ascii')
        regex=r'PASS_ORIGINAL_TERRAIN_MODEL checks=(\d+)\s*'if kind=='model'else r'PASS_ORIGINAL_TERRAIN_GEOMETRY checks=(\d+) polygon_samples=(\d+) shared_triangle_tiles=2\s*'
        match=re.fullmatch(regex,stdout);result['exit_code']=done.returncode
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        result['checks']=int(match[1])
        if kind=='geometry':result.update(polygon_samples=int(match[2]),shared_triangle_tile_owners=2)
        result['status']='PASS_UNCHANGED_CPP14_'+kind.upper()+'_CASES_AGAINST_CURRENT_PRODUCTION_HEADERS'
    except Exception as ex:
        failure=str(ex);result.update(status='FAIL_CPU_REGRESSION_NO_BASELINE_CHANGED',error=failure[:8000])
    finally:
        unchanged=all(ref(r['path'])==r for r in protected);result['protected_inputs_unchanged']=unchanged
        result['cleanup']=cleanup(work,stage,protected)
        if not unchanged:result.update(status='FAIL_PROTECTED_INPUT_CHANGED_DURING_REGRESSION')
    result.update(native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False,actual_gpu_parity=False,legacy_tests_or_source_modified=False)
    output=stage/'asset_result.json';write_new(output,result);return ref(output),result

def main():
    cli=argparse.ArgumentParser();mode=cli.add_mutually_exclusive_group(required=True);mode.add_argument('--plan',action='store_true');mode.add_argument('--run',action='store_true')
    cli.add_argument('--attempt',default='asset_cpu01');cli.add_argument('--model-sha256');cli.add_argument('--normal-sha256');args=cli.parse_args()
    tests=pinned_tests();original,original_ref=library();functions=golden_definition()[1]
    if args.plan:
        output=ROOT/'asset_cpu_plan.json'
        write_new(output,dict(status='PREPARED_NOT_EXECUTED_AWAITING_MODEL_FREEZE',driver=ref(Path(__file__)),legacy_tests=tests,library=original_ref,golden_reuse=dict(exact_pinned_source_sha256=PINNED['original_terrain_model.py'],selected_functions=functions,old_main_and_fixed_ROOT_not_executed=True),
            cases=CASES,not_covered_here=['66x66 GPU normal/shadow cache allocation, rasterization and visual acceptance; separate field CPU reference tests are not relabelled as these old cases.'],
            execution_gate='Explicit frozen Model/Normal SHA CLI values required; current Source snapshots are captured freshly only after the freeze signal.',
            native_or_console_executed=False,production_source_or_tests_modified=False))
        print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',plan=ref(output))));return
    assert re.fullmatch(r'asset_cpu\d{2}',args.attempt)
    for value in (args.model_sha256,args.normal_sha256):assert value and re.fullmatch(r'[0-9a-f]{64}',value)
    assert ref(SRC/'OriginalTerrainModel.h')['sha256']==args.model_sha256
    assert ref(SRC/'OriginalTerrainNormalModel.h')['sha256']==args.normal_sha256
    assert not any(os.environ.get(k)for k in ('CL','_CL_','LINK'))
    stage=ROOT/args.attempt;assert not stage.exists();stage.mkdir()
    inputs=closure()+[original_ref,ref(Path(__file__))]+tests
    write_new(stage/'asset_started.json',dict(inputs=inputs,plan=ref(ROOT/'asset_cpu_plan.json'),model_freeze_sha256=args.model_sha256,normal_freeze_sha256=args.normal_sha256,no_old_script_main=True,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False))
    results=[execute_case(kind,stage,inputs,original)for kind in ('model','geometry')]
    passed=all(r[1]['status'].startswith('PASS_')for r in results)
    result=dict(status='PASS_CURRENT_NORMAL_PRODUCER_OLD_TERRAIN_REGRESSIONS'if passed else'FAIL_REGRESSION_REQUIRES_REVIEW_NO_BASELINE_CHANGED',cases=[r[0]for r in results],checks=sum(r[1].get('checks',0)for r in results),inputs=inputs,production_source_and_legacy_cases_unchanged=True,
        old_script_main_or_fixed_ROOT_used=False,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False,actual_gpu_parity=False)
    output=stage/'asset_result.json';write_new(output,result);print(json.dumps(dict(status=result['status'],checks=result['checks'],result=ref(output))))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
