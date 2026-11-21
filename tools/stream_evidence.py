"""Shared provenance gate for linking/staging the stream candidate."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header

def validate(build_path):
    build_path=Path(build_path).resolve()
    b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/streams/conformance.json'; c=json.loads(cpath.read_text(encoding='utf-8'))
    r=json.loads(Path(c['reference_build']['path']).read_text(encoding='utf-8'))
    required=[b['library'],b['executable'],b['sdk_manifest'],b['compiler'],*b['objects'],*b['sources'],*b['logs'],
              c['inputs'],c['reference_build'],c['provider_build'],c['verifier'],*c['traces'],*c['support_inputs'],
              {'path':r['path'],'sha256':r['sha256']},r['library'],r['source'],r['host_adapter'],r['map'],r['log'],r['compiler']]
    if any(not Path(row['path']).is_file() or digest(Path(row['path']))!=row['sha256'] for row in required):
        raise RuntimeError('Stream source/build/conformance artifact changed')
    if (b['status']!='X64_STREAM_PROVIDER_BUILT_NOT_YET_ACCEPTED' or b['runtime']!='/MD'
        or b['compiler_warnings'] or c['status']!='STREAM_COMPONENT_CONFORMANCE_PASS' or c['failures']
        or Path(c['provider_build']['path']).resolve()!=build_path or any(t['returncode'] for t in c['traces'])
        or pe_header(Path(r['path']))['architecture']!='x86'
        or pe_header(Path(b['executable']['path']))['architecture']!='x64'
        or not any('?ReadIt@FMemoryStream@@' in line and 'FireWorksWin32:FMemoryStream.obj' in line for line in r['map_proof'])
        or any(int.from_bytes(Path(row['path']).read_bytes()[:2],'little')!=0x8664 for row in b['objects'])):
        raise RuntimeError('Invalid stream reference or provider contract evidence')
    return b,c,{'name':'Streams','library':b['library'],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'TESTED_STREAM_COMPONENT_SUBSET_NOT_FULL_SAVE_COMPATIBILITY'}
