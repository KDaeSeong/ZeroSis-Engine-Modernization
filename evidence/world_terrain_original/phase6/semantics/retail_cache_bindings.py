"""Targeted original PE reads and x86 decoding for cache texture data flow.

This does not run retail code or rebuild the historical phase0 probes. The PE
sections are read directly, so pefile is not required. No binary is emitted.
"""
from pathlib import Path
import hashlib
import json
import struct
import capstone

STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
EVIDENCE = PROJECT/'evidence/world_terrain_original'
EXE_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
SOURCE_PATHS = {
 'pipeline': EVIDENCE/'retail_terrain_pipeline_probe.json',
 'registry': EVIDENCE/'retail_renderer_probe.json',
 'shader_semantics': EVIDENCE/'terrain_shader_semantics.json',
 'cache_vs': EVIDENCE/'phase5/semantics/bytecode/CacheBake_0_vs.asm',
 'cache_ps': EVIDENCE/'phase5/semantics/bytecode/CacheBake_0_ps.asm',
 'cache_spec_ps': EVIDENCE/'phase5/semantics/bytecode/CacheBake_1_ps.asm',
 'normal_ps': EVIDENCE/'phase5/semantics/bytecode/NormalCalculate_0_ps.asm',
 'terrain_ps': EVIDENCE/'phase5/semantics/bytecode/TerrainShader_0_ps.asm',
 'self_shadow': EVIDENCE/'phase5/semantics/shadow/TerrainShaderScreen_3_ps.asm',
 'previous_contract': EVIDENCE/'phase5/semantics/lighting_contract.json',
 'composite': STAGE/'composite/result.json',
}


def ref(path):
    path = Path(path)
    data, st = path.read_bytes(), path.stat()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        file_identity=[st.st_dev, st.st_ino], mtime_ns=st.st_mtime_ns,
        file_attributes=getattr(st, 'st_file_attributes', 0), links=st.st_nlink)


before = {k: ref(p) for k, p in SOURCE_PATHS.items()}
old_semantics = json.loads(SOURCE_PATHS['shader_semantics'].read_text('utf8'))
exe = Path(old_semantics['exe']['path'])
exe_before = ref(exe)
assert exe_before['sha256'] == EXE_SHA
raw = exe.read_bytes()
pe = struct.unpack_from('<I', raw, 0x3c)[0]
assert raw[pe:pe+4] == b'PE\0\0'
section_count = struct.unpack_from('<H', raw, pe+6)[0]
optional_size = struct.unpack_from('<H', raw, pe+20)[0]
assert struct.unpack_from('<H', raw, pe+24)[0] == 0x10b
image_base = struct.unpack_from('<I', raw, pe+24+28)[0]
sections = []
for i in range(section_count):
    at = pe+24+optional_size+i*40
    virtual_size, rva, size, offset = struct.unpack_from('<IIII', raw, at+8)
    sections.append(dict(name=raw[at:at+8].rstrip(b'\0').decode('ascii'),
        va=image_base+rva, virtual_bytes=virtual_size, bytes=size, file_offset=offset))


def bytes_at(va, count):
    section = next(s for s in sections if s['va'] <= va < s['va']+s['virtual_bytes'])
    delta = va-section['va']
    assert delta+count <= section['bytes'], 'Selected address must have original file-backed bytes'
    return raw[section['file_offset']+delta:section['file_offset']+delta+count]


decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
RANGES = {
 'texture_creation': (0x67878f, 0x678955),
 'normal_descriptor': (0x515630, 0x5156b5),
 'cache_descriptor': (0x6cf830, 0x6cfa2b),
 'final_descriptor': (0x5ad770, 0x5ad96a),
 'chunk_prepare': (0x694a60, 0x694c5e),
 'material_mrt': (0x694da5, 0x694e30),
 'material_draw': (0x6956bb, 0x6956f4),
 'normal_setup_and_draw': (0x6958fe, 0x6959bd),
 'macro_shadow_draw': (0x6959bd, 0x695b93),
 'cache_mrt_draw': (0x695c30, 0x695d24),
 'final_callers': (0x691048, 0x691092),
 'rt_record': (0x8ccfb0, 0x8cd046),
 'mrt_wrapper': (0x8cd7a0, 0x8cd824),
 'queue_draw': (0x8ccd80, 0x8ccdfe),
}
blocks, rows = {}, {}
for name, (start, stop) in RANGES.items():
    data = bytes_at(start, stop-start)
    instructions = list(decoder.disasm(data, start))
    assert instructions and instructions[0].address == start
    rows[name] = instructions
    blocks[name] = dict(start=f'{start:08x}', stop=f'{stop:08x}', bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(), decoded_instructions=len(instructions))
