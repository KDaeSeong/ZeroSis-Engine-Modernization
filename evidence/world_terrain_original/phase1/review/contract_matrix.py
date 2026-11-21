"""Freeze the independent phase-1 acceptance matrix from read-only phase-0 evidence."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
REVIEW=Path(__file__).absolute().parent
STAGE=REVIEW.parents[1]
PROJECT=STAGE.parents[1]

def ref(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    rows=[
        ('G01','Global grid','Share continuous heightfield vertices across hex boundaries; keep the source field at 64 texels per hex. Any draw LOD or unresolved tessellation basis remains explicitly candidate.',
         'CPU: adjacent chunk edge samples agree; texel-to-cube examples (0,0),(64,64),(128,128); no per-tile fan reset.'),
        ('G02','Coordinate basis','Convert the renderer Y-up position/normal into the original Z-up basis before projection selection and UV construction; keep original UV units separate from compact camera tile units.',
         'CPU: flat up selects projection0, two vertical normals choose1/2; UV mode0 scale0.33 and modes1/2 scale0.66.'),
        ('M01','Map cells','Use only terrain/hills/mountain/natural-wonder gate for the terrain bit. Water/missing plot continent is0; ordinary unknown features do not get the natural-wonder fallback.',
         'CPU: all terrain and wonder exceptions; forest/jungle/marsh/ice leave bit unchanged; unknown natural wonder->Fuji, unknown ordinary feature->base.'),
        ('M02','Negative rows','Use floor(Y/2), matching arithmetic shift, for signed offset/cube coordinates including candidate rows -2 and -1.',
         'CPU: roundtrip offset/cube for negative and positive odd/even rows.'),
        ('R01','Local random stream','Use private uint32 MSVCR90 state seeded by detached mapRandomSeed; do not call std::rand or SDK gameplay RNG. Shuffler range reduction and permutation reuse must follow actual helper evidence.',
         'CPU: fixed stream and permutation vectors; compare helper stride4/stride12 behavior and bound beyond32767; record remaining virtual-call RNG uncertainty.'),
        ('P01','Placement','Visit levels4->1, shuffled outside-map positions, pieces and four orientations. Ignore off-map cells. Reject continent mismatch only inside the both-masks-nonzero branch; require an on-map owned cell and no claimed owned overlap.',
         'CPU: wildcard/zero masks, zero continents, wrong continent, claimed ownership, fully off-map candidates, deterministic same seed.'),
        ('P02','Direction uncertainty','Preserve the four proved permutations/translations but do not promote the unresolved multiplication order to proved placement equivalence.',
         'Report exactly: 규칙 동등, 배치 동등은 미검증. Actual retail layout comparison is deferred.'),
        ('S01','Stamping','Use TerrainDef row indices from T1. ID changes only when T_BLEND is strictly greater, so equal blends keep the earlier stamp. Height uses H_BLEND weighted average; initialize ID3 and weight sum1e-6.',
         'CPU: greater/equal/zero blend, overlapping weighted heights, row-vs-ID counterexample, explicit height offset/world-scale parameters.'),
        ('B01','Kernel/chunk slots','Use the normalized outer product of (0.125,0.6360560059547424,1,0.6360560059547424,0.125); wrap global texel edges. Count a64-texel chunk plus2-texel border, retain at most8 expanded materials and normalize selected weights.',
         'CPU: center0.157207 within float tolerance, sum1, edge wrap, projection-expanded frequency/top8, defined tie policy and first-slot fallback below0.001.'),
        ('B02','Texture color space','Average raw diffuse/specular squares using W=alpha^8*w, skipping w<=0.01. Do not accidentally combine an automatic SRGB sample decode with another raw-data square. BaseDominance has no effect.',
         'CPU and shader-source: independent two-layer squared-space vector, alpha exponent endpoints, zero-sum fallback, dominance-invariance. Actual GPU equality deferred.'),
        ('V01','Separate exploration mask','Unrevealed status needs its own eligibility mask. ID3 is a legitimate material, not an unknown sentinel; picking visibility is stricter than exploration and cannot replace the revealed mask.',
         'CPU: explored-invisible neighbor still participates; unexposed input mutation does not affect revealed IDs/heights/normals/top8/weights or output colors.'),
        ('V02','Hidden-data noninterference','Sanitize hidden fields before placement, height, normal and chunk-frequency generation, not just after final color blending.',
         'Metamorphic CPU test: change every hidden terrain/wonder/continent while keeping revealed snapshot+seed fixed; compare all revealed presentation inputs.'),
        ('I01','Exact integer tile ownership','A global triangle may cross hex boundaries. A nointerpolation vertex pick ID cannot represent every covered fragment. Resolve the fragment world position to the exact tile or keep an equivalent depth-correct ID pass.',
         'CPU tile-position boundary/offset/wrap oracle; source checks for SV_Target1 uint/R32_UINT, unchanged key ordering/generation checks. Actual GPU readback/pixel comparison deferred.'),
        ('A01','Sealed source package','Keep DLC/Shared TerrainDef row order and source SHA; include D/H/S and the complete original piece library once. Do not sort rows by continent/legacy ID or rewrite v1 inputs.',
         'Pure file tests: row0 Asia_Tundra, row3 Euro_Coast, Mesa scale0.05, Amer mountain projection0, truncated/duplicate/out-of-range data rejected, package hash roundtrip.'),
        ('C01','Cache invalidation','Retained ground reuse must include the new package identity, detached seed, natural-wonder/cell inputs and all effective visibility/geometry inputs. Old caches cannot survive an unkeyed new semantic field.',
         'CPU: mutate one newly consumed field at a time and miss; unit-only clock/pose mutations still hit; failed candidate retains old entry.'),
        ('E01','Execution boundary','Only file parsing, controlled CPU components, shader/compiler diagnostics and compile/link are authorized. No Host/GameCore/CLR/HWND/GPU/audio/game or original installation/MODS/settings/saves/default registration changes.',
         'Source and subprocess/import audit; retain native GPU/visual/picking/regression acceptance as unverified.')]
    value=dict(schema='zerosis.terrain.phase1.independent_contract_matrix.v1',
        status='PASS_PHASE0_BASELINE_WITH_PHASE1_ACCEPTANCE_GATES_RECORDED',
        phase0_check=ref(REVIEW/'phase0_plan_check_receipt.json'),
        inputs=[ref(PROJECT/'AGENTS.md'),ref(PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md'),ref(PROJECT/'docs/CLAUDE_HANDOFF.md')]+
            [ref(STAGE/name) for name in ('retail_piece_placement_probe.json','retail_map_cells_probe.json',
                'retail_terrain_blend_cpu_probe.json','terrain_shader_semantics.json','piece_cells.json')],
        criteria=[dict(id=a,area=b,requirement=c,offline_acceptance=d) for a,b,c,d in rows],
        native_gates=['Actual CPU/GPU color and tile-ID readback equivalence','Actual original-layout and visual comparison','Moving unit/depth/occlusion/picking regressions'],
        original_placement_equivalence_verified=False,native_execution=False,existing_files_modified=False)
    path=REVIEW/'contract_matrix.json';assert not path.exists()
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')
    print(json.dumps(dict(status=value['status'],criteria=len(rows),native_execution=False)))

if __name__=='__main__':main()
