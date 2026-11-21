"""Run the original 68-claim checker with only its output leaf redirected."""
import hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
original=STAGE.parent/'plan_check.py'
source=original.read_text('utf8')
old="out = STAGE / 'plan_check.json'"
new="out = STAGE / 'phase2/plan_check.json'"
assert source.count(old)==1 and not(STAGE/'plan_check.json').exists()
before=hashlib.sha256(original.read_bytes()).hexdigest()
baseline=STAGE.parent/'plan_check.json';baseline_bytes=baseline.read_bytes()
scope=dict(__file__=str(original),__name__='__phase2_plan_claim_check__')
exec(compile(source.replace(old,new),str(original),'exec'),scope)
result=scope['value'];assert result['status']=='PASS' and len(result['checks'])==68
assert before==hashlib.sha256(original.read_bytes()).hexdigest() and baseline.read_bytes()==baseline_bytes
receipt=dict(status='PASS_68_ORIGINAL_CLAIMS_OUTPUT_REDIRECT_ONLY',original_checker_path=str(original),
    original_checker_sha256=before,original_output_unchanged=True,substitutions=[dict(old=old,new=new)],
    checks=len(result['checks']),native_execution=False)
with (STAGE/'plan_check_receipt.json').open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2);f.write('\n')
