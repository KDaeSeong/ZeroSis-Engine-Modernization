"""Generate small deterministic zlib vectors; no public or user saves retained."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/retail_save_container/compression'
TARGET=PROJECT/'Tests/Fixtures/RetailSaveInflate/streams.bin'


def main():
    if len(sys.argv)!=1 or sys.flags.optimize:raise RuntimeError('Unexpected fixture invocation')
    report=STAGE/'fixtures.json'
    if report.exists():
        old=json.loads(report.read_text(encoding='utf-8'));data=TARGET.read_bytes()
        assert old['status']=='PASS_SYNTHETIC_INFLATE_FIXTURES' and hashlib.sha256(data).hexdigest()==old['fixture']['sha256']
        print(json.dumps(dict(status=old['status'],reused=True,bytes=len(data))));return
    rows=[]
    def add(name,kind,compressed,plain):rows.append((name,kind,compressed,plain))
    plain=(b'ZeroSis\0Civilization V\xff'+bytes(range(256)))*400
    state=0x62a1b59d;random=bytearray()
    for _ in range(8192):
        state=(state*1664525+1013904223)&0xffffffff;random.append(state>>24)
    add('empty',0,zlib.compress(b''),b'')
    add('fixed_huffman',0,zlib.compress(plain),plain)
    c=zlib.compressobj(strategy=zlib.Z_FIXED);add('forced_fixed',0,c.compress(plain)+c.flush(),plain)
    c=zlib.compressobj(level=0);add('stored_binary',0,c.compress(random)+c.flush(),bytes(random))
    c=zlib.compressobj();first=c.compress(plain)+c.flush(zlib.Z_SYNC_FLUSH)
    add('nonfinal_empty_stored',1,first,plain)
    second=c.compress(random)+c.flush();add('earlier_boundary_then_finish',0,first+second,plain+random)
    c=zlib.compressobj();add('full_flush_same_wire_class',1,c.compress(plain)+c.flush(zlib.Z_FULL_FLUSH),plain)
    c=zlib.compressobj();chunk=c.compress(plain)+c.flush(zlib.Z_BLOCK)
    add('nonfinal_huffman_boundary',2,chunk,plain)
    add('wrapper_header_only',2,b'\x78\x9c',b'')
    add('no_input',2,b'',b'')
    complete=zlib.compress(plain)
    add('final_block_missing_adler',2,complete[:-4],plain)
    decoder=zlib.decompressobj();part=complete[:len(complete)//2]
    add('cut_inside_block',2,part,decoder.decompress(part))
    bad=bytearray(complete);bad[-1]^=1;add('bad_adler',4,bytes(bad),b'')
    c=zlib.compressobj(zdict=b'known dictionary');add('preset_dictionary',3,c.compress(plain)+c.flush(),b'')
    c=zlib.compressobj(wbits=31);add('gzip_not_enabled',4,c.compress(plain)+c.flush(),b'')
    add('invalid_header',4,b'\x78\x00\x00\x00\xff\xff',b'')
    payload=bytearray(b'ZSINFL01'+struct.pack('<I',len(rows)))
    manifest=[]
    def word(value):payload.extend(struct.pack('<I',value))
    for name,kind,compressed,plain in rows:
        name_bytes=name.encode('ascii');word(len(name_bytes));payload.extend(name_bytes)
        word(kind);word(len(plain));payload.extend(hashlib.sha256(plain).digest());word(len(compressed));payload.extend(compressed)
        manifest.append(dict(name=name,kind=kind,compressed_bytes=len(compressed),output_bytes=len(plain),output_sha256=hashlib.sha256(plain).hexdigest()))
    assert len(payload)<65536
    for path in (TARGET,*TARGET.parents):
        if path.exists():assert not path.lstat().st_file_attributes&0x400
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    with TARGET.open('xb') as f:f.write(payload)
    result=dict(status='PASS_SYNTHETIC_INFLATE_FIXTURES',utc=datetime.now(timezone.utc).isoformat(),
        generator_zlib=zlib.ZLIB_RUNTIME_VERSION,fixture=dict(path=str(TARGET),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()),
        vectors=manifest,public_save_body_retained=False,user_saves_accessed=False,host_gamecore_or_hwnd_executed=False)
    with report.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(status=result['status'],vectors=len(rows),retained_bytes=len(payload))))


if __name__=='__main__':main()
