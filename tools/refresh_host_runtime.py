"""Refresh bounded actual GameCore runtime proof after host or DLL changes."""
import json,sys
from pathlib import Path
from collect_baseline import PROJECT
from native_build import run
from host_runtime_evidence import ROOT,record,validate
from stage_host_runtime import main as stage

def main():
    try:
        report,_=validate()
        print('ACTUAL_CORE_RUNTIME_CURRENT '+','.join(row['run_id'] for row in report['runs']),flush=True)
    except (FileNotFoundError,RuntimeError,ValueError,KeyError):
        identifiers=[]
        for language in ('en_US','ko_KR'):
            print('RUN_ACTUAL_CORE '+language,flush=True)
            result=run([sys.executable,PROJECT/'tools/run_gamecore_initialization.py','--mode','check-core','--language',language],cwd=PROJECT,timeout=330)
            output=result.stdout.decode('utf-8',errors='replace')
            if result.returncode:
                print(output[-5000:]);print(result.stderr.decode('utf-8',errors='replace')[-3000:]);raise SystemExit(result.returncode)
            summaries=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
            if len(summaries)!=1 or summaries[0]['status']!='GAMECORE_INITIALIZATION_PASS':raise RuntimeError('Runtime runner summary missing')
            report_path=Path(summaries[0]['report'])
            if report_path.parent.parent!=ROOT:raise RuntimeError('Unexpected runtime report path')
            identifiers.append(report_path.parent.name)
        record(identifiers);report,_=validate()
    stage()
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in report['runs']]}))

if __name__=='__main__':main()
