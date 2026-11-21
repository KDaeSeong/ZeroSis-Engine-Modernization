"""Disassemble every DXBC blob embedded in the retail CivilizationV_DX11.exe with the Windows SDK fxc /dumpbin.

The game EXE is only read as bytes. fxc only disassembles bytecode; no game, Host, window or GPU is used.
Large per-blob listings go to a scratch directory outside the project; only the index is kept.
usage: python -B -X utf8 shader_disasm.py SCRATCH_DIR INDEX.json
"""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

GAME_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
EXE_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
FXC = Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')
STAGES = {0: 'ps', 1: 'vs', 2: 'gs', 3: 'hs', 4: 'ds', 5: 'cs'}


def blobs(raw: bytes):
    for match in re.finditer(b'DXBC', raw):
        offset = match.start()
        if offset + 32 > len(raw):
            continue
        size, count = struct.unpack_from('<II', raw, offset + 24)
        if not (32 < size < 2_000_000 and 0 < count < 16):
            continue
        blob = raw[offset:offset + size]
        chunks = {}
        for chunk_offset in struct.unpack_from('<%dI' % count, blob, 32):
            chunks[blob[chunk_offset:chunk_offset + 4].decode('latin1')] = chunk_offset + 8
        code = chunks.get('SHDR', chunks.get('SHEX'))
        if code is None:
            continue
        stage = STAGES[struct.unpack_from('<I', blob, code)[0] >> 16]
        yield offset, stage, blob


def disassemble(job):
    source, listing = job
    result = subprocess.run([str(FXC), '/nologo', '/dumpbin', '/Fc', str(listing), str(source)],
                            capture_output=True, timeout=120)
    return source.name, result.returncode, (result.stdout + result.stderr)[-400:].decode('mbcs', errors='replace')


def features(text: str) -> dict:
    # fxc /dumpbin listings are not numbered: each instruction is one line, indented inside control flow.
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith('//')]
    body = [l for l in lines if not l.startswith('dcl_') and not re.fullmatch(r'(vs|ps|gs|hs|ds|cs)_\d_\d', l)]
    return dict(
        model=next((l for l in lines if re.fullmatch(r'(vs|ps|gs|hs|ds|cs)_\d_\d', l)), None),
        resources=[l for l in lines if l.startswith('dcl_resource')],
        samplers=sum(1 for l in lines if l.startswith('dcl_sampler')),
        cbuffers=[l for l in lines if l.startswith('dcl_constantbuffer')],
        outputs=[l for l in lines if l.startswith('dcl_output')],
        inputs=[l for l in lines if l.startswith('dcl_input')],
        sample_ops=sum(1 for l in body if l.startswith('sample')),
        load_ops=sum(1 for l in body if l.startswith('ld')),
        instructions=len(body))


def main(scratch: Path, index: Path) -> int:
    raw = GAME_EXE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXE_SHA:
        raise SystemExit('Retail EXE differs from the analysed build')
    scratch.mkdir(parents=True, exist_ok=True)
    jobs, rows = [], []
    for offset, stage, blob in blobs(raw):
        source = scratch / f'{offset:08x}_{stage}.cso'
        listing = scratch / f'{offset:08x}_{stage}.asm'
        if not source.exists():
            source.write_bytes(blob)
        if not listing.exists():
            jobs.append((source, listing))
        rows.append(dict(file_offset=offset, stage=stage, bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                         listing=listing.name))
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for name, code, tail in pool.map(disassemble, jobs):
            if code:
                failures.append(dict(blob=name, returncode=code, tail=tail))
    for row in rows:
        text = (scratch / row['listing']).read_text('utf8', errors='replace') if (scratch / row['listing']).exists() else ''
        row.update(features(text))
    value = dict(schema='zerosis.world_terrain_original.shader_disasm.v1', exe=dict(path=str(GAME_EXE), sha256=EXE_SHA),
                 tool=dict(path=str(FXC), sha256=hashlib.sha256(FXC.read_bytes()).hexdigest(), mode='/dumpbin'),
                 scratch_dir=str(scratch), blobs=len(rows), failures=failures, rows=rows,
                 game_or_host_executed=False, gpu_used=False)
    with index.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=1)
        stream.write('\n')
    print(json.dumps(dict(blobs=len(rows), disassembled_now=len(jobs), failures=len(failures))))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]).absolute()))
