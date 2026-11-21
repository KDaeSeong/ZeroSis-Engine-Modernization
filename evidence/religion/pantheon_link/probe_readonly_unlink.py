"""Test one readonly hardlink deletion using only two disposable owned names."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import stat

STAGE = Path(__file__).absolute().parent
SOURCE = STAGE / 'readonly_unlink_probe.source.tmp'
TARGET = STAGE / 'readonly_unlink_probe.target.tmp'
OUTPUT = STAGE / 'readonly_unlink_probe.json'
DATA = b'ZS readonly unlink probe\n'
FLAGS = 0x15

class StandardInfo(ctypes.Structure):
    _fields_ = [('AllocationSize', ctypes.c_longlong), ('EndOfFile', ctypes.c_longlong),
               ('NumberOfLinks', ctypes.c_uint32), ('DeletePending', ctypes.c_ubyte),
               ('Directory', ctypes.c_ubyte)]

class FileIdInfo(ctypes.Structure):
    _fields_ = [('VolumeSerialNumber', ctypes.c_ulonglong), ('FileId', ctypes.c_ubyte * 16)]

class BasicInfo(ctypes.Structure):
    _fields_ = [('CreationTime', ctypes.c_longlong), ('LastAccessTime', ctypes.c_longlong),
               ('LastWriteTime', ctypes.c_longlong), ('ChangeTime', ctypes.c_longlong),
               ('FileAttributes', ctypes.c_uint32)]

def observe(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and not info.st_file_attributes & 0x400
    assert path.read_bytes() == DATA
    return dict(device=str(info.st_dev), file_id=format(info.st_ino, 'x'),
                bytes=info.st_size, mtime_ns=str(info.st_mtime_ns),
                attributes=info.st_file_attributes, links=info.st_nlink,
                sha256=hashlib.sha256(DATA).hexdigest())

def main():
    assert not any(os.path.lexists(q) for q in (SOURCE, TARGET, OUTPUT))
    assert all(q.parent == STAGE for q in (SOURCE, TARGET, OUTPUT))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetFileInformationByHandleEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_uint32]
    kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
    kernel.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_uint32]
    kernel.SetFileInformationByHandle.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    def remove_link(path):
        expected = observe(path)
        handle = kernel.CreateFileW('\\\\?\\' + str(path), 0x10080, 5, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            standard, identity, basic = StandardInfo(), FileIdInfo(), BasicInfo()
            for kind, value in ((1, standard), (18, identity), (0, basic)):
                if not kernel.GetFileInformationByHandleEx(handle, kind, ctypes.byref(value), ctypes.sizeof(value)):
                    raise ctypes.WinError(ctypes.get_last_error())
            assert str(identity.VolumeSerialNumber) == expected['device']
            assert format(int.from_bytes(identity.FileId, 'little'), 'x') == expected['file_id']
            assert standard.EndOfFile == expected['bytes'] and not standard.Directory and not standard.DeletePending
            assert standard.NumberOfLinks == expected['links']
            assert basic.FileAttributes == expected['attributes']
            assert str(basic.LastWriteTime * 100 - 11644473600000000000) == expected['mtime_ns']
            disposition = ctypes.c_uint32(FLAGS)
            if not kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            assert kernel.CloseHandle(handle)
        assert not os.path.lexists(path)
        return expected
    report = dict(schema='zerosis.pantheon_link.readonly_unlink_probe.v1', status='FAIL',
        bytes=len(DATA), source=str(SOURCE), target=str(TARGET), flags=FLAGS,
        ignore_readonly_attribute=True, force_image_section_check_requested=True,
        only_disposable_owned_names_used=True, game_process_queries=0,
        retail_user_state_accessed=False, host_gamecore_hwnd_executed=False)
    try:
        with SOURCE.open('xb') as stream:
            stream.write(DATA)
        os.link(SOURCE, TARGET)
        assert SOURCE.read_bytes() == TARGET.read_bytes() == DATA
        os.chmod(SOURCE, stat.S_IREAD)
        before, target_before = observe(SOURCE), observe(TARGET)
        assert before == target_before and before['attributes'] & 1 and before['links'] == 2
        remove_link(TARGET)
        after = observe(SOURCE)
        assert after['links'] == 1
        assert {k:v for k,v in before.items() if k != 'links'} == {k:v for k,v in after.items() if k != 'links'}
        report.update(status='PASS_READONLY_LINK_UNLINK_ATTRIBUTES_PRESERVED',
            source_before=before, source_after=after, target_absent=True,
            handle_identity_verified=True, surviving_alias_attributes_unchanged=True)
        remove_link(SOURCE)
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__, error=str(error),
                      winerror=getattr(error, 'winerror', None))
    finally:
        # Fallback cleanup changes attributes only on these exact disposable files.
        fallback = False
        for path in (TARGET, SOURCE):
            if os.path.lexists(path):
                assert observe(path)['sha256'] == hashlib.sha256(DATA).hexdigest()
                os.chmod(path, stat.S_IWRITE)
                path.unlink()
                fallback = True
        report.update(temporary_files_removed=not SOURCE.exists() and not TARGET.exists(),
                      test_only_fallback_cleanup_used=fallback)
        with OUTPUT.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report))
    return 0 if report['status'].startswith('PASS_') else 1

if __name__ == '__main__':
    raise SystemExit(main())
