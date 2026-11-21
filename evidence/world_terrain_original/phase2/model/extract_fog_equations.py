"""Disassemble only four SHA-pinned retail fog shaders; never load the game."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(PROJECT / 'tools'))
from build_exit_confirm_host import artifact
from menu_suite_storage import storage

HERE = Path(__file__).absolute().parent


def write_new(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=1, ensure_ascii=False)
        stream.write('\n')


def main():
    stage = HERE / 'bytecode'
    stage.mkdir(exist_ok=False)
    source = PROJECT / 'evidence/world_terrain_original'
    semantics = json.loads((source / 'terrain_shader_semantics.json').read_text('utf8'))
    pipeline = json.loads((source / 'retail_terrain_pipeline_probe.json').read_text('utf8'))
    effects = {row['name']: row for row in pipeline['effect_records']['effects'].values()}
    exe = Path(semantics['exe']['path'])
    exe_row = artifact(exe)
    assert exe_row['sha256'] == semantics['exe']['sha256'] == pipeline['exe']['sha256']
    fxc = Path(semantics['tool']['path'])
    fxc_row = artifact(fxc)
    assert fxc_row['sha256'] == semantics['tool']['sha256']
    raw = exe.read_bytes()
    rows, owned = [], []
    for effect, index, slot in [('TerrainShader', 0, 'ps'), ('TerrainShader', 3, 'vs'),
                                 ('FOWParticleShader', 0, 'ps'), ('FOWBaseLayer', 0, 'ps')]:
        ref = effects[effect]['passes'][index][slot]['sm5']
        offset = int(ref['file_offset'], 16)
        data = raw[offset:offset + ref['bytes']]
        assert hashlib.sha256(data).hexdigest() == ref['sha256']
        stem = effect + '_' + str(index) + '_' + slot
        blob, listing = stage / (stem + '.cso'), stage / (stem + '.asm')
        with blob.open('xb') as stream:
            stream.write(data)
        owned.append(blob)
        result = subprocess.run([str(fxc), '/nologo', '/dumpbin', '/Fc', str(listing), str(blob)],
                                capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(result.stdout.decode('mbcs', errors='replace')[:2000])
        rows.append(dict(effect=effect, pass_index=index, slot=slot, retail_blob=ref,
                         listing=artifact(listing)))
    cleanup = []
    for path in owned:
        row = dict(artifact(path), allocated_bytes=storage.allocated(path))
        info = storage.ordinary(path)
        assert info.st_nlink == 1 and not info.st_file_attributes & 1
        assert artifact(path) == {key: row[key] for key in artifact(path)}
        assert path.is_relative_to(stage)
        path.unlink()
        row['result'] = 'DELETED_OWNED_REGENERABLE_DXBC_INPUT'
        cleanup.append(row)
    write_new(stage / 'result.json', dict(schema='zerosis.original_fog.bytecode_subset.v1',
        status='PASS_SHA_PINNED_DISASSEMBLY_ONLY', exe=exe_row, tool=fxc_row,
        inputs=[artifact(source / 'terrain_shader_semantics.json'), artifact(source / 'retail_terrain_pipeline_probe.json')],
        shaders=rows, cleanup=cleanup, game_or_host_executed=False, gpu_used=False))
    print(json.dumps(dict(status='PASS', shaders=len(rows), deleted_bytes=sum(row['bytes'] for row in cleanup))))


if __name__ == '__main__':
    main()
