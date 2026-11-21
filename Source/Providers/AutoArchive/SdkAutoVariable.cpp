#include "SdkAutoArchiveIncludes.h"

#ifndef FINAL_RELEASE
#error This provider implements the observed FINAL_RELEASE variable ABI only.
#endif

namespace {
void registerVariable(FAutoVariableBase& variable, const std::string& name, FAutoArchive& archive) {
    archive.add(variable);
    try { archive.setVariableName(variable, name); }
    catch (...) { archive.remove(variable); throw; }
}
}

FAutoVariableBase::FAutoVariableBase(const std::string& name, FAutoArchive& archive)
    : m_archiveOwner(NULL), m_registeredName(NULL) { registerVariable(*this, name, archive); }
FAutoVariableBase::FAutoVariableBase(const std::string& name, FAutoArchive& archive, bool callStackTracking)
    : m_archiveOwner(NULL), m_registeredName(NULL) {
    (void)callStackTracking;
    registerVariable(*this, name, archive);
}
FAutoVariableBase::~FAutoVariableBase() { if (m_archiveOwner) m_archiveOwner->remove(*this); }
std::string FAutoVariableBase::getStackTrace() const { return "Stack Trace unavailable"; }
std::string FAutoVariableBase::getStackTraceRemark() const { return std::string(); }
std::string FAutoVariableBase::debugDump(const std::vector<std::pair<std::string, std::string> >& callStacks) const {
    (void)callStacks;
    return std::string("Variable Out Of Sync : ") + name();
}
