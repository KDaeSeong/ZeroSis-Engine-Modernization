"""Pin the original SQLite version for x64 behavior comparison, not a library upgrade."""
from __future__ import annotations
import hashlib
import json
from pathlib import PurePosixPath
import urllib.request
import zipfile
from collect_baseline import PROJECT,digest

URL='https://www.sqlite.org/2013/sqlite-amalgamation-3071700.zip'
C_SHA1='246987605d0503c700a08b9ee99a6b5d67454aab'
ARCHIVE_SHA256='022ef41bd83a1333faf40dc8f1f8469205f4a18c30dc5e137889ba7ea924ef30'

def prepare():
    parent=PROJECT/'Source/ThirdParty';parent.mkdir(parents=True,exist_ok=True)
    archive=parent/'sqlite-amalgamation-3071700.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=30) as r:data=r.read(4000000)
        if hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA256:raise RuntimeError('Pinned SQLite archive mismatch')
        archive.write_bytes(data)
    if digest(archive)!=ARCHIVE_SHA256:raise RuntimeError('Pinned SQLite archive changed')
    expected={'shell.c','sqlite3.c','sqlite3.h','sqlite3ext.h'};entries=[]
    with zipfile.ZipFile(archive) as z:
        c=z.read('sqlite-amalgamation-3071700/sqlite3.c')
        if hashlib.sha1(c).hexdigest()!=C_SHA1:raise RuntimeError('Official release C checksum mismatch')
        for item in z.infolist():
            rel=PurePosixPath(item.filename)
            if item.is_dir():continue
            if len(rel.parts)!=2 or rel.parts[0]!='sqlite-amalgamation-3071700' or rel.name not in expected:raise RuntimeError('Unexpected SQLite archive member')
            target=parent.joinpath(*rel.parts);data=z.read(item)
            if target.exists() and target.read_bytes()!=data:raise RuntimeError('Modified pinned upstream source')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(data)
            entries.append({'path':str(target),'sha256':digest(target)})
    result={'version':'3.7.17','source_url':URL,'checksum_source':'https://www.sqlite.org/releaselog/3_7_17.html',
            'official_c_sha1':C_SHA1,'archive':{'path':str(archive),'sha256':digest(archive)},'sources':entries,
            'scope':'Original-version compatibility baseline; no maintained SQLite upgrade asserted'}
    e=PROJECT/'evidence/database';e.mkdir(parents=True,exist_ok=True)
    (e/'sqlite_source.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
if __name__=='__main__':print(json.dumps(prepare(),indent=2))
