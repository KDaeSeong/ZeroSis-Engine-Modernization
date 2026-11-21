"""Check real Host clock-driven world/UI pose refresh evidence after smoke play."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import uuid
from PIL import Image, ImageChops

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from verify_interactive_decisions import read_run, require
import verify_interactive_game as base


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', required=True)
    args = ap.parse_args()
    request, result, output, _, _, runtime, evidence = read_run(args.run, research_tree=True)
    animation = request.get('unit_assets', {}).get('animation_runtime')
    require(animation and animation['format_version'] == 2, 'Run did not seal animation runtime inputs')
    check_artifacts(animation)
    require(result.get('runtime_inputs_unchanged') is True, 'Animated runtime inputs changed')
    generated = result['generated_files']

    def retained(name):
        matches = [Path(row['path']) for row in generated if Path(row['path']).name == name]
        require(len(matches) == 1, 'Missing/ambiguous animation evidence: ' + name)
        return base.generated(result, matches[0], runtime)

    build = json.loads(Path(request['provenance']['host_build']['path']).read_text(encoding='utf-8'))
    sources = {Path(row['path']).name: row for row in [*build['compiler_inputs'], *build['sources']]}
    expected = {
        'InteractiveGameLoop.h': ('steady_clock::now()', 'refreshAnimation(elapsed)', 'RefreshPreparedGpuFrame(candidate',
                                  'retainedOverlays', 'animationStateBefore', 'ReleaseWorldTerrainResources'),
        'WorldTerrainRenderer.cpp': ('cache.units->Animate(view.animationSeconds)',),
        'BitmapWindow.cpp': ('Visual refresh cannot change committed input geometry',),
        'UnitAnimation.h': ('std::fmod(', 'ZSGrannyBridge_Sample',),
    }
    for name, tokens in expected.items():
        require(name in sources, 'Compiled source closure lacks ' + name)
        check_artifacts(sources[name])
        body = Path(sources[name]['path']).read_text(encoding='utf-8')
        require(all(token in body for token in tokens), 'Compiled animation contract differs: ' + name)
    results = []
    for mode in ('world', 'ui'):
        records = re.findall(r'^INTERACTIVE_ANIMATION_FRAME=' + mode + r'\|(\d+)\|([\d.]+)\|(\d+)\|(\d+)$', output, re.M)
        require(len(records) == 3 and [int(x[0]) for x in records] == [1, 2, 3], 'Missing ordered clock frames: ' + mode)
        times = [float(x[1]) for x in records]
        require(all(b > a for a, b in zip(times, times[1:])) and all(t >= .25 * (i + 1) for i, t in enumerate(times)),
                'Animation did not advance on its monotonic clock')
        require(len({x[2:] for x in records}) == 1, 'Animation changed generation/turn inside one retained scene')
        require(output.count('INTERACTIVE_ANIMATION_STATE_UNCHANGED=' + mode) == 1, 'Missing state-retention marker')
        before, after = retained('animation-' + mode + '-before.txt'), retained('animation-' + mode + '-after.txt')
        require(before.read_bytes() == after.read_bytes(), 'Detached animation changed observed SDK state')
        frames = [retained(f'animation-{mode}-{i}.png') for i in (1, 2, 3)]
        pixels = []
        images = [Image.open(p).convert('RGB') for p in frames]
        try:
            require(all(i.size == (1280, 720) for i in images), 'Animation capture dimensions differ from the actual window')
            for first, second in zip(images, images[1:]):
                delta = ImageChops.difference(first, second)
                bbox = delta.getbbox()
                count = sum(1 for r, g, b in delta.getdata() if r or g or b)
                require(bbox is not None and count > 0, 'Animation time did not change the displayed original-unit pixels')
                pixels.append({'changed_pixels': count, 'bounds_xyxy': bbox})
        finally:
            for image in images:
                image.close()
        results.append({'mode': mode, 'clock_seconds': times, 'input_generation': int(records[0][2]),
                        'turn': int(records[0][3]), 'frames': [artifact(p) for p in frames],
                        'pixel_differences': pixels, 'semantic_before': artifact(before), 'semantic_after': artifact(after),
                        'observed_sdk_state_unchanged': True})
    proof = PROJECT / 'validators' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:12])
    proof.mkdir(exist_ok=False)
    script = proof / Path(__file__).name
    shutil.copy2(__file__, script)
    report = {'status': 'PASS_INTERACTIVE_ORIGINAL_UNIT_ANIMATION', 'run_id': args.run, 'host_pid': result['pid'],
              'request': artifact(evidence / 'request.json'), 'result': artifact(evidence / 'result.json'),
              'verifier': artifact(script), 'phases': results,
              'scope': 'original Warrior IdleA curve CPU skinning on the x64 Host clock, GPU world/UI refresh without input-generation changes',
              'limits': ['SDK state comparison is the retained semantic snapshot, not every private serialized field.',
                         'IdleA and stock Warrior only; movement/combat clips and other original units remain.',
                         'These are hidden-window automated captures, not human full-gameplay or retail visual equivalence.']}
    path = proof / 'animation.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'proof': artifact(path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
