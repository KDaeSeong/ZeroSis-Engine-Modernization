"""One isolated scene compile from the captured SDK snapshot; no game is run."""
from pathlib import Path
from datetime import datetime, timezone
import contextlib
import hashlib
import json
import shutil
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from render_ui_popup import prepare
from interactive_ui_driver import validate_social_policy_scene_proof

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    inputs = ROOT / 'Build/UiPopupPixels/20261009T045057Z_bebb746a6d3f'
    expected = {
        'candidate-snapshot.json': '5027d675002360b0d75c9bc910e347a661964a37893fd353797aa79d099da026',
        'inline_colors.json': 'b57a12160c53354eeb1c06aeea7123d20ded686fdde51f9207ea9202586aca44',
        'inline_icons.json': '364202d1b463291e4dec148f15d9b75e72546309bde4575e89686f915c9f2fdb',
    }
    original = ROOT / ('Build/InteractiveGameRuntime/20261009T044447Z_88730f00e24b/'
                       'sessions/c90eeeaa202df7b7f39061a9d361c12e/play-ui-21.json')
    assert digest(original) == '6f7d300daa716ffdcde4aeab1fe705f5e5ba849f80a85830e775011ed4b5f70e'
    assert all(digest(inputs / name) == sha for name, sha in expected.items())
    sources = [ROOT / 'tools' / name for name in (
        'civ5_ui_assets.py', 'ui_pixel_scene.py', 'render_ui_popup.py',
        'interactive_ui_driver.py', 'prepare_ui_popup_assets.py', 'ui_bitmap_fonts.py')]
    before = {str(path): digest(path) for path in [original, *sources]}
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    output = ROOT / 'Build/UiPopupPixels' / run
    evidence = ROOT / 'evidence/social_policy_render_provenance' / run
    output.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    for name in expected:
        shutil.copyfile(inputs / name, output / name)
    report = {
        'status': 'FAILED_ACTUAL_SNAPSHOT_SCENE_COMPONENT', 'run_id': run,
        'captured_sdk_snapshot': str(original),
        'candidate_difference': 'Only PolicyInfo.defaultSize.source uses the verified retail Styles.xml identity.',
        'input_sha256': expected, 'source_sha256': before, 'build_directory': str(output),
        'game_launched': False, 'native_input_verified': False, 'retail_pixels_verified': False,
        'scene_prepared': False, 'driver_scene_proof_passed': False,
    }
    try:
        manifest = output / 'scene_manifest.json'
        with (evidence / 'prepare.log').open('w', encoding='utf8') as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                prepare(output / 'candidate-snapshot.json', output, manifest, context='social-policy')
        report['scene_prepared'] = True
        validate_social_policy_scene_proof(
            json.loads((output / 'candidate-snapshot.json').read_text(encoding='utf8')),
            json.loads(manifest.read_text(encoding='utf8')), closed=False)
        report['driver_scene_proof_passed'] = True
        report['manifest'] = {'path': str(manifest), 'sha256': digest(manifest)}
        report['status'] = 'PASS_ACTUAL_SNAPSHOT_SCENE_AND_DRIVER_COMPONENT_ONLY'
    except Exception:
        report['error'] = traceback.format_exc()
    report['source_inputs_unchanged'] = all(digest(Path(path)) == sha for path, sha in before.items())
    report['copied_inputs_unchanged'] = all(digest(output / name) == sha for name, sha in expected.items())
    if not report['source_inputs_unchanged'] or not report['copied_inputs_unchanged']:
        report['status'] = 'FAILED_INPUT_CHANGED'
    result = evidence / 'result.json'
    result.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'report': str(result), 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['status'].startswith('PASS_') else 1

if __name__ == '__main__':
    raise SystemExit(main())
