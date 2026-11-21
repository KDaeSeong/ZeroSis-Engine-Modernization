"""Add seven layout-neutral map access declarations to the accepted SDK port."""
import json
from collect_baseline import PROJECT,digest
from world_builder_map_access import PREFIX as OBJECT_PREFIX,patches as object_patches
from world_builder_map_bridge_access import PREFIX as BRIDGE_PREFIX,patches as bridge_patches


def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_019/sdk_x64_patches.json';old=json.loads(base.read_text(encoding='utf-8'))
    prefixes=(OBJECT_PREFIX,BRIDGE_PREFIX)
    retained=[p for p in plan['patches'] if not p['id'].startswith(prefixes)]
    if retained!=old['patches'] or len(retained)!=488:raise RuntimeError('Accepted 488-patch baseline differs')
    added=object_patches()+bridge_patches();plan['patches']=retained+added
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(('serialization_','temp_callers_','auto_callers_','db_callers_','localization_callers_','world_mod_access_',*prefixes))]
    ledger['unchanged_world_builder_map_baseline']={'path':str(base),'sha256':digest(base)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'map_access_declarations':len(added),'layout_changed':False}))


if __name__=='__main__':main()
