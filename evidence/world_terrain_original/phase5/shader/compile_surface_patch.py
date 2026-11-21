"""Compile only the finite-policy surface patch and reuse four unchanged proofs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('phase5_lighting_shader_contracts', ROOT/'strict_lighting_shader.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
ref, write_new = h.ref, h.write_new


def load_old():
    path = ROOT/'attempt01/result.json'
    result = json.loads(path.read_text('utf8'))
    assert result['status'] == 'PASS_STRICT_PHASE5_LIGHTING_SHADER_ABI'
    for row in result['fixed_inputs'] + result['extra_fixed_inputs']:
        if row['path'] != str(h.base.SURFACE):
            assert ref(row['path']) == row, 'An input to the reused terrain/legacy proof changed: '+row['path']
    assert ref(result['compiler']['path']) == result['compiler']
    assert h.base.digest(h.base.literal(h.RENDERER)) == result['literal_sha256']['legacy']
    assert h.base.digest(h.base.literal(h.base.TERRAIN)) == result['literal_sha256']['terrain']
    return path, result


def seal():
    path = ROOT/'current.json'
    current = json.loads(path.read_text('utf8'))
    assert current['status'] == 'PASS_SIX_CURRENT_SHADER_STAGES_WITH_TWO_SURFACE_PATCH_COMPILES'
    assert all(ref(row['path']) == row for row in current['fixed_inputs'])
    review_path = ROOT.parent/'review/integration_review.json'
    review = json.loads(review_path.read_text('utf8'))
    assert not review['blocking_findings'] and review['source_files_unchanged_during_review']
    rows = list(review['source_files_after'].values())
    for row in rows:
        assert ref(row['path'])['sha256'] == row['sha256']
    assert any(row['path'] == str(h.RENDERER) for row in rows)
    assert h.base.digest(h.base.literal(h.RENDERER)) == current['literal_sha256']['legacy']
    value = dict(status='PASS_PHASE5_FINAL_SHADER_SOURCE_SEAL', current_result=ref(path),
        integration_review=ref(review_path), renderer=ref(h.RENDERER), source_files=rows,
        fixed_inputs=current['fixed_inputs'], host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(ROOT/'source_seal.json', value)
    print(json.dumps(dict(status=value['status'], source_seal=ref(ROOT/'source_seal.json'))))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--seal', action='store_true')
    args = cli.parse_args()
    if args.seal:
        seal()
        return
    old_path, old = load_old()
    stage = ROOT/'attempt02'
    assert not stage.exists(), 'Inspect the owned patch attempt before retrying'
    shaders = dict(surface=h.base.literal(h.base.SURFACE), terrain=h.base.literal(h.base.TERRAIN), legacy=h.base.literal(h.RENDERER))
    hashes = {k: h.base.digest(v) for k, v in shaders.items()}
    checks = h.source_contracts(shaders)
    surface = shaders['surface']
    checks.update(gaussian_result_finite_policy='return isfinite(result)?result:0;' in surface,
        cubic_overflow_policy='if(!isfinite(qCubed))qCubed=0;' in surface,
        lighting_overflow_policy='if(!all(isfinite(lit)))lit=deep.rgb;' in surface)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    paths = [h.base.SURFACE, h.base.TYPES, h.base.TERRAIN, h.base.TERRAIN_TYPES,
             Path(__file__).resolve(), ROOT/'strict_lighting_shader.py'] + h.EXTRA
    fixed = [ref(p) for p in dict.fromkeys(paths)]
    compiler = old['compiler']
    stage.mkdir()
    write_new(stage/'started.json', dict(fixed_inputs=fixed, compiler=compiler,
        source_checks=checks, reused_result=ref(old_path), literal_sha256=hashes))
    owned, passes = [], []
    inputs_unchanged = False
    try:
        source = stage/'surface.hlsl'
        source.write_bytes(surface.encode('ascii'))
        owned.append(source)
        for entry, profile in [('vertexMain', 'vs_5_0'), ('pixelMain', 'ps_5_0')]:
            key = 'surface_'+profile
            bytecode, listing = stage/(key+'.cso'), stage/(key+'.asm')
            owned += [bytecode, listing]
            cmd = [compiler['path'], '/nologo', '/Ges', '/WX', '/T', profile, '/E', entry,
                   '/Fo', str(bytecode), '/Fc', str(listing), str(source)]
            done = subprocess.run(cmd, cwd=stage, capture_output=True, timeout=30,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            raw_log = done.stdout+done.stderr
            log = raw_log.decode('mbcs', errors='replace')
            log_path = stage/(key+'_compiler.txt')
            log_path.write_text(log[:4000], encoding='utf8')
            row = dict(stem='surface', entry=entry, profile=profile, command=cmd, exit_code=done.returncode,
                log=ref(log_path), complete_log_bytes=len(raw_log), complete_log_sha256=hashlib.sha256(raw_log).hexdigest(),
                compiler_warning='warning' in log.lower())
            if bytecode.exists():
                row['bytecode'] = ref(bytecode)
            if listing.exists() and bytecode.exists():
                row['listing'] = ref(listing)
                row['reflection'] = h.reflection(listing.read_text('utf8'), 'surface', profile, bytecode.read_bytes())
            passes.append(row)
    finally:
        inputs_unchanged = all(ref(r['path']) == r for r in fixed) and ref(compiler['path']) == compiler
        files = [ref(p) for p in owned if p.exists()]
        for row in files:
            p = Path(row['path'])
            assert p.resolve().parent == stage.resolve() and row['links'] == 1 and not row['file_attributes'] & 0x401
            assert ref(p) == row
        write_new(stage/'cleanup_plan.json', dict(files=files, protected_inputs=fixed, exact_leaf_only=True))
        for row in files:
            p = Path(row['path'])
            assert ref(p) == row
            p.unlink()
        write_new(stage/'cleanup_result.json', dict(status='PASS_EXACT_SURFACE_PATCH_INTERMEDIATES_REMOVED',
            files=files, deleted_files=len(files), released_unique_allocated_bytes=sum(r['allocated_bytes'] for r in files),
            all_absent=all(not Path(r['path']).exists() for r in files)))
    passed = inputs_unchanged and len(passes) == 2 and all(r['exit_code'] == 0 and not r['compiler_warning']
        and r.get('reflection') and all(r['reflection']['checks'].values()) for r in passes)
    result = dict(schema='zerosis.original_lighting.phase5.surface_finite_patch.v1',
        status='PASS_TWO_STRICT_SURFACE_FINITE_POLICY_COMPILES' if passed else 'FAIL_SURFACE_PATCH',
        fixed_inputs=fixed, inputs_unchanged=inputs_unchanged, compiler=compiler, source_checks=checks,
        literal_sha256=hashes, passes=passes, reused_result=ref(old_path), cleanup=ref(stage/'cleanup_result.json'),
        finite_policy='Invalid determinant/q or overflowed Gaussian/cubic/composite values use explicit safe fallback outside the original valid domain. Finite q>=16 remains unmasked for the original cubic depth term.',
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(stage/'result.json', result)
    assert passed, 'See patch result; no source seal was written'
    reused = [dict(row, proof=ref(old_path)) for row in old['passes'] if row['stem'] in ('terrain', 'legacy')]
    current_passes = [dict(row, proof=ref(stage/'result.json')) for row in passes] + reused
    assert len(current_passes) == 6
    current = dict(schema='zerosis.original_lighting.phase5.current_shader_proof.v1',
        status='PASS_SIX_CURRENT_SHADER_STAGES_WITH_TWO_SURFACE_PATCH_COMPILES', fixed_inputs=fixed,
        literal_sha256=hashes, source_checks=checks, passes=current_passes,
        original_result=ref(old_path), surface_patch=ref(stage/'result.json'),
        actual_shader_compile_count_this_phase=8, reused_unchanged_stages=4, unnecessary_recompilations=0,
        compiler_warnings=0, final_source_seal='PENDING_INDEPENDENT_INTEGRATION_REVIEW',
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(ROOT/'current.json', current)
    write_new(ROOT/'header_seal.json', dict(status='PASS_CURRENT_SHADER_HEADERS_AND_LEGACY_LITERAL',
        current_result=ref(ROOT/'current.json'), fixed_inputs=fixed, literal_sha256=hashes,
        renderer_literal_only=True, full_renderer_integration_seal_pending=True,
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status=current['status'], newly_compiled=2, reused=4, source_checks=len(checks),
        patch_sha256=ref(stage/'result.json')['sha256'], current_sha256=ref(ROOT/'current.json')['sha256'])))


if __name__ == '__main__':
    main()
