"""Materialize the bounded v2 embedded rig inputs and verified x64 curve runtime.

Only private new runtime directories are written. Existing v1 packages need no
CLR dependencies. Animation is presentation data, never a save-schema change.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct

PROJECT = Path(__file__).resolve().parents[1]
BRIDGE_REPORT = PROJECT / 'evidence/granny_animation_bridge/20261005T113900Z/report.json'
RAW_NAMES = frozenset(('unitmodels_stringdatabase.gsd', 'Warrior.gr2', 'Warrior_V2.gr2',
                       'Warrior_V4.gr2', 'Warrior_IdleA.gr2'))
DLL_NAMES = frozenset(('ZeroSisGrannyAnimationBridge.dll', 'Firaxis.Framework.dll',
                       'Firaxis.Framework.Granny.dll', 'Firaxis.Framework.FirePlace.dll',
                       'Firaxis.Framework.Granny.Implx64.dll'))
CLR_CONFIG = (b'<?xml version="1.0"?><configuration><startup useLegacyV2RuntimeActivationPolicy="true">'
              b'<supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/></startup></configuration>')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def artifact(path):
    return {'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size}


def embedded_assets(package):
    """Skip the bounded v1 geometry body, then read v2's fixed safe basenames."""
    path = Path(package)
    if not 20 <= path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError('Unit package size exceeds its bound')
    data = path.read_bytes()
    if data[:12] == b'ZSUNIT01\x01\0\0\0':
        return {}
    if data[:12] != b'ZSUNIT02\x02\0\0\0':
        raise ValueError('Unsupported unit asset version')
    cursor = 12

    def take(count):
        nonlocal cursor
        if count < 0 or count > len(data) - cursor:
            raise ValueError('Truncated unit asset record')
        block = data[cursor:cursor + count]
        cursor += count
        return block

    def word(limit, minimum=1):
        value, = struct.unpack('<I', take(4))
        if not minimum <= value <= limit:
            raise ValueError('Unit asset count exceeds its bound')
        return value

    for _ in range(word(64)):
        take(word(16 * 1024 * 1024, 128))
    vertices = indices = 0
    for _ in range(word(64)):
        take(word(256))
        for _ in range(word(128)):
            word(63, 0)
            vc, ic = word(200000), word(600000)
            vertices += vc
            indices += ic
            if vertices > 1000000 or indices > 3000000 or ic % 3:
                raise ValueError('Unit geometry aggregate exceeds its bound')
            take(vc * 32 + ic * 4)
    files = {}
    for _ in range(word(len(RAW_NAMES))):
        name = take(word(128)).decode('ascii')
        if name not in RAW_NAMES or name in files:
            raise ValueError('Unexpected or duplicate embedded animation file')
        files[name] = take(word(16 * 1024 * 1024))
    if set(files) != RAW_NAMES:
        raise ValueError('Embedded animation input closure is incomplete')
    # Full rig, transforms, topology and weight validation belongs to the native
    # loader. This helper only exposes the fixed data-file materialization set.
    if cursor >= len(data):
        raise ValueError('Animated unit package has no rig records')
    return files


def materialize(package, runtime, materialize_immutable, retained=None):
    files = embedded_assets(package)
    if not files:
        return None, [], []
    runtime = Path(runtime).resolve(strict=True)
    if not runtime.is_relative_to(PROJECT / 'Build'):
        raise ValueError('Animation runtime must stay inside the private Build tree')
    rows, methods = [], []
    for name, payload in files.items():
        target = runtime / name
        with target.open('xb') as f:
            f.write(payload)
        rows.append({'source': 'embedded:' + str(package), **artifact(target)})
    if retained is None:
        report = json.loads(BRIDGE_REPORT.read_text(encoding='utf-8'))
        if report.get('status') != 'PASS_NATIVE_GRANNY_C_ABI_X64' or not report.get('source_inputs_unchanged'):
            raise ValueError('Animation bridge lacks a passing x64 native report')
        dependencies = [report['bridge'], *report['private_sdk_assemblies']]
        # The reused binary must still correspond to its original implementation.
        for name in ('GrannyAnimationBridge.h', 'GrannyAnimationBridge.cpp'):
            source = PROJECT / 'Source/Animation' / name
            if digest(source) != report['source_input_hashes_after'].get(str(source)):
                raise ValueError('Animation bridge source changed since its verified build')
        proof = artifact(BRIDGE_REPORT)
    else:
        dependencies = retained['dependencies']
        proof = retained['bridge_report']
        if digest(Path(proof['path'])) != proof['sha256']:
            raise ValueError('Retained animation bridge proof changed')
    if {Path(row['path']).name for row in dependencies} != DLL_NAMES or len(dependencies) != len(DLL_NAMES):
        raise ValueError('Animation runtime dependency closure is incomplete')
    copied = []
    for row in dependencies:
        source = Path(row['path']).resolve(strict=True)
        if digest(source) != row['sha256']:
            raise ValueError('Animation dependency differs from its verified input')
        target = runtime / source.name
        methods.append(materialize_immutable(source, target, PROJECT / 'Build/RuntimeInputCache'))
        ref = artifact(target)
        if ref['sha256'] != row['sha256']:
            raise ValueError('Materialized animation dependency hash mismatch')
        rows.append({'source': str(source), **ref})
        copied.append(ref)
    config = runtime / 'ZeroSisHost_x64.exe.config'
    with config.open('xb') as f:
        f.write(CLR_CONFIG)
    rows.append({'source': str(Path(__file__)), **artifact(config)})
    return {'format_version': 2, 'bridge_report': proof, 'dependencies': copied,
            'config': artifact(config), 'embedded_inputs': [row for row in rows if Path(row['path']).name in RAW_NAMES],
            'preparer': artifact(Path(__file__))}, rows, methods
