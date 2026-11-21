"""Read-only original forest/tessellation/camera evidence and compiler disassembly."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
spec = importlib.util.spec_from_file_location('water_pe', STAGE.parent / 'reflection/water_pe_view.py')
pe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe_module)


def write_new(name, value):
    with (STAGE / name).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def hits(data, needle):
    at = data.find(needle)
    while at >= 0:
        yield at
        at = data.find(needle, at + 1)


def main():
    pe = pe_module.Pe()
    code = next(s for s in pe.sections if s[4] == '.text')
    def va(offset):
        section = next(s for s in pe.sections if s[3] <= offset < s[3] + s[2])
        return section[0] + offset - section[3]
    findings = []
    for string in (b'CameraInfo\0', b'Minimum Zoom Level\0', b'Camera zoom out type\0',
                   b'StraightZoom\0', b'BicubicTerrainTessellation\0', b'Camera Pitch: %4.2f\0'):
        for offset in hits(pe.raw, string):
            address = va(offset)
            refs = []
            for raw_ref in hits(pe.raw[code[3]:code[3] + code[2]], struct.pack('<I', address)):
                ref = code[0] + raw_ref
                refs.append(dict(address=hex(ref), listing=pe.listing(max(code[0], ref - 32), ref + 80)))
            findings.append(dict(string=string[:-1].decode('ascii'), address=hex(address), references=refs))
    matrix_hits = []
    for values in ((-1., 3., -3., 1.), (-.5, 1.5, -1.5, .5), (-1/6, .5, -.5, 1/6)):
        for offset in hits(pe.raw, struct.pack('<4f', *values)):
            address = va(offset)
            if offset + 64 <= len(pe.raw):
                matrix_hits.append(dict(address=hex(address), values=struct.unpack_from('<16f', pe.raw, offset),
                                        xrefs=[hex(code[0] + r) for r in hits(
                                            pe.raw[code[3]:code[3] + code[2]], struct.pack('<I', address))]))
    source = PROJECT / 'evidence/world_terrain_original/retail_terrain_pipeline_probe.json'
    effects = json.loads(source.read_text('utf8'))['effect_records']['effects']
    compiler = Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')
    assert pe_module.ref(compiler)['sha256'] == 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
    shaders, seen = [], set()
    for effect in ('0x2c', '0x49'):
        for number, render_pass in enumerate(effects[effect]['passes']):
            for stage, record in render_pass.items():
                if effect == '0x49' and stage not in ('hs', 'ds'):
                    continue
                row = record['sm5']
                if row['sha256'] in seen:
                    continue
                seen.add(row['sha256'])
                offset = int(row['file_offset'], 16)
                data = pe.raw[offset:offset + row['bytes']]
                assert hashlib.sha256(data).hexdigest() == row['sha256']
                name = effects[effect]['name'] + '_' + str(number) + '_' + stage
                target = STAGE / (name + '.dxbc')
                assert not target.exists()
                target.write_bytes(data)
                call = [str(compiler), '/nologo', '/dumpbin', str(target)]
                result = subprocess.run(call, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, check=False, timeout=30,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                assert result.returncode == 0, result.stderr.decode(errors='replace')
                assembly = STAGE / (name + '.asm.txt')
                assert not assembly.exists()
                assembly.write_bytes(result.stdout)
                assert not result.stderr
                shaders.append(dict(effect=effect, first_pass=number, stage=stage, source=row,
                                    compiler=pe_module.ref(compiler), command=call, return_code=0,
                                    assembly=pe_module.ref(assembly), extracted=pe_module.ref(target)))
    pe.verify()
    write_new('geometry_probe.json', dict(status='PASS_FILE_ONLY_EXTRACTION', original_exe=pe.before,
              effect_evidence=pe_module.ref(source), camera_string_xrefs=findings,
              basis_candidates=matrix_hits, shader_disassemblies=shaders,
              shader_executed=False, native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='PASS_FILE_ONLY_EXTRACTION', shaders=len(shaders),
                          camera_strings=len(findings), basis_candidates=len(matrix_hits))))


if __name__ == '__main__':
    main()
