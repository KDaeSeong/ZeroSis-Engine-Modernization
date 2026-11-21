"""Split planned CPU regressions so a mutable geometry DTO cannot affect a model-only run."""
from pathlib import Path
import argparse,importlib.util,json,os,re,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--case',choices=('model','geometry'),required=True);cli.add_argument('--attempt',required=True)
    cli.add_argument('--model-sha256',required=True);cli.add_argument('--normal-sha256',required=True);args=cli.parse_args()
    assert re.fullmatch('asset_'+args.case+r'\d{2}',args.attempt)
    plan=json.loads((ROOT/'asset_cpu_plan.json').read_text('utf8'));driver=ROOT/'asset_cpu_regressions.py'
    import hashlib
    assert hashlib.sha256(driver.read_bytes()).hexdigest()==plan['driver']['sha256']
    spec=importlib.util.spec_from_file_location('asset_pinned_cpu_regressions',driver);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.ref(module.SRC/'OriginalTerrainModel.h')['sha256']==args.model_sha256
    assert module.ref(module.SRC/'OriginalTerrainNormalModel.h')['sha256']==args.normal_sha256
    assert not any(os.environ.get(k)for k in ('CL','_CL_','LINK'))
    tests=module.pinned_tests();original,original_ref=module.library()
    pending=[module.TESTS/('original_terrain_'+args.case+'.cpp')];found={}
    while pending:
        p=pending.pop().resolve()
        if p in found:continue
        assert p.is_relative_to(module.PROJECT.resolve());found[p]=module.ref(p)
        for name in re.findall(r'^\s*#\s*include\s*"([^"]+)"',p.read_text('utf8'),re.M):
            if name=='original_terrain_golden.h':continue
            q=next((q for q in (p.parent/name,module.SRC/name)if q.is_file()),None);assert q is not None
            pending.append(q)
    inputs=[found[p]for p in sorted(found)]+tests+[original_ref,module.ref(driver),module.ref(Path(__file__))]
    stage=ROOT/args.attempt;assert not stage.exists();stage.mkdir()
    module.write_new(stage/'asset_started.json',dict(inputs=inputs,original_plan=module.ref(ROOT/'asset_cpu_plan.json'),
        selected_case=args.case,reason='Parent separated model from geometry until the screen-lighting DTO edit has finished.',
        frozen_model_sha256=args.model_sha256,frozen_normal_sha256=args.normal_sha256,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False))
    row,result=module.execute_case(args.case,stage,inputs,original)
    passed=result['status'].startswith('PASS_')
    out=dict(status='PASS_CURRENT_NORMAL_PRODUCER_UNCHANGED_'+args.case.upper()+'_REGRESSION'if passed else'FAIL_NO_BASELINE_CHANGED',
        checks=result.get('checks',0),result=row,protected_inputs=inputs,plan=module.ref(ROOT/'asset_cpu_plan.json'),
        other_case_executed=False,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False)
    path=stage/'asset_result.json';module.write_new(path,out)
    print(json.dumps(dict(status=out['status'],checks=out['checks'],result=module.ref(path))))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
