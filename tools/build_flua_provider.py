"""Build original SDK FLua reference and the real x64 value/table bridge."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import environment_for, run, checked_run

def artifact(path): return {'path':str(path),'sha256':digest(path)}

def build(vs):
    source=PROJECT/'Tests/sdk_flua_trace.cpp'; provider=PROJECT/'Source/Providers/FLua'
    evidence=PROJECT/'evidence/flua'; evidence.mkdir(parents=True,exist_ok=True)
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    from foundation_evidence import validate as validate_foundation
    foundation,_,foundation_entry=validate_foundation(PROJECT/'evidence/foundation/build_result.json')
    original=json.loads((PROJECT/'evidence/database/reference/build_result.json').read_text())
    results={}; inputs=[]
    for arch in ('x86','x64'):
        out=PROJECT/'Build/FLua'/arch; out.mkdir(parents=True,exist_ok=True)
        sdk=PROJECT/('Source/SDK_BNW_Original' if arch=='x86' else 'Source/SDK_BNW_x64')
        fire=sdk/'FirePlace/include'; headers=fire/'FireWorks/FLua/include'
        lua_headers=sdk/'ThirdPartyLibs/Lua51/include'
        vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC')
        win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
        if arch=='x86':
            env={k.upper():v for k,v in os.environ.items()}
            env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
            compiler=vc/'bin/cl.exe'
        else:env,compiler=environment_for(vs,arch,out);compiler=Path(compiler)
        flags=['/nologo','/O2','/MD','/EHsc','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
            '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0',f'/I"{provider}"',f'/I"{PROJECT/"Source/Providers/Streams"}"',f'/I"{PROJECT/"Source/Porting"}"']
        roots=[headers,fire,lua_headers]
        if arch=='x86':flags+=['/W3']+[f'/I"{p}"' for p in roots]
        else:flags+=['/W4','/WX','/std:c++14','/utf-8','/DFLUA_CANDIDATE','/external:W0']+[f'/external:I"{p}"' for p in roots]
        logs=[];responses=[];objects=[]
        def compile_one(name,args,link=()):
            rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(rsp))
            r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env,timeout=60)
            log=evidence/(arch+'_'+name+'.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
            codes=set(re.findall(r'\bwarning\s+(C\d+)',read_text(log)))
            if r.returncode or codes-({'C4819'} if arch=='x86' else set()):raise RuntimeError(read_text(log)[:7000])
        if arch=='x64':
            for cpp in sorted(provider.glob('*.cpp')):
                obj=out/(cpp.stem+'.obj');compile_one(cpp.stem,flags+['/c',f'"{cpp}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
            library=out/'ZeroSis_FLua_x64.lib'
            checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[o['path'] for o in objects]],cwd=out,env=env)
            libraries=[library,Path(lua['library']['path']),Path(foundation_entry['library']['path'])];sources=[source]
        else:
            library=sdk/'FirePlace/lib/FLuaWin32.lib'
            libraries=[library,sdk/'FirePlace/lib/FireWorksWin32.lib',sdk/'ThirdPartyLibs/Lua51/lib/lua51_Win32.lib']
            sources=[source,PROJECT/'Tests/sdk_stream_reference_host.cpp']
            dll=next(row['copy'] for row in original['original_dlls'] if Path(row['copy']['path']).name.lower()=='lua51_win32.dll')
            if digest(Path(dll['path']))!=dll['sha256']:raise RuntimeError('Original Lua DLL changed')
            target=out/'lua51_Win32.dll';shutil.copyfile(dll['path'],target);inputs.append(artifact(target))
        exe=out/'flua_trace.exe';linkmap=out/'flua_trace.map'
        link=['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF',f'/MACHINE:{arch.upper()}',f'/MAP:{linkmap}']
        link += [n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]
        if arch=='x86':link+=['/LTCG']
        compile_one('harness',flags+[f'"{p}"' for p in sources+libraries]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"'],link)
        if arch=='x86':checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
        results[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'library':artifact(library),'libraries':[artifact(p) for p in libraries],
            'map':artifact(linkmap),'compiler':artifact(compiler),'objects':objects,'logs':logs,'responses':responses,'flags':flags}
        inputs += [artifact(p) for p in headers.glob('*.h')]+[artifact(p) for p in lua_headers.glob('*.h')]+[artifact(lua_headers/'lua.hpp')]
    result={'status':'SDK_FLUA_VALUE_BRIDGE_BUILT','runtime':'/MD',**results,
        'library':results['x64']['library'],'objects':results['x64']['objects'],
        'sources':[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(PROJECT/'Tests/sdk_stream_reference_host.cpp'),artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h')],
        'sdk_inputs':inputs+[artifact(PROJECT/'Source/Porting/CvLuaCheckedInteger.h')], 'lua_provider':artifact(PROJECT/'evidence/lua_provider/build_result.json'),
        'foundation_provider':foundation_entry,'builder':artifact(Path(__file__).resolve()),'game_launched':False,'gamecore_loaded':False}
    (evidence/'build_result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True)
    print(build(p.parse_args().vs)['status'])
