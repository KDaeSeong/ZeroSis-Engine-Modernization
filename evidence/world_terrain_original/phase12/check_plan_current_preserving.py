"""Run original68 bytecode claims with only output redirected; preserve semantic history."""
import hashlib, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
original = STAGE.parent / 'plan_check.py'
source = original.read_text('utf8')
old = "out = STAGE / 'plan_check.json'"
new = "out = STAGE / 'phase12/plan_check_current.json'"
assert source.count(old) == 1 and not (STAGE / 'plan_check_current.json').exists()
before = hashlib.sha256(original.read_bytes()).hexdigest()
baseline = STAGE.parent / 'plan_check.json'
baseline_bytes = baseline.read_bytes()
scope = dict(__file__=str(original), __name__='__phase12_current_plan_claim_check__')
exec(compile(source.replace(old, new), str(original), 'exec'), scope)
result = scope['value']
assert result['status'] == 'PASS' and len(result['checks']) == 68
assert before == hashlib.sha256(original.read_bytes()).hexdigest() and baseline.read_bytes() == baseline_bytes
receipt = dict(status='PASS_68_ORIGINAL_BYTECODE_CLAIMS_OUTPUT_REDIRECT_ONLY', original_checker_path=str(original),
    original_checker_sha256=before, original_output_unchanged=True,
    semantic_correction='Phase6 corrects finalt8 to baked specular; Phase10 corrects finalt9 to specscreenmap.dds after proving the renderer base at primary+8. The Phase8 raw-reflection provider identification is superseded. Original68 instruction claims remain unchanged.',
    substitutions=[dict(old=old, new=new)], checks=len(result['checks']), native_execution=False)
with (STAGE / 'plan_check_current_receipt.json').open('x', encoding='utf8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
