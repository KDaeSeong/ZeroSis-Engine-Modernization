"""Independent file-backed constants and arithmetic references for cache sampling."""
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
PROJECT = ROOT.parents[3]
sys.path.insert(0, str(PROJECT / 'evidence/world_terrain_original/phase8/normal_cache'))
from normal_contract_pe import Image


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def fold(value, raw):
    for byte in raw:
        value = ((value ^ byte) * 1099511628211) & 0xffffffffffffffff
    return value


class Reference:
    def __init__(self):
        self.image = Image(Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe"))
        self.constants = {}
        for name, address, expected in (
            ('metricX',0xb9a6d4,'0000803f'),('metricY',0xb9a6d8,'2db25d3f'),
            ('metricZ',0xb9a6dc,'cdcc4c3e'),('inverse255',0xa26a0c,'8180803b')):
            raw = self.image.read(address,4)
            assert raw.hex() == expected
            self.constants[name] = dict(va=f'{address:08x}',raw=raw.hex(),value=struct.unpack('<f',raw)[0])
        assert struct.unpack('<d',self.image.read(0x9dea50,8))[0] == 65535
        self.assert_instructions(0x463e2f,0x463e5d,[
            'cvtsi2ss xmm3, ecx','mulss xmm3, xmm2','subss xmm3, dword ptr [edi + 0x7ec]',
            'mulss xmm3, xmm0','addss xmm3, dword ptr [eax]'])
        self.assert_instructions(0x70b4e7,0x70b52c,[
            'fld dword ptr [esi]','fdiv dword ptr [esi + 4]','or eax, 0xc00',
            'fadd dword ptr [edi + 0x7ec]','fmul qword ptr [0x9dea50]',
            'fistp dword ptr [esp + 0x30]','mov cx, word ptr [esp + 0x30]'])
        self.assert_instructions(0x5cec46,0x5cec66,[
            'movzx edx, cx','cvtsi2ss xmm0, edx','mulss xmm0, dword ptr [0xa26a0c]',
            'mulss xmm0, dword ptr [eax + 0x1acc]'])
        self.assert_instructions(0x67837e,0x6783ac,[
            'mov eax, dword ptr [0xb9a6d4]','mov dword ptr [ebx + 0x1acc], eax',
            'mov ecx, dword ptr [0xb9a6d8]','mov dword ptr [ebx + 0x1ad0], ecx',
            'mov edx, dword ptr [0xb9a6dc]','mov dword ptr [ebx + 0x1ad4], edx'])
        self.assert_instructions(0x5cec99,0x5ced17,[
            'fdivrp st(1)','subss xmm1, xmm0','subss xmm0, xmm2','addss xmm0, xmm2'])
        self.height_hash=1469598103934665603
        for raw in range(65536):
            # Execute the two proven scalar multiply nodes with independent
            # explicit IEEE float32 rounding, not a copied production helper.
            value=f32(f32(float(raw)*self.constants['inverse255']['value'])*self.constants['metricZ']['value'])
            self.height_hash=fold(self.height_hash,struct.pack('<f',value))
        self.quantize_hash=1469598103934665603
        self.quantize_cases=0
        for reference in (0.0,f32(15300/65535),1.0):
            for raw in range(65536):
                normalized=f32(raw/65535)
                centered=f32(normalized-reference)
                exact=(Fraction.from_float(centered)+Fraction.from_float(reference))*65535
                if exact<0 or exact>65535:
                    # Explicit production domain guards are tested separately.
                    continue
                expected=exact.numerator//exact.denominator
                self.quantize_hash=fold(self.quantize_hash,struct.pack('<H',expected))
                self.quantize_cases+=1
        self.image.finish()

    def assert_instructions(self,start,stop,required):
        listing=[row['instruction'] for row in self.image.listing(start,stop)]
        for instruction in required:
            assert instruction in listing,(hex(start),instruction)

    def header(self,path):
        with Path(path).open('x',encoding='ascii',newline='\n') as stream:
            stream.write('#pragma once\nnamespace CacheSamplingGolden {\n')
            stream.write('constexpr unsigned long long RawHeightHash=0x%016xull;\n'%self.height_hash)
            stream.write('constexpr unsigned long long QuantizeHash=0x%016xull;\n'%self.quantize_hash)
            stream.write('constexpr unsigned QuantizeCases=%du;\n'%self.quantize_cases)
            stream.write('}\n')

    def report(self):
        return dict(original_sha256=self.image.sha,constants=self.constants,
            raw_height_reference='Original scalar opcode DAG with independent IEEE float32 nodes, all65536 inputs',
            raw_height_hash=f'{self.height_hash:016x}',quantize_hash=f'{self.quantize_hash:016x}',
            quantize_cases=self.quantize_cases,
            quantize_reference='Fraction arithmetic on binary32 centered/reference inputs, truncate without copied production code',
            extended_x87_division_cutoff_equivalence=False,
            runtime_metric_override_or_display_origin_proven=False)
