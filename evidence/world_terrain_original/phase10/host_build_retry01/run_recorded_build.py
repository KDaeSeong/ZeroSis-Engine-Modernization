"""Keep the compiler controller alive and record its actual exit code."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]


def write_new(name,value):
    with (ROOT/name).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan-sha256',required=True);args=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}',args.plan_sha256)
    plan=ROOT/'plan.json'
    assert hashlib.sha256(plan.read_bytes()).hexdigest()==args.plan_sha256
    assert PROJECT==Path.cwd() and not any((ROOT/name).exists() for name in (
        'driver.stdout.txt','driver.stderr.txt','launcher.json','controller_exit.json'))
    command=[sys.executable,'-B','-u','-X','utf8','tools/build_menu_suite_host.py','--build-plan',
        'evidence/world_terrain_original/phase10/host_build_retry01/plan.json','--plan-sha256',args.plan_sha256]
    with (ROOT/'driver.stdout.txt').open('xb') as stdout,(ROOT/'driver.stderr.txt').open('xb') as stderr:
        process=subprocess.Popen(command,cwd=PROJECT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        write_new('launcher.json',dict(status='COMPILER_ONLY_FOREGROUND_CONTROLLER_STARTED',
            controller_pid=os.getpid(),builder_pid=process.pid,command=command,
            started_utc=datetime.now(timezone.utc).isoformat(),native_game_host_or_sdk_launch_allowed=False))
        print(json.dumps(dict(status='COMPILER_ONLY_CONTROLLER_ACTIVE',controller_pid=os.getpid(),builder_pid=process.pid)),flush=True)
        returncode=process.wait()
    write_new('controller_exit.json',dict(status='BUILDER_ACTUAL_EXIT_RECORDED',returncode=returncode,
        finished_utc=datetime.now(timezone.utc).isoformat(),builder_pid=process.pid,
        stdout_sha256=hashlib.sha256((ROOT/'driver.stdout.txt').read_bytes()).hexdigest(),
        stderr_sha256=hashlib.sha256((ROOT/'driver.stderr.txt').read_bytes()).hexdigest(),
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='BUILDER_ACTUAL_EXIT_RECORDED',returncode=returncode)),flush=True)
    raise SystemExit(returncode)


if __name__=='__main__':main()
