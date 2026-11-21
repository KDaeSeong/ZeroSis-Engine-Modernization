#include "SdkFoundationIncludes.h"

FCriticalSection::FCriticalSection() { InitializeCriticalSection(&m_kCriticalSection); }
FCriticalSection::~FCriticalSection() { DeleteCriticalSection(&m_kCriticalSection); }
bool FCriticalSection::Try() { return TryEnterCriticalSection(&m_kCriticalSection)!=FALSE; }
void FCriticalSection::Enter() { EnterCriticalSection(&m_kCriticalSection); }
void FCriticalSection::Leave() { LeaveCriticalSection(&m_kCriticalSection); }
int FCriticalSection::GetLockCount() const { return m_kCriticalSection.LockCount; }
int FCriticalSection::GetRecursionCount() const { return m_kCriticalSection.RecursionCount; }
