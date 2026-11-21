#pragma once

// Resolve a required Great Work hash without writing any stream bytes.
// Lookup owns the Type pointer until Hash returns; no SDK headers are needed.
#include <cstdint>
#include <stdexcept>

namespace ZeroSisSerialization {

template<class Lookup>
std::uint32_t ResolveRequiredUnitGreatWorkHash(Lookup& lookup) {
    if (!lookup.DatabaseReady())
        throw std::runtime_error("Unit Great Work save database is unavailable");
    if (!lookup.Prepare())
        throw std::runtime_error("Unit Great Work save query preparation failed");
    if (!lookup.Bind())
        throw std::runtime_error("Unit Great Work save query binding failed");
    if (!lookup.Step())
        throw std::runtime_error("Unit Great Work save query returned no row");
    const char* type = lookup.Type();
    if (!type || type[0] == '\0')
        throw std::runtime_error("Unit Great Work save type is empty");
    const std::uint32_t hash = lookup.Hash(type);
    if (hash == 0)
        throw std::runtime_error("Unit Great Work save hash is zero");
    return hash;
}

template<class Resolver>
std::uint32_t UnitGreatWorkHashForSave(bool hasWork, Resolver resolve) {
    if (!hasWork) return 0;
    const std::uint32_t hash = resolve();
    if (hash == 0)
        throw std::runtime_error("Unit Great Work save hash is zero");
    return hash;
}

} // namespace ZeroSisSerialization
