"""Pinned read-only retail PE address reader; never loads retail code."""
from pathlib import Path
import hashlib
import json
import struct
import capstone

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
EXPECTED='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'


def ref(path):
    path=Path(path).absolute();before=path.stat()
    assert path.resolve()==path and not before.st_file_attributes&0x400
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=path.stat()
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    return dict(path=str(path),bytes=after.st_size,sha256=digest,file_identity=[after.st_dev,after.st_ino],mtime_ns=after.st_mtime_ns,file_attributes=after.st_file_attributes)


class Pe:
    def __init__(self):
        previous=json.loads((PROJECT/'evidence/world_terrain_original/phase8/screen_lighting/screen_provider_contract.json').read_text('utf8'))
        self.path=Path(previous['exe']['path']);self.before=ref(self.path)
        assert self.before['sha256']==EXPECTED
        self.raw=self.path.read_bytes();pe=struct.unpack_from('<I',self.raw,60)[0]
        assert self.raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',self.raw,pe+24)[0]==0x10b
        self.base=struct.unpack_from('<I',self.raw,pe+52)[0]
        self.sections=[];opt=struct.unpack_from('<H',self.raw,pe+20)[0]
        for i in range(struct.unpack_from('<H',self.raw,pe+6)[0]):
            at=pe+24+opt+40*i
            v,r,n,o=struct.unpack_from('<IIII',self.raw,at+8)
            self.sections.append((self.base+r,v,n,o,self.raw[at:at+8].rstrip(b'\0').decode('ascii')))
        self.md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)

    def offset(self,va,n=1):
        section=next(s for s in self.sections if s[0]<=va<s[0]+max(s[1],s[2]))
        assert va-section[0]+n<=section[2],hex(va)
        return section[3]+va-section[0]

    def data(self,va,n):
        at=self.offset(va,n);return self.raw[at:at+n]

    def u32(self,va):return struct.unpack('<I',self.data(va,4))[0]

    def string(self,va):return self.data(va,128).split(b'\0')[0].decode('ascii')

    def rows(self,start,stop):return list(self.md.disasm_lite(self.data(start,stop-start),start))

    def listing(self,start,stop):return '\n'.join(f'{a:08x} {m} {o}' for a,n,m,o in self.rows(start,stop))

    def verify(self):assert ref(self.path)==self.before


def write_new(name,result):
    path=STAGE/name;assert path.parent==STAGE and path.name.startswith('water_') and not path.exists()
    with path.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    return ref(path)
