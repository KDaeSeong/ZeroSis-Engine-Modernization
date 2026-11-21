"""Close bounded static-byte provenance and exact CPU work-file retirement."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')

def raw_range(raw,start,end):
    pe=struct.unpack_from('<I',raw,60)[0];count=struct.unpack_from('<H',raw,pe+6)[0]
    optional=pe+24;base=struct.unpack_from('<I',raw,optional+28)[0]
    sections=optional+struct.unpack_from('<H',raw,pe+20)[0]
    for index in range(count):
        virtual,rva,size,pointer=struct.unpack_from('<IIII',raw,sections+index*40+8)
        if rva<=start-base<rva+max(virtual,size):return raw[pointer+start-base-rva:pointer+end-base-rva]
    raise ValueError('Bounded static function escaped a PE section')

def main():
    build=json.loads((PROJECT/'evidence/ui_window_host/20261115T005626Z_256252d8abe3/build_result.json').read_text('utf8'))
    tool=common.sealed(build['dumpbin'])
    inventory=json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    exe=Path(inventory['game_root'])/'CivilizationV_DX11.exe';exe_ref=common.artifact(exe)
    assert exe_ref['sha256']=='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
    raw=exe.read_bytes();ranges=[]
    for label,start,end in [('shuffle_indices',0x907a00,0x907a7f),('shuffle_positions',0x693a00,0x693aa0),
                            ('matcher_pass',0x648a00,0x648f5c),('blend_writer',0x5ce920,0x5cf197)]:
        value=raw_range(raw,start,end)
        ranges.append(dict(label=label,start=f'{start:08x}',end_exclusive=f'{end:08x}',bytes=len(value),
            sha256=hashlib.sha256(value).hexdigest(),listing=common.artifact(STAGE/(label+'.txt'))))
    evidence=dict(schema='zerosis.original_terrain_model.bounded_byte_evidence.v1',source_exe=exe_ref,tool=tool,
        static_disassembly_only=True,original_exe_or_library_code_executed=False,functions=ranges,
        reconstruction=dict(
            random='MSVCR90 state=state*214013+2531011 (u32); return (state>>16)&0x7fff.',
            shuffle='Forward Fisher-Yates: next=first+stride, bound=2. Compose 15-bit rand digits until mask>=bound or mask==0xffffffff; use unsigned remainder. Strides4/12 do not change the random sequence.',
            positions='Columns outer, rows inner, each from -2 through size+1 before the shuffle.',
            index_arrays='Piece and orientation indices initialise once per pass. Shuffle their previous permutation in place at every position.',
            acceptance='After each accepted placement claims its owner cells, the orientation loop continues; no success break.',
            stored_weights='Normalise the complete material table, extract eight without renormalising, first-slot fallback when their total<0.001, then truncate each weight*255.',
            caveats=['Calls to rand behind virtual calls before the matcher remain unknown.',
                'Orientation component order then position is a candidate; original matrix multiplication order remains open.']))
    write_new(STAGE/'shuffle_byte_evidence.json',evidence)
    # Only this agent's failed build work and superseded CPU proof bundle are
    # retired. Keep the failing source gzip and initial compiler log for context.
    targets=[STAGE/'cpu/build',STAGE/'cpu_retry01']
    rows=[];directories=[]
    for target in targets:
        assert target.resolve()==target and target.is_relative_to(STAGE) and target.is_dir()
        for directory,names,leaves in os.walk(target,followlinks=False):
            assert not os.stat(directory,follow_symlinks=False).st_file_attributes&0x400
            directories.append(Path(directory))
            for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
            for name in leaves:
                path=Path(directory)/name;row=common.artifact(path)
                assert row['links']==1 and not row['file_attributes']&0x401
                row['allocated_bytes']=storage.allocated(path);rows.append(row)
    plan=dict(schema='zerosis.original_terrain_model.superseded_work_cleanup.v1',files=rows,
        roots=[str(p) for p in targets],current_model=common.artifact(PROJECT/'Source/Presentation/OriginalTerrainModel.h'),
        latest_proof=common.artifact(STAGE/'cpu_retry02/result.json'),
        retained_failure_source=common.artifact(STAGE/'failed_header_first.gz'),
        retained_initial_compile_log=common.artifact(STAGE/'cpu/compile_original_terrain_model_x64_cxx14.txt'))
    write_new(STAGE/'cleanup_plan.json',plan)
    for row in rows:
        now=common.artifact(row['path']);assert all(now[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):directory.rmdir()
    result=dict(status='PASS_EXACT_OWNED_SUPERSEDED_CPU_WORK_RETIRED',files=rows,deleted_files=len(rows),
        deleted_directories=len(directories),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
        current_source_or_originals_changed=False)
    write_new(STAGE/'cleanup_result.json',result)
    latest=json.loads((STAGE/'cpu_retry02/result.json').read_text('utf8'))
    receipt=dict(schema='zerosis.original_terrain_model.final.v1',status='PASS_RULE_MODEL_CXX14_OFFLINE',
        report_label='규칙 동등, 배치 동등은 미검증',
        production_header=common.artifact(PROJECT/'Source/Presentation/OriginalTerrainModel.h'),
        test_sources=[common.artifact(PROJECT/name) for name in ('Tests/original_terrain_model.cpp','Tests/original_terrain_model.py')],
        latest_cpu_test=common.artifact(STAGE/'cpu_retry02/result.json'),assertions=latest['checks'],
        assertion_note='Includes 33000 per-element permutation preservation checks; not 37999 independent scenarios.',
        byte_evidence=common.artifact(STAGE/'shuffle_byte_evidence.json'),
        cleanup=[common.artifact(STAGE/'cpu_retry02/cleanup_result.json'),common.artifact(STAGE/'cleanup_result.json')],
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,retail_placement_or_gpu_parity_verified=False)
    write_new(STAGE/'result.json',receipt)
    print(json.dumps(dict(status=receipt['status'],header_sha256=receipt['production_header']['sha256'],
        assertions=receipt['assertions'],retired_files=len(rows),released_unique_allocated_bytes=result['released_unique_allocated_bytes'])))

if __name__=='__main__':main()