checks = []


def require(name, block, needles):
    pos, found = 0, []
    for needle in needles:
        candidates = [(n, i) for n, i in enumerate(rows[block]) if n >= pos and f'{i.mnemonic} {i.op_str}' == needle]
        assert candidates, (name, needle)
        n, ins = candidates[0]
        found.append(dict(address=f'{ins.address:08x}', instruction=needle))
        pos = n+1
    checks.append(dict(name=name, block=block, pass_=True, matched=found))


require('physical-height-normal-shadow-target-creation', 'texture_creation', [
 'push 0xa293f0', 'mov dword ptr [ebx + 0x69c], eax',
 'push 0xa29418', 'push 0xa2942c', 'mov dword ptr [ebx + 0x6a0], eax',
 'mov dword ptr [ebx + 0x6a8], eax'])
require('chunk-stable-local-handles', 'chunk_prepare', [
 'mov esi, dword ptr [eax + 0x6a0]', 'mov ebx, dword ptr [eax + 0x68c]',
 'mov dword ptr [esp + 0x58], esi', 'mov dword ptr [esp + 0x6c], ebx',
 'mov ebx, dword ptr [eax + 0x694]', 'mov dword ptr [esp + 0x3c], ebx',
 'mov eax, dword ptr [eax + 0x698]', 'mov dword ptr [esp + 0x44], eax'])
require('same-height-handle-in-normal-descriptor-call', 'chunk_prepare', [
 'mov edx, dword ptr [esp + 0x3c]', 'push edx', 'lea eax, [esp + 0x78]', 'push eax', 'call 0x515630'])
require('normal-descriptor-duplicates-height-in-first-two-bindings', 'normal_descriptor', [
 'push 0x4a', 'call 0x8c69b0', 'mov eax, dword ptr [esp + 0x10]',
 'mov word ptr [edx + 0x18], ax', 'mov word ptr [edx + 0x1a], ax'])
require('material-mrt-source0-diffuse-source1-height', 'material_mrt', [
 'mov ecx, dword ptr [esp + 0x5c]', 'mov eax, dword ptr [esp + 0x68]',
 'push eax', 'push ecx', 'push ebx', 'call 0x8cd7a0'])
require('material-shader-pass1-or2-queued', 'material_draw', [
 'mov eax, dword ptr [edx + 0x59c]', 'push 1', 'push eax', 'push ecx', 'call 0x8ccd80',
 'push 2', 'push eax', 'push ecx', 'call 0x8ccd80'])
require('normal-runtime-cardinal-offset-and-strength16', 'normal_setup_and_draw', [
 'mov ecx, dword ptr [0x2de04d0]', 'call 0x597520',
 'movss xmm0, dword ptr [0x9efba8]', 'movss dword ptr [eax + 0x10], xmm0',
 'divss xmm0, dword ptr [esp + 0x34]', 'divss xmm1, dword ptr [esp + 0x68]',
 'movss dword ptr [eax + 4], xmm0', 'xorps xmm0, xmm0',
 'movss dword ptr [eax], xmm1', 'movss dword ptr [eax + 8], xmm0'])
require('normal-pass0-source-and-target', 'normal_setup_and_draw', [
 'push 0xa296e0', 'mov eax, dword ptr [esp + 0x84]', 'push eax', 'call 0x8cd6a0',
 'mov edx, dword ptr [ecx + 0x5fc]', 'push 0', 'mov eax, dword ptr [esp + 0x78]',
 'push edx', 'push eax', 'call 0x8ccd80'])
require('macro-shadow-source-and-pass3', 'macro_shadow_draw', [
 'mov ecx, dword ptr [esp + 0x44]', 'push 0xa296f4', 'push ecx', 'call 0x8cd6a0',
 'mov eax, dword ptr [edx + 0x59c]', 'push 3', 'push eax', 'push ecx', 'call 0x8ccd80'])
require('cache-arguments-forwarded-with-same-handles', 'chunk_prepare', [
 'mov ecx, dword ptr [esp + 0x40]', 'mov edx, dword ptr [esp + 0x44]',
 'mov eax, dword ptr [esp + 0x48]', 'mov ebx, dword ptr [esp + 0x6c]',
 'push ecx', 'mov ecx, dword ptr [esp + 0x5c]', 'push edx', 'push eax', 'push ebx', 'push ecx',
 'lea edx, [esp + 0x4c]', 'push edx', 'call 0x6cf830'])
