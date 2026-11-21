"""Harden actual SDK temporary-array ownership and the BNW embedded database callers."""
import json
from collect_baseline import PROJECT,digest

PREFIX='temp_callers_'

def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_011/sdk_x64_patches.json';prior=json.loads(base.read_text(encoding='utf-8'))
    retained=[p for p in plan['patches'] if not p['id'].startswith(PREFIX)]
    if retained!=prior['patches']:raise RuntimeError('The accepted 452-patch baseline changed; review before caller edits')
    baseline_count=len(retained)
    plan['patches']=retained;working={}
    def current(relative):
        if relative not in working:
            text=(PROJECT/'Source/SDK_BNW_Original'/relative).read_bytes().decode('latin1')
            for patch in retained:
                if patch['file']==relative:
                    if text.count(patch['old'])!=patch['count']:raise RuntimeError('Baseline patch drift')
                    text=text.replace(patch['old'],patch['new'])
            working[relative]=text
        return working[relative]
    def add(relative,name,old,new,reason):
        if current(relative).count(old)!=1:raise RuntimeError('Caller patch match drift: '+name)
        source=PROJECT/'Source/SDK_BNW_Original'/relative
        plan['patches'].append(dict(id=PREFIX+name,file=relative,source_sha256=digest(source),old=old,new=new,count=1,reason=reason))
        working[relative]=working[relative].replace(old,new)
    def windows(text):return text.strip('\n').replace('\n','\r\n')
    header='FirePlace/include/FireWorks/FTempHeap.h'
    add(header,'standard_headers','#include "FUncopyable.h"','#include "FUncopyable.h"\r\n#include <new>\r\n#include <stdexcept>\r\n#include <climits>',
        'Declare checked-size and allocation failure contracts without modifying the TempHeap ABI.')
    text=current(header);start=text.index('struct FTempHeapFastVectorAllocator');end=text.index('\r\n};',start)+4
    add(header,'vector_allocator',text[start:end],windows('''
struct FTempHeapFastVectorAllocator
{
    static void* AllocAligned(unsigned int nBytes, unsigned int nAlign, unsigned int nAllocPool, unsigned int nAllocSubID)
    {
        if (!nBytes) return NULL;
        if (nAlign && (nAlign & (nAlign - 1))) throw std::invalid_argument("Invalid temporary vector alignment");
        (void)nAllocPool; (void)nAllocSubID;
        void* result = nAlign <= 16 ? GetTempHeap()->Allocate(nBytes) : NULL;
        if (!result) result = FMALLOCALIGNED(nBytes, nAlign, nAllocPool, nAllocSubID);
        if (!result) throw std::bad_alloc();
        return result;
    }
    static void FreeAligned(void* memory)
    {
        if (!memory) return;
        TempHeap* heap = GetTempHeap();
        if (heap->OwnsAllocation(static_cast<byte*>(memory))) heap->DeAllocate(static_cast<byte*>(memory));
        else FFREEALIGNED(memory);
    }
};
'''),'Zero bytes never acquire an arena lease; over-aligned allocations bypass the arena; preserve matched aligned frees and explicit failure.')
    text=current(header);start=text.index('template< class T, int POOL, int TAG >');end=text.index('\r\n};',start)+4
    add(header,'array_ownership',text[start:end],windows('''
inline size_t FTempHeapCheckedArrayBytes(size_t count, size_t stride)
{
    if (count && stride > static_cast<size_t>(-1) / count) throw std::length_error("Temporary array size overflow");
    return count * stride;
}

template<class T, int POOL, int TAG>
class FTempArray : public FUncopyable
{
public:
    FTempArray(uint count) : m_pAlloc(NULL), m_pHeap(NULL)
    {
        const size_t bytes = FTempHeapCheckedArrayBytes(count, sizeof(T));
        if (!bytes) return;
        if (bytes <= UINT_MAX && __alignof(T) <= 16)
        {
            TempHeap* heap = GetTempHeap();
            m_pAlloc = reinterpret_cast<T*>(heap->Allocate(static_cast<uint>(bytes)));
            if (m_pAlloc) { m_pHeap = heap; return; }
        }
        m_pAlloc = reinterpret_cast<T*>(FMALLOCALIGNED(bytes, __alignof(T), POOL, TAG));
        if (!m_pAlloc) throw std::bad_alloc();
    }
    ~FTempArray()
    {
        if (!m_pAlloc) return;
        if (m_pHeap) m_pHeap->DeAllocate(reinterpret_cast<const byte*>(m_pAlloc));
        else FFREEALIGNED(m_pAlloc);
    }
    operator const T*() const { return m_pAlloc; }
    operator T*() { return m_pAlloc; }
    T* operator->() const { return m_pAlloc; }
    const T* get() const { return m_pAlloc; }
    T* get() { return m_pAlloc; }
private:
    T* m_pAlloc;
    TempHeap* m_pHeap;
};
'''),'Check native product before uint narrowing; track actual arena owner; zero size has no lease; aligned fallback retains full size and throws on failure. Raw storage still does not construct T.')
    game='CvGameCoreDLL_Expansion2/CvGame.cpp'
    add(game,'database_include','#include "CvCheckedNarrow.h"','#include "CvCheckedNarrow.h"\r\n#include "CvEmbeddedDatabaseIO.h"',
        'Use the directly tested embedded database I/O helper from the BNW caller.')
    text=current(game);start=text.index('\t\tFIFile* pkFile = FFILESYSTEM.Create(wstrDatabasePath.c_str(), FIFile::modeWrite);')
    end=text.index('\r\n\t}\r\n\r\n\t//when loading from file',start)
    add(game,'database_read',text[start:end],'\t\tCvEmbeddedDatabase::Read(kStream, wstrDatabasePath, lSize);',
        'Read the full payload before creating a replacement; check all transfers and flush/close/replace; retain the old cache on ordinary precommit failures.')
    text=current(game);start=text.index('\t//Need to Convert the UTF-8 string into a wide character string so windows can open this file.',text.index('void CvGame::Write(FDataStream&'))
    end=text.index('\r\n}\r\n\r\n//\t---------------------------------------------------------------------------\r\nvoid CvGame::WriteSupportingClassData',start)
    add(game,'database_write',text[start:end],windows('''
    const std::wstring wstrDatabasePath = CvStringUtils::FromUTF8ToUTF16(strPath);
    CvEmbeddedDatabase::Write(kStream, wstrDatabasePath);
'''),'Preserve the uint32-size/raw-payload format; buffer ownership and handle cleanup are scoped; reject size/read failures before serializing the field.')
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(('serialization_',PREFIX))]
    ledger['unchanged_temp_heap_caller_baseline']={'path':str(base),'sha256':digest(base)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'caller_patches':len(plan['patches'])-baseline_count,'accepted_baseline_unchanged':True}))
if __name__=='__main__':main()
