#pragma once
#include "SdkLocalizationIncludes.h"
#include "SdkLocalizationIcu.h"
#include <mutex>

namespace Localization {
class StringImplementation {
public:
    static bool ReadComposed(String& value, size_t form, std::string& output);
};
}

namespace ZeroSisLocalization {
std::recursive_mutex& RuntimeMutex();
bool IcuReady();
bool IsKnownLanguage(const Localization::Language* language);
const char* LocaleOf(const Localization::Language& language);
bool ValidateMessage(const char* text, size_t length, std::vector<Localization::StringParameter>& parameters);
bool RenderMessage(const char* text, size_t length, const std::vector<Localization::ParameterArgument>& arguments,
                   const Localization::Language& language, std::string& output);
bool TransformArgument(const Localization::ParameterArgument& argument, const std::string& style,
                       const std::string& options, const Localization::Language& language,
                       const std::vector<Localization::ParameterArgument>& arguments, std::string& output);
}
