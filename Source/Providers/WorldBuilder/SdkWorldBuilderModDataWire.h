#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace ZeroSisWorldBuilder {
struct ModField { std::uint32_t type,name,value; };
struct ModSchema { std::vector<ModField> fields;std::vector<std::vector<std::uint32_t> > enums; };
struct ModDocument { ModSchema map,plot;std::vector<std::uint32_t> values;std::vector<char> strings; };
// All serialized integers remain little-endian 32-bit values on both platforms.
// Exact mode rejects truncated/trailing data. The legacy pointer-only SDK API
// must receive trusted, already bounded data; it cannot establish input length.
ModDocument ReadModDocument(const void* bytes,std::size_t size,bool exact=true);
std::vector<unsigned char> WriteModDocument(const ModDocument& document);
void ValidateModDocument(const ModDocument& document);
}
