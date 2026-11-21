"""Observe a pinned public compressed body in bounded memory; never load a game."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
from urllib.request import Request, urlopen
import zlib

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/retail_save_container/compression'
COMMIT='858ce8532725f634e64fa8acaf355aa8e50829bf'
URL=f'https://raw.githubusercontent.com/bmaupin/js-civ5save/{COMMIT}/src/__tests__/resources/1.0.3.279.Civ5Save'


def require(value,message):
    if not value:raise RuntimeError(message)


def probe(data):
    """No partial result is classified as a complete restored/valid save."""
    maximum=64*1024*1024
    decoder=zlib.decompressobj()
    digest=hashlib.sha256()
    output_count=0
    first=bytearray()
    calls=0
    error=None
    consumed=0
    for begin in range(0,len(data),4096):
        pending=data[begin:begin+4096]
        try:
            while pending:
                calls+=1
                previous=len(pending)
                block=decoder.decompress(pending,min(65536,maximum-output_count+1))
                output_count+=len(block)
                require(output_count<=maximum,'Public decompressed output exceeded 64 MiB')
                digest.update(block)
                first.extend(block[:max(0,64-len(first))])
                pending=decoder.unconsumed_tail
                require(len(pending)<previous or block,'Decoder made no progress')
                consumed=begin+min(4096,len(data)-begin)-len(pending)-len(decoder.unused_data)
                if decoder.eof:break
        except zlib.error as failure:
            error=str(failure)
            break
        if decoder.eof:break
    return dict(status='OBSERVED_PUBLIC_COMPRESSION_NOT_SAVE_VALIDATION',
        compressed_bytes=len(data),decompressed_bytes=output_count,decompressed_sha256=digest.hexdigest(),
        zlib_runtime_version=zlib.ZLIB_RUNTIME_VERSION,zlib_end_of_stream=decoder.eof,
        decoder_error=error,decoder_calls=calls,last_offered_consumed_position=consumed,
        unused_bytes=len(decoder.unused_data)+(len(data)-consumed-len(decoder.unused_data) if decoder.eof else 0),
        unconsumed_tail_bytes=len(decoder.unconsumed_tail),compressed_tail_hex=data[-16:].hex(),
        decompressed_first_word=struct.unpack('<I',first[:4])[0] if len(first)>=4 else None,
        output_limit_bytes=maximum,complete_save_validated=False,sdk_restore_verified=False,
        partial_decompression_accepted_as_complete=False)


def main():
    require(len(sys.argv)==1 and not sys.flags.optimize,'Unexpected compression probe invocation')
    report=STAGE/'public_probe.json'
    require(not report.exists(),'Inspect an existing public probe instead of overwriting it')
    with urlopen(Request(URL,headers={'User-Agent':'ZeroSis-Bounded-Public-Compression-Probe'}),timeout=20) as stream:
        require(stream.geturl()==URL,'Unexpected public fixture redirect')
        data=stream.read(1024*1024+1)
    require(len(data)==418069 and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==
        '186fb9a84f4e47192e11b8cd98b436a48ccbee16','Immutable public save differs')
    prefix=(PROJECT/'Tests/Fixtures/RetailSaveHeader/bnw_279.prefix').read_bytes()
    prefix+=(PROJECT/'Tests/Fixtures/RetailSavePregame/bnw_279.pregame').read_bytes()
    require(len(prefix)==10991 and data[:len(prefix)]==prefix,'Previously verified uncompressed boundary changed')
    result=probe(data[len(prefix):])
    result.update(source_url=URL,upstream_git_blob='186fb9a84f4e47192e11b8cd98b436a48ccbee16',
        utc=datetime.now(timezone.utc).isoformat(),compressed_data_offset=len(prefix),
        full_public_save_retained=False,decompressed_body_retained=False,user_saves_accessed=False,
        host_gamecore_or_hwnd_executed=False,previous_goal_turn_classification='progress')
    for part in (STAGE,*STAGE.parents):
        if part.exists():require(not part.lstat().st_file_attributes&0x400,'Reparse output path')
    STAGE.mkdir(parents=True,exist_ok=True)
    with report.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
