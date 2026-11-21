"""Isolated, layout-neutral access for atomic publication of an SDK map."""
from collect_baseline import PROJECT,digest
from world_builder_map_access import isolated_headers as object_headers,patches as object_patches,apply_access_patch

PREFIX='world_map_bridge_access_'
def patches():
    result=[]
    targets=[('CvWorldBuilderMap/include/CvWorldBuilderMap.h','class CvWorldBuilderMap : FUncopyable\r\n{\r\n'),
        ('CvWorldBuilderMap/include/CvWorldBuilderMapTypeGroup.h','class CvWorldBuilderMapTypeGroup\r\n{\r\n'),
        ('FirePlace/include/FireWorks/FString.h','class FStringA\r\n{\r\n'),
        ('CvWorldBuilderMap/include/CvWorldBuilderMapElementAllocator.h','class CvWorldBuilderMapElementAllocator\r\n{\r\n'),
        ('CvWorldBuilderMap/include/CvWorldBuilderMapElementAllocator.h','\tclass Handle\r\n\t{\r\n')]
    for i,(relative,old) in enumerate(targets):
        original=PROJECT/'Source/SDK_BNW_Original'/relative
        if original.read_bytes().decode('latin1').count(old)!=1:raise RuntimeError('Map bridge access anchor changed')
        result.append({'id':PREFIX+str(i),'file':relative,'source_sha256':digest(original),'old':old,
            'new':old+'\tfriend struct ZeroSisWorldBuilderMapBridgeAccess;\r\n','count':1,
            'reason':'Prepare owned map state and commit with non-allocating swaps; no fields, virtual methods, signatures, or wire layouts change.'})
    return result

def integrated():
    for patch in object_patches()+patches():
        text=(PROJECT/'Source/SDK_BNW_x64'/patch['file']).read_bytes().decode('latin1')
        if apply_access_patch(text,patch)!=text:return False
    return True

def isolated_headers(root):
    rows=object_headers(root)
    for row in rows:
        from pathlib import Path
        p=Path(row['path']);relative=p.relative_to(root).as_posix();text=p.read_bytes().decode('latin1')
        for patch in patches():
            if patch['file']==relative:text=apply_access_patch(text,patch)
        p.write_bytes(text.encode('latin1'));row['sha256']=digest(p)
    return rows
