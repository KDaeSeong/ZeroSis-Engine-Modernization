"""Observe one installed-game startup without changing the executable or settings."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import struct
import time


class StartupInfo(c.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
                ('title', w.LPWSTR), ('x', w.DWORD), ('y', w.DWORD),
                ('cx', w.DWORD), ('cy', w.DWORD), ('cxchars', w.DWORD),
                ('cychars', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
                ('show', w.WORD), ('reservedsize', w.WORD), ('reservedbytes', c.c_void_p),
                ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]


class ProcessInfo(c.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE),
                ('pid', w.DWORD), ('tid', w.DWORD)]


class DebugEvent(c.Structure):
    _fields_ = [('kind', w.DWORD), ('pid', w.DWORD), ('tid', w.DWORD),
                ('padding', w.DWORD), ('data', c.c_ubyte * 160)]


def main():
    if c.sizeof(c.c_void_p) != 8:
        raise RuntimeError('This observer requires 64-bit Python')
    k = c.WinDLL('kernel32', use_last_error=True)
    k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL,
                                w.DWORD, c.c_void_p, w.LPCWSTR,
                                c.POINTER(StartupInfo), c.POINTER(ProcessInfo)]
    k.CreateProcessW.restype = w.BOOL
    k.WaitForDebugEvent.argtypes = [c.POINTER(DebugEvent), w.DWORD]
    k.WaitForDebugEvent.restype = w.BOOL
    k.ContinueDebugEvent.argtypes = [w.DWORD, w.DWORD, w.DWORD]
    k.ContinueDebugEvent.restype = w.BOOL
    k.DebugSetProcessKillOnExit.argtypes = [w.BOOL]
    k.DebugActiveProcessStop.argtypes = [w.DWORD]
    k.CloseHandle.argtypes = [w.HANDLE]
    k.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p,
                                   c.c_size_t, c.POINTER(c.c_size_t)]
    k.ReadProcessMemory.restype = w.BOOL
    k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
    k.GetFinalPathNameByHandleW.restype = w.DWORD
    root = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
    exe = root / 'CivilizationV_DX11.exe'
    os.environ['SteamAppId'] = os.environ['SteamGameId'] = '8930'
    si, pi = StartupInfo(), ProcessInfo()
    si.cb = c.sizeof(si)
    command = c.create_unicode_buffer('"' + str(exe) + '"')
    if not k.CreateProcessW(str(exe), command, None, None, False, 2, None,
                            str(root), c.byref(si), c.byref(pi)):
        raise c.WinError(c.get_last_error())
    k.DebugSetProcessKillOnExit(False)
    records, modules, handles = [], [], set()
    exited, started = False, time.monotonic()

    def read(address, length):
        buffer, count = c.create_string_buffer(length), c.c_size_t()
        if not k.ReadProcessMemory(pi.process, address, buffer, length, c.byref(count)):
            return b''
        return buffer.raw[:count.value]

    try:
        while time.monotonic() - started < 35:
            event = DebugEvent()
            if not k.WaitForDebugEvent(c.byref(event), 500):
                error = c.get_last_error()
                if error == 121:
                    continue
                raise c.WinError(error)
            data, continuation = bytes(event.data), 0x00010002
            if event.kind == 1:
                code, address, first = struct.unpack_from('<I', data)[0], struct.unpack_from('<Q', data, 16)[0], struct.unpack_from('<I', data, 152)[0]
                owner = next((m for m in reversed(modules) if m['base'] <= address < m['base'] + m['size']), None)
                if len(records) < 100:
                    records.append({'event': 'exception', 'code': hex(code), 'address': hex(address),
                                    'first_chance': bool(first), 'module': owner['path'] if owner else None})
                if code not in (0x80000003, 0x4000001f):
                    continuation = 0x80010001
            elif event.kind in (3, 6):
                filehandle = struct.unpack_from('<Q', data)[0]
                base = struct.unpack_from('<Q', data, 24 if event.kind == 3 else 8)[0]
                name = c.create_unicode_buffer(32768)
                path = name.value if not filehandle else ''
                if filehandle:
                    k.GetFinalPathNameByHandleW(filehandle, name, len(name), 0)
                    path = name.value
                    k.CloseHandle(filehandle)
                size = 0
                header = read(base, 4096)
                if len(header) >= 64 and header[:2] == b'MZ':
                    pe = struct.unpack_from('<I', header, 60)[0]
                    if pe + 84 <= len(header):
                        size = struct.unpack_from('<I', header, pe + 80)[0]
                modules.append({'path': path, 'base': base, 'size': size})
                if event.kind == 3:
                    handles.update(struct.unpack_from('<QQ', data, 8))
            elif event.kind == 2:
                handles.add(struct.unpack_from('<Q', data)[0])
            elif event.kind == 8:
                pointer, wide, length = struct.unpack_from('<QHH', data)
                raw = read(pointer, min(length * (2 if wide else 1), 8192))
                message = raw.decode('utf-16-le' if wide else 'mbcs', errors='replace').rstrip('\x00')
                if len(records) < 100:
                    records.append({'event': 'debug_output', 'text': message[:2000]})
            elif event.kind == 5:
                records.append({'event': 'exit', 'code': hex(struct.unpack_from('<I', data)[0])})
                exited = True
            if not k.ContinueDebugEvent(event.pid, event.tid, continuation):
                raise c.WinError(c.get_last_error())
            if exited:
                break
    finally:
        if not exited:
            k.DebugActiveProcessStop(pi.pid)
        for handle in handles | {pi.process, pi.thread}:
            if handle:
                k.CloseHandle(handle)
    print(json.dumps({'pid': pi.pid, 'exited': exited, 'seconds': round(time.monotonic() - started, 2),
                      'executable_or_settings_changed': False, 'events': records}, ensure_ascii=False))


if __name__ == '__main__':
    main()
