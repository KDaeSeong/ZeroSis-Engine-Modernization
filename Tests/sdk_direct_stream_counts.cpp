// Full PopupReturn writer bodies and authenticated count-only fragments with
// actual SDK streams and real STL vector/list/CvString types. Other records'
// payload/layout and two FStaticVector allocators are explicitly outside scope.
#include "SdkStreamIncludes.h"
#ifdef _WIN64
#include "../Source/Porting/CvCheckedNarrow.h"
#endif
#include <hash_map>
#include <CvEnums.h>
#include <CvGameCoreEnums.h>
#include <CvDLLUtilDefines.h>
#include <CvString.h>
#include <CvEnumSerialization.h>
#include <FireWorks/FStlContainerSerialization.h>
#include <stdexcept>

#include "SdkDirectStreamCounts.h"

namespace {
typedef std::vector<unsigned char> Bytes;
struct Checks {
    unsigned long count;
    Checks() : count(0) {}
    void Require(bool condition, const char* message) {
        ++count; if (!condition) throw std::runtime_error(message);
    }
};
unsigned int Count(unsigned int kind, unsigned int path, unsigned int row = 0) {
    return kind == 0 ? 0u : kind == 1 ? 1u : 2u + (path + row) % 5u;
}
int Payload(unsigned int path, unsigned int item) {
    const int value = static_cast<int>(0x513200u + path * 0x100u + item * 19u);
    return item & 1u ? -value : value;
}
std::string Text(unsigned int item) {
    if (item == 0) return std::string();
    if (item == 1) return std::string("A\0B", 3);
    if (item == 2) return std::string("\xed\x95\x9c\xea\xb8\x80", 6);
    return std::string("Popup ")+static_cast<char>('0' + item);
}
void Append32(Bytes& bytes, unsigned int value) {
    for (unsigned int i = 0; i < 4; ++i) bytes.push_back(static_cast<unsigned char>(value >> (8 * i)));
}
void AppendCount(Bytes& bytes, unsigned int count, unsigned int width) {
    Append32(bytes, count); if (width == 8) Append32(bytes, 0);
}
void Read32(Checks& c, FMemoryStream& stream, unsigned int expected, bool unsignedReader = false) {
    if (unsignedReader) {
        unsigned int value = 0; stream >> value;
        c.Require(value == expected, "Actual SDK uint32 count reader differs");
    } else {
        int value = 0; stream >> value;
        c.Require(static_cast<unsigned int>(value) == expected, "Actual SDK int32 count reader differs");
    }
}
void Save(Checks& c, const Bytes& bytes, const char* family, unsigned int kind) {
    char name[96]; std::sprintf(name, "%s_popup_%u.bin", family, kind);
    FILE* file = std::fopen(name, "wb"); c.Require(file != NULL, "Cannot open owned synthetic wire output");
    const std::size_t written = std::fwrite(&bytes[0], 1, bytes.size(), file);
    c.Require(std::fclose(file) == 0 && written == bytes.size(), "Short owned synthetic wire output");
}
unsigned int Width(unsigned int path, bool legacy64) {
    return legacy64 && path != 8u && path != 11u && path != 17u ? 8u : 4u;
}
bool UnsignedReader(unsigned int path) { return path == 10u || path == 16u; }
unsigned int Group(unsigned int path) {
    if (path < 8u) return 7u;
    if (path < 12u) return path - 8u;
    if (path < 16u) return 4u;
    return path - 11u;
}
struct Slot { unsigned int path, row; Slot(unsigned int p, unsigned int r = 0) : path(p), row(r) {} };
std::vector<Slot> Slots(unsigned int group) {
    std::vector<Slot> out;
    if (group == 7u) for (unsigned int path = 0; path < 8; ++path) out.push_back(Slot(path));
    else if (group < 4u) out.push_back(Slot(group + 8u));
    else if (group == 4u) {
        out.push_back(Slot(12));
        for (unsigned int row = 0; row < 22; ++row) out.push_back(Slot(13, row));
        out.push_back(Slot(14)); out.push_back(Slot(15));
    } else out.push_back(Slot(group + 11u));
    return out;
}
template<class T> void Fill(T& obj, unsigned int kind) {
    std::vector<int>* integers[8] = { &obj.m_aiSelectedRadioButton, &obj.m_aiBitField, NULL,
        &obj.m_aiSpinnerWidgetValues, &obj.m_aiPulldownID, &obj.m_aiListBoxID,
        &obj.m_aiSpinBoxID, &obj.m_aiButtonID };
    for (unsigned int path = 0; path < 8; ++path) {
        if (path == 2u) {
            obj.m_aszEditBoxString.clear();
            for (unsigned int i = 0; i < Count(kind, path); ++i)
                obj.m_aszEditBoxString.push_back(CvString(Text(i)));
        } else {
            integers[path]->resize(Count(kind, path));
            for (unsigned int i = 0; i < Count(kind, path); ++i) (*integers[path])[i] = Payload(path, i);
        }
    }
    obj.m_FormationEntries.resize(Count(kind, 8));
    obj.m_aDigCompletePlots.resize(Count(kind, 9));
    obj.m_aRequests.resize(Count(kind, 10));
    obj.m_RequestedSavings.resize(Count(kind, 11));
    obj.m_aiSpyListNameOrder.resize(Count(kind, 12));
    for (unsigned int row = 0; row < 22; ++row) obj.m_aHeistLocations[row].resize(Count(kind, 13, row));
    obj.m_aSpyNotificationMessages.resize(Count(kind, 14));
    obj.m_aIntrigueNotificationMessages.resize(Count(kind, 15));
    obj.m_listReplayMessages.resize(Count(kind, 16));
    obj.m_Plots.resize(Count(kind, 17));
}
Bytes PopupOracle(unsigned int kind, unsigned int width) {
    Bytes bytes; Append32(bytes, 1u);
    for (unsigned int path = 0; path < 8; ++path) {
        AppendCount(bytes, Count(kind, path), width);
        for (unsigned int i = 0; i < Count(kind, path); ++i) {
            if (path == 2u) {
                const std::string value = Text(i); Append32(bytes, static_cast<unsigned int>(value.size()));
                bytes.insert(bytes.end(), value.begin(), value.end());
            } else Append32(bytes, static_cast<unsigned int>(Payload(path, i)));
        }
    }
    return bytes;
}
template<class Popup> void PopupFamily(Checks& c, unsigned int width, const char* family) {
    for (unsigned int kind = 0; kind < 3; ++kind) {
        Popup popup; Fill(popup, kind);
        const Bytes body = PopupOracle(kind, width);
        if (kind == 0) c.Require(body.size() == (width == 4u ? 36u : 68u), "Literal empty Popup extent differs");
        FMemoryStream stream; stream << 0x7132ab45u; popup.write(stream);
        c.Require(stream.GetEOF() == body.size() + 4u && stream.GetPosition() == stream.GetEOF(), "Full Popup writer extent differs");
        Bytes expected; Append32(expected, 0x7132ab45u); expected.insert(expected.end(), body.begin(), body.end());
        stream << 0xd3c2b1a0u; Append32(expected, 0xd3c2b1a0u);
        c.Require(stream.GetEOF() == expected.size() && std::memcmp(stream.GetBuf(), &expected[0], expected.size()) == 0,
            "Exact full Popup/string/canary wire differs from independent literal oracle");
        stream.Rewind(); Read32(c, stream, 0x7132ab45u); Read32(c, stream, 1u, true);
        for (unsigned int path = 0; path < 8; ++path) {
            const unsigned int begin = stream.GetPosition(); Read32(c, stream, Count(kind, path));
            if (width == 8u) Read32(c, stream, 0u, true);
            c.Require(stream.GetPosition() - begin == width, "Actual Popup count reader width differs");
            for (unsigned int i = 0; i < Count(kind, path); ++i) {
                if (path == 2u) {
                    CvString value; stream >> value;
                    c.Require(static_cast<const std::string&>(value) == Text(i), "Actual CvString reader changed bytes or embedded NUL");
                } else Read32(c, stream, static_cast<unsigned int>(Payload(path, i)));
            }
        }
        Read32(c, stream, 0xd3c2b1a0u);
        c.Require(stream.AtEnd() && stream.GetPosition() == stream.GetEOF(), "Full Popup reader missed the last-field canary");
        const unsigned char* data = reinterpret_cast<const unsigned char*>(stream.GetBuf());
        Save(c, Bytes(data, data + stream.GetEOF()), family, kind);
        if (width == 8u) c.Require(body != PopupOracle(kind, 4u) && body.size() == PopupOracle(kind, 4u).size() + 32u,
            "Legacy Popup negative control did not expose all eight extra count words");
    }
}
template<class T> void Emit(T& obj, unsigned int group, FMemoryStream& stream) {
    switch (group) {
    case 0: obj.Army(stream); break;
    case 1: obj.Culture(stream); break;
    case 2: obj.Diplomacy(stream); break;
    case 3: obj.Economic(stream); break;
    case 4: obj.Espionage(stream); break;
    case 5: obj.ReplayInfo(stream); break;
    case 6: obj.ReplayMessage(stream); break;
    case 7: obj.Popup(stream); break;
    default: throw std::logic_error("Unknown count-fragment group");
    }
}
template<class T> void FragmentFamily(Checks& c, bool legacy64) {
    for (unsigned int kind = 0; kind < 3; ++kind) {
        T obj; Fill(obj, kind);
        for (unsigned int group = 0; group < 7; ++group) {
            const std::vector<Slot> slots = Slots(group);
            Bytes expected; Append32(expected, 0x19a2b3c4u);
            for (std::size_t i = 0; i < slots.size(); ++i)
                AppendCount(expected, Count(kind, slots[i].path, slots[i].row), Width(slots[i].path, legacy64));
            Append32(expected, 0x52d3c4b5u);
            FMemoryStream stream; stream << 0x19a2b3c4u; Emit(obj, group, stream); stream << 0x52d3c4b5u;
            c.Require(stream.GetEOF() == expected.size() && std::memcmp(stream.GetBuf(), &expected[0], expected.size()) == 0,
                "Typed authenticated count fragment differs from reader-width/canary oracle");
            stream.Rewind(); Read32(c, stream, 0x19a2b3c4u);
            for (std::size_t i = 0; i < slots.size(); ++i) {
                const unsigned int width = Width(slots[i].path, legacy64), begin = stream.GetPosition();
                Read32(c, stream, Count(kind, slots[i].path, slots[i].row), UnsignedReader(slots[i].path));
                if (width == 8u) Read32(c, stream, 0u, true);
                c.Require(stream.GetPosition() - begin == width, "Actual typed fragment count width differs");
            }
            Read32(c, stream, 0x52d3c4b5u);
            c.Require(stream.AtEnd(), "Count fragment reader crossed its boundary canary");
            for (std::size_t i = 0; i < slots.size(); ++i) {
                const unsigned int path = slots[i].path;
                unsigned int expectedVisits = 0;
                for (std::size_t j = 0; j < slots.size(); ++j)
                    if (slots[j].path == path) expectedVisits += Count(kind, path, slots[j].row);
                c.Require(obj.visits[path] == expectedVisits,
                    "Authenticated typed loop header differs from independent expected iteration count");
            }
        }
    }
}

#ifdef _WIN64
void SetFake(DirectEntryProbes& obj, unsigned int path, unsigned int row, std::size_t value) {
    switch (path) {
    case 0: obj.m_aiSelectedRadioButton.declared = value; break;
    case 1: obj.m_aiBitField.declared = value; break;
    case 2: obj.m_aszEditBoxString.declared = value; break;
    case 3: obj.m_aiSpinnerWidgetValues.declared = value; break;
    case 4: obj.m_aiPulldownID.declared = value; break;
    case 5: obj.m_aiListBoxID.declared = value; break;
    case 6: obj.m_aiSpinBoxID.declared = value; break;
    case 7: obj.m_aiButtonID.declared = value; break;
    case 8: obj.m_FormationEntries.declared = static_cast<unsigned int>(value); break;
    case 9: obj.m_aDigCompletePlots.declared = value; break;
    case 10: obj.m_aRequests.declared = value; break;
    case 11: obj.m_RequestedSavings.declared = static_cast<unsigned int>(value); break;
    case 12: obj.m_aiSpyListNameOrder.declared = value; break;
    case 13: obj.m_aHeistLocations[row].declared = value; break;
    case 14: obj.m_aSpyNotificationMessages.declared = value; break;
    case 15: obj.m_aIntrigueNotificationMessages.declared = value; break;
    case 16: obj.m_listReplayMessages.declared = value; break;
    case 17: obj.m_Plots.declared = value; break;
    default: throw std::logic_error("Unknown fake-size target");
    }
}
void Preflights(Checks& c, unsigned int& rejected, unsigned int& inclusive) {
    rejected = inclusive = 0;
    for (unsigned int path = 0; path < 18; ++path) {
        const std::size_t maximum = UnsignedReader(path) ? static_cast<std::size_t>(UINT_MAX) : static_cast<std::size_t>(INT_MAX);
        const bool uintSource = path == 8u || path == 11u;
        const std::size_t bad[3] = { maximum + 1u, static_cast<std::size_t>(UINT_MAX), (std::numeric_limits<std::size_t>::max)() };
        const unsigned int rows = path == 13u ? 22u : 1u;
        for (unsigned int row = 0; row < rows; ++row) {
            for (unsigned int test = 0; test < 3; ++test) {
                if ((UnsignedReader(path) && test == 1u) || (uintSource && test == 2u)) continue;
                DirectEntryProbes probe; SetFake(probe, path, row, bad[test]);
                FMemoryStream stream; stream << 0x492a3b1cu; bool threw = false;
                try { Emit(probe, Group(path), stream); } catch (const std::range_error&) { threw = true; }
                c.Require(threw, "Authenticated entry preflight accepted an out-of-policy count");
                c.Require(stream.GetEOF() == 4u && stream.GetPosition() == 4u &&
                    std::memcmp(stream.GetBuf(), "\x1c\x3b\x2a\x49", 4) == 0,
                    "Entry rejection wrote before all guards or changed the existing canary");
                ++rejected;
            }
            DirectEntryProbes probe; SetFake(probe, path, row, maximum);
            FMemoryStream stream; stream << 0x492a3b1cu; Emit(probe, Group(path), stream); stream << 0xd3c2b1a0u;
            const std::vector<Slot> slots = Slots(Group(path));
            c.Require(stream.GetEOF() == 8u + slots.size() * 4u, "Inclusive limit changed fixed count widths");
            stream.Rewind(); Read32(c, stream, 0x492a3b1cu);
            for (std::size_t i = 0; i < slots.size(); ++i)
                Read32(c, stream, slots[i].path == path && slots[i].row == row ? static_cast<unsigned int>(maximum) : 0u,
                    UnsignedReader(slots[i].path));
            Read32(c, stream, 0xd3c2b1a0u); c.Require(stream.AtEnd(), "Inclusive preflight crossed the final canary");
            ++inclusive;
        }
    }
    c.Require(rejected == 113u && inclusive == 39u, "Missing entry guard or one of 22 heist rows");
}
#endif
}

