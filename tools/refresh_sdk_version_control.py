"""Preserve SDK changes without committing original SDKs or binary inputs."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
BASE=PROJECT/'Source/SDK_BNW_Original'
TARGET=PROJECT/'Source/SDK_BNW_x64'
PATCH=PROJECT/'patches/sdk-bnw-x64.patch'
MANIFEST=PROJECT/'patches/sdk-bnw-inputs.json'
EXCLUDED_ROOTS=('Build/','Play/','Stage/','Source/Assets/','Source/SDK_BNW_Original/',
    'Source/SDK_BNW_x64/','Source/ThirdParty/')
EXCLUDED_PARTS={'frozen','frozen_inputs','compiler_tree','include_roots','external','source_before','__pycache__','node_modules'}
EXCLUDED_SUFFIXES={'.exe','.dll','.lib','.obj','.pdb','.bin','.packet','.dds','.gr2','.fpk','.fxsb',
    '.cso','.dxbc','.rdc','.dmp','.zip','.7z','.gz','.log','.db','.sqlite','.sqlite3','.civ5save','.civ5map','.save'}
SECRET_PATTERNS=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{60,}'),
    re.compile(rb'(?<![A-Za-z0-9_])sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]


def git(args):
    done=subprocess.run(['git','-c','safe.directory='+PROJECT.as_posix(),'-c','core.autocrlf=false',*args],cwd=PROJECT,capture_output=True,
        stdin=subprocess.DEVNULL,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return done


def tree(root):
    result=[]
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in [*dirs,*files]:
            assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400,'Reparse input refused'
        for name in files:
            path=Path(directory)/name;raw=path.read_bytes()
            result.append(dict(path=path.relative_to(root).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    return sorted(result,key=lambda row:row['path'])


def make():
    baseline,modified=tree(BASE),tree(TARGET)
    before={r['path']:r for r in baseline};after={r['path']:r for r in modified}
    changed=[name for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name)]
    run=git(['diff','--no-index','--binary','--no-ext-diff','--no-textconv','--src-prefix=a/','--dst-prefix=b/','--',
        'Source/SDK_BNW_Original','Source/SDK_BNW_x64'])
    assert run.returncode in (0,1),'SDK difference could not be generated'
    patch=run.stdout.replace(b'a/Source/SDK_BNW_Original/',b'a/Source/SDK_BNW_x64/')
    assert b'GIT binary patch' not in patch,'A modified SDK binary requires separate review'
    manifest=dict(schema='zerosis.sdk.source-control.v1',baseline_root='Source/SDK_BNW_Original',
        target_root='Source/SDK_BNW_x64',baseline=baseline,modified=modified,changed_paths=changed,
        patch_sha256=hashlib.sha256(patch).hexdigest(),original_sdk_or_binary_contents_included=False)
    return patch,(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8'),len(changed)


def denied(name):
    path=Path(name);parts=set(path.parts)
    return (any(name.startswith(root) for root in EXCLUDED_ROOTS) or bool(parts&EXCLUDED_PARTS)
        or path.suffix.lower() in EXCLUDED_SUFFIXES or path.name=='UiPopupAssets.generated.h'
        or path.name=='.env' or path.name.startswith('.env.') or path.name in {'credentials.json','id_rsa','id_ed25519'})


def staged_audit():
    listed=git(['ls-files','--stage','-z']);assert listed.returncode==0
    entries=[]
    for raw in listed.stdout.split(b'\0'):
        if not raw:continue
        header,name=raw.split(b'\t',1);mode,oid,stage=header.split();assert stage==b'0'
        name=name.decode('utf8');assert mode in (b'100644',b'100755') and not denied(name),'Excluded staged path: '+name
        entries.append((name,oid))
    process=subprocess.Popen(['git','-c','safe.directory='+PROJECT.as_posix(),'cat-file','--batch'],cwd=PROJECT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    stdout,stderr=process.communicate(b'\n'.join(oid for _,oid in entries)+b'\n',timeout=60)
    assert process.returncode==0 and not stderr
    offset=0;rows=[];findings=[]
    for name,oid in entries:
        end=stdout.index(b'\n',offset);header=stdout[offset:end].split();offset=end+1
        assert header[:2]==[oid,b'blob'];length=int(header[2]);raw=stdout[offset:offset+length];offset+=length+1
        assert len(raw)==length and length<10*1024**2,'Oversized staged payload: '+name
        if any(pattern.search(raw) for pattern in SECRET_PATTERNS):findings.append(name)
        source=PROJECT/name;assert source.is_file() and hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(raw).digest(),name
        rows.append(dict(path=name,bytes=length,sha256=hashlib.sha256(raw).hexdigest()))
    assert not findings,'Credential-shaped material requires review in: '+', '.join(findings)
    return dict(status='PASS_SOURCE_ONLY_INDEX_AUDIT',files=len(rows),logical_bytes=sum(r['bytes'] for r in rows),
        largest_file=max(rows,key=lambda r:r['bytes']) if rows else None,secret_findings=findings,manifest=rows,
        excluded_original_assets_builds_saves_vendor_inputs=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--audit-output',type=Path);args=parser.parse_args()
    count=None
    if BASE.is_dir() and TARGET.is_dir():
        patch,manifest,count=make()
        if args.check:
            assert PATCH.read_bytes()==patch and MANIFEST.read_bytes()==manifest,'SDK changed: refresh its patch before committing'
        else:
            PATCH.parent.mkdir(exist_ok=True);PATCH.write_bytes(patch);MANIFEST.write_bytes(manifest)
        assert git(['apply','--reverse','--check','--',str(PATCH.relative_to(PROJECT))]).returncode==0,'SDK patch reverse check failed'
    elif not args.check:raise RuntimeError('Both local original and modified SDK inputs are required to refresh')
    result=staged_audit() if args.check else dict(status='PASS_SDK_PATCH_AND_HASH_MANIFEST',changed_sdk_files=count,patch_bytes=PATCH.stat().st_size)
    if args.audit_output:
        path=args.audit_output.absolute();assert path.is_relative_to(PROJECT/'evidence/version_control')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='manifest'}))


if __name__=='__main__':main()
