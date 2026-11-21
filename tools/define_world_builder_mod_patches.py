"""Append layout-neutral mod-data access to the exact accepted 482-patch baseline."""
import json
from collect_baseline import PROJECT,digest
from world_builder_mod_access import PREFIX,patches

def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_018/sdk_x64_patches.json';old=json.loads(base.read_text(encoding='utf-8'))
    retained=[p for p in plan['patches'] if not p['id'].startswith(PREFIX)]
    if retained!=old['patches'] or len(retained)!=482:raise RuntimeError('Accepted 482-patch baseline differs')
    added=patches();plan['patches']=retained+added;path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(('serialization_','temp_callers_','auto_callers_','db_callers_','localization_callers_',PREFIX))]
    ledger['unchanged_world_builder_mod_baseline']={'path':str(base),'sha256':digest(base)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'world_builder_access_declarations':len(added),'layout_changed':False}))

if __name__=='__main__':main()
