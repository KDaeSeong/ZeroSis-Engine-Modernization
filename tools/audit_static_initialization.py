"""Inspect PE startup tables and direct instruction edges; never load a DLL.

This is a bounded static inventory, not a proof that arbitrary indirect calls,
exception handlers, imports, or the Windows loader are safe at runtime.
"""
from bisect import bisect_right
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import struct

from collect_baseline import PROJECT, digest, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


class Image:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if self.data[:2] != b'MZ':
            raise RuntimeError('Missing DOS header')
        pe = self.unpack('<I', 0x3c)[0]
        if self.read(pe, 4) != b'PE\0\0' or self.unpack('<H', pe + 4)[0] != 0x8664:
            raise RuntimeError('Expected AMD64 PE image')
        count = self.unpack('<H', pe + 6)[0]
        optional_size = self.unpack('<H', pe + 20)[0]
        optional = pe + 24
        if self.unpack('<H', optional)[0] != 0x20b or optional_size < 240 or not 0 < count <= 96:
            raise RuntimeError('Unsupported PE header')
        self.base = self.unpack('<Q', optional + 24)[0]
        self.entrypoint = self.base + self.unpack('<I', optional + 16)[0]
        self.sections = []
        for i in range(count):
            at = optional + optional_size + i * 40
            name = self.read(at, 8).split(b'\0')[0].decode('ascii')
            virtual_size, rva, size, raw = self.unpack('<IIII', at + 8)
            self.read(raw, size)
            self.sections.append(dict(name=name, rva=rva, virtual_size=virtual_size, size=size, raw=raw))
        self.directories = [self.unpack('<II', optional + 112 + i * 8) for i in range(16)]
        self.tls_callbacks = []
        tls, tls_size = self.directories[9]
        if tls:
            if tls_size < 40:
                raise RuntimeError('Truncated AMD64 TLS directory')
            callbacks = self.unpack('<Q', self.offset(tls + 24, 8))[0]
            if callbacks:
                for index in range(4096):
                    callback = self.unpack('<Q', self.offset(callbacks - self.base + index * 8, 8))[0]
                    if not callback:
                        break
                    self.tls_callbacks.append(callback)
                else:
                    raise RuntimeError('Unterminated TLS callback table')
        self.imports = {}
        imp, length = self.directories[1]
        for offset in range(0, length, 20):
            values = self.unpack('<IIIII', self.offset(imp + offset, 20))
            if not any(values):
                break
            lookup, _, _, module, thunk = values
            module_name = self.cstring(module)
            for index in range(65536):
                value = self.unpack('<Q', self.offset((lookup or thunk) + index * 8, 8))[0]
                if not value:
                    break
                name = ('ordinal:' + str(value & 0xffff)) if value >> 63 else self.cstring(value + 2)
                self.imports[self.base + thunk + index * 8] = dict(module=module_name, name=name)
            else:
                raise RuntimeError('Unterminated import lookup table')
        pdata, length = self.directories[3]
        if length % 12:
            raise RuntimeError('Invalid x64 exception directory length')
        self.functions = []
        for offset in range(0, length, 12):
            start, end, unwind = self.unpack('<III', self.offset(pdata + offset, 12))
            if start >= end:
                raise RuntimeError('Invalid x64 runtime function extent')
            self.functions.append((self.base + start, self.base + end, unwind))
        self.functions.sort()
        self.starts = [row[0] for row in self.functions]

    def read(self, offset, length):
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise RuntimeError('PE file read out of bounds')
        return self.data[offset:offset + length]

    def unpack(self, fmt, offset):
        return struct.unpack(fmt, self.read(offset, struct.calcsize(fmt)))

    def offset(self, rva, length=1):
        for section in self.sections:
            delta = rva - section['rva']
            if 0 <= delta and delta + length <= section['size']:
                return section['raw'] + delta
        raise RuntimeError('RVA is not backed by file bytes: ' + hex(rva))

    def cstring(self, rva):
        at = self.offset(rva)
        end = self.data.find(b'\0', at, min(at + 65536, len(self.data)))
        if end < 0:
            raise RuntimeError('Unterminated PE string')
        return self.data[at:end].decode('ascii')

    def section_bytes(self, name):
        section = next(s for s in self.sections if s['name'] == name)
        return self.read(section['raw'], section['size'])


