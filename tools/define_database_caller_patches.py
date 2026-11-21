"""Declare explicit database Results assignment without changing object or saved layouts."""
import json
from collect_baseline import PROJECT,digest

PREFIX='db_callers_'
def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_014/sdk_x64_patches.json';prior=json.loads(base.read_text(encoding='utf-8'))
    retained=[p for p in plan['patches'] if not p['id'].startswith(PREFIX)]
    if retained!=prior['patches'] or len(retained)!=479:raise RuntimeError('Accepted 479-patch baseline changed')
    relative='CvGameDatabase/include/DatabaseResults.h';source=PROJECT/'Source/SDK_BNW_Original'/relative
    old='\t\tCvGameDatabaseAPI Results(const Results& copy);'
    text=source.read_bytes().decode('latin1')
    for patch in retained:
        if patch['file']==relative:text=text.replace(patch['old'],patch['new'])
    if text.count(old)!=1:raise RuntimeError('Database assignment declaration anchor changed')
    new=old+'\r\n\t\t// Deep reprepare like the copy constructor; no shared statement ownership.\r\n\t\tCvGameDatabaseAPI Results& operator=(const Results& copy);'
    plan['patches']=retained+[dict(id=PREFIX+'results_assignment',file=relative,source_sha256=digest(source),old=old,new=new,count=1,
        reason='Replace the implicit shallow owning-pointer assignment with explicit prepare-then-swap; public function added, object/saved layouts unchanged. Recompile all consumers.')]
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(('serialization_','temp_callers_','auto_callers_',PREFIX))]
    ledger['unchanged_database_caller_baseline']={'path':str(base),'sha256':digest(base)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'database_caller_patches':1,'accepted_baseline_unchanged':True}))
if __name__=='__main__':main()
