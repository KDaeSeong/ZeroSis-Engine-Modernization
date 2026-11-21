"""Give String access to its form metadata without changing SDK object layouts."""
import json
from collect_baseline import PROJECT, digest

PREFIX = 'localization_callers_'


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    base = PROJECT / 'evidence/sdk_x64/attempts/attempt_015/sdk_x64_patches.json'
    prior = json.loads(base.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith(PREFIX)]
    if retained != prior['patches'] or len(retained) != 480:
        raise RuntimeError('Accepted 480-patch baseline changed')
    relative = 'CvLocalization/include/CvLocalization.h'
    source = PROJECT / 'Source/SDK_BNW_Original' / relative
    old = '\t\tbool Compose(const std::vector<ParameterArgument>& arguments);\r\n\tprivate:'
    if source.read_bytes().decode('latin1').count(old) != 1:
        raise RuntimeError('Localization form access anchor changed')
    new = old + '\r\n\t\t// String owns these forms; access does not change their object layout.\r\n\t\tfriend class String;'
    additions = [dict(id=PREFIX+'form_metadata_access', file=relative,
        source_sha256=digest(source), old=old, new=new, count=1,
        reason='Permit the real String implementation to set form plurality, traits and composed values; no fields, vtables, signatures or saved formats change.')]
    old = '\t\tCvLocalizationAPI static String Empty;\r\n\t\t\r\n\tprivate:'
    if source.read_bytes().decode('latin1').count(old) != 1:
        raise RuntimeError('Localization composed access anchor changed')
    new = old.replace('\tprivate:', '\tprivate:\r\n\t\t// Internal renderer reads a successfully composed form without composing it twice.\r\n\t\tfriend class StringImplementation;')
    additions.append(dict(id=PREFIX+'composed_form_access', file=relative, source_sha256=digest(source), old=old, new=new, count=1,
        reason='Allow the internal renderer to consume a composed form once; no public API or object/saved layout changes.'))
    plan['patches'] = retained + additions
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [p['id'] for p in plan['patches']
        if p['id'].startswith(('serialization_', 'temp_callers_', 'auto_callers_', 'db_callers_', PREFIX))]
    ledger['unchanged_localization_caller_baseline'] = {'path': str(base), 'sha256': digest(base)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'patches': len(plan['patches']), 'localization_patches': len(additions), 'layout_changed': False}))


if __name__ == '__main__':
    main()
