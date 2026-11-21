"""Disassemble six pinned original water/river DXBC blobs without graphics use."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
BYTECODE = STAGE / 'bytecode'
ORIGINAL_EVIDENCE = PROJECT / 'evidence/world_terrain_original'
EXE_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
FXC_SHA = 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
SELECTED = [('WaterShader', 0, 'vs'), ('WaterShader', 0, 'ps'), ('WaterShader', 1, 'ps'),
            ('WaterShader', 2, 'ps'), ('RiverShader', 0, 'vs'), ('RiverShader', 0, 'ps')]
spec = importlib.util.spec_from_file_location('water_semantics_storage', PROJECT/'tools/audit_exit_host_storage.py')
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
    assert not BYTECODE.exists(), 'Inspect the owned selected-shader output before retrying'
    pipeline_path = ORIGINAL_EVIDENCE/'retail_terrain_pipeline_probe.json'
    pipeline = json.loads(pipeline_path.read_text('utf8'))
    semantics = json.loads((ORIGINAL_EVIDENCE/'terrain_shader_semantics.json').read_text('utf8'))
    exe = ref(Path(semantics['exe']['path']))
    compiler = ref(Path(semantics['tool']['path']))
    assert exe['sha256'] == pipeline['exe']['sha256'] == EXE_SHA and compiler['sha256'] == FXC_SHA
    effects = {value['name']:value for value in pipeline['effect_records']['effects'].values()}
    original = Path(exe['path']).read_bytes()
    BYTECODE.mkdir()
    rows, owned = [], []
    try:
        for effect, index, stage in SELECTED:
            blob = effects[effect]['passes'][index][stage]['sm5']
            offset = int(blob['file_offset'],16)
            raw = original[offset:offset+blob['bytes']]
            assert hashlib.sha256(raw).hexdigest() == blob['sha256']
            stem = effect + '_' + str(index) + '_' + stage
            temporary, listing = BYTECODE/(stem+'.cso'), BYTECODE/(stem+'.asm')
            with temporary.open('xb') as stream:
                stream.write(raw)
            owned.append(ref(temporary))
            command = [compiler['path'],'/nologo','/dumpbin','/Fc',str(listing),str(temporary)]
            done = subprocess.run(command,cwd=BYTECODE,capture_output=True,timeout=90,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            log = (done.stdout+done.stderr).decode('mbcs',errors='replace')
            log_path = BYTECODE/(stem+'_dump.txt')
            log_path.write_text(log,encoding='utf8')
            assert done.returncode == 0 and listing.exists(), log[:1000]
            rows.append(dict(effect=effect,pass_index=index,stage=stage,source_blob=blob,
                             compiler_command=command,exit_code=done.returncode,log=ref(log_path),listing=ref(listing)))
        assert ref(Path(exe['path'])) == exe and ref(Path(compiler['path'])) == compiler
    finally:
        for row in owned:
            path = Path(row['path'])
            assert path.is_relative_to(BYTECODE) and row['links']==1 and not row['file_attributes']&0x401
            assert ref(path)==row
        write_new(BYTECODE/'cleanup_plan.json',dict(files=owned,original_exe=exe,compiler=compiler))
        for row in owned:
            path=Path(row['path'])
            assert ref(path)==row
            path.unlink()
        write_new(BYTECODE/'cleanup_result.json',dict(status='PASS_EXACT_TEMPORARY_DXBC_REMOVED',files=owned,
                  deleted_files=len(owned),logical_bytes=sum(row['bytes'] for row in owned),
                  unique_predelete_allocation_bytes=sum(row['allocated_bytes'] for row in owned),
                  original_exe_and_compiler_unchanged=True))
    result=dict(schema='zerosis.original_water.phase3.selected_shader_disassembly.v1',
                status='PASS_SIX_PINNED_WATER_RIVER_LISTINGS',original_exe=exe,compiler=compiler,
                pipeline_probe=ref(pipeline_path),selected=rows,cleanup=ref(BYTECODE/'cleanup_result.json'),
                host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,graphics_device_created=False,
                original_game_or_gpu_image_parity_verified=False)
    write_new(BYTECODE/'result.json',result)
    print(json.dumps(dict(status=result['status'],selected_shaders=len(rows),
                         retained_listing_bytes=sum(row['listing']['bytes'] for row in rows),
                         temporary_dxbc_deleted=len(owned),original_exe_unchanged=True)))


if __name__=='__main__':
    main()
