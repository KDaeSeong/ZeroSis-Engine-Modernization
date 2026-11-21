"""Check static bootstrap records against actual bytes, without executing their code."""
from collections import Counter
import json
from pathlib import Path
import re
import struct
from collect_baseline import PROJECT
from audit_static_initialization import Image
from build_bootstrap_component import body
from verify_world_builder_map_object import check_artifacts


def validate():
    path = PROJECT / 'evidence/bootstrap/static_initialization/inventory.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    check_artifacts(report)
    if report['status'] != 'PE_STARTUP_INVENTORY_AND_DIRECT_EDGES_RECORDED_NOT_LOADER_SAFETY_PROOF':
        raise RuntimeError('Wrong static inventory scope')
    if len(report['modules']) != 3 or {m['name'] for m in report['modules']} != {'GameCore', 'Database', 'Localization'}:
        raise RuntimeError('Missing owned DLL in bootstrap inventory')
    images = {}
    rebuilt = []
    for module in report['modules']:
        image = Image(module['dll']['path']); images[module['name']] = image
        if [hex(x) for x in image.tls_callbacks] != module['tls_callbacks']:
            raise RuntimeError('TLS callback bytes differ')
        for table in module['crt_tables']:
            data = image.read(image.offset(int(table['rva'], 16), table['bytes']), table['bytes'])
            if [hex(value[0]) for value in struct.iter_unpack('<Q', data)] != [r['target'] for r in table['entries']]:
                raise RuntimeError('Recorded CRT table does not match DLL bytes')
            rebuilt += [{'module': module['name'], 'table': table['name'], **row}
                        for row in table['entries'] if int(row['target'], 16)]
        if module['map_equivalence'] is not None:
            mapped = Image(module['map_equivalence']['mapped_dll']['path'])
            if image.base != mapped.base or any(image.section_bytes(s) != mapped.section_bytes(s) for s in ('.text', '.pdata')):
                raise RuntimeError('Official/mapped DLL code equivalence changed')
    if rebuilt != report['startup_entries'] or dict(Counter(r['module'] for r in rebuilt)) != report['startup_entries_by_module']:
        raise RuntimeError('CRT startup accounting differs')
    if report['startup_entries_by_module'] != {'GameCore': 136, 'Localization': 2} or report['tls_callback_count'] != 0:
        raise RuntimeError('Bootstrap table baseline changed; review it explicitly')
    if any(not r['symbols'] for r in rebuilt) or report['unknown_direct_targets'] or report['missing_instruction_count']:
        raise RuntimeError('Static address inventory has unmapped/missing direct code')
    nodes = report['reachable_direct_nodes']
    for phase, counts in report['phase_counts'].items():
        selected = [n for n in nodes if phase in n['phases']]
        actual = {'functions': len(selected), 'indirect_transfers': sum(len(n['indirect_transfers']) for n in selected),
                  'missing_instruction_addresses': sum(len(n['missing_instruction_addresses']) for n in selected)}
        if actual != counts:
            raise RuntimeError('Phase call-edge accounting differs')
    for node in nodes:
        image = images[node['module']]
        image.offset(int(node['address'], 16) - image.base)
    ownership = report['globals_ownership_review']
    source = Path(ownership['source']['path']).read_bytes().decode('latin1')
    init = body(source, 'void CvGlobals::init()'); uninit = body(source, 'void CvGlobals::uninit()')
    assignments = [{'field': m[1], 'type': m[2]} for m in re.finditer(r'\b(m_\w+)\s*=\s*FNEW\((\w+)', init)]
    deleted = sorted(set(re.findall(r'\bSAFE_DELETE\((m_\w+)\)', uninit)))
    if assignments != ownership['init_direct_FNEW_assignments'] or deleted != ownership['uninit_SAFE_DELETE_fields']:
        raise RuntimeError('Source ownership inventory changed')
    if [r for r in assignments if r['field'] not in deleted] != ownership['directly_allocated_fields_missing_from_uninit_deletes']:
        raise RuntimeError('Recorded unresolved ownership finding differs')
    if ownership['runtime_reproduction_done'] or any(report[k] for k in (
            'runtime_loader_safety_verified', 'exception_handler_paths_traversed', 'all_indirect_calls_resolved',
            'all_atexit_registrations_recovered', 'destructor_transitive_closure_complete',
            'dll_entrypoint_graph_traversed', 'argument_values_propagated',
            'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Static report claims unperformed runtime/complete-path verification')
    return report


if __name__ == '__main__':
    report = validate()
    print(json.dumps({'status': 'STATIC_BOOTSTRAP_RECORDS_MATCH_CURRENT_BYTES_RUNTIME_GATE_OPEN',
                      'startup_entries': len(report['startup_entries']), 'direct_nodes': len(report['reachable_direct_nodes']),
                      'runtime_verified': False, 'ownership_findings_still_open': report['globals_ownership_review']['directly_allocated_fields_missing_from_uninit_deletes']}))
