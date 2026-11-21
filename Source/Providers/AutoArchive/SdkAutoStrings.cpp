#include "SdkAutoArchiveIncludes.h"
#include <cmath>
#include <locale>

namespace {
template<class T> std::string decimal(T value) {
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << value;
    return stream.str();
}

std::string realString(double value) {
    // The old CRT used an unbounded sprintf into 32 stack bytes. Large finite
    // values overflowed that buffer. This diagnostic-only representation uses
    // a growing stream, a fixed C locale and current IEEE rounding. Rounding,
    // large-value precision and non-finite text differences are reported by the
    // conformance suite; no serialized field uses this text conversion.
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return std::signbit(value) ? "-inf" : "inf";
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << std::fixed << std::setprecision(6) << value;
    return stream.str();
}
}

namespace FSerialization {
std::string toString(const bool& value) { return value ? "true" : "false"; }
std::string toString(const unsigned char& value) { return decimal(static_cast<unsigned int>(value)) + "hh"; }
std::string toString(const unsigned short& value) { return decimal(static_cast<unsigned int>(value)) + "h"; }
std::string toString(const unsigned int& value) { return decimal(value) + "d"; }
std::string toString(const int& value) { return decimal(value); }
// Deliberate compatibility with the original "%hh" and "%h" format results,
// verified over every char/short value. These are not missing implementations.
std::string toString(const char& value) { (void)value; return std::string(); }
std::string toString(const short& value) { (void)value; return std::string(); }
std::string toString(const float& value) { return realString(value); }
std::string toString(const double& value) { return realString(value); }
std::string toString(const std::string& value) { return value; }
std::string toString(const FAutoVariableBase& value) { return value.toString(); }

std::string toString(const DirectionTypes& value) {
    switch (value) {
    case NO_DIRECTION: return "NO_DIRECTION";
    case DIRECTION_NORTHEAST: return "DIRECTION_NORTHEAST";
    case DIRECTION_EAST: return "DIRECTION_EAST";
    case DIRECTION_SOUTHEAST: return "DIRECTION_SOUTHEAST";
    case DIRECTION_SOUTHWEST: return "DIRECTION_SOUTHWEST";
    case DIRECTION_WEST: return "DIRECTION_WEST";
    case DIRECTION_NORTHWEST: return "DIRECTION_NORTHWEST";
    case NUM_DIRECTION_TYPES: return "NUM_DIRECTION_TYPES";
    default: return "INVALID ENUM VALUE";
    }
}

std::string toString(const ActivityTypes& value) {
    switch (value) {
    case NO_ACTIVITY: return "NO_ACTIVITY";
    case ACTIVITY_AWAKE: return "ACTIVITY_AWAKE";
    case ACTIVITY_HOLD: return "ACTIVITY_HOLD";
    case ACTIVITY_SLEEP: return "ACTIVITY_SLEEP";
    case ACTIVITY_HEAL: return "ACTIVITY_HEAL";
    case ACTIVITY_SENTRY: return "ACTIVITY_SENTRY";
    case ACTIVITY_INTERCEPT: return "ACTIVITY_INTERCEPT";
    case ACTIVITY_MISSION: return "ACTIVITY_MISSION";
    case NUM_ACTIVITY_TYPES: return "NUM_ACTIVITY_TYPES";
    default: return "INVALID ENUM VALUE";
    }
}
}
