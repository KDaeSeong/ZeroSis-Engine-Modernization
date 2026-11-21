"""Close the screen-reflection RT provider and renderer-local option rules."""
from pathlib import Path
import hashlib
import json
import struct
import capstone
import screen_contract_pe as previous

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]


def main():
    old = json.loads((STAGE / "screen_contract_pe.json").read_text("utf8"))
    exe = Path(old["exe"]["path"])
    before = previous.artifact(exe)
    assert before == old["exe"]
    raw = exe.read_bytes()
    pe = struct.unpack_from("<I", raw, 60)[0]
    base = struct.unpack_from("<I", raw, pe + 52)[0]
    opt = struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(struct.unpack_from("<H", raw, pe + 6)[0]):
        at = pe + 24 + opt + i * 40
        v, r, n, o = struct.unpack_from("<IIII", raw, at + 8)
        sections.append((base + r, v, n, o))
    def data(va, n):
        s = next(s for s in sections if s[0] <= va < s[0] + s[1])
        assert va - s[0] + n <= s[2]
        return raw[s[3] + va - s[0]:s[3] + va - s[0] + n]
    def cstr(va):
        return data(va, 128).split(b"\0")[0].decode("ascii")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ranges = {
        "bulk_copy": (0x6782cf, 0x678303),
        "caller_one": (0x5bcf43, 0x5bcf66),
        "caller_two": (0x60fe88, 0x60fea7),
        "reflection_creation": (0x5f0a33, 0x5f0ac8),
        "reflection_clear_and_scene": (0x5a0f80, 0x5a1058),
        "reflection_setting": (0x5d8d76, 0x5d8da1),
        "terrain_setting": (0x5d8df7, 0x5d8e22),
        "specular_default": (0x6b840a, 0x6b842e),
    }
    blocks = {}
    for name, (start, stop) in ranges.items():
        source = data(start, stop - start)
        rows = list(md.disasm_lite(source, start))
        assert rows and sum(r[1] for r in rows) == len(source), name
        blocks[name] = dict(start=f"{start:08x}", stop=f"{stop:08x}",
            bytes=len(source), sha256=hashlib.sha256(source).hexdigest(),
            instructions=[dict(va=f"{a:08x}", mnemonic=m, operands=o) for a, n, m, o in rows])
    checks = []
    def require(name, key, snippets):
        rows = [r["mnemonic"] + " " + r["operands"] for r in blocks[key]["instructions"]]
        assert all(s in rows for s in snippets), (name, rows)
        checks.append(dict(name=name, block=key, snippets=snippets))
    require("source_arg3_copied_to_owner548", "bulk_copy", [
        "mov esi, dword ptr [ebp + 0x10]", "lea edi, [ebx + 0x548]",
        "mov ecx, 0xa", "rep movsd dword ptr es:[edi], dword ptr [esi]"])
    require("source_array_first_actual_call", "caller_one", [
        "push 0xda12a4", "call 0x678290"])
    require("source_array_second_actual_call", "caller_two", [
        "push 0xda12a4", "call 0x678290"])
    assert 0x564 - 0x548 == 0x1c and 0xda12a4 + 0x1c == 0xda12c0
    require("reflection_rt_creation_and_global", "reflection_creation", [
        "mov eax, dword ptr [0xd90f98]", "mov eax, 0x400", "push 0xa28cd8",
        "push 0x102", "call 0x8c6650", "mov dword ptr [0xda12c0], eax"])
    require("reflection_clear_and_four_scene_masks", "reflection_clear_and_scene", [
        "push 0xa1fa54", "xorps xmm0, xmm0", "mov eax, dword ptr [0xda12c0]",
        "call 0x8cd6a0", "call 0x609730", "call 0x6ec630",
        "call 0x69e5b0", "call 0x751f30"])
    require("reflection_quality_key", "reflection_setting", [
        "push 0xd90f98", "push 0xa1b5fc"])
    require("terrain_quality_key", "terrain_setting", [
        "push 0xd90f74", "push 0xa1b6b4"])
    require("specular_only_for_detail3", "specular_default", [
        "cmp dword ptr [0xd90f74], 3", "sete al", "mov byte ptr [esi + 0x75fd9], al"])
    assert cstr(0xa28cd8) == "Reflection Texture Raw"
    assert cstr(0xa1fa54) == "Clear Reflections"
    assert cstr(0xa1b5fc) == "ReflectionLevel"
    assert cstr(0xa1b6b4) == "TerrainDetailLevel"
    assert cstr(0xa1b5dc) == "Reflection Quality (0 = off)"
    vs = PROJECT / "evidence/world_terrain_original/phase2/model/bytecode/TerrainShader_3_vs.asm"
    text = vs.read_text("utf8")
    assert "mov o0.xyzw, r1.xyzw" in text
    assert "div o5.xy, r1.xyxx, r1.wwww" in text
    assert previous.artifact(exe) == before
    result = dict(schema=1, status="PASS_ORIGINAL_REFLECTION_RT_TO_FINAL_T9_AND_LOCAL_POLICY",
        exe=before, source=previous.artifact(__file__),
        earlier_partial=previous.artifact(STAGE / "screen_contract_pe.json"),
        blocks=blocks, checks=checks, non_tessellated_vs=previous.artifact(vs),
        confirmed=[
            "Final t9 = owner+564 = sourceArray+1c = globalda12c0.",
            "globalda12c0 is Reflection Texture Raw, created1024x1024 for ReflectionLevel1 and enabled water technique.",
            "ReflectionLevel is the original graphics key bound to globald90f98; TerrainDetailLevel is bound to globald90f74.",
            "Diffuse starts enabled; specular starts enabled only when TerrainDetailLevel3. Debug overrides subsequently update cb28/cb27.",
            "The reflection buffer is cleared to zero colour before four separately gated scene-class draw callbacks.",
            "UV from VS3 clip.xy/clip.w to PS0 .5*value+.5 is equivalent to pixel.x/viewportWidth,1-pixel.y/viewportHeight."],
        superseded_inference=[
            "specscreenmap.dds(globalda12c8) maps to owner+56c, not the final t9 owner+564. No asset pack should be created for that inference.",
            "A neutral1 screen-light value is not the recovered provider; final t9 consumes the reflection buffer sample."],
        policy_scope="Renderer-local copy of original rules only; original INI/settings/save schema are not read or changed.",
        candidates=[
            "Current two-draw isolated planar reflection producer does not reproduce all four original scene callbacks.",
            "Actual original reflection camera/clip plane and RTV/SRV normal-vs-sRGB selection are not yet traced.",
            "Current encoded UNORM reflection SRV is explicitly gamma-decoded by a candidate producer adapter; the exact original consumer itself adds no gamma decode.",
            "Current clamp-linear sampler and disabled-target allocation elision are safety/storage choices."],
        original_asset_packs_added=0, original_asset_payload_copied=0,
        old_sources_or_settings_modified=False, native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    with (STAGE / "screen_provider_contract.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(json.dumps(dict(status=result["status"], checks=len(checks),
                         output=str(STAGE / "screen_provider_contract.json"))))


if __name__ == "__main__":
    main()
