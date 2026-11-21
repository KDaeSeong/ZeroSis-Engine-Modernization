"""Small raw-PE reader for the pinned original; disassembles data, never loads it."""
from pathlib import Path
import hashlib
import stat
import struct
import capstone

EXPECTED_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'


class Image:
    def __init__(self, path, expected_sha=EXPECTED_SHA):
        self.path = Path(path).absolute()
        for item in (self.path, *self.path.parents):
            info = item.lstat()
            assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400
        before = self.path.stat()
        self.raw = self.path.read_bytes()
        after = self.path.stat()
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        self.sha = hashlib.sha256(self.raw).hexdigest()
        assert self.sha == expected_sha
        self.original = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                         getattr(after, 'st_file_attributes', 0))
        pe = struct.unpack_from('<I', self.raw, 0x3c)[0]
        assert self.raw[pe:pe+4] == b'PE\0\0'
        count = struct.unpack_from('<H', self.raw, pe+6)[0]
        optional_size = struct.unpack_from('<H', self.raw, pe+20)[0]
        assert struct.unpack_from('<H', self.raw, pe+24)[0] == 0x10b
        self.base = struct.unpack_from('<I', self.raw, pe+24+28)[0]
        self.sections = []
        for index in range(count):
            at = pe+24+optional_size+index*40
            virtual, rva, size, offset = struct.unpack_from('<IIII', self.raw, at+8)
            self.sections.append(dict(name=self.raw[at:at+8].rstrip(b'\0').decode('ascii'),
                va=self.base+rva, virtual_bytes=virtual, bytes=size, file_offset=offset))
        self.decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.optional = pe+24

    def read(self, va, size):
        section = next(section for section in self.sections if section['va'] <= va < section['va']+section['virtual_bytes'])
        delta = va-section['va']
        assert delta+size <= section['bytes'], 'Runtime-filled/unbacked data has no file evidence'
        offset = section['file_offset']+delta
        return self.raw[offset:offset+size]

    def va(self, offset):
        section = next(section for section in self.sections if section['file_offset'] <= offset < section['file_offset']+section['bytes'])
        return section['va']+offset-section['file_offset']

    def u32(self, va):
        return struct.unpack('<I', self.read(va, 4))[0]

    def cstring(self, va):
        section = next(section for section in self.sections if section['va'] <= va < section['va']+section['virtual_bytes'])
        count = min(4096, section['bytes']-(va-section['va']))
        raw = self.read(va, count)
        assert b'\0' in raw
        return raw.split(b'\0', 1)[0].decode('ascii')

    def imports(self):
        rva, size = struct.unpack_from('<II', self.raw, self.optional+104)
        result = {}
        for offset in range(0, size, 20):
            original, _, _, name, first = struct.unpack('<IIIII', self.read(self.base+rva+offset, 20))
            if not original:
                break
            index = 0
            while True:
                hint = self.u32(self.base+original+index*4)
                if not hint:
                    break
                result[self.base+first+index*4] = dict(dll=self.cstring(self.base+name),
                    name=('#'+str(hint&0xffff)) if hint&0x80000000 else self.cstring(self.base+hint+2))
                index += 1
        return result

    def exports(self):
        rva, _ = struct.unpack_from('<II', self.raw, self.optional+96)
        base, count, names, functions, strings, ordinals = struct.unpack_from('<IIIIII', self.read(self.base+rva+16, 24))
        result = {}
        for index in range(names):
            name = self.cstring(self.base+self.u32(self.base+strings+index*4))
            ordinal = struct.unpack('<H', self.read(self.base+ordinals+index*2, 2))[0]
            result[name] = self.base+self.u32(self.base+functions+ordinal*4)
        return result

    def strings(self, needle):
        needle = needle.encode('ascii') if isinstance(needle, str) else needle
        found, start = [], 0
        while True:
            offset = self.raw.find(needle, start)
            if offset < 0:
                return found
            end = self.raw.find(b'\0', offset)
            found.append(dict(va=self.va(offset), value=self.raw[offset:min(end, offset+160)].decode('ascii', 'replace')))
            start = offset+len(needle)

    def literal_references(self, value, section_name='.text'):
        needle, found = struct.pack('<I', value), []
        for section in self.sections:
            if section['name'] != section_name:
                continue
            start = section['file_offset']
            stop = start+section['bytes']
            cursor = start
            while True:
                offset = self.raw.find(needle, cursor, stop)
                if offset < 0:
                    break
                found.append(self.va(offset))
                cursor = offset+1
        return found

    def instructions(self, start, stop):
        return list(self.decoder.disasm(self.read(start, stop-start), start))

    def listing(self, start, stop):
        return [dict(address=f'{ins.address:08x}', instruction=f'{ins.mnemonic} {ins.op_str}'.strip())
                for ins in self.instructions(start, stop)]

    def finish(self):
        info = self.path.stat()
        assert self.original == (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                                 getattr(info, 'st_file_attributes', 0))
        assert hashlib.sha256(self.path.read_bytes()).hexdigest() == self.sha
