"""Read two selected original composite shaders; no game or GPU execution."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
OLD = PROJECT/'evidence/world_terrain_original/phase5/semantics/extract_lighting.py'
spec = importlib.util.spec_from_file_location('phase6_original_shader_io', OLD)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)


def main():
    out = STAGE/'composite'
    assert not out.exists(), 'Inspect the retained two-shader proof before retrying'
    probe = PROJECT/'evidence/world_terrain_original/retail_terrain_pipeline_probe.json'
    original = json.loads(probe.read_text('utf8'))
    semantics = json.loads((PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json').read_text('utf8'))
    exe = io.ref(Path(semantics['exe']['path']))
    compiler = io.ref(Path(semantics['tool']['path']))
    assert exe['sha256'] == io.EXE_SHA and compiler['sha256'] == io.FXC_SHA
    effect = next(v for v in original['effect_records']['effects'].values() if v['name'] == 'CompositeShader')
    data = Path(exe['path']).read_bytes()
    out.mkdir()
    owned, rows = [], []
    try:
        for stage in ['vs', 'ps']:
            blob = effect['passes'][0][stage]['sm5']
            at = int(blob['file_offset'], 16)
            raw = data[at:at+blob['bytes']]
            assert hashlib.sha256(raw).hexdigest() == blob['sha256']
            temp = out/f'CompositeShader_0_{stage}.cso'
            listing = out/f'CompositeShader_0_{stage}.asm'
            with temp.open('xb') as stream:
                stream.write(raw)
            owned.append(io.ref(temp))
            command = [compiler['path'], '/nologo', '/dumpbin', '/Fc', str(listing), str(temp)]
            done = subprocess.run(command, cwd=out, capture_output=True, timeout=30,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            assert done.returncode == 0 and listing.is_file()
            rows.append(dict(stage=stage, blob=blob, command=command, exit_code=done.returncode, listing=io.ref(listing)))
    finally:
        for row in owned:
            path = Path(row['path'])
            assert path.resolve().parent == out.resolve() and row['links'] == 1 and not row['file_attributes'] & 0x401
            assert io.ref(path) == row
        io.write_new(out/'cleanup_plan.json', dict(files=owned, exact_leaf_only=True))
        for row in owned:
            path = Path(row['path'])
            assert io.ref(path) == row
            path.unlink()
        assert io.ref(Path(exe['path'])) == exe and io.ref(Path(compiler['path'])) == compiler
        io.write_new(out/'cleanup_result.json', dict(status='PASS_EXACT_TWO_TEMP_COMPOSITE_DXBC_REMOVED',
            files=owned, deleted_files=len(owned), logical_bytes=sum(r['bytes'] for r in owned),
            released_unique_allocated_bytes=sum(r['allocated_bytes'] for r in owned),
            all_absent=all(not Path(r['path']).exists() for r in owned), original_and_compiler_unchanged=True))
    result = dict(schema='zerosis.original_detail.phase6.selected_composite.v1',
        status='PASS_TWO_ORIGINAL_COMPOSITE_SHADER_LISTINGS', original_exe=exe, compiler=compiler,
        pipeline_probe=io.ref(probe), reused_reader=io.ref(OLD), selected=rows, cleanup=io.ref(out/'cleanup_result.json'),
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    io.write_new(out/'result.json', result)
    print(json.dumps(dict(status=result['status'], shader_count=2, temporary_deleted=len(owned),
        retained_listing_bytes=sum(r['listing']['bytes'] for r in rows))))


if __name__ == '__main__':
    main()
