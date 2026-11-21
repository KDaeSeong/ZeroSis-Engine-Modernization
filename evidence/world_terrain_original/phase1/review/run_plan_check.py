"""Run the unchanged phase-0 claim checker with only its output leaf redirected."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
REVIEW=Path(__file__).absolute().parent
STAGE=REVIEW.parents[1]
PROJECT=STAGE.parents[1]
CHECKER=STAGE/'plan_check.py'
ORIGINAL=STAGE/'plan_check.json'
OUTPUT=REVIEW/'phase0_plan_check.json'
RECEIPT=REVIEW/'phase0_plan_check_receipt.json'

def ref(path):
    raw=path.read_bytes();info=path.stat()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns)

def audit(event,args):
    if event in ('subprocess.Popen','os.system','ctypes.dlopen','os.spawn','os.posix_spawn'):
        raise RuntimeError('Native execution is forbidden in the static claim check')
    if event=='open' and isinstance(args[0],(str,bytes)):
        mode=args[1];flags=args[2]
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&0x743)
        if writing and Path(args[0]).absolute() not in (OUTPUT,RECEIPT):
            raise RuntimeError('Static checker attempted a non-owned write')
    if event in ('os.remove','os.rmdir','os.rename','os.replace'):
        raise RuntimeError('Static checker must not delete or replace files')

def main():
    assert not OUTPUT.exists() and not RECEIPT.exists(),'Inspect the existing verification instead of rerunning it'
    before=ref(ORIGINAL);source=CHECKER.read_text('utf8');tree=ast.parse(source,filename=str(CHECKER))
    changes=0
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='out':
            assert ast.unparse(node.value)=="STAGE / 'plan_check.json'"
            node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(OUTPUT))],keywords=[]);changes+=1
    assert changes==1
    ast.fix_missing_locations(tree)
    sys.addaudithook(audit)
    exec(compile(tree,str(CHECKER),'exec'),dict(__name__='__main__',__file__=str(CHECKER)))
    after=ref(ORIGINAL);assert before==after
    result=json.loads(OUTPUT.read_text('utf8'))
    receipt=dict(schema='zerosis.terrain.phase1.phase0_claim_check.v1',checker=ref(CHECKER),
        original_report_before=before,original_report_after=after,redirected_report=ref(OUTPUT),
        ast_change='Only the single final out assignment changed to the fresh review output path; checker source was not written.',
        status=result['status'],checks=len(result['checks']),failed=[k for k,v in result['checks'].items() if not v],
        native_execution=False,existing_evidence_modified=False)
    with RECEIPT.open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    assert receipt['status']=='PASS' and receipt['checks']==68
    print(json.dumps(dict(status='PASS_UNCHANGED_PHASE0_CHECKER_REDIRECTED',checks=receipt['checks'],existing_evidence_modified=False)))

if __name__=='__main__':main()
