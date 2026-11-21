"""Fetch the official ICU 4.4.2 commit; never execute archive contents."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
from collect_baseline import PROJECT,digest

COMMIT='f405ecdb9e1bc999fc46921507383ee153eb4d04'
URL='https://codeload.github.com/unicode-org/icu/zip/'+COMMIT
ARCHIVE_SHA256='0b2b2454b55a0455674afbdae5531a51f1a04625c27b8a969d2b32e25b74c669'

def main():
    out=PROJECT/'Source/ThirdParty/ICU44';out.mkdir(parents=True,exist_ok=True)
    archive=out/('icu-'+COMMIT+'.zip');receipt=out/'source_receipt.json'
    if archive.exists():
        if not receipt.exists() or json.loads(receipt.read_text())['archive']['sha256']!=digest(archive) or digest(archive)!=ARCHIVE_SHA256:
            raise RuntimeError('Unsealed ICU archive already exists')
    else:
        request=urllib.request.Request(URL,headers={'User-Agent':'ZeroSis-Engine-Research'})
        with urllib.request.urlopen(request,timeout=45) as response:
            data=response.read(64*1024*1024+1);resolved=response.url
        if len(data)>64*1024*1024:raise RuntimeError('ICU archive exceeds expected bound')
        if hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA256:raise RuntimeError('ICU archive differs from pinned official commit archive')
        archive.write_bytes(data)
        receipt.write_text(json.dumps({'repository':'https://github.com/unicode-org/icu','tag':'icu-release-4-4-2',
            'commit':COMMIT,'url':URL,'resolved_url':resolved,'archive':{'path':str(archive),'sha256':digest(archive)},
            'size':len(data),'scope':'Official source acquisition only; no installed game changes'},indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();headers=[n for n in names if n.endswith('/source/common/unicode/uversion.h')]
        if len(headers)!=1:raise RuntimeError('Unexpected ICU source layout')
        prefix=headers[0].split('source/common/unicode/uversion.h')[0]
        root=out/'original';root.mkdir(exist_ok=True);manifest=[];total=0
        for info in z.infolist():
            if info.is_dir() or not info.filename.startswith(prefix):continue
            relative=info.filename[len(prefix):]
            if not (relative.startswith(('source/common/','source/i18n/','source/stubdata/')) or relative in ('license.html','readme.html')):continue
            target=(root/relative).resolve()
            if not target.is_relative_to(root.resolve()):raise RuntimeError('Unsafe ICU archive path')
            total+=info.file_size
            if total>128*1024*1024:raise RuntimeError('ICU extraction exceeds expected bound')
            data=z.read(info);sha=hashlib.sha256(data).hexdigest()
            if target.exists() and digest(target)!=sha:raise RuntimeError('Original ICU file changed: '+str(target))
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(data)
            manifest.append({'path':str(target),'relative':relative,'sha256':sha})
        (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'files':len(manifest),'source_bytes':total,'archive_sha256':digest(archive),'commit':COMMIT}))

if __name__=='__main__':main()
