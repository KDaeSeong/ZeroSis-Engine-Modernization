"""Disassemble five pinned lighting blobs; never load the game or a graphics device."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
EVIDENCE = PROJECT/'evidence/world_terrain_original'
SELECTED = [('CacheBake', 0, 'vs'), ('CacheBake', 0, 'ps'), ('CacheBake', 1, 'ps'),
            ('NormalCalculate', 0, 'ps'), ('TerrainShader', 0, 'ps')]
EXE_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
FXC_SHA = 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
spec = importlib.util.spec_from_file_location('phase5_lighting_storage', PROJECT/'tools/audit_exit_host_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def ref(path):
    value = storage.ordinary(path)
    digest, allocation = storage.digest(path), storage.allocated(path)
    assert storage.metadata(value) == storage.metadata(storage.ordinary(path))
    return dict(path=str(path), **storage.metadata(value), sha256=digest, allocated_bytes=allocation)


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    out = STAGE/'bytecode'
    assert not out.exists(), 'Use the retained selected lighting listings; inspect before a retry'
    probe = EVIDENCE/'retail_terrain_pipeline_probe.json'
    semantics = EVIDENCE/'terrain_shader_semantics.json'
    p = json.loads(probe.read_text('utf8'))
    s = json.loads(semantics.read_text('utf8'))
    exe = ref(Path(s['exe']['path']))
    compiler = ref(Path(s['tool']['path']))
    assert exe['sha256'] == p['exe']['sha256'] == EXE_SHA
    assert compiler['sha256'] == FXC_SHA
    effects = {v['name']: v for v in p['effect_records']['effects'].values()}
    original = Path(exe['path']).read_bytes()
    out.mkdir()
    rows, owned = [], []
    try:
        for effect, index, stage in SELECTED:
            blob = effects[effect]['passes'][index][stage]['sm5']
            offset = int(blob['file_offset'], 16)
            raw = original[offset:offset+blob['bytes']]
            assert hashlib.sha256(raw).hexdigest() == blob['sha256']
            stem = f'{effect}_{index}_{stage}'
            temporary, listing = out/(stem+'.cso'), out/(stem+'.asm')
            with temporary.open('xb') as stream:
                stream.write(raw)
            owned.append(ref(temporary))
            command = [compiler['path'], '/nologo', '/dumpbin', '/Fc', str(listing), str(temporary)]
            done = subprocess.run(command, cwd=out, capture_output=True, timeout=30,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            diagnostic = (done.stdout+done.stderr).decode('mbcs', errors='replace')
            assert done.returncode == 0 and listing.is_file(), diagnostic[:1000]
            rows.append(dict(effect=effect, pass_index=index, stage=stage, source_blob=blob,
                             command=command, exit_code=done.returncode,
                             diagnostic=diagnostic[:500], listing=ref(listing)))
        assert ref(Path(exe['path'])) == exe
        assert ref(Path(compiler['path'])) == compiler
    finally:
        for row in owned:
            path = Path(row['path'])
            assert path.is_relative_to(out) and row['links'] == 1 and not row['file_attributes'] & 0x401
            assert ref(path) == row
        write_new(out/'cleanup_plan.json', dict(exact_owned_leaves=owned, no_recursive_delete=True,
                    protected_original=exe, protected_compiler=compiler))
        for row in owned:
            path = Path(row['path'])
            assert ref(path) == row
            path.unlink()
        write_new(out/'cleanup_result.json', dict(status='PASS_EXACT_TEMP_DXBC_REMOVED', deleted_files=len(owned),
                    logical_bytes=sum(r['bytes'] for r in owned),
                    unique_predelete_allocated_bytes=sum(r['allocated_bytes'] for r in owned),
                    all_absent=all(not Path(r['path']).exists() for r in owned),
                    original_exe_and_compiler_unchanged=ref(Path(exe['path'])) == exe and ref(Path(compiler['path'])) == compiler))
    result = dict(schema='zerosis.original_lighting.phase5.selected_disassembly.v1',
                  status='PASS_FIVE_PINNED_ORIGINAL_LIGHTING_LISTINGS', original_exe=exe, compiler=compiler,
                  pipeline_probe=ref(probe), phase0_semantics=ref(semantics),
                  selected=rows, cleanup=ref(out/'cleanup_result.json'),
                  host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False, graphics_device_created=False,
                  original_phases_modified=False)
    write_new(out/'result.json', result)
    print(json.dumps(dict(status=result['status'], listings=len(rows),
                retained_listing_bytes=sum(r['listing']['bytes'] for r in rows),
                temporary_dxbc_deleted=len(owned))))


if __name__ == '__main__':
    main()
