"""Read-only Windows file-size inventory; distinguish paths, hardlinks and compression."""
from __future__ import annotations
import argparse
from collections import defaultdict
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    started = time.monotonic()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    allocated = kernel.GetCompressedFileSizeW
    allocated.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    allocated.restype = ctypes.c_ulong
    objects, groups, suffixes, biggest, errors, skipped = {}, {}, {}, [], [], []
    count = logical = allocated_paths = 0

    def group(collection, key, identity, length, disk):
        item = collection.setdefault(key, {'files': 0, 'logical_bytes': 0, 'allocated_path_bytes': 0, 'identities': set()})
        item['files'] += 1
        item['logical_bytes'] += length
        item['allocated_path_bytes'] += disk
        item['identities'].add(identity)

    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    try:
                        info = os.stat(path, follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            if getattr(info, 'st_file_attributes', 0) & 0x400:
                                skipped.append(str(path))
                            else:
                                stack.append(path)
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            skipped.append(str(path))
                            continue
                        if not info.st_ino:
                            raise ValueError('No stable Windows file identity')
                        identity = (info.st_dev, info.st_ino)
                        if identity not in objects:
                            high = ctypes.c_ulong()
                            ctypes.set_last_error(0)
                            low = allocated(str(path), ctypes.byref(high))
                            if low == 0xffffffff and ctypes.get_last_error():
                                raise ctypes.WinError(ctypes.get_last_error())
                            objects[identity] = {'bytes': info.st_size, 'allocated': (high.value << 32) | low,
                                                 'path_count': 0, 'first_path': str(path), 'links': info.st_nlink}
                        item = objects[identity]
                        if item['bytes'] != info.st_size:
                            raise ValueError('File changed during inventory')
                        item['path_count'] += 1
                        disk = item['allocated']
                        count += 1
                        logical += info.st_size
                        allocated_paths += disk
                        parts = path.relative_to(root).parts
                        for depth in (1, 2, 3):
                            if len(parts) > depth:
                                group(groups, '/'.join(parts[:depth]), identity, info.st_size, disk)
                        group(suffixes, path.suffix.lower() or '[none]', identity, info.st_size, disk)
                        if info.st_size >= 128 * 1024 * 1024:
                            biggest.append({'path': str(path), 'bytes': info.st_size, 'allocated_bytes': disk,
                                            'links': info.st_nlink})
                    except (OSError, ValueError) as error:
                        errors.append({'path': str(path), 'error': str(error)})
        except OSError as error:
            errors.append({'path': str(directory), 'error': str(error)})

    def rows(collection):
        result = []
        for name, values in collection.items():
            ids = values.pop('identities')
            result.append({'name': name, **values, 'unique_files': len(ids),
                           'unique_allocated_bytes': sum(objects[i]['allocated'] for i in ids)})
        return sorted(result, key=lambda row: row['logical_bytes'], reverse=True)

    report = {'status': 'COMPLETE_METADATA_AUDIT' if not errors and not skipped else 'PARTIAL_METADATA_AUDIT',
              'root': str(root), 'utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': round(time.monotonic()-started, 3), 'path_count': count,
              'unique_file_count': len(objects), 'logical_path_bytes': logical,
              'allocated_path_bytes': allocated_paths,
              'unique_logical_bytes': sum(v['bytes'] for v in objects.values()),
              'unique_allocated_bytes': sum(v['allocated'] for v in objects.values()),
              'hardlinked_path_extra_count': count-len(objects),
              'groups': rows(groups), 'extensions': rows(suffixes),
              'largest_files': sorted(biggest, key=lambda row: row['bytes'], reverse=True)[:50],
              'errors': errors, 'skipped': skipped,
              'limits': ['Allocation is GetCompressedFileSizeW per NTFS file identity; directory/MFT overhead and volume free space are excluded.',
                         'Group unique allocations overlap when a hardlink crosses groups; do not sum those group values.',
                         'This audit reads file metadata and does not hash or delete content.']}
    output = root / 'evidence' / 'storage' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('groups', 'extensions', 'largest_files')}, ensure_ascii=False))
    print(json.dumps({'report': str(output), 'top_groups': report['groups'][:22],
                      'top_extensions': report['extensions'][:12]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
