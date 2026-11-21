"""Validate frozen database-corpus evidence without treating live caches as immutable."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, pe_header, read_text
from database_evidence import artifacts, validate as validate_provider


def validate():
    path = PROJECT / 'evidence/database/corpus/conformance.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    _, _, provider = validate_provider(PROJECT / 'evidence/database/candidate/build_result.json')
    # Original cache paths are capture provenance. Only the frozen copies are test inputs;
    # a later legitimate game run may replace the live caches without changing this proof.
    sealed = {key: value for key, value in report.items() if key != 'copies'}
    sealed['copies'] = [row['copy'] for row in report['copies']]
    for row in artifacts(sealed):
        file = Path(row['path'])
        if not file.is_file() or digest(file) != row['sha256']:
            raise RuntimeError('Database corpus artifact changed: ' + str(file))
    names = {'Civ5CoreDatabase.db', 'Civ5DebugDatabase.db', 'Localization-Merged.db'}
    if (report['status'] != 'SDK_DATABASE_CACHED_CORPUS_PASS' or report['provider'] != provider
            or set(report['builds']) != {'x86', 'x64'} or len(report['audits']) != 5
            or len(report['copies']) != 3 or len(report['runs']) != 6 or len(report['comparisons']) != 3
            or not report['originals_unchanged'] or not report['copies_unchanged']
            or report['game_launched'] or report['gamecore_loaded']):
        raise RuntimeError('Database corpus scope/provenance invalid')
    for arch, build in report['builds'].items():
        if pe_header(Path(build['executable']['path']))['architecture'] != arch:
            raise RuntimeError('Database corpus executable architecture changed')
        if re.search(r'\bwarning\s+[A-Z]+\d+', read_text(Path(build['log']['path']))):
            raise RuntimeError('Database corpus build warnings')
    root = (PROJECT / 'Build/Database/corpus').resolve()
    if {Path(row['copy']['path']).name for row in report['copies']} != names:
        raise RuntimeError('Database corpus fixtures missing')
    for row in report['copies']:
        frozen = Path(row['copy']['path']).resolve()
        frozen.relative_to(root)
        if (row['original_opened_by_harness'] or frozen == Path(row['original']['path']).resolve()
                or row['copy']['sha256'] != row['original']['sha256']
                or frozen.stat().st_size != row['size'] or row['mtime_ns'] <= 0):
            raise RuntimeError('Database corpus snapshot provenance invalid')
    keyed = {(row['database'], row['architecture']): row for row in report['runs']}
    if set(keyed) != {(name, arch) for name in names for arch in ('x86', 'x64')}:
        raise RuntimeError('Database corpus native run coverage invalid')
    for comparison in report['comparisons']:
        name = comparison['database']
        traces = []
        for arch in ('x86', 'x64'):
            run = keyed[name, arch]
            trace = Path(run['log']['path']).read_bytes().replace(b'\r\n', b'\n')
            if run['returncode'] or not re.search(rb'^PASS\|\d+\s*$', trace, re.M):
                raise RuntimeError('Database corpus native run failed')
            summary = re.search(rb'^CORPUS\|(\d+)\|(\d+)\|(\d+)\|integrity_ok\s*$', trace, re.M)
            tables = re.findall(rb'^TABLE\|.*\|\d+\|\d+\|[0-9a-f]{64}\s*$', trace, re.M)
            if not summary or [int(summary[i]) for i in (1, 2, 3)] != [comparison[k] for k in ('tables', 'rows', 'values')]:
                raise RuntimeError('Database corpus native accounting changed')
            if len(tables) != comparison['tables']:
                raise RuntimeError('Database corpus table digests missing')
            traces.append(trace)
        if (traces[0] != traces[1] or not comparison['equal_table_digests_and_trace']
                or Path(comparison['diff']['path']).read_bytes()):
            raise RuntimeError('Database corpus comparison failed')
    if {row['database'] for row in report['comparisons']} != names or any(
            sum(row[key] for row in report['comparisons']) != report[key] for key in ('tables', 'rows', 'values')):
        raise RuntimeError('Database corpus totals invalid')
    return report, {'path': str(path), 'sha256': digest(path)}
