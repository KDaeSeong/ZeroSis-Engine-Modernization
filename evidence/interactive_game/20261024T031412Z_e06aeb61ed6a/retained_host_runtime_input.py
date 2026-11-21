"""Read-only runtime input gate for the attested Host after object retirement.

This accepts one published build, not arbitrary missing linker inputs. Five
objects are historical only after the exact attestation and retirement receipt;
two documentation identities are verified from their publication backups.
Executable sources, libraries, dependencies and the retained PE remain required.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import stat


BUILD_ID = '20261024T021245Z_18bbd0dd26e7'
REPORT_SHA = '26edcf537984d5bf6cc74be3a908dcec92fda946ba03a2e5188fb32a22fbf5f2'
AUDIT_SHA = '633586ca57bbf9343113e364e8b35bea8c16934e01a99719c065bdd9c0222aba'
UPDATE_SHA = '5a8250cf26f4d5bb0a595677eac5970c60fdd3b42d93a9558f46963dfe95dc1d'
UNITS = (('host_main', 'HostMain'), ('window', 'BitmapWindow'),
         ('renderer', 'BitmapRenderer'), ('world_renderer', 'WorldViewRenderer'),
         ('terrain_renderer', 'WorldTerrainRenderer'))


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _pair(row):
    _require(isinstance(row, dict) and isinstance(row.get('path'), str) and
             isinstance(row.get('sha256'), str), 'Malformed retained Host artifact')
    return _key(row['path']), row['sha256']


def _snapshot(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class _Files:
    def __init__(self):
        self.checked = {}

    def ordinary(self, path):
        path = Path(path)
        _require(path.is_absolute() and '..' not in path.parts, 'Noncanonical Host artifact path')
        for parent in (path, *path.parents):
            info = parent.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and
                     not getattr(info, 'st_file_attributes', 0) & 0x400,
                     'Reparse Host artifact path: ' + str(parent))
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode), 'Host artifact is not a regular file')
        return info

    def verify(self, row):
        pair = _pair(row)
        path = Path(row['path'])
        before = self.ordinary(path)
        if pair in self.checked:
            _require(_snapshot(before) == self.checked[pair][1] and
                     ('bytes' not in row or (type(row['bytes']) is int and
                                            row['bytes'] == self.checked[pair][0]['bytes'])),
                     'Host input identity or byte count changed during validation')
            return self.checked[pair][0]
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        _require(digest.hexdigest() == row['sha256'] and
                 ('bytes' not in row or (type(row['bytes']) is int and row['bytes'] == before.st_size)) and
                 _snapshot(before) == _snapshot(path.stat()), 'Changed retained Host input: ' + str(path))
        actual = dict(path=str(path), bytes=before.st_size, sha256=digest.hexdigest())
        self.checked[pair] = actual, _snapshot(before)
        return actual

    def json(self, row, compressed=False):
        actual = self.verify(row)
        _require(actual['bytes'] <= 8 * 1024 * 1024, 'Host evidence exceeds bound')
        raw = Path(actual['path']).read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == actual['sha256'], 'Host evidence changed while reading')
        if compressed:
            with gzip.open(actual['path'], 'rb') as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            _require(len(raw) <= 8 * 1024 * 1024, 'Host backup exceeds bound')
        return json.loads(raw.decode('utf-8-sig'))

    def finish(self):
        for row, snapshot in self.checked.values():
            _require(_snapshot(self.ordinary(row['path'])) == snapshot, 'Host input changed before completion')


def _walk(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and 'sha256' in value:
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_retained_host_runtime(build, project):
    """Rehash retained inputs, keeping exact retired objects as historical proof."""
    project = Path(project).absolute()
    files = _Files()
    report_ref = dict(path=str(project / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'),
                      sha256=REPORT_SHA)
    sealed = files.json(report_ref)
    _require(json.dumps(build, sort_keys=True, separators=(',', ':')) ==
             json.dumps(sealed, sort_keys=True, separators=(',', ':')) and build.get('build_id') == BUILD_ID,
             'Runtime Host report differs from the published build')
    stage = project / 'evidence/native_save_archive/host_relink/18bbd0dd26e70e623276'
    audit_ref = dict(path=str(stage / 'publication/final_audit.json'), sha256=AUDIT_SHA)
    audit = files.json(audit_ref)
    _require(audit['status'] == 'PASS_FRESH_CURRENT_HOST_LINK_PUBLICATION_AND_RETIREMENT_AUDIT' and
             audit['human_escape_stop_respected'] is True and audit['new_host_runtime_executed'] is False,
             'Host publication scope differs')
    attestation = files.json(audit['attestation'])
    post = files.json(audit['post'])
    update_ref = dict(path=str(stage / 'publication/progress_update.json'), sha256=UPDATE_SHA)
    update = files.json(update_ref)
    _require(attestation['status'] == 'PASS_RELINKED_NATIVE_HOST_STATIC_ATTESTATION' and
             _pair(attestation['build_result']) == _pair(report_ref) and
             _pair(update['build_result']) == _pair(report_ref) and
             _pair(update['attestation']) == _pair(audit['attestation']) and
             _pair(audit['executable']) == _pair(build['executable']), 'Host attestation belongs to another build')
    retirement = files.json(update['cleanup'])
    plan = files.json(retirement['plan'], compressed=True)
    _require(retirement['status'] == 'PASS_FIVE_ATTESTED_OBJECTS_AND_TWO_PRECOMPILE_FAILED_SNAPSHOTS_RETIRED' and
             _pair(retirement['attestation']) == _pair(audit['attestation']) and
             _pair(plan['build_result']) == _pair(report_ref) and
             _pair(plan['attestation']) == _pair(audit['attestation']), 'Host retirement belongs to another build')
    units = build['final_compilation']['translation_units']
    _require(len(units) == len(attestation['actual_coff_objects']) == 5, 'Host object inventory differs')
    targets = {_pair(row): row for row in plan['targets']}
    retired = {}
    for index, (unit, proof, (name, stem)) in enumerate(zip(units, attestation['actual_coff_objects'], UNITS)):
        row = unit['object']
        expected = project / f'Build/UiWindowHost/{BUILD_ID}/final/tu_{index:02d}_{name}/obj/{stem}.obj'
        _require(unit['translation_unit'] == proof['translation_unit'] == name and
                 type(unit['returncode']) is int and unit['returncode'] == 0 and
                 _key(row['path']) == _key(expected) and _pair(row) == _pair(proof['object']) and
                 _pair(row) in targets and row['bytes'] == targets[_pair(row)]['bytes'] and
                 not os.path.lexists(expected), 'Unattested or present retired Host object')
        retired[_pair(row)] = row
    revisions = update['changed_metadata']
    _require(revisions == post['authorized_metadata_revisions'] and len(revisions) == 2,
             'Host metadata publication proof differs')
    expected_metadata = { _key(project / path) for path in (
        'evidence/save_menu/20261013_original_screen/current_progress.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md') }
    historical = {}
    for revision in revisions:
        before, after = revision['before'], revision['after']
        _require(_key(before['path']) in expected_metadata and _key(before['path']) == _key(after['path']) and
                 revision['backup_roundtrip_verified'] is True, 'Unrelated historical Host metadata')
        backup = files.verify(revision['backup'])
        with gzip.open(backup['path'], 'rb') as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        _require(len(raw) == before['bytes'] and hashlib.sha256(raw).hexdigest() == before['sha256'],
                 'Host metadata backup does not restore its build-time identity')
        historical[_pair(before)] = before
    _require(len(historical) == 2, 'Duplicate historical Host metadata')
    _require({pair[0] for pair in historical} == expected_metadata, 'Historical Host metadata paths differ')
    historical_visits, retired_visits = set(), set()
    for row in _walk(build):
        pair = _pair(row)
        if pair in retired:
            _require(row.get('bytes', retired[pair]['bytes']) == retired[pair]['bytes'], 'Retired object size differs')
            retired_visits.add(pair)
        elif pair in historical:
            _require(row.get('bytes', historical[pair]['bytes']) == historical[pair]['bytes'], 'Metadata size differs')
            historical_visits.add(pair)
        else:
            files.verify(row)
    _require(retired_visits == set(retired) and historical_visits == set(historical), 'Host historical inventory not consumed')
    files.finish()
    return dict(scope='RETAINED_HOST_RUNTIME_INPUTS_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT',
                publication_audit=files.verify(audit_ref), attestation=files.verify(audit['attestation']),
                retirement=files.verify(update['cleanup']),
                retained_artifact_identities_verified=len(files.checked),
                absent_discovery_objects=[], absent_final_objects=[
                    dict(original_path=row['path'], sha256=row['sha256'], bytes=row['bytes']) for row in retired.values()],
                historical_metadata_backups_verified=2, host_executed=False, save_compatibility_verified=False)
