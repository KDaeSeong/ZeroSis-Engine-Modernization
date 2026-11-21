"""Run the policy callback regression suite without emitting full failures."""
import hashlib
import json
import sys
import time
import unittest
from pathlib import Path

project = Path(__file__).resolve().parents[4]
output = Path(__file__).resolve().parent
sys.path[:0] = [str(project), str(project / 'tools')]
protected = [
    'tools/worker_research_timeline.py', 'Tests/test_worker_research_timeline.py',
    'tools/verify_interactive_decisions.py', 'tools/action_info_panel_timeline.py',
    'Source/Host/UiPopupContext.h', 'Source/Host/InteractiveUiSession.h',
    'evidence/interactive_game/20261011T124731Z_b821f4b6c26a/result.json',
    'evidence/interactive_game/20261011T125838Z_2f697438e208/result.json',
]
def hashes():
    return {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in protected}

before = hashes()
start = time.monotonic()
log = output / 'focused_tests.log'
with log.open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName('Tests.test_worker_research_timeline'))
after = hashes()
report = {
    'status': 'PASS' if result.wasSuccessful() and before == after else 'FAILED',
    'tests_run': result.testsRun, 'failures': len(result.failures),
    'errors': len(result.errors), 'skipped': len(result.skipped),
    'elapsed_seconds': time.monotonic() - start,
    'source_and_native_evidence_unchanged': before == after,
    'before': before, 'after': after,
    'log': {'path': str(log), 'bytes': log.stat().st_size,
            'sha256': hashlib.sha256(log.read_bytes()).hexdigest()},
}
(output / 'component.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('status', 'tests_run', 'failures', 'errors',
                                      'skipped', 'source_and_native_evidence_unchanged')}))
sys.exit(0 if report['status'] == 'PASS' else 1)
