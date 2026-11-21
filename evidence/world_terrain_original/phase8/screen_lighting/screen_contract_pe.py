"""Bounded, read-only original screen-specular consumer and debug-gate proof."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import capstone

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / "tools"))
from civ5_ui_assets import Fpk


def artifact(path):
    path = Path(path)
    before = path.stat()
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            before.st_file_attributes, before.st_nlink) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
            after.st_file_attributes, after.st_nlink)
    return dict(path=str(path), bytes=after.st_size, sha256=digest,
                file_identity=[after.st_dev, after.st_ino], mtime_ns=after.st_mtime_ns,
                file_attributes=after.st_file_attributes, links=after.st_nlink)


def main():
    prior_path = PROJECT / "evidence/world_terrain_original/phase6/semantics/retail_cache_bindings.json"
    prior = json.loads(prior_path.read_text("utf8"))
    exe = Path(prior["exe"]["path"])
    exe_before = artifact(exe)
    assert exe_before["sha256"] == "b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818"
    raw = exe.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3c)[0]
    assert raw[pe:pe + 4] == b"PE\0\0" and struct.unpack_from("<H", raw, pe + 24)[0] == 0x10b
    count, opt = struct.unpack_from("<H", raw, pe + 6)[0], struct.unpack_from("<H", raw, pe + 20)[0]
    base = struct.unpack_from("<I", raw, pe + 52)[0]
    sections = []
    for index in range(count):
        at = pe + 24 + opt + index * 40
        virtual, rva, size, offset = struct.unpack_from("<IIII", raw, at + 8)
        sections.append((base + rva, virtual, size, offset))

    def bytes_at(va, length):
        section = next(s for s in sections if s[0] <= va < s[0] + s[1])
        delta = va - section[0]
        assert 0 <= delta and delta + length <= section[2]
        return raw[section[3] + delta:section[3] + delta + length]

    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ranges = {
        "final_t9_descriptor": (0x5ad91e, 0x5ad940),
        "debug_registration": (0x79c760, 0x79c7ac),
        "diffuse_specular_debug_callback": (0x4791b8, 0x479213),
        "terrain_policy_setter": (0x6ada40, 0x6adaa1),
        "final_gate_constant_writes": (0x6ae1fb, 0x6ae230),
        "diffuse_default_true": (0x733aee, 0x733afd),
        "named_asset_load": (0x561a22, 0x561a47),
        "named_asset_load_alternative": (0x709b9a, 0x709bc5),
    }
    blocks = {}
    for name, (start, stop) in ranges.items():
        data = bytes_at(start, stop - start)
        instructions = list(decoder.disasm_lite(data, start))
        assert instructions and sum(r[1] for r in instructions) == len(data), name
        blocks[name] = dict(start=f"{start:08x}", stop=f"{stop:08x}",
            bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
            instructions=[dict(va=f"{va:08x}", mnemonic=mnemonic, operands=operands)
                          for va, size, mnemonic, operands in instructions])

    checks = []
    def require(name, block, snippets):
        text = [r["mnemonic"] + " " + r["operands"] for r in blocks[block]["instructions"]]
        assert all(s in text for s in snippets), (name, text)
        checks.append(dict(name=name, block=block, snippets=snippets))

    require("final_entry9_reads_owner_handle", "final_t9_descriptor", [
        "mov eax, dword ptr [esi + 0x13c]", "movzx eax, word ptr [eax + 0x564]",
        "mov word ptr [edi + 0x2a], ax"])
    require("debug_flags_forwarded", "diffuse_specular_debug_callback", [
        "mov byte ptr [esi + 0x75fd8], al", "mov byte ptr [esi + 0x75fd9], al",
        "call 0x6ada40"])
    require("policy_fields", "terrain_policy_setter", [
        "mov edx, dword ptr [esp + 0x20]", "mov eax, dword ptr [esp + 0x24]",
        "mov dword ptr [ecx + 0x2418], edx", "mov dword ptr [ecx + 0x241c], eax"])
    require("cb28_diffuse_cb27_specular", "final_gate_constant_writes", [
        "cmp dword ptr [ebp + 0x2418], 0", "cmp dword ptr [ebp + 0x241c], 0",
        "movss dword ptr [ebx + 0x1c0], xmm1", "movss dword ptr [ebx + 0x1b0], xmm0"])
    require("named_asset_global", "named_asset_load", [
        "push 0xa3d3d4", "call 0x8c6540", "mov dword ptr [0xda12c8], eax"])
    asset_name = b"assets\\terrain\\lighting\\specscreenmap.dds"
    assert bytes_at(0xa3d3d4, len(asset_name)) == asset_name
    assert struct.unpack("<4I", bytes_at(0xb99aec, 16))[:2] == (0xa28020, 0xa27ff8)
    assert bytes_at(0xa28020, 38).split(b"\0")[0] == b"DebugMenu/Terrain_Panel/ToggleDiffuse"
    assert bytes_at(0xa27ff8, 39).split(b"\0")[0] == b"DebugMenu/Terrain_Panel/ToggleSpecular"
    shader = PROJECT / "evidence/world_terrain_original/phase5/semantics/bytecode/TerrainShader_0_ps.asm"
    text = shader.read_text("utf8")
    for snippet in [
        "mad r1.xy, v5.xyxx, l(0.500000, 0.500000, 0.000000, 0.000000), l(0.500000, 0.500000, 0.000000, 0.000000)",
        "sample_indexable(texture2d)(float,float,float,float) r1.xyz, r1.xyxx, t9.xyzw, s9",
        "movc r2.xyz, cb1[28].xxxx, r2.xyzx, l(0,0,0,0)",
        "movc r0.yzw, cb1[27].xxxx, r0.yyzw, r2.xxyz"]:
        assert snippet in text
    pack_path = exe.parent / "Resource/DX9/TerrainTextures.fpk"
    pack_stat = pack_path.stat()
    pack = Fpk(pack_path)
    dds, source = pack.read("specscreenmap.dds")
    assert source["sha256"] == "6f29e8b9c71a8e7ec4dd2983ac5fd46f45938635ec2bd2d1c113a6f40bc1455f"
    assert dds[:4] == b"DDS " and dds[84:88] == b"DXT5"
    assert struct.unpack_from("<II", dds, 12) == (1024, 1024)
    assert artifact(exe) == exe_before
    result = dict(schema=1, status="PASS_SCREEN_CONSUMER_DEBUG_POLICY_AND_NAMED_ASSET_LOAD_PARTIAL",
        exe=exe_before, source=artifact(__file__), previous_contract=artifact(prior_path),
        final_pixel_shader=artifact(shader), capstone=capstone.__version__, blocks=blocks,
        checks=checks, asset=dict(**source, height=1024, width=1024,
            mip_count=struct.unpack_from("<I", dds, 28)[0], format="BC3_UNORM",
            pack_file_identity=[pack_stat.st_dev, pack_stat.st_ino],
            pack_mtime_ns=pack_stat.st_mtime_ns, raw_asset_written=False),
        confirmed=[
            "Final t9 is sampled at uv = 0.5 * TEXCOORD3 + 0.5 and multiplies decoded baked specular.",
            "Debug ToggleDiffuse is callback case1 -> policy field2418 -> cb1[28]; ToggleSpecular is case2 -> field241c -> cb1[27].",
            "Both settings are renderer-local policy fields; they are not original user settings files.",
            "A 1024x1024 BC3 specscreenmap DDS is loaded by original code into globalda12c8."],
        remaining_unknowns=[
            "The named DDS load/globalda12c8 to descriptor-owner handle564 edge remains unproven.",
            "Actual original specular default, sampler state, view-coordinate production and mip/sRGB policy require follow-up."],
        old_sources_or_settings_modified=False, native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    with (STAGE / "screen_contract_pe.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(json.dumps(dict(status=result["status"], checks=len(checks), asset_bytes=len(dds),
                         output=str(STAGE / "screen_contract_pe.json"))))


if __name__ == "__main__":
    main()
