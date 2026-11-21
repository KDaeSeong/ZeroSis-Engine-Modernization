"""Pinned original reflection projection traces; never loads original code."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
READER=PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py'
spec=importlib.util.spec_from_file_location('reflection_pinned_pe_reader',READER)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def positions(data,needle):
    at=data.find(needle)
    while at>=0:
        yield at
        at=data.find(needle,at+1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True)
    parser.add_argument('--range',action='append',default=[])
    parser.add_argument('--literal',action='append',default=[])
    parser.add_argument('--float',action='append',default=[])
    args=parser.parse_args()
    assert args.name.startswith('reflection_') and args.name.replace('_','').isalnum()
    output=ROOT/(args.name+'.json');assert not output.exists()
    pe=module.Pe();blocks={}
    for definition in args.range:
        name,start,stop=definition.split(':');start,stop=int(start,16),int(stop,16)
        assert name not in blocks and 0<stop-start<=32768
        raw=pe.data(start,stop-start);rows=pe.rows(start,stop)
        blocks[name]=dict(start=hex(start),stop=hex(stop),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            fully_decoded=sum(row[1] for row in rows)==len(raw),
            instructions=[dict(va=hex(a),bytes=n,mnemonic=m,operands=o) for a,n,m,o in rows])
    code=next(s for s in pe.sections if s[4]=='.text')
    raw_code=pe.raw[code[3]:code[3]+code[2]]
    literals={arg:[hex(code[0]+at) for at in positions(raw_code,struct.pack('<I',int(arg,16)))] for arg in args.literal}
    floats={arg:dict(bits=hex(pe.u32(int(arg,16))),value=struct.unpack('<f',pe.data(int(arg,16),4))[0]) for arg in args.float}
    pe.verify()
    result=dict(schema='zerosis.phase12.reflection_static_trace.v1',status='PASS_PINNED_ORIGINAL_BYTES_READ_ONLY',
        original=pe.before,reader=module.ref(READER),tracer=module.ref(Path(__file__).absolute()),
        blocks=blocks,literal_byte_references=literals,float_literals=floats,
        candidate_reference_note='Byte-pattern references require aligned disassembly and ownership evidence before interpretation.',
        original_code_loaded_or_executed=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],blocks=len(blocks),references=sum(len(v) for v in literals.values()),output=module.ref(output))))


if __name__=='__main__':main()
