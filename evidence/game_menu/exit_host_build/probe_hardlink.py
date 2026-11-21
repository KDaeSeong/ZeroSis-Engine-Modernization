"""Bounded one-file hardlink/create/unlink permission check; no native engine."""
from pathlib import Path
import hashlib
import json
import os
import stat

STAGE=Path(__file__).resolve().parent
PROJECT=STAGE.parents[2]
source=PROJECT/'Build/UiWindowHost/20261024T082423Z_b604cddf0d2d/frozen/include_roots/project/Source/Host/HostMain.cpp'
folder=STAGE/'hardlink_probe'
target=folder/'HostMain.cpp.link-test'
assert not folder.exists()
assert source.resolve(strict=True).is_relative_to(PROJECT/'Build/UiWindowHost')
for path in [source,*source.parents]:
    assert not path.lstat().st_file_attributes&0x400
    if path==PROJECT:
        break
before=source.stat();raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='cf15a1872548fe5a1c70b8026da3fed41b090ebe0f186c7279a1a5cd04d9aab0'
folder.mkdir()
result={'source':str(source),'target':str(target),'source_sha256':hashlib.sha256(raw).hexdigest(),
        'source_id':[before.st_dev,before.st_ino],'before_links':before.st_nlink,
        'game_host_sdk_or_window_executed':False}
try:
    os.link(source,target)
    after=target.stat()
    assert [after.st_dev,after.st_ino]==result['source_id']
    assert source.stat().st_nlink==before.st_nlink+1
    assert target.read_bytes()==raw and not target.lstat().st_file_attributes&0x400
    target.unlink()
    result.update(status='PASS_HARDLINK_CREATE_AND_EXACT_UNLINK',target_deleted=True)
except OSError as error:
    result.update(status='FAIL_OS_HARDLINK_PERMISSION',winerror=getattr(error,'winerror',None),error=str(error))
    assert not os.path.lexists(target)
finally:
    folder.rmdir()
    after=source.stat()
    assert (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_file_attributes,after.st_nlink)==(
        before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_file_attributes,before.st_nlink)
    assert source.read_bytes()==raw
    result['source_unchanged']=True
    destination=STAGE/'hardlink_permission_probe.json'
    assert not destination.exists()
    destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
assert result['status'].startswith('PASS'), result['status']
