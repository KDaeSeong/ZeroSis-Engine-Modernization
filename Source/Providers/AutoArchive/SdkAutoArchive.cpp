#include "SdkAutoArchiveIncludes.h"
#include <atomic>

#ifndef FINAL_RELEASE
#error This provider implements the observed FINAL_RELEASE archive ABI only.
#endif

namespace {
std::atomic<bool> callStacksEnabled(true);

unsigned int wireCount(size_t value) {
    if (value > UINT_MAX) throw std::length_error("AutoArchive exceeds uint32 wire count");
    return static_cast<unsigned int>(value);
}

unsigned int readCount(FDataStream& stream) {
    unsigned int count = 0;
    stream >> count;
    // Each entry needs at least its uint32 index. Values can have zero-byte encodings.
    if (count > stream.GetSizeLeft() / sizeof(unsigned int))
        throw std::out_of_range("AutoArchive count extends past stream end");
    return count;
}

FAutoVariableBase& readVariable(FDataStream& stream, const std::vector<FAutoVariableBase*>& contents) {
    unsigned int index = 0;
    stream >> index;
    if (index >= contents.size() || !contents[index])
        throw std::out_of_range("Invalid AutoArchive variable index");
    return *contents[index];
}
}

FAutoArchive::FAutoArchive() {}
FAutoArchive::~FAutoArchive() {
    // Variables normally die first. Detach any surviving registration so its base
    // destructor will not call an already destroyed archive.
    for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->m_archiveOwner = NULL;
}

void FAutoArchive::add(FAutoVariableBase& variable) {
    if (variable.m_archiveOwner) throw std::invalid_argument("AutoVariable already has an archive owner");
    if (std::find(m_contents.begin(), m_contents.end(), &variable) != m_contents.end())
        throw std::invalid_argument("Duplicate AutoArchive registration");
    if (m_contents.size() >= UINT_MAX) throw std::length_error("AutoArchive registration limit");
    m_contents.push_back(&variable);
    variable.m_archiveOwner = this;
}

void FAutoArchive::remove(FAutoVariableBase& variable) {
    // The SDK removed only the registration, leaving a dirty pointer and a false
    // delta count. Removal must clean both containers, including repeated calls.
    m_deltas.erase(&variable);
    std::vector<FAutoVariableBase*>::iterator found = std::find(m_contents.begin(), m_contents.end(), &variable);
    if (found != m_contents.end()) m_contents.erase(found);
    if (variable.m_archiveOwner == this) variable.m_archiveOwner = NULL;
}

void FAutoArchive::load(FDataStream& stream) {
    for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->load(stream);
}

void FAutoArchive::save(FDataStream& stream) const {
    for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->save(stream);
}

void FAutoArchive::saveDelta(FDataStream& stream, std::vector<std::pair<std::string, std::string> >& callStacks) const {
    (void)callStacks; // The original FINAL_RELEASE binary leaves this vector unchanged.
    // Validate membership before emitting any bytes. An unregistered pointer can
    // arrive through the public inline touch(), even if remove() is now correct.
    for (std::set<FAutoVariableBase*>::const_iterator it = m_deltas.begin(); it != m_deltas.end(); ++it)
        if (std::find(m_contents.begin(), m_contents.end(), *it) == m_contents.end())
            throw std::invalid_argument("Unregistered AutoArchive delta");
    stream << wireCount(m_deltas.size());
    // Preserve the SDK pointer-order traversal and registration-index wire format.
    // Archives and variable callbacks are owner-thread confined and non-reentrant.
    for (std::set<FAutoVariableBase*>::const_iterator it = m_deltas.begin(); it != m_deltas.end(); ++it) {
        const size_t index = static_cast<size_t>(std::find(m_contents.begin(), m_contents.end(), *it) - m_contents.begin());
        stream << wireCount(index);
        (*it)->saveDelta(stream);
    }
    // On an exception, pending deltas survive. The caller must discard a partial
    // output stream; an archive cannot roll back an arbitrary stream or callback.
    m_deltas.clear();
}

void FAutoArchive::loadDelta(FDataStream& stream) {
    const unsigned int count = readCount(stream);
    for (unsigned int i = 0; i != count; ++i) readVariable(stream, m_contents).loadDelta(stream);
}

void FAutoArchive::clearDelta() {
    for (std::set<FAutoVariableBase*>::const_iterator it = m_deltas.begin(); it != m_deltas.end(); ++it) {
        if (std::find(m_contents.begin(), m_contents.end(), *it) == m_contents.end())
            throw std::invalid_argument("Unregistered AutoArchive delta");
        (*it)->clearDelta();
    }
    m_deltas.clear();
}

void FAutoArchive::reset() {
    // Reset values only; the SDK intentionally leaves pending delta membership alone.
    for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->reset();
}

bool FAutoArchive::hasDeltas() const { return !m_deltas.empty(); }

std::vector<const FAutoVariableBase*> FAutoArchive::findMismatchedVariables(FDataStream& stream) const {
    const unsigned int count = readCount(stream);
    std::vector<const FAutoVariableBase*> result;
    for (unsigned int i = 0; i != count; ++i) {
        FAutoVariableBase& variable = readVariable(stream, m_contents);
        if (!variable.compare(stream)) result.push_back(&variable);
    }
    return result;
}

const FAutoVariableBase* FAutoArchive::findVariable(const std::string& name) const {
    for (size_t i = 0; i != m_contents.size(); ++i)
        if (m_contents[i]->name() == name) return m_contents[i];
    return NULL;
}

void FAutoArchive::EnableCallStacks(bool enabled) { callStacksEnabled.store(enabled, std::memory_order_relaxed); }
bool FAutoArchive::AreCallStacksEnabled() { return callStacksEnabled.load(std::memory_order_relaxed); }

FDataStream& operator<<(FDataStream& stream, const FAutoArchive& archive) { archive.save(stream); return stream; }
FDataStream& operator>>(FDataStream& stream, FAutoArchive& archive) { archive.load(stream); return stream; }
