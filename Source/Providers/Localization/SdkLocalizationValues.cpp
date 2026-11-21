#define CvLocalizationAPI __declspec(dllexport)
#include "SdkLocalizationIncludes.h"
#include <limits>

namespace Localization {
SharedString::SharedString() : m_Buffer(), m_BufferLength(0), m_offset(0), m_length(0) {}
SharedString::SharedString(const char* text, size_t length) : m_Buffer(), m_BufferLength(0), m_offset(0), m_length(0) {
    if (!text && length) throw std::invalid_argument("Null localization string with nonzero length");
    if (length == (std::numeric_limits<size_t>::max)()) throw std::length_error("Localization string size overflow");
    std::shared_ptr<char> candidate(new char[length + 1], std::default_delete<char[]>());
    if (length) std::memcpy(candidate.get(), text, length);
    candidate.get()[length] = '\0';
    m_Buffer.swap(candidate); m_BufferLength = length + 1; m_length = length;
}
SharedString::SharedString(const SharedString& other)
    : m_Buffer(other.m_Buffer), m_BufferLength(other.m_BufferLength), m_offset(other.m_offset), m_length(other.m_length) {}
SharedString& SharedString::operator=(const SharedString& other) {
    if (this != &other) { m_Buffer = other.m_Buffer; m_BufferLength = other.m_BufferLength; m_offset = other.m_offset; m_length = other.m_length; }
    return *this;
}
const char* SharedString::GetBuffer(size_t& length) const { length = m_BufferLength; return m_Buffer.get(); }
const char* SharedString::GetString(size_t& length) const { length = m_length; return m_Buffer ? m_Buffer.get() + m_offset : NULL; }
size_t SharedString::GetBufferLength() const { return m_BufferLength; }
size_t SharedString::GetOffset() const { return m_offset; }
size_t SharedString::GetLength() const { return m_length; }
bool SharedString::SetOffsetAndLength(size_t offset, size_t length) {
    if (offset > m_BufferLength || length > m_BufferLength - offset) return false;
    m_offset = offset; m_length = length; return true;
}

StringParameter::StringParameter() : ArgumentIndex(0), uiTextKeyStart(0), lenTextKey(0), uiParameterStart(0), uiParameterEnd(0),
    uiTransformTagStart(0), uiTransformTagEnd(0), m_injected_parameters() {}
StringParameter::StringParameter(const StringParameter& other) : ArgumentIndex(other.ArgumentIndex),
    uiTextKeyStart(other.uiTextKeyStart), lenTextKey(other.lenTextKey), uiParameterStart(other.uiParameterStart), uiParameterEnd(other.uiParameterEnd),
    uiTransformTagStart(other.uiTransformTagStart), uiTransformTagEnd(other.uiTransformTagEnd), m_injected_parameters(other.m_injected_parameters) {}
}