class Module:
    def __init__(self, name, dll, linkmap, dumpbin, root, mapped_dll=None):
        self.name = name
        self.image = Image(dll)
        self.symbols, self.by_name, self.function_names = {}, {}, {}
        text = read_text(Path(linkmap))
        for line in text.splitlines():
            match = re.match(r'^\s*([\da-f]{4}):([\da-f]{8})\s+(\S+)\s+([\da-f]{16})\s+(.*)$', line, re.I)
            if not match:
                continue
            address = int(match[4], 16)
            row = {'name': match[3], 'owner': match[5].split()[-1]}
            self.symbols.setdefault(address, []).append(row)
            self.by_name.setdefault(match[3], set()).add(address)
            if match[5].split()[0] == 'f':
                self.function_names.setdefault(address, []).append(row)
        self.map_starts = sorted(self.function_names)
        self.mapped_equivalence = None
        if mapped_dll is not None:
            mapped = Image(mapped_dll)
            if self.image.base != mapped.base or [(s['name'], s['rva']) for s in self.image.sections] != [(s['name'], s['rva']) for s in mapped.sections]:
                raise RuntimeError('Diagnostic map layout differs from official DLL')
            for section in ('.text', '.pdata'):
                if self.image.section_bytes(section) != mapped.section_bytes(section):
                    raise RuntimeError('Diagnostic map code/function extents differ from official DLL')
            self.mapped_equivalence = {'mapped_dll': artifact(Path(mapped_dll)), 'same_image_base_and_section_rvas': True,
                                       'identical_text_and_pdata_bytes': True}
        self.tables = []
        for line in text.splitlines():
            match = re.match(r'^\s*(\w{4}):(\w{8})\s+(\w{8})H\s+(\.CRT\$\S+)', line)
            if not match:
                continue
            segment, offset, size = (int(x, 16) for x in match.groups()[:3])
            section = self.image.sections[segment - 1]
            rva = section['rva'] + offset
            if size % 8:
                raise RuntimeError('Non-pointer AMD64 CRT table')
            raw = self.image.read(self.image.offset(rva, size), size)
            if mapped_dll is not None and raw != mapped.read(mapped.offset(rva, size), size):
                raise RuntimeError('Diagnostic map CRT pointers differ from official DLL')
            entries = []
            for index, (address,) in enumerate(struct.iter_unpack('<Q', raw)):
                entries.append({'index': index, 'rva': hex(rva + index * 8), 'target': hex(address),
                                'symbols': self.symbols.get(address, [])})
            self.tables.append({'name': match[4], 'rva': hex(rva), 'bytes': size, 'entries': entries})
        key = digest(Path(dll))[:16]
        log = root / (name + '_' + key + '_disassembly.log')
        metadata = log.with_suffix('.json')
        input_identity = {'dll': artifact(Path(dll)), 'tool': artifact(dumpbin)}
        valid = False
        if metadata.is_file() and log.is_file():
            previous = json.loads(metadata.read_text(encoding='utf-8'))
            valid = previous.get('inputs') == input_identity and previous.get('log') == artifact(log) and previous.get('exit_code') == 0
        if not valid:
            result = run([dumpbin, '/nologo', '/disasm:nobytes', dll], cwd=root, timeout=180)
            log.write_bytes(result.stdout + result.stderr)
            metadata.write_text(json.dumps({'inputs': input_identity, 'log': artifact(log), 'exit_code': result.returncode}, indent=2) + '\n', encoding='utf-8')
            if result.returncode:
                raise RuntimeError('Static disassembly failed')
        self.instructions = {}
        for line in read_text(log).splitlines():
            match = re.match(r'^\s*([\dA-Fa-f]{16}):\s+(\S+)\s*(.*?)\s*$', line)
            if match:
                self.instructions[int(match[1], 16)] = (match[2].lower(), match[3])
        self.addresses = sorted(self.instructions)
        self.next_instruction = dict(zip(self.addresses, self.addresses[1:]))
        self.proof = {'name': name, 'dll': artifact(Path(dll)), 'map': artifact(Path(linkmap)), 'disassembly': artifact(log),
                      'disassembly_record': artifact(metadata), 'map_equivalence': self.mapped_equivalence,
                      'crt_tables': self.tables, 'imported_modules': sorted({r['module'] for r in self.image.imports.values()}),
                      'entrypoint': hex(self.image.entrypoint), 'tls_callbacks': [hex(x) for x in self.image.tls_callbacks],
                      'runtime_functions': len(self.image.functions), 'decoded_instructions': len(self.instructions)}

    def extent(self, address):
        index = bisect_right(self.image.starts, address) - 1
        if index >= 0:
            start, end, unwind = self.image.functions[index]
            if start <= address < end:
                flags = self.image.read(self.image.offset(unwind), 1)[0] >> 3
                return start, end, 'pdata', flags
        index = bisect_right(self.map_starts, address) - 1
        if index >= 0:
            start = self.map_starts[index]
            end = self.map_starts[index + 1] if index + 1 < len(self.map_starts) else self.addresses[-1] + 1
            return start, end, 'map_bound', None
        raise RuntimeError('No function bound at ' + hex(address))

    def inspect(self, address):
        start, end, source, flags = self.extent(address)
        pending, seen = [address], set()
        edges, indirect, destructor_refs = [], [], set()
        missing = []
        while pending:
            pc = pending.pop()
            if pc in seen or not start <= pc < end:
                continue
            seen.add(pc)
            if pc not in self.instructions:
                missing.append(hex(pc)); continue
            operation, operand = self.instructions[pc]
            for match in re.finditer(r'\[([\dA-Fa-f]{16})h?\]', operand):
                value = int(match[1], 16)
                if any(s['name'].startswith('??__F') for s in self.symbols.get(value, [])):
                    destructor_refs.add(value)
            branch = operation.startswith('j') or operation.startswith('loop')
            if operation == 'call' or branch:
                direct = re.fullmatch(r'([\dA-Fa-f]{16})h?', operand)
                imported = re.search(r'\[([\dA-Fa-f]{16})h?\]', operand)
                if direct:
                    target = int(direct[1], 16)
                    if branch and start <= target < end:
                        pending.append(target)
                    else:
                        edges.append({'at': hex(pc), 'operation': operation, 'target': hex(target)})
                elif imported and int(imported[1], 16) in self.image.imports:
                    edges.append({'at': hex(pc), 'operation': operation, 'import': self.image.imports[int(imported[1], 16)]})
                else:
                    indirect.append({'at': hex(pc), 'operation': operation, 'operand': operand})
            if operation in ('ret', 'retn', 'retf', 'jmp', 'int', 'int3', 'ud2'):
                continue
            successor = self.next_instruction.get(pc)
            if successor is not None and successor < end:
                pending.append(successor)
        return {'module': self.name, 'address': hex(address), 'function_start': hex(start), 'end': hex(end),
                'bounds': source, 'unwind_flags': flags, 'symbols': self.symbols.get(start, []),
                'instructions_reached': len(seen), 'direct_edges': edges, 'indirect_transfers': indirect,
                'destructor_address_references': [hex(x) for x in sorted(destructor_refs)], 'missing_instruction_addresses': missing}


