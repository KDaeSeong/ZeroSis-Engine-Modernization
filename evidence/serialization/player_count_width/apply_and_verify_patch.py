"""Apply/replay only the reviewed Traits count patch; no SDK build or installed input."""
from __future__ import annotations
from datetime import datetime, timezone
import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
REL = 'CvGameCoreDLL_Expansion2/CvTraitClasses.cpp'
ORIGINAL = PROJECT/'Source/SDK_BNW_Original'/REL
TARGET = PROJECT/'Source/SDK_BNW_x64'/REL
PATCHES = PROJECT/'Source/Porting/sdk_x64_patches.json'
MANIFEST = PROJECT/'evidence/sdk_x64/port_manifest.json'
RECEIPT = STAGE/'port_patch_tracking.json'
BASELINES = {
    TARGET: 'bdc0d8722941f5f2d22dd2d7dd68f6dc6f8040eaca1e187e622a89c8f7ad7b49',
    PATCHES: '1b35dfad0c2eb8d87fb724668dd133cde3506fe84cc0c5d5da79c619131d8174',
    MANIFEST: '07560902d804ee20417ca797645aa10974357409c4546da4b627e61ef5efb203',
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def artifact(path):
    info = path.stat()
    return dict(path=str(path), bytes=info.st_size, sha256=digest(path.read_bytes()),
                file_identity=[info.st_dev, info.st_ino], hardlink_count=info.st_nlink,
                mtime_ns=info.st_mtime_ns)


def guarded(path):
    require(path.absolute().is_relative_to(PROJECT), 'Path outside authorized project')
    current = path.absolute()
    while current != PROJECT.parent:
        if current.exists():
            info = current.lstat()
            require(not stat.S_ISLNK(info.st_mode) and
                    not (getattr(info, 'st_file_attributes', 0) & 0x400), 'Reparse target/ancestor')
        current = current.parent
    require(path.resolve().is_relative_to(PROJECT.resolve()), 'Resolved path outside project')
    if path.exists():
        require(path.is_file() and path.stat().st_nlink == 1, 'Mutable target is not an unshared regular file')


def atomic(path, content, expected):
    guarded(path)
    require(digest(path.read_bytes()) == expected, 'Concurrent mutation before replacement')
    temporary = path.with_name(path.name + '.player-count-width.stage')
    guarded(temporary)
    require(not temporary.exists(), 'Owned staging path already exists')
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        require(digest(path.read_bytes()) == expected, 'Concurrent mutation during staging')
        os.replace(temporary, path)
        require(path.read_bytes() == content, 'Atomic replacement content mismatch')
    finally:
        if temporary.exists():
            guarded(temporary)
            temporary.unlink()


def replay(specification, relative):
    original = PROJECT/'Source/SDK_BNW_Original'/relative
    raw = original.read_bytes()
    source_hash = digest(raw)
    applied = []
    for patch in specification['patches']:
        if patch['file'] != relative:
            continue
        old, new = patch['old'].encode('latin1'), patch['new'].encode('latin1')
        require(patch['source_sha256'] == source_hash and old and raw.count(old) == patch['count'],
                'Tracked patch source/count drift: ' + patch['id'])
        raw = raw.replace(old, new)
        applied.append(patch['id'])
    return raw, applied


def new_patches():
    source_hash = digest(ORIGINAL.read_bytes())
    require(source_hash == '8e5c3fe9ad40e44e2ad9a16e9ea590ff13ced2b51925f96b280495d82fec8edc',
            'Copied Traits source changed')
    def row(identifier, old, new, reason):
        return dict(id=identifier, file=REL, source_sha256=source_hash,
                    old=old.replace('\n', '\r\n'), new=new.replace('\n', '\r\n'), count=1, reason=reason)
    return [
        row('traits_serialization_checked_count_preflight',
            'void CvPlayerTraits::Write(FDataStream& kStream)\n{\n',
            'void CvPlayerTraits::Write(FDataStream& kStream)\n{\n'
            '\t// Validate all vector counts before output; the original readers use int32.\n'
            '\tconst int iNumMayaBonusChoices = CvChecked::Integer<int>(m_aMayaBonusChoices.size());\n'
            '\tconst int iNumNoTrain = CvChecked::Integer<int>(m_abNoTrain.size());\n'
            '\tconst int iNumUniqueLuxuryAreas = CvChecked::Integer<int>(m_aUniqueLuxuryAreas.size());\n\n',
            'Reject all three unrepresentable signed reader counts before the first stream write, including the late UniqueLuxury cast.'),
        row('traits_serialization_maya_count_i32',
            '\tstd::vector<MayaBonusChoice>::const_iterator it;\n'
            '\tkStream << m_aMayaBonusChoices.size();\n'
            '\tfor(it = m_aMayaBonusChoices.begin(); it != m_aMayaBonusChoices.end(); it++)\n'
            '\t{\n\t\tkStream << it->m_eUnitType;\n\t\tkStream << it->m_iBaktunJustFinished;\n\t}',
            '\tkStream << iNumMayaBonusChoices;\n'
            '\tfor(int iI = 0; iI < iNumMayaBonusChoices; iI++)\n'
            '\t{\n\t\tkStream << m_aMayaBonusChoices[iI].m_eUnitType;\n'
            '\t\tkStream << m_aMayaBonusChoices[iI].m_iBaktunJustFinished;\n\t}',
            'Replace x64 size_t8 with the checked int32 count and use that exact bound without changing element wire order.'),
        row('traits_serialization_no_train_count_i32',
            '\tkStream << m_abNoTrain.size();\n\tfor (uint ui = 0; ui < m_abNoTrain.size(); ui++)',
            '\tkStream << iNumNoTrain;\n\tfor (int ui = 0; ui < iNumNoTrain; ui++)',
            'Replace vector<bool> size_t8 with the checked int32 count; retain scalar bool element serialization.'),
        row('traits_serialization_unique_luxury_checked_count_i32',
            '\tkStream << (int)m_aUniqueLuxuryAreas.size();\n'
            '\tfor (unsigned int iI = 0; iI < m_aUniqueLuxuryAreas.size(); iI++)',
            '\tkStream << iNumUniqueLuxuryAreas;\n\tfor (int iI = 0; iI < iNumUniqueLuxuryAreas; iI++)',
            'The old prefix was already four bytes; replace its unchecked signed cast and iteration extent with the preflight count.'),
    ]


def proof_inputs():
    rows = [ORIGINAL, PROJECT/'Source/Porting/CvCheckedNarrow.h', PROJECT/'tools/build_sdk_x64.py']
    for tree in ('SDK_BNW_Original', 'SDK_BNW_x64'):
        root = PROJECT/'Source'/tree
        rows += [root/'CvGameCoreDLL_Expansion2'/name for name in (
            'CvTraitClasses.h', 'CvBuilderTaskingAI.cpp', 'CvBuilderTaskingAI.h',
            'CvCityConnections.cpp', 'CvCityConnections.h')]
        rows += [root/'FirePlace/include/FireWorks/FFastVector.h']
    return rows


def verify():
    receipt = json.loads(RECEIPT.read_text(encoding='utf-8'))
    require(receipt['status'] == 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED', 'Incomplete scoped patch receipt')
    for row in receipt['after'] + receipt['protected']:
        require(artifact(Path(row['path'])) == row, 'Published artifact/identity changed')
    specification = json.loads(PATCHES.read_text(encoding='utf-8'))
    generated, applied = replay(specification, REL)
    require(generated == TARGET.read_bytes(), 'Current port differs from RAM replay')
    rows = json.loads(MANIFEST.read_text(encoding='utf-8'))
    selected = [r for r in rows if r['relative_path'] == REL]
    require(len(selected) == 1 and selected[0]['port_sha256'] == digest(generated)
            and selected[0]['patch_ids'] == applied, 'Current manifest differs from RAM replay')
    print(json.dumps(dict(status='PASS_SCOPED_TRAITS_COUNT_PATCH_REPLAY', bytes=len(generated),
                          sha256=digest(generated), patch_ids=applied, native_executed=False)))


def main():
    require(not sys.flags.optimize and sys.argv[1:] in ([], ['--verify']), 'Unexpected arguments')
    if sys.argv[1:]:
        verify()
        return
    require(not RECEIPT.exists(), 'Scoped patch receipt already exists; use --verify')
    before = [artifact(path) for path in BASELINES]
    for path, expected in BASELINES.items():
        guarded(path)
        require(digest(path.read_bytes()) == expected, 'Reviewed mutable baseline changed')
    protected = [artifact(path) for path in proof_inputs()]
    old_source, old_spec, old_manifest = TARGET.read_bytes(), PATCHES.read_bytes(), MANIFEST.read_bytes()
    specification = json.loads(old_spec)
    manifest = json.loads(old_manifest)
    baseline, previous_ids = replay(specification, REL)
    require(baseline == old_source, 'Existing recipe does not reproduce the current Traits port')
    additions = new_patches()
    require(not ({r['id'] for r in additions} & {r['id'] for r in specification['patches']}), 'Duplicate patch IDs')
    after_specification = dict(specification, patches=specification['patches'] + additions)
    candidate, applied = replay(after_specification, REL)
    # Verify the three FStaticVector cases without changing them or invoking
    # generate_port(), which would access installed SDK inputs and all outputs.
    for name in ('CvBuilderTaskingAI.cpp', 'CvCityConnections.cpp'):
        relative = 'CvGameCoreDLL_Expansion2/' + name
        generated, _ = replay(after_specification, relative)
        require(generated == (PROJECT/'Source/SDK_BNW_x64'/relative).read_bytes(), 'Unchanged FStaticVector port drift')
    free_units = ('\tkStream << m_aFreeTraitUnits.size();\r\n'
        '\tfor(uint ui = 0; ui < m_aFreeTraitUnits.size(); ui++)\r\n'
        '\t{\r\n\t\tkStream << m_aFreeTraitUnits[ui].m_iFreeUnit;\r\n'
        '\t\tkStream << m_aFreeTraitUnits[ui].m_ePrereqTech;\r\n\t}').encode('latin1')
    require(old_source.count(free_units) == 1 and candidate.count(free_units) == 1, 'FreeTraitUnits body changed')
    nl = '\r\n' if b'\r\n' in old_spec else '\n'
    closing = (nl + '  ]' + nl + '}').encode('utf-8')
    insertion = old_spec.rfind(closing)
    require(insertion > 0, 'Patch registry closing layout changed')
    new_rows = '\n'.join('  ' + line for line in json.dumps(additions, ensure_ascii=False, indent=2).splitlines()[1:-1])
    encoded_rows = (',' + nl + new_rows.replace('\n', nl)).encode('utf-8')
    new_spec = old_spec[:insertion] + encoded_rows + old_spec[insertion:]
    require(json.loads(new_spec) == after_specification, 'Appended patch registry differs from planned objects')
    selected = [r for r in manifest if r['relative_path'] == REL]
    require(len(selected) == 1 and selected[0]['port_sha256'] == digest(old_source)
            and selected[0]['patch_ids'] == previous_ids, 'Existing manifest Traits row drift')
    original_row = selected[0]
    updated_row = dict(original_row, port_sha256=digest(candidate), patch_ids=applied)
    mn = '\r\n' if b'\r\n' in old_manifest else '\n'
    def row_bytes(row):
        return mn.join('  ' + line for line in json.dumps(row, ensure_ascii=False, indent=2).splitlines()).encode('utf-8')
    old_row, new_row = row_bytes(original_row), row_bytes(updated_row)
    require(old_manifest.count(old_row) == 1, 'Manifest row formatting changed')
    new_manifest = old_manifest.replace(old_row, new_row)
    after_manifest = json.loads(new_manifest)
    require(len(after_manifest) == len(manifest), 'Manifest row count changed')
    require(all(a == (updated_row if b['relative_path'] == REL else b)
                for a, b in zip(after_manifest, manifest)), 'Unrelated manifest fields changed')
    outputs = {TARGET: candidate, PATCHES: new_spec, MANIFEST: new_manifest}
    backups = []
    for path, raw in ((TARGET, old_source), (PATCHES, old_spec), (MANIFEST, old_manifest)):
        backup = STAGE/(path.name + '.before.gz')
        guarded(backup)
        require(not backup.exists(), 'Backup would overwrite retained evidence')
        compressed = gzip.compress(raw, mtime=0)
        require(gzip.decompress(compressed) == raw, 'Backup roundtrip failed')
        backup.write_bytes(compressed)
        backups.append(dict(**artifact(backup), original_path=str(path), original_sha256=digest(raw), roundtrip_verified=True))
    report = dict(format=1, status='BACKED_UP_TRACKING_PENDING', created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Traits writer only: two size_t wire widths and one unchecked signed cast; no schema or payload changes',
        before=before, protected=protected, backups=backups, added_patch_ids=[r['id'] for r in additions],
        generator_semantics='Copied snapshot + ordered Latin1 exact replacements; source hashes and match counts checked in RAM',
        full_generate_port_called=False, installed_original_accessed=False, full_sdk_built=False,
        native_or_game_executed=False, host_gamecore_or_hwnd_executed=False, user_saves_accessed=False,
        signed_reader_limit=2147483647, changed_sdk_files=[str(TARGET)], unchanged_static_vector_cases=[
            'CvPlayerTraits::m_aFreeTraitUnits', 'CvBuilderTaskingAI::m_aiNonTerritoryPlots', 'CvCityConnections::m_aiCityPlotIDs'])
    RECEIPT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for path, raw in outputs.items():
        atomic(path, raw, BASELINES[path])
    require(all(artifact(Path(row['path'])) == row for row in protected), 'Protected input changed during operation')
    require(PATCHES.read_bytes().replace(encoded_rows, b'', 1) == old_spec, 'Existing patch bytes changed')
    require(MANIFEST.read_bytes().replace(new_row, old_row, 1) == old_manifest, 'Other manifest bytes changed')
    source_diff = ''.join(difflib.unified_diff(old_source.decode('latin1').splitlines(keepends=True),
        candidate.decode('latin1').splitlines(keepends=True), fromfile='CvTraitClasses.cpp.before', tofile='CvTraitClasses.cpp.after'))
    diff_path = STAGE/'traits_count_width.diff'
    require(not diff_path.exists(), 'Diff output already exists')
    diff_path.write_text(source_diff, encoding='utf-8', newline='')
    report.update(status='PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED', completed_utc=datetime.now(timezone.utc).isoformat(),
        after=[artifact(path) for path in outputs], source_diff=artifact(diff_path),
        validation=dict(ram_generated_bytes=len(candidate), ram_generated_sha256=digest(candidate), byte_equal=True,
            previous_patch_count=len(specification['patches']), new_patch_count=len(after_specification['patches']),
            manifest_rows=len(manifest), existing_patch_bytes_preserved=True, other_manifest_bytes_preserved=True,
            target_manifest_fields_changed=['port_sha256', 'patch_ids'], protected_inputs_unchanged=True,
            free_trait_units_body_unchanged=True, checked_preflight_before_first_write=True),
        logical_bytes_delta_mutable=sum(len(outputs[p]) - next(r['bytes'] for r in before if r['path'] == str(p)) for p in outputs))
    RECEIPT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    verify()


if __name__ == '__main__':
    main()
