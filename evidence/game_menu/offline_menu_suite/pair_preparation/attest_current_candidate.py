"""Independent file-only current menu Host attestation and six-target draft.

This script never invokes a compiler, image, provider, SDK or native loader.
Cleanup and profile registration are separate root-reviewed operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_menu_suite_host as builder
import retained_host_runtime_input as retained
import retained_menu_suite_host_input as menu

BUILDER_SHA = 'e276135b4af603d89332c849bf8ff8cba4b10916436f71ae0be71ac700db6fcd'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    return builder.common.artifact(Path(path).absolute())


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--build-report', type=Path, required=True)
    cli.add_argument('--report-sha256', required=True)
    options = cli.parse_args()
    require(__debug__ and sys.dont_write_bytecode and re.fullmatch('[0-9a-f]{64}', options.report_sha256),
            'Use Python -B and an exact successful build-report hash')
    require(artifact(Path(builder.__file__))['sha256'] == BUILDER_SHA, 'Reviewed current build tool changed')
    files = retained._Files(check_metadata=True)
    report_ref = artifact(options.build_report)
    require(report_ref['sha256'] == options.report_sha256, 'Successful Host report pin differs')
    build = files.json(report_ref)
    identifier = build.get('build_id', '')
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', identifier) and
            build.get('schema') == 'zerosis.ui_window_host_build.v1' and build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            all(build.get(name) is False for name in menu.OFFLINE_FIELDS), 'Not a successful current offline Host build')
    output = STAGE / identifier
    require(not output.exists(), 'Independent attestation is single-use; inspect its existing result')
    root = PROJECT / 'Build/UiWindowHost' / identifier
    require(menu.key(report_ref['path']) == menu.key(PROJECT / 'evidence/ui_window_host' / identifier / 'build_result.json') and
            menu.key(build['executable']['path']) == menu.key(root / 'final/ZeroSisHost_x64.exe'),
            'Current Host report/image escaped their exact build roles')
    run_ref = artifact(Path(build['started']['path']).with_name('run.json'))
    run = files.json(run_ref)
    require(run.get('status') == 'PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY' and run['build_id'] == identifier and
            menu.same(run['build_result'], report_ref) and run.get('host_sdk_clr_window_gpu_or_dll_executed') is False,
            'Current successful build/run identity differs')
    phases = ['environment', *('discover_' + name for name in menu.TUS), *('compile_' + name for name in menu.TUS), 'link']
    require([row['phase'] for row in run['commands']] == phases and all(row.get('returncode') == 0 for row in run['commands']) and
            not run['denied_operations'], 'Actual current toolchain phases differ')
    parser, helpers, helper_refs = builder.load_helpers()
    frozen = menu.frozen_rows(build)
    current = menu.rows(build['current_source_inputs'])
    compiler = menu.rows(build['compiler_inputs'])
    for row in [*frozen.values(), *current.values(), *build['protected_artifacts']]:
        files.verify(row)
    actual_frozen = menu.rows(run['materialized'])
    require(set(actual_frozen) == set(frozen) and all(menu.same(row, actual_frozen[path]) for path, row in frozen.items()),
            'Actual current frozen inventory differs')
    aliases, origin_set = {}, set()
    implicit = set(menu.rows(build['implicit_libraries']))
    links = copies = 0
    for path, row in frozen.items():
        origin = menu.key(row['origin'])
        require(origin not in origin_set and Path(row['path']).is_relative_to(root / 'frozen'), 'Frozen origin duplicated or escaped')
        origin_set.add(origin)
        if origin in current:
            require((row['bytes'], row['sha256']) == (current[origin]['bytes'], current[origin]['sha256']), 'Frozen/current source bytes differ')
            aliases[origin] = row
        else:
            require(path in implicit, 'Only exact implicit libraries may lack a live source snapshot')
        if row['materialization'] == 'attested_snapshot_hardlink':
            donor = files.verify(dict(path=row['reused_from_path'], bytes=row['bytes'], sha256=row['sha256']))
            require(files.verify(row)['file_identity'] == donor['file_identity'], 'Declared frozen donor link differs')
            links += 1
        else:
            require(row['materialization'] in ('owned_changed_source_copy', 'owned_added_source_copy') and
                    files.ordinary(row['path']).st_nlink == 1, 'Current source copy is not private')
            copies += 1
    objects, dependency_counts, union = [], [], set()
    require(len(build['final_compilation']['translation_units']) == len(run['discovery']) == 5,
            'Current Host must attest all five actual translation units')
    for index, (unit, name, stem) in enumerate(zip(build['final_compilation']['translation_units'], menu.TUS, menu.STEMS)):
        require(unit['translation_unit'] == name and unit['returncode'] == 0 and
                menu.key(unit['object']['path']) == menu.key(root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj'),
                'Unexpected current five-object compilation role')
        fields = files.json(unit['dependency_report'])['Data']
        actual = {menu.key(path) for path in (fields['Source'], *fields['Includes'])}
        require(actual <= set(compiler) and len(actual) == unit['actual_dependency_count'] == unit['expected_dependency_count'],
                'Actual frozen compiler dependency set differs')
        discovered = {menu.key(path) for path in run['discovery'][index]['actual_paths']}
        require({menu.key(frozen[path]['origin']) for path in actual} == discovered, 'Final dependency set differs from actual syntax discovery')
        raw = menu.read(files, unit['object'])
        coff, defaults = parser.coff(raw), helpers.object_defaults(raw)
        require(coff['machine_hex'] == unit['coff_machine'] == '0x8664' and defaults == unit['default_libraries'],
                'Actual current COFF/directive evidence differs')
        objects.append(dict(translation_unit=name, object=files.verify(unit['object']), coff_machine=coff['machine_hex'],
                            section_count=coff['section_count'], default_libraries=defaults))
        dependency_counts.append(len(actual))
        union.update(actual)
    require(union == set(compiler), 'Current compiler union is incomplete')
    link = menu.read(files, build['link_response']).decode('utf-8-sig').replace('\r\n', '\n')
    require([menu.key(path) for path in re.findall(r'^"([^"\n]+\.obj)"$', link, re.M | re.I)] ==
            [menu.key(row['object']['path']) for row in objects], 'Link did not consume exactly the five attested objects')
    original_header = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
    header = aliases[menu.key(original_header)]
    arrays, order = menu.parse_catalog(menu.read(files, header), 74, ('ZeroSisUiScene', 'ExitConfirm', *('MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout')))
    image = build['executable']
    raw = menu.read(files, image)
    pe, independent_pe = menu.PE(raw), parser.PE(raw)
    catalog, imports = pe.catalog(arrays, order), pe.imports()
    require(catalog == helpers.catalog_summary(independent_pe.catalog(arrays, order)) == build['catalog'] and
            imports == independent_pe.imports() == build['imports']['dependencies'] and
            len(pe.occurrences(menu.MARKER)) == len(independent_pe.occurrences(menu.MARKER)) == 1,
            'Independent current PE/catalog/import/marker observations differ')
    optional = struct.unpack_from('<I', raw, 0x3c)[0] + 24
    require(all(struct.unpack_from('<II', raw, optional + 112 + 8 * index) == (0, 0) for index in (13, 14)),
            'Current Host has CLR or delay-import metadata')
    for field, value in build.items():
        for row in menu.walk(value):
            files.verify(row)
    files.finish()
    output.mkdir()
    attestation = dict(schema='zerosis.menu_suite_host.independent_attestation.v1',
        status='PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS', build_result=report_ref,
        image=files.verify(image), header=files.verify(current[menu.key(original_header)]), frozen_header=files.verify(header),
        run=run_ref, catalog=catalog, imports=imports, restore_marker_readonly_occurrences=1,
        actual_tu_dependency_counts=dependency_counts, compiler_input_count=len(compiler), frozen_input_count=len(frozen),
        current_input_count=len(current), source_manifest_count=len(build['sources']), code_objects_checked=5,
        actual_coff_objects=objects, hardlinked_files=links, private_copies=copies,
        helper_api_refs=helper_refs, host_or_sdk_or_dll_or_window_execution=False, full_native_or_original_ui_acceptance=False)
    attestation_path = output / 'independent_attestation.json'
    attestation_path.write_text(json.dumps(attestation, indent=2) + '\n', encoding='utf-8')
    candidates = [unit['object'] for unit in build['final_compilation']['translation_units']]
    candidates.append(artifact(root / 'read_build_environment.cmd'))
    cleanup = dict(schema='zerosis.menu_suite_host.cleanup_plan.v1', candidates=candidates,
        logical_bytes=sum(row['bytes'] for row in candidates), retained_current_executable=image,
        independent_verification=artifact(attestation_path), historical_object_refs_retired_after_verification=True,
        recursive_deletion=False, originals_saves_default_sdk_or_frozen_sources_deleted=False,
        native_execution=False, root_review_and_exact_action_required=True)
    (output / 'cleanup_plan.json').write_text(json.dumps(cleanup, indent=2) + '\n', encoding='utf-8')
    extras = [row['path'] for path, row in current.items() if path not in aliases]
    draft = dict(schema='zerosis.retained_menu_host.profile_draft.v1', kind='retained_menu_suite', build_id=identifier,
        executable_bytes=image['bytes'], executable_sha256=image['sha256'], catalog=catalog,
        required_payloads=['ZeroSisUiScene', 'ExitConfirm', 'ExitConfirmLayout', 'TouchControlsMenu', 'SaveMapMenu',
                           'MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout'],
        compiler_dependency_count=len(compiler), current_source_count=len(current), source_manifest_count=len(build['sources']),
        materialized_input_count=len(frozen), donor_hardlinks=links, private_source_copies=copies,
        dependency_counts=dependency_counts, import_count=len(imports),
        nonfrozen_current_inputs=[str(Path(path).relative_to(PROJECT)) if Path(path).is_relative_to(PROJECT) else path for path in extras],
        report=report_ref, attestation=artifact(attestation_path), run=run_ref, cleanup_plan=artifact(output / 'cleanup_plan.json'),
        pending_fields=['cleanup_result_path/sha256', 'typed_retirement_ledger_path/sha256', 'final_audit_path/sha256'],
        registered=False, native_execution=False)
    (output / 'profile_draft.json').write_text(json.dumps(draft, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=attestation['status'], build_id=identifier, attestation=artifact(attestation_path),
        cleanup_plan=artifact(output / 'cleanup_plan.json'), catalog_payloads=len(order), code_objects=5,
        compiler_inputs=len(compiler), frozen_inputs=len(frozen), native_execution=False)))


if __name__ == '__main__':
    main()