require('cache-input-slot-order', 'cache_descriptor', [
 'mov dx, word ptr [esp + 0xc]', 'mov word ptr [ecx + 0x18], dx',
 'mov dx, word ptr [esp + 0x10]', 'mov word ptr [ecx + 0x1a], dx',
 'mov dx, word ptr [esp + 0x18]', 'mov word ptr [ecx + 0x1c], dx',
 'mov dx, word ptr [esp + 0x14]', 'mov word ptr [ecx + 0x1e], dx'])
require('cache-mrt1-specular-target', 'cache_mrt_draw', [
 'mov ecx, dword ptr [ebp + 0x194]', 'mov edx, dword ptr [ebp + 0x190]',
 'push ecx', 'push edx', 'call 0x8cd7a0', 'mov ecx, dword ptr [eax + 0x62c]',
 'push 1', 'push ecx', 'push edx', 'call 0x8ccd80'])
require('final-slot0-argument2', 'final_descriptor', [
 'mov di, word ptr [esp + 0x10]', 'mov word ptr [eax + 0x18], di'])
require('final-slot8-argument3', 'final_descriptor', [
 'push ebx', 'mov di, word ptr [esp + 0x18]', 'mov word ptr [eax + 0x28], di'])
require('final-specular-pair-provider', 'final_callers', [
 'mov eax, dword ptr [esi + 0x19c]', 'mov ecx, dword ptr [esi + 0x198]',
 'push eax', 'push ecx', 'call 0x5ad770',
 'mov eax, dword ptr [esi + 0x194]', 'mov ecx, dword ptr [esi + 0x190]',
 'push eax', 'push ecx', 'call 0x5ad770'])
require('rt-record-keeps-first-and-second-target-order', 'rt_record', [
 'mov esi, dword ptr [esp + 0x10]', 'mov dword ptr [eax + edx + 0x14], esi',
 'mov eax, dword ptr [esp + 0x14]', 'mov dword ptr [edx + esi + 0x18], eax'])

