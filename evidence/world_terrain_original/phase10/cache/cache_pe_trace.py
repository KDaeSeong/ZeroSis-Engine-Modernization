"""Bounded static PE tracing; never loads the original executable as code."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
PROJECT = ROOT.parents[3]
sys.path.insert(0, str(PROJECT / 'evidence/world_terrain_original/phase8/normal_cache'))
from normal_contract_pe import Image


def reference(path):
    info = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                file_attributes=getattr(info, 'st_file_attributes', 0))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--name', required=True)
    cli.add_argument('--range', action='append', default=[])
    cli.add_argument('--literal', action='append', default=[])
    cli.add_argument('--string', action='append', default=[])
    args = cli.parse_args()
    assert args.name.startswith('cache_') and args.name.replace('_', '').isalnum()
    output = ROOT / (args.name + '.json')
    assert not output.exists()
    image = Image(Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe"))
    blocks = {}
    for argument in args.range:
        name, start, stop = argument.split(':')
        start, stop = int(start, 16), int(stop, 16)
        assert name not in blocks and 0 < stop-start <= 32768
        raw = image.read(start, stop-start)
        blocks[name] = dict(start=f'{start:08x}', stop=f'{stop:08x}', bytes=len(raw),
                            sha256=hashlib.sha256(raw).hexdigest(),
                            listing=image.listing(start, stop))
    literals = {argument: [f'{x:08x}' for x in image.literal_references(int(argument, 16))]
                for argument in args.literal}
    strings = {argument: image.strings(argument) for argument in args.string}
    image.finish()
    report = dict(schema='zerosis.phase10.targeted_cache_pe.v1',
                  status='PASS_STATIC_ORIGINAL_BYTES_ONLY', original=reference(image.path),
                  reader=reference(PROJECT / 'evidence/world_terrain_original/phase8/normal_cache/normal_contract_pe.py'),
                  tracer=reference(Path(__file__).absolute()), blocks=blocks,
                  literal_byte_references=literals, strings=strings,
                  original_binary_loaded_or_executed=False, native_engine_executions=0)
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=report['status'], blocks=len(blocks),
                          instructions=sum(len(block['listing']) for block in blocks.values()),
                          artifact=reference(output))))


if __name__ == '__main__':
    main()
