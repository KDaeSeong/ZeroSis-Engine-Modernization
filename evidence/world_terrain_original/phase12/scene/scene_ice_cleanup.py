"""Delete only this task's nine regenerable intermediates after exact guards."""
from pathlib import Path
import ctypes,hashlib,json,os
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
BUILD=PROJECT/'Build/OriginalIcePhase12'
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
kernel.CreateFileW.restype=ctypes.c_void_p
kernel.GetFileInformationByHandleEx.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32]
kernel.GetFileInformationByHandleEx.restype=ctypes.c_int
kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle.restype=ctypes.c_int
class StandardInfo(ctypes.Structure):
    _fields_=[('allocation',ctypes.c_int64),('end',ctypes.c_int64),('links',ctypes.c_uint32),('pending',ctypes.c_ubyte),('directory',ctypes.c_ubyte)]
def record(path):
    path=path.resolve(strict=True);s=os.stat(path);assert path.is_file() and not s.st_file_attributes&0x400
    handle=kernel.CreateFileW(str(path),0x80,7,None,3,0,None);assert handle not in (None,ctypes.c_void_p(-1).value)
    try:
        standard=StandardInfo();assert kernel.GetFileInformationByHandleEx(handle,1,ctypes.byref(standard),ctypes.sizeof(standard))
        assert standard.end==s.st_size and standard.links==s.st_nlink and not standard.directory
    finally:assert kernel.CloseHandle(handle)
    return dict(path=str(path),bytes=s.st_size,allocated_bytes=standard.allocation,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        identity=[s.st_dev,s.st_ino],links=s.st_nlink,attrs=s.st_file_attributes,mtime_ns=s.st_mtime_ns)
def main():
    out=ROOT/'scene_ice_cleanup.json';number=1
    while out.exists():
        number+=1;out=ROOT/('scene_ice_cleanup_%02d.json'%number)
    expected={'original_ice_contract.exe','original_ice_contract.map','original_ice_contract.obj','read_build_environment.cmd',
        'scene_compile.rsp','scene_ice_vs.cso','scene_ice_vs.hlsl'}
    assert BUILD.resolve(strict=True)==PROJECT.resolve(strict=True)/'Build/OriginalIcePhase12'
    assert {p.name for p in BUILD.iterdir()}==expected
    paths=[BUILD/name for name in sorted(expected)]+[ROOT/name for name in ('scene_ice_0_vs.dxbc','scene_ice_0_ps.dxbc')if(ROOT/name).exists()]
    rows=[record(path)for path in paths];assert len({tuple(r['identity'])for r in rows})==len(rows) and all(r['links']==1 for r in rows)
    result=json.loads((ROOT/'scene_ice_result.json').read_text('utf8'));initial=json.loads((ROOT/'scene_ice_initial_contract.json').read_text('utf8'))
    required=[result['compiled']['exe'],result['fxc']['hlsl'],result['fxc']['dxbc'],*initial['extracted_shaders']]
    known={row['path']:row for row in rows}
    for item in required:
        if item['path']in known:assert known[item['path']]['sha256']==item['sha256']
        else:
            prior=json.loads((ROOT/'scene_ice_cleanup.json').read_text('utf8'))
            assert not Path(item['path']).exists()and any(x['path']==item['path']and x['sha256']==item['sha256']for x in prior['deleted'])
    preserved=result['source_files']+[result['source_trace']['exe'],result['asset_validation']['low_origin'],result['asset_validation']['loose_high_origin']]
    preserved_before=[record(Path(x['path']))for x in preserved]
    assert all(x['sha256']==before['sha256']for x,before in zip(preserved,preserved_before))
    for path,before in zip(paths,rows):
        assert path.resolve(strict=True)==Path(before['path']) and (path.parent==BUILD or path.parent==ROOT)
        assert record(path)==before
        path.unlink();assert not path.exists();before['result']='DELETED'
    assert not any(BUILD.iterdir());BUILD.rmdir();assert not BUILD.exists()
    preserved_after=[record(Path(x['path']))for x in preserved]
    assert preserved_after==preserved_before
    retained_paths=[PROJECT/x for x in ('Source/Presentation/OriginalIceAssets.h','Source/Presentation/OriginalIceContract.h',
        'Source/Presentation/OriginalIceShader.h','Tests/original_ice_contract.cpp','Tests/original_ice_contract.py')]
    retained_paths += sorted(ROOT.glob('scene_ice*'));retained=[record(path)for path in retained_paths if path.is_file()]
    by_id={tuple(row['identity']):row['allocated_bytes']for row in retained}
    report=dict(status='PASS_OWN_ICE_INTERMEDIATE_CLEANUP_PRESERVATION',deleted=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(x['bytes']for x in rows),reclaimed_allocated_bytes=sum(x['allocated_bytes']for x in rows),
        retained_before_receipt=retained,retained_unique_allocated_bytes_before_receipt=sum(by_id.values()),
        preserved_files=len(preserved_before),preservation_differences=0,original_asset_packages_written=0,
        scope='Only own Build/OriginalIcePhase12 seven files and two original DXBC extractions; no recursive delete',
        full_project_size_not_measured=True,other_task_or_runtime_files_modified=False,
        host_sdk_clr_granny_hwnd_gpu_audio_or_game_executed=False)
    with out.open('x',encoding='utf8')as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in report.items()if k in ('status','deleted_files','reclaimed_allocated_bytes','retained_unique_allocated_bytes_before_receipt','preservation_differences')}))
if __name__=='__main__':main()