int main(int argc, char** argv) {
    try {
        Checks checks;
        typedef char Int32Required[sizeof(int) == 4 ? 1 : -1]; (void)sizeof(Int32Required);
        typedef char Major22Required[MAX_MAJOR_CIVS == 22 ? 1 : -1]; (void)sizeof(Major22Required);
        unsigned int rejected = 0, inclusive = 0;
#ifdef _WIN64
        checks.Require(argc == 2 && std::strcmp(argv[1], "--x64") == 0, "Expected isolated x64 mode");
        PopupFamily<DirectFixed::PopupReturn>(checks, 4, "canonical");
        PopupFamily<DirectOriginal::PopupReturn>(checks, 8, "legacy64");
        FragmentFamily<DirectFixedCounts>(checks, false); FragmentFamily<DirectOriginalCounts>(checks, true);
        Preflights(checks, rejected, inclusive);
#else
        checks.Require(argc == 2 && std::strcmp(argv[1], "--x86original") == 0, "Expected archived x86 mode");
        PopupFamily<DirectOriginal::PopupReturn>(checks, 4, "canonical");
        FragmentFamily<DirectOriginalCounts>(checks, false);
#endif
        std::printf("{\"status\":\"PASS_SDK_DIRECT_STREAM_COUNTS\",\"checks\":%lu,\"source_count_paths\":18,"
            "\"width_corrections\":15,\"range_only_corrections\":3,\"popup_full_body_cases\":3,\"typed_fragment_paths\":10,"
            "\"typed_fragment_loop_headers_exercised\":true,"
            "\"canonical_count_bytes\":4,\"legacy_size_t_count_bytes\":%u,\"oversized_preflight_rejections\":%u,"
            "\"inclusive_limit_cases\":%u,\"heist_preflight_slots\":22,\"non_popup_payloads_verified\":false,"
            "\"opaque_fragment_elements\":true,\"uint_size_storage_shims\":2,\"hash_resolution_performed\":false,"
            "\"gamecore_loaded\":false,\"window_created\":false,\"user_saves_accessed\":false,"
            "\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n",
            checks.count,
#ifdef _WIN64
            8u,
#else
            0u,
#endif
            rejected, inclusive);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "Direct stream count component failure: %s\n", error.what()); return 1;
    }
}
