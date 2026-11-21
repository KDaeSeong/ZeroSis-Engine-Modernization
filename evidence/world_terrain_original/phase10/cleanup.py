"""Retire only this phase's extracted, reproducible original shader blobs."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new


def main():
    output=ROOT/'geometry/extracted_cleanup_result.json'
    assert not output.exists()
    probe=json.loads((ROOT/'geometry/geometry_probe.json').read_text('utf8'))
    rows=[]
    for shader in probe['shader_disassemblies']:
        path=Path(shader['extracted']['path'])
        assert path.parent==ROOT/'geometry' and path.suffix=='.dxbc'
        assert path.absolute()==path.resolve() and path.resolve().is_relative_to((PROJECT/'evidence').resolve())
        row=ref(path)
        assert row['sha256']==shader['extracted']['sha256'] and row['links']==1 and not row['file_attributes']&0x401
        # Retained assembly plus the pinned original PE permit exact extraction.
        assert ref(shader['assembly']['path'])['sha256']==shader['assembly']['sha256']
        rows.append(row)
    write_new(ROOT/'geometry/extracted_cleanup_plan.json',dict(files=rows,original=probe['original_exe'],exact_owned_leaves_only=True))
    for row in rows:
        path=Path(row['path']);assert ref(path)==row;path.unlink()
    write_new(output,dict(status='PASS_EXACT_REPRODUCIBLE_SHADER_BLOBS_REMOVED',files=rows,
        deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
        original_pe_modified=False,source_modified=False,original_assemblies_retained=True))
    print(json.dumps(dict(status='PASS_EXACT_REPRODUCIBLE_SHADER_BLOBS_REMOVED',files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))))


if __name__=='__main__':main()
