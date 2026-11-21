"""Invoke the unchanged audited preparer in a new explicit-profile evidence root."""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
PINS = {
    'prepare_latest_engine_pair.py': '5c391a3272834bad289531b0f2bbb167bb377a09f3e9e5deb5ada8b7ada802ae',
    'prepare_current_sdk_play.py': '1254720f955671dc895c45109a9417a088211f0f5823d9c26e1d8b2ebf90e8ae',
    'run_interactive_game.py': '0fd33968ca92f14b7197fdb186d3a9060a68cad6ffe62499cc1f85ec5f625172',
    'runtime_input_cache.py': 'cc9a819989a6d5191352001e0cf3b618bd08a3acf781caf744b4fc52182f2f19',
    'current_runtime_sdk_input.py': 'ff092c1b0ba80c3b5d33a79f6246bd9606073e9c49a79e2fd60a8bb9feaf0b88',
}
for name, digest in PINS.items():
    assert hashlib.sha256((PROJECT / 'tools' / name).read_bytes()).hexdigest() == digest, name
profile = PROJECT / 'evidence/world_terrain_original/phase6/pair_preparation/20261115T093013Z_23c5037b12b9/prepared_profile.json'
digest = 'b0259d789969a98e2bbd445b5dcdac60e4017ac6e84cf516ba43c418b2a9bd14'
assert hashlib.sha256(profile.read_bytes()).hexdigest() == digest
assert not (STAGE / 'base_preparation').exists(), 'Use a new reviewed attempt after failure'
with (STAGE / 'base_invocation.json').open('x', encoding='utf8') as stream:
    json.dump(dict(status='REVIEWED_FILE_ONLY_BASE_PREPARATION', helper_pins=PINS,
        profile=dict(path=str(profile), sha256=digest), overridden_data_constant='EXPLICIT_MENU_STAGE_ROOT',
        new_stage_root=str(STAGE / 'base_preparation'), source_bytes_modified=False,
        native_execution_allowed=False, default_promotion_allowed=False), stream, indent=2)
    stream.write('\n')
import prepare_latest_engine_pair as prepare
prepare.EXPLICIT_MENU_STAGE_ROOT = STAGE / 'base_preparation'
raise SystemExit(prepare.main(['--host-input-profile', str(profile), '--host-input-profile-sha256', digest]))
