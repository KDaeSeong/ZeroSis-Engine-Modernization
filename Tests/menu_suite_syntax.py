"""Compile current Host/window syntax only; never load a game or create a window."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import build_menu_suite_host as build


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--attempt',required=True)
    args=parser.parse_args()
    stage=PROJECT/'evidence/game_menu/offline_menu_suite/syntax'/args.attempt
    stage.mkdir(parents=True,exist_ok=False)
    parent,_=build.read_document(build.PARENT_REPORT,build.PARENT_SHA)
    roots=build.input_root_map(parent)
    env=os.environ.copy()
    env.update({key:build.replace_paths(value,roots.values()) for key,value in parent['final_environment'].items()})
    for key in ('CL','_CL_','LINK','_LINK_'):env.pop(key,None)
    rows=[]
    for row in parent['final_compilation']['translation_units']:
        if row['translation_unit'] not in ('host_main','window'):continue
        name=row['translation_unit'];dependency=stage/(name+'.json');response=stage/(name+'.rsp')
        response.write_bytes(build.discovery_response(Path(row['response']['path']).read_bytes(),roots,dependency))
        command=[parent['compiler']['path'],'@'+str(response)]
        result=subprocess.run(command,cwd=stage,env=env,capture_output=True,timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        output=result.stdout+result.stderr
        (stage/(name+'.log')).write_bytes(output)
        rows.append(dict(unit=name,returncode=result.returncode,log=str(stage/(name+'.log')),
                         command=command,object_written=False))
        print(name,result.returncode,flush=True)
        if result.returncode:
            print(output.decode('mbcs',errors='replace')[:6000],flush=True)
    receipt=dict(status='PASS' if all(row['returncode']==0 for row in rows) else 'FAIL',
                 commands=rows,Host_SDK_CLR_HWND_GPU_game_executed=False,
                 scope='Current HostMain and changed BitmapWindow /Zs only; final frozen compile/link remains separate')
    (stage/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return 0 if receipt['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