pipeline = json.loads(SOURCE_PATHS['pipeline'].read_text('utf8'))
screen = next(v for v in pipeline['effect_records']['effects'].values() if v['name'] == 'TerrainShaderScreen')
assert screen['passes'][1]['ps']['sm5']['sha256'] == screen['passes'][2]['ps']['sm5']['sha256']
assert screen['passes'][1]['ps']['sm5']['sha256'] == '9b6410c808c30199badc546aeed70574c8624504ae9a6bfdafaaf80c55eed259'
screen_semantics = next(r for r in old_semantics['shaders'] if r['effect'] == 'TerrainShaderScreen' and r['pass_index'] == 1 and r['slot'] == 'ps')
assert screen_semantics['status'] == 'PASS'
cache_vs = SOURCE_PATHS['cache_vs'].read_text('utf8')
cache_ps = SOURCE_PATHS['cache_ps'].read_text('utf8')
terrain_ps = SOURCE_PATHS['terrain_ps'].read_text('utf8')
assert '// NORMAL                   0   xyz         1' in cache_vs and 'mov o1.xyz, v1.xyzx' in cache_vs
assert 'sample_indexable(texture2d)(float,float,float,float) r2.xyz, v2.xyxx, t0.xyzw, s0' in cache_ps
assert 'mad r0.xyz, r2.zzzz, v1.xyzx, r0.xyzx' in cache_ps
assert 'sample_indexable(texture2d)(float,float,float,float) r0.yzw, v2.xyxx, t8.wxyz, s8' in terrain_ps
strength_bits = struct.unpack('<I', bytes_at(0x9efba8, 4))[0]
assert strength_bits == 0x41800000
after = {k: ref(p) for k, p in SOURCE_PATHS.items()}
assert before == after and ref(exe) == exe_before
result = dict(schema='zerosis.original_detail.phase6.cache_input_and_specular_consumer.v1',
 status='PASS_TARGETED_ORIGINAL_CACHE_BINDING_AND_FINAL_SPECULAR_CONSUMER_TRACE',
 exe=exe_before, tool=dict(capstone=capstone.__version__, python_binding=ref(Path(capstone.__file__)),
                         native_decoder=ref(Path(capstone._cs._name)), pefile_required=False),
 inputs_before=before, inputs_after=after, blocks=blocks, checks=checks,
 confirmed_connections={
  'normal_source': 'TerrainShaderScreen pass1/2 MRT1 is mixed material height. The same RT handle is forwarded to NormalCalculate descriptor entries0/1 and its actual pass0 draw.',
  'normal_offsets_strength': 'Normal cb1[0]=(1/width,1/height,0,unused), cb1[1].x=16.0 in this original call path.',
  'base_vs_normal': 'CacheBake VS NORMAL0 input v1 passes unchanged to o1/PS v1. The sampled Sobel/encoded detail normal is separately PS t0.rgb. The original CPU source of NORMAL0 is not established here.',
  'cache_inputs': 'CacheBake t0=NormalCalculate output, t1=mixed diffuse, t2.R=Macro Shadow (TerrainShaderScreen pass3 40-step self-shadow), t3=mixed specular in this cache path.',
  'cache_output1': 'CacheBake pass1 is queued with chunk+190 as output0 and chunk+194 as output1; original shader output1 is gamma/LUT specular RGB with separately scaled alpha.',
  'final_specular_consumer': 'TerrainShader descriptor entry8 receives argument3; raw cache path supplies chunk+194, the same CacheBake output1. Paired retained path supplies chunk+19c alongside diffuse+198.',
  'final_formula_correction': 'Final PS t8 is the baked specular cache in these actual descriptor providers, not the albedo cache inferred earlier. C=encode(decode(specularCache)*screenLight[t9]+decode(diffuseEnabled?litCache:0)) when cb1[27].x; otherwise C=diffuseEnabled?litCache:0.',
 },
 stable_chunk_stack=dict(note='Offsets are relative to the fixed ESP after the chunk function prologue; transient pushes are normalized in each call proof.',
  material_height_rt='local+3c <- Terrain+694', macro_shadow_rt='local+44 <- Terrain+698',
  mixed_specular_rt='local+48 <- Terrain+690 or null', normal_output_rt='local+58 <- Terrain+6a0',
  mixed_diffuse_rt='local+6c <- Terrain+68c', normal_descriptor='local+74', cache_descriptor='local+38'),
 descriptor_arguments={
  '0x515630': {'effect': '0x4a NormalCalculate', 'entry0/1': 'argument2'},
  '0x6cf830': {'effect': '0x4b CacheBake', 'entry0': 'argument2', 'entry1': 'argument3', 'entry2': 'argument5', 'entry3': 'argument4'},
  '0x5ad770': {'effect': '0x49 TerrainShader', 'entry0': 'argument2', 'entry8': 'argument3', 'entry9': 'Terrain+564 screen-space input'},
 },
 new_constants=dict(sobel_strength=dict(va='009efba8', bits='0x41800000', value=16.0),
                    normal_offset_z=0.0),
 interpretation_revision=dict(previous_evidence_modified=False,
  corrected_claims=['Phase0/phase5 final t8 albedo interpretation is superseded by actual descriptor-provider trace.',
                    'Material-height→NormalCalculate and 40step self-shadow→CacheBake are no longer unsupported binding guesses for this traced path.']),
 remaining_unknowns=[
  'Original CPU NORMAL0 generator, cache dimensions/resampling/precision/mip policy, sampler settings and frame scheduling.',
  'Original screen-light t9 producer, actual values and enables cb1[27]/[28]; neutral1 light is a current candidate, not a recovered runtime constant.',
  'Complete packed-cache compression equivalence and all lower-detail/special-case consumers; the direct raw CacheBake output1→final descriptor entry8 path is proven.',
  'Original external OM blend descriptors. Composite pass0 only copies one RGBA sample; this does not establish an additive hardware blend state.',
  'Dynamic scene shadows beyond the separately traced 40step terrain self-shadow, current atlas raw/world conversion and unknown-ray safety policy.',
 ],
 speculative_paths_excluded=['Same numeric offsets in the unrelated 0x80f SV_Rivers/SV_Hills texture owner were rejected; creation names alone were not used to infer pass contents.'],
 binaries_created_by_this_probe=0, original_code_loaded_or_executed=False,
 host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
out = STAGE/'retail_cache_bindings.json'
with out.open('x', encoding='utf8') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(dict(status=result['status'], checks=len(checks), selected_code_blocks=len(blocks),
    bytes=out.stat().st_size, sha256=hashlib.sha256(out.read_bytes()).hexdigest())))
