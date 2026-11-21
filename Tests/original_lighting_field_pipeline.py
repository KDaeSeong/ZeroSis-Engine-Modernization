"""Exercise the production field-preparation policy with an injected CPU-only backend."""
from pathlib import Path
import json, os, re, sys
sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/world_terrain_original/phase6/pipeline/cpu01'
BUILD = PROJECT / 'Build/OriginalLightingFieldPipeline/cpu01'
sys.path[:0] = [str(PROJECT / 'tools'), str(PROJECT / 'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    assert not BUILD.exists() and not STAGE.exists(), 'Use a new reviewed attempt after failure'
    assert not any(os.environ.get(name) for name in ('CL', '_CL_', 'LINK'))
    STAGE.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    names = ['Source/Presentation/' + name for name in (
        'OriginalLightingFieldBridge.inc', 'OriginalLightingFieldModel.h', 'OriginalLightingFieldBinding.h',
        'OriginalLightingModel.h', 'OriginalWaterOpticsModel.h', 'OriginalTerrainModel.h', 'OriginalTerrainGeometry.h',
        'OriginalTerrainBinding.h', 'WorldViewRenderer.h', 'WorldCameraControls.h', 'BitmapRenderer.h')]
    names += ['Tests/original_lighting_field_pipeline.cpp', 'Tests/original_lighting_field_pipeline.py']
    before = [common.artifact(PROJECT / name) for name in names]
    write_new(STAGE / 'started.json', dict(inputs=before, injected_backend='PureCPU resources; actual production Bridge.inc',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled = build_cxx14('original_lighting_field_pipeline', BUILD, STAGE,
        PROJECT / 'Tests/original_lighting_field_pipeline.cpp', [PROJECT / 'Source/Presentation'])
    imports = run([Path(compiled['compiler']).with_name('dumpbin.exe'), '/dependents', compiled['path']], cwd=BUILD, timeout=30)
    dlls = sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$', imports.stdout.decode('mbcs'), re.M)))
    assert imports.returncode == 0 and {name.lower() for name in dlls} == {'kernel32.dll'}, dlls
    executable = common.artifact(compiled['path'])
    result = run([compiled['path']], cwd=BUILD, timeout=30)
    output = result.stdout.decode('ascii')
    match = re.fullmatch(r'PASS_LIGHTING_FIELD_PIPELINE checks=(\d+) builds=(\d+) loads=(\d+)\s*', output)
    assert result.returncode == 0 and not result.stderr and match, (result.returncode, output, result.stderr)
    assert int(match[2]) == 6 and int(match[3]) == 1
    after = [common.artifact(PROJECT / name) for name in names]
    assert before == after
    rows = []
    assert BUILD.resolve().is_relative_to((PROJECT / 'Build/OriginalLightingFieldPipeline').resolve())
    for path in sorted(BUILD.iterdir()):
        assert path.is_file() and path.suffix in ('.exe', '.obj', '.map', '.rsp', '.cmd')
        row = common.artifact(path)
        row['allocated_bytes'] = storage.allocated(path)
        assert row['links'] == 1 and not row['file_attributes'] & 0x401
        rows.append(row)
    write_new(STAGE / 'cleanup_plan.json', dict(directory=str(BUILD), exact_owned_leaves_only=True,
        files=rows, protected_source_inputs=after))
    for row in rows:
        path = Path(row['path'])
        now = common.artifact(path)
        assert all(now[key] == row[key] for key in ('bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes', 'links'))
        path.unlink()
    assert not any(BUILD.iterdir())
    BUILD.rmdir()
    cleanup = dict(status='PASS_EXACT_OWNED_FIELD_PIPELINE_INTERMEDIATES_REMOVED', retired_files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows), files=rows)
    write_new(STAGE / 'cleanup_result.json', cleanup)
    proof = dict(status='PASS_PRODUCTION_FIELD_PREPARATION_POLICY_CPU_BACKEND', checks=int(match[1]),
        backend_build_calls=int(match[2]), shared_baker_loads=int(match[3]),
        inputs_before=before, inputs_after=after, build=compiled, executed_console=executable,
        imported_dlls=dlls, retained_test_executable=False,
        cases=['Wrapped draw images share one canonical field', 'Ready fields avoid capture/sampling/baking for120 presentation refreshes',
               'Injected allocation failure leaves existing fields intact and does not publish a partial candidate',
               'New atlas-owned meshes receive fresh fields; no-material chunks allocate none',
               'Actual known/shadow producer dimensions and quantization match the backend contract',
               'Final baked-specular/linear-screen-light composition and policy constants match Source binding'],
        cleanup=common.artifact(STAGE / 'cleanup_result.json'),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE / 'result.json', proof)
    print(json.dumps(dict(status=proof['status'], checks=proof['checks'],
        retired_files=len(rows), released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'])))


if __name__ == '__main__':
    main()
