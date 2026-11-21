"""Delete only private partial outputs of the superseded access-denied build."""
from pathlib import Path
import os,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new

def main():
    successful=json.loads((ROOT/'host_build_retry02/controller_exit.json').read_text('utf8'))
    assert successful['returncode']==0
    profile=ROOT/'pair_preparation/20261116T114748Z_014dd63ad3bc/prepared_profile.json'
    assert profile.is_file()
    latest=json.loads((PROJECT/'evidence/ui_window_host/20261116T114748Z_014dd63ad3bc/build_result.json').read_text('utf8'))
    protected={str(Path(row['path']).resolve()).casefold() for row in latest['current_source_inputs']+latest['protected_artifacts']}
    protected.update(str(Path(row['path']).resolve()).casefold() for row in latest['compiler_inputs'])
    roots=[PROJECT/'Build/UiWindowHost/20261115T215809Z_7d033e5af2d1',PROJECT/'evidence/ui_window_host/20261115T215809Z_7d033e5af2d1']
    rows=[];directories=[]
    for directory in roots:
        assert directory.resolve()==directory and directory.is_dir()
        assert directory.is_relative_to(PROJECT/'Build') or directory.is_relative_to(PROJECT/'evidence')
        for path in sorted(directory.rglob('*')):
            state=os.stat(path,follow_symlinks=False)
            assert not state.st_file_attributes&0x400 and str(path.resolve()).casefold() not in protected
            if path.is_dir():directories.append(path)
            else:
                row=ref(path);assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(ROOT/'failed_cleanup_plan.json',dict(status='PREPARED_EXACT_SUPERSEDED_PRIVATE_BUILD_LEAVES',
        roots=list(map(str,roots)),files=rows,replacement=ref(profile),never_delete_current_or_shared=True))
    for row in rows:
        path=Path(row['path']);assert ref(path)==row;path.unlink()
    for path in sorted(directories,key=lambda p:len(p.parts),reverse=True):path.rmdir()
    for path in roots:path.rmdir()
    write_new(ROOT/'failed_cleanup_result.json',dict(status='PASS_SUPERSEDED_ACCESS_DENIED_BUILD_PRIVATE_OUTPUTS_REMOVED',
        files=rows,deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
        source_or_current_runtime_or_saves_deleted=False,failure_metadata_retained=True))
    print(json.dumps(dict(status='PASS_SUPERSEDED_PRIVATE_OUTPUTS_REMOVED',files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))))

if __name__=='__main__':main()
