"""Layout-neutral pool access for the native SDK map implementation."""
import shutil
from collect_baseline import PROJECT,digest

PREFIX='world_map_access_'
def patches():
    relative='CvWorldBuilderMap/include/CvWorldBuilderMapElementAllocator.h'
    original=PROJECT/'Source/SDK_BNW_Original'/relative
    result=[]
    for i,old in enumerate(('class CvWorldBuilderMapElementAllocator\r\n{\r\n','\tclass Handle\r\n\t{\r\n')):
        if original.read_bytes().decode('latin1').count(old)!=1:raise RuntimeError('Map access anchor changed')
        result.append({'id':PREFIX+str(i),'file':relative,'source_sha256':digest(original),'old':old,
            'new':old+'\tfriend struct ZeroSisWorldBuilderMapPoolAccess;\r\n','count':1,
            'reason':'Validate and prepare actual map pool operations without changing fields, vtables, signatures, or wire layouts.'})
    return result

def apply_access_patch(text,patch):
    # Multiple access recipes insert at the same class opening. Inspect the
    # adjacent friend declarations instead of requiring one contiguous spelling.
    if text.count(patch['old'])!=1:raise RuntimeError('Current map access anchor changed')
    at=text.index(patch['old'])+len(patch['old']);wanted=patch['new'][len(patch['old']):].strip()
    for line in text[at:].splitlines():
        if not line.strip():continue
        if not line.strip().startswith('friend struct '):break
        if line.strip()==wanted:return text
    return text[:at]+patch['new'][len(patch['old']):]+text[at:]

def integrated():
    for patch in patches():
        text=(PROJECT/'Source/SDK_BNW_x64'/patch['file']).read_bytes().decode('latin1')
        if apply_access_patch(text,patch)!=text:return False
    return True

def isolated_headers(root):
    source_root=PROJECT/'Source/SDK_BNW_x64';rows=[]
    for part in ('FirePlace/include','CvWorldBuilderMap/include'):
        for source in (source_root/part).rglob('*'):
            if not source.is_file():continue
            relative=source.relative_to(source_root);target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            data=source.read_bytes().decode('latin1')
            for p in patches():
                if p['file']==relative.as_posix():data=apply_access_patch(data,p)
            target.write_bytes(data.encode('latin1'))
            rows.append({'path':str(target),'sha256':digest(target),'input':{'path':str(source),'sha256':digest(source)}})
    return rows