def main():
    root = PROJECT / 'evidence/bootstrap/static_initialization'
    root.mkdir(parents=True, exist_ok=True)
    link_path = PROJECT / 'evidence/sdk_x64/link_analysis.json'
    trial_path = PROJECT / 'evidence/debug/link_trial.json'
    link, trial = (json.loads(p.read_text(encoding='utf-8')) for p in (link_path, trial_path))
    check_artifacts([link['generated_dll'], trial['runs'][1]['dll'], trial['runs'][1]['map'], trial['official_link']])
    if link['linker_unresolved_symbol_total'] != 0 or trial['official_link']['sha256'] != digest(link_path):
        raise RuntimeError('Official DLL/diagnostic link provenance differs')
    dumpbin = Path(trial['linker']['path']).with_name('dumpbin.exe')
    modules = {'GameCore': Module('GameCore', link['generated_dll']['path'], trial['runs'][1]['map']['path'], dumpbin, root, trial['runs'][1]['dll']['path'])}
    inputs = [artifact(link_path), artifact(trial_path)]
    for name in ('Database', 'Localization'):
        provider = next(p for p in link['providers'] if p['name'] == name)
        path = Path(provider['build_report']['path'])
        if digest(path) != provider['build_report']['sha256']:
            raise RuntimeError('Dependency build report changed')
        build = json.loads(path.read_text(encoding='utf-8'))
        check_artifacts([build['dll'], build['map']])
        modules[name] = Module(name, build['dll']['path'], build['map']['path'], dumpbin, root)
        inputs.append(artifact(path))
    by_dll = {m.image.path.name.lower(): m for m in modules.values()}
    startup, roots, unmapped = [], [], []
    for name, module in modules.items():
        for table in module.tables:
            # Include every non-null CRT callback slot, not just compiler XCU entries.
            for row in table['entries']:
                target = int(row['target'], 16)
                if target:
                    entry = {'module': name, 'table': table['name'], **row}
                    startup.append(entry); roots.append((name, target))
                    if not row['symbols']:
                        unmapped.append(entry)
    if unmapped:
        raise RuntimeError('A CRT entry has no map symbol')
    nodes, destroy_roots = {}, set()
    external, cross_module, unknown = [], [], []
    phase_nodes = {}
    def traverse(seeds, phase):
        pending, visited = deque(seeds), set()
        while pending:
            name, address = pending.popleft()
            key = (name, address)
            if key in visited:
                continue
            visited.add(key)
            module = modules[name]
            if address not in module.instructions:
                unknown.append({'phase': phase, 'module': name, 'target': hex(address)}); continue
            if key not in nodes:
                nodes[key] = module.inspect(address)
                nodes[key]['phases'] = []
            node = nodes[key]
            node['phases'].append(phase)
            for ref in node['destructor_address_references']:
                destroy_roots.add((name, int(ref, 16)))
            for edge in node['direct_edges']:
                if 'target' in edge:
                    pending.append((name, int(edge['target'], 16)))
                else:
                    imp = edge['import']; dependency = by_dll.get(imp['module'].lower())
                    targets = dependency.by_name.get(imp['name'], set()) if dependency else set()
                    observation = {'phase': phase, 'from_module': name, 'from_function': hex(address), **edge}
                    if len(targets) == 1:
                        target = next(iter(targets)); pending.append((dependency.name, target))
                        cross_module.append({**observation, 'to_module': dependency.name, 'target': hex(target)})
                    else:
                        external.append(observation)
        phase_nodes[phase] = visited
    tls_roots = [(name, address) for name, module in modules.items() for address in module.image.tls_callbacks]
    traverse(roots + tls_roots, 'startup')
    # Address references identify compiler destructor thunks; they are candidates,
    # not evidence that every possible atexit registration has been recovered.
    destructor_nodes = []
    for name, address in sorted(destroy_roots):
        if address in modules[name].instructions:
            destructor_nodes.append(modules[name].inspect(address))
    traverse(list(destroy_roots), 'destructor_candidates')
    from build_bootstrap_component import body
    globals_path = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGlobals.cpp'
    globals_text = globals_path.read_bytes().decode('latin1')
    init_body = body(globals_text, 'void CvGlobals::init()')
    uninit_body = body(globals_text, 'void CvGlobals::uninit()')
    allocations = [{'field': m[1], 'type': m[2]} for m in re.finditer(r'\b(m_\w+)\s*=\s*FNEW\((\w+)', init_body)]
    deleted = sorted(set(re.findall(r'\bSAFE_DELETE\((m_\w+)\)', uninit_body)))
    missing_delete = [r for r in allocations if r['field'] not in deleted]
    ownership = {'source': artifact(globals_path), 'init_direct_FNEW_assignments': allocations,
                 'uninit_SAFE_DELETE_fields': deleted, 'directly_allocated_fields_missing_from_uninit_deletes': missing_delete,
                 'scope': 'SOURCE_OWNERSHIP_REVIEW_FINDING_NOT_NATIVE_GAME_LIFETIME_PROOF', 'runtime_reproduction_done': False}
    phases = {name: {'functions': len(visited),
                     'indirect_transfers': sum(len(nodes[k]['indirect_transfers']) for k in visited if k in nodes),
                     'missing_instruction_addresses': sum(len(nodes[k]['missing_instruction_addresses']) for k in visited if k in nodes)}
              for name, visited in phase_nodes.items()}
    report = {'status': 'PE_STARTUP_INVENTORY_AND_DIRECT_EDGES_RECORDED_NOT_LOADER_SAFETY_PROOF',
              'builder': artifact(Path(__file__).resolve()), 'inputs': inputs, 'modules': [m.proof for m in modules.values()],
              'startup_entries': startup, 'startup_entries_by_module': dict(Counter(r['module'] for r in startup)),
              'startup_entries_by_owner': dict(Counter(r['symbols'][0]['owner'] for r in startup)),
              'tls_callback_count': len(tls_roots), 'phase_counts': phases, 'globals_ownership_review': ownership,
              'reachable_direct_nodes': list(nodes.values()), 'external_import_boundaries': external,
              'cross_module_edges': cross_module, 'unknown_direct_targets': unknown,
              'referenced_destructor_thunks': destructor_nodes,
              'indirect_transfer_count': sum(len(n['indirect_transfers']) for n in nodes.values()),
              'missing_instruction_count': sum(len(n['missing_instruction_addresses']) for n in nodes.values()),
              'runtime_loader_safety_verified': False, 'exception_handler_paths_traversed': False,
              'all_indirect_calls_resolved': False, 'all_atexit_registrations_recovered': False,
              'destructor_direct_edges_traversed': True, 'destructor_transitive_closure_complete': False,
              'dll_entrypoint_graph_traversed': False, 'argument_values_propagated': False,
              'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'inventory.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'startup_entries': report['startup_entries_by_module'],
                      'direct_nodes': len(nodes), 'phase_counts': phases, 'indirect_transfers': report['indirect_transfer_count'],
                      'unknown_direct_targets': len(unknown), 'destructor_thunks': len(destructor_nodes),
                      'missing_uninit_deletes': missing_delete,
                      'reviewed_binaries_never_loaded': True}))


if __name__ == '__main__':
    main()
