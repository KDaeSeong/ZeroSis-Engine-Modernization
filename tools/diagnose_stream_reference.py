"""Capture startup faults of our own standalone reference child only."""
import ctypes as c
from ctypes import wintypes as w
import json
import struct
import subprocess
import time
from collect_baseline import PROJECT

def main():
    k = c.WinDLL('kernel32', use_last_error=True)
    k.WaitForDebugEvent.argtypes = [c.c_void_p, w.DWORD]
    k.ContinueDebugEvent.argtypes = [w.DWORD,w.DWORD,w.DWORD]
    k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD]
    k.CloseHandle.argtypes = [w.HANDLE]
    k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenThread.restype=w.HANDLE
    k.Wow64GetThreadContext.argtypes=[w.HANDLE,c.c_void_p]
    k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
    event = c.create_string_buffer(1024)
    exe=PROJECT/'Build/Streams_reference/x86/stream_reference.exe'
    p=subprocess.Popen([str(exe),'memory'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       creationflags=0x2 | subprocess.CREATE_NO_WINDOW)
    records=[]
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if not k.WaitForDebugEvent(event,200): continue
            code,pid,tid=struct.unpack_from('<III',event.raw)
            row={'event':code,'pid':pid,'tid':tid}
            handled=0x10002
            if code in (3,6):
                handle=struct.unpack_from('<Q',event.raw,16)[0]
                base=struct.unpack_from('<Q',event.raw,40 if code==3 else 24)[0]
                path=c.create_unicode_buffer(32768)
                if handle:
                    k.GetFinalPathNameByHandleW(handle,path,len(path),0)
                    k.CloseHandle(handle)
                row.update(base=hex(base),path=path.value)
            if code==1:
                fault=struct.unpack_from('<I',event.raw,16)[0]
                row.update(exception=hex(fault),address=hex(struct.unpack_from('<Q',event.raw,32)[0]),
                           first_chance=struct.unpack_from('<I',event.raw,168)[0])
                if fault not in (0x80000003,0x4000001f): handled=0x80010001
                if fault==0xc0000005:
                    thread=k.OpenThread(8,False,tid); ctx=c.create_string_buffer(716)
                    struct.pack_into('<I',ctx,0,0x10007)
                    if k.Wow64GetThreadContext(thread,ctx):
                        esp=struct.unpack_from('<I',ctx.raw,196)[0]
                        stack=c.create_string_buffer(128)
                        if k.ReadProcessMemory(int(p._handle),esp,stack,len(stack),None):
                            row['stack']=[hex(n) for n in struct.unpack('<32I',stack.raw)]
                    k.CloseHandle(thread)
            records.append(row)
            k.ContinueDebugEvent(pid,tid,handled)
            if code==5: break
    finally:
        if p.poll() is None: p.kill()
        out,err=p.communicate(timeout=5)
    result={'events':records,'returncode':p.returncode,'stdout':out.decode('ascii',errors='replace'),'stderr':err.decode('ascii',errors='replace')}
    (PROJECT/'evidence/streams/reference/startup_diagnostic.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__': main()
