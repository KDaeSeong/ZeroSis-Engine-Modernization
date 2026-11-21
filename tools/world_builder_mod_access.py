"""Layout-neutral access declarations needed for atomic SDK storage installation."""
from collect_baseline import PROJECT,digest
import shutil

PREFIX='world_mod_access_'

def patches():
    result=[]
    targets=[('CvWorldBuilderMap/include/CvWorldBuilderMapModData.h',name) for name in
        ('class ModDataStringBuffer : FUncopyable','class ModEnum','class ModType','class CvWorldBuilderMapModData : FUncopyable')]
    targets += [('FirePlace/include/FireWorks/FFastVector.h',name) for name in
        ('template< class T, bool bPODType > class BaseVector','> class FStaticVector : public BaseVector< T, bPODType >')]
    for i,(relative,anchor) in enumerate(targets):
        original=PROJECT/'Source/SDK_BNW_Original'/relative;old=anchor+'\r\n{\r\n'
        if original.read_bytes().decode('latin1').count(old)!=1:raise RuntimeError('Mod storage access anchor changed: '+anchor)
        new=old+'\tfriend struct ZeroSisWorldBuilderModDataAccess;\r\n'
        result.append({'id':PREFIX+str(i),'file':relative,'source_sha256':digest(original),'old':old,'new':new,'count':1,
            'reason':'Allow the actual mod-data provider to prepare owned storage and install it without allocation; no fields, vtables, signatures, or serialized layouts change.'})
    return result

def isolated_headers(root):
    plan=patches();files={}
    # Local quoted includes in the SDK must resolve inside one coherent tree;
    # overlaying FFastVector alone would include both pragma-once identities.
    source_root=PROJECT/'Source/SDK_BNW_x64/FirePlace/include'
    for source in source_root.rglob('*'):
        if not source.is_file():continue
        target=root/'FirePlace/include'/source.relative_to(source_root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        files[str(target)]={'path':str(target),'sha256':digest(target),'input':{'path':str(source),'sha256':digest(source)}}
    for relative in sorted({p['file'] for p in plan}):
        source=PROJECT/'Source/SDK_BNW_x64'/relative;text=source.read_bytes().decode('latin1')
        for patch in [p for p in plan if p['file']==relative]:
            if patch['new'] in text:continue
            if text.count(patch['old'])!=1:raise RuntimeError('Current header anchor differs')
            text=text.replace(patch['old'],patch['new'])
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode('latin1'))
        files[str(target)]={'path':str(target),'sha256':digest(target),'input':{'path':str(source),'sha256':digest(source)}}
    return list(files.values())
