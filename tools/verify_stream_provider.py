"""Compare actual archived x86 stream code, x64 provider, and byte-format oracle."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import struct
from build_stream_reference import build_reference, MODES
from build_stream_provider import build, artifact
from collect_baseline import PROJECT,digest
from native_build import run

# All fixed-width fields in the shared C++ trace; UINT64/GUID are SDK native order.
FIELDS=[(1,False),(1,False),(1,False),(1,False),(2,True),(2,True),(2,True),
        (4,True),(4,True),(4,True),(8,True),(8,False),(4,True),(8,True),(16,False)]

def inputs():
    rng=random.Random(0x5A20515)
    records=[]
    for index in range(2048):
        row=bytearray([index%2,(index//2)%2,rng.randrange(256),rng.randrange(256)])
        for bits in (16,16,16,32,32,32,64,64):
            corners=[0,1,(1<<(bits-1))-1,1<<(bits-1),(1<<bits)-1]
            n=corners[index] if index<len(corners) else rng.getrandbits(bits)
            row.extend(n.to_bytes(bits//8,'little'))
        for bits,exponent,mantissa in ((32,8,23),(64,11,52)):
            # Include +/-0, infinities, quiet NaN, subnormals; random remainder finite.
            corners=[0,1<<(bits-1),((1<<exponent)-1)<<mantissa,
                     ((1<<exponent)-1)<<mantissa|1<<(bits-1),
                     ((1<<exponent)-1)<<mantissa|1<<(mantissa-1),1,(1<<mantissa)-1]
            n=corners[index] if index<len(corners) else rng.getrandbits(bits)
            if index>=len(corners) and (n>>mantissa)&((1<<exponent)-1)==(1<<exponent)-1:
                n^=1<<mantissa
            row.extend(n.to_bytes(bits//8,'little'))
        row.extend(rng.getrandbits(128).to_bytes(16,'little'))
        assert len(row)==66
        records.append(bytes(row))
    return b''.join(records)

def oracle(raw,endian):
    result=bytearray()
    for start in range(0,len(raw),66):
        offset=start
        for width,swap in FIELDS:
            part=raw[offset:offset+width]; result.extend(part[::-1] if swap and endian!=1 else part); offset+=width
    return result.hex()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--vs',type=Path,required=True); args=parser.parse_args()
    reference=build_reference(); candidate=build(args.vs)
    evidence=PROJECT/'evidence/streams'; directory=PROJECT/'Build/Streams_provider'
    seed=directory/'records.bin'; raw=inputs(); seed.write_bytes(raw)
    artifacts=[]; failures=[]; equal=[]; expected_differences=[]; line_count=0
    for mode in (*MODES,'random0','random1','random2','hardening'):
        outputs={}
        for name,exe in [('reference',reference['path']),('provider',candidate['executable']['path'])]:
            if mode=='hardening' and name=='reference': continue
            command=[exe,mode]+([seed] if mode.startswith('random') else [])
            result=run(command,cwd=Path(exe).parent,timeout=10)
            path=evidence/name/(mode+'.txt'); path.write_bytes(result.stdout+result.stderr)
            artifacts.append({**artifact(path),'returncode':result.returncode,'mode':mode,'implementation':name})
            outputs[name]=path.read_text(encoding='ascii').splitlines()
            if result.returncode: failures.append(f'{name}/{mode}: exit {result.returncode}')
        output=outputs['provider']; line_count+=len(output)
        if mode=='hardening':
            if len(output)!=1 or not output[0].startswith('HARDENING|'): failures.append('hardening result absent')
        elif mode in ('pastseek','pastskip'):
            expected=[line.replace(f'STATE|{mode}|8|8|4|8|4294967292|8|4|1|1|0|0',
                                    f'STATE|{mode}|0|0|4|0|4|0|4|0|1|0|0') for line in outputs['reference']]
            if output!=expected: failures.append(f'{mode}: unexpected difference beyond state preservation')
            expected_differences.append({'mode':mode,'original':outputs['reference'],'candidate':output})
        elif outputs['reference']!=output:
            failures.append(f'{mode}: reference mismatch')
        else: equal.append(mode)
        if mode.startswith('random'):
            expected='HEX|random|'+oracle(raw,int(mode[-1]))
            for name,lines in outputs.items():
                if lines[0]!=expected: failures.append(f'{name}/{mode}: byte oracle mismatch')
                if lines[1]!='ROUNDTRIP|2048|0': failures.append(f'{name}/{mode}: round trip mismatch')
    hard=(evidence/'provider/hardening.txt').read_text().strip().split('|')
    report={'status':'STREAM_COMPONENT_CONFORMANCE_PASS' if not failures else 'FAIL','failures':failures,
        'equal_reference_scenarios':equal,'intentional_invalid_input_state_fixes':expected_differences,
        'random_records_per_endian':2048,'endian_modes':3,'record_width':66,
        'scalar_fields_compared':2048*3*len(FIELDS),'serialized_bytes_compared':len(raw)*3,
        'provider_trace_lines':line_count,'hardening_assertions':int(hard[1]) if hard[0]=='HARDENING' else 0,
        'hardening_rejections':int(hard[2]) if hard[0]=='HARDENING' else 0,
        'inputs':artifact(seed),'reference_build':artifact(evidence/'reference/build_result.json'),
        'provider_build':artifact(evidence/'provider/build_result.json'),'traces':artifacts,
        'support_inputs':[artifact(PROJECT/'tools'/name) for name in ('build_stream_reference.py','build_stream_provider.py','native_build.py','collect_baseline.py')],
        'verifier':artifact(Path(__file__).resolve()),'game_launched':False,'game_runtime_verified':False,
        'scope':'Actual SDK primitive/std-string/memory-stream component execution; not full save compatibility',
        'exclusions':['FString serialization','FAutoArchive','FMemoryStreamRLE','FEndian::SwapEndianStruct',
                      'complete enum serialization','allocation failure injection','game host callbacks','save-load gameplay']}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','failures','scalar_fields_compared','serialized_bytes_compared','hardening_assertions','hardening_rejections')}))
    if failures: raise SystemExit(1)
if __name__=='__main__': main()
