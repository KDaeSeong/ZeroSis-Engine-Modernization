"""Keep SDK STL count fields at their original x86 wire width."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest

def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_009/sdk_x64_patches.json'
    previous=json.loads(base.read_text(encoding='utf-8'))
    if [p for p in plan['patches'] if not p['id'].startswith('serialization_')]!=previous['patches']:
        raise RuntimeError('Non-serialization patch plan changed; review before adding protocol edits')
    plan['patches']=[p for p in plan['patches'] if not p['id'].startswith('serialization_')]
    relative='FirePlace/include/FireWorks/FStlContainerSerialization.h'
    source=PROJECT/'Source/SDK_BNW_Original'/relative
    raw=source.read_bytes().decode('latin1')
    edits=[
        ('include_checked_count','#include <deque>','#include "CvCheckedNarrow.h"\r\n#include <deque>'),
        ('sequence_write_count','m_saveTo << container.size();','m_saveTo << CvChecked::Integer<unsigned int>(container.size());'),
        ('sequence_read_count','ContainerType::size_type count = 0;','unsigned int count = 0;'),
        ('associative_write_count','size_t count = container.size();','const unsigned int count = CvChecked::Integer<unsigned int>(container.size());'),
        ('associative_read_count','container.clear();\r\n\tsize_t count = 0;','container.clear();\r\n\tunsigned int count = 0;')]
    changes=[(relative,*edit) for edit in edits]
    changes += [
        ('CvGameCoreDLL_Expansion2/CvReplayInfo.cpp','replay_write_count',
         'const size_t count = readFrom.size();',
         'const unsigned int count = CvChecked::Integer<unsigned int>(readFrom.size());'),
        ('CvGameCoreDLL_Expansion2/CvReplayInfo.cpp','replay_read_count',
         'size_t uiSize;\r\n\tloadFrom >> uiSize;',
         'unsigned int uiSize;\r\n\tloadFrom >> uiSize;'),
        ('CvGameCoreDLL_Expansion2/CvStructs.cpp','vote_read_count',
         'size_t iSize;\r\n\tkStream >> iSize;',
         'unsigned int iSize;\r\n\tkStream >> iSize;'),
        ('CvGameCoreDLL_Expansion2/CvStructs.cpp','vote_write_count',
         'kStream << aVoteOptions.size();',
         'kStream << CvChecked::Integer<unsigned int>(aVoteOptions.size());')]
    working={}
    for relative,name,old,new in changes:
        source=PROJECT/'Source/SDK_BNW_Original'/relative
        if relative not in working:
            raw=source.read_bytes().decode('latin1')
            for prior in plan['patches']:
                if prior['file']==relative: raw=raw.replace(prior['old'],prior['new'])
            working[relative]=raw
        raw=working[relative]
        if raw.count(old)!=1: raise RuntimeError('Protocol patch match drift: '+name)
        plan['patches'].append({'id':'serialization_'+name,'file':relative,'source_sha256':digest(source),
            'old':old,'new':new,'count':1,
            'reason':'Preserve the original unsigned 32-bit container count on disk; reject larger native counts before writing. Container ordering and game rules unchanged.'})
        working[relative]=raw.replace(old,new)
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['unchanged_numeric_patch_baseline']={'path':str(base),'sha256':digest(base)}
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith('serialization_')]
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'serialization_patches':len(changes),'previous_patches_unchanged':True}))
if __name__=='__main__': main()
