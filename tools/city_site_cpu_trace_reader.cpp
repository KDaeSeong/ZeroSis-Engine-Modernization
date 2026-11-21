#define _WIN32_WINNT 0x0A00
#include <Windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include <winternl.h>

#include "../Source/Diagnostics/CitySiteCpuTrace.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using ZeroSisDiagnostics::CitySiteCpuTraceJob;
using ZeroSisDiagnostics::ConcurrencyProof;
using ZeroSisDiagnostics::CpuSlice;
using ZeroSisDiagnostics::FindDistinctCoreOverlap;
using ZeroSisDiagnostics::TraceMarker;

const GUID kTraceLoggingProvider = {0x2d76305f, 0x91f4, 0x4d48, {0x9b, 0x32, 0x28, 0x15, 0x07, 0x66, 0x9f, 0x73}};
const GUID kProcessProvider = {0x3d6fa8d0, 0xfe05, 0x11d0, {0x9d, 0xda, 0x00, 0xc0, 0x4f, 0xd7, 0xba, 0x7c}};
const GUID kThreadProvider = {0x3d6fa8d1, 0xfe05, 0x11d0, {0x9d, 0xda, 0x00, 0xc0, 0x4f, 0xd7, 0xba, 0x7c}};
const GUID kSystemTraceProvider = {0x9e814aad, 0x3204, 0x11d2, {0x9a, 0x82, 0x00, 0x60, 0x08, 0xa8, 0x69, 0x39}};
const std::uint32_t kUnknown = (std::numeric_limits<std::uint32_t>::max)();
bool gEtlOpened = false;
ULONG gTracePointerSize = sizeof(void*);

ULONG TdhContextFor(PEVENT_RECORD event, TDH_CONTEXT& context) {
    if ((event->EventHeader.Flags & EVENT_HEADER_FLAG_CLASSIC_HEADER) == 0)
        return 0;
    context = {};
    context.ParameterValue = gTracePointerSize;
    context.ParameterType = TDH_CONTEXT_POINTERSIZE;
    context.ParameterSize = 0;
    return 1;
}

struct TraceData {
    std::vector<TraceMarker> markers;
    std::vector<CpuSlice> slices;
    std::vector<std::string> threadEvents;
    std::vector<std::string> processEvents;
    std::set<std::pair<std::uint32_t, std::uint32_t>> workers;
    std::map<std::uint32_t, std::uint32_t> activeThreadProcess;
    struct ThreadLifetime { std::uint32_t processId; std::uint32_t threadId; std::uint64_t begin; std::uint64_t end; };
    std::vector<ThreadLifetime> threadLifetimes;
    std::map<std::uint32_t, std::size_t> activeThreadLifetime;
    std::map<std::pair<std::uint16_t, std::uint8_t>, std::uint32_t> coreByLogical;
    std::uint64_t frequency = 0;
    bool traceTopologyBound = true;
    bool traceClockIsQpc = true;
    std::uint32_t traceProcessorCount = 0;
    std::uint64_t expectedBootTime100ns = 0;
    std::uint64_t etlBootTime100ns = 0;
    std::uint32_t etlClockType = 0;
    ULONG eventsLost = 0;
    ULONG buffersLost = 0;
    ULONG readEventsLost = 0;
    ULONG readBuffers = 0;
    std::uint64_t cswitchesSeen = 0;
    std::uint64_t workerCswitchesSeen = 0;
    std::uint64_t unmappedWorkerCswitches = 0;
    std::uint64_t processLifecycleEventsObserved = 0;
    std::uint64_t threadLifecycleEventsDecoded = 0;
    std::map<std::uint32_t, std::uint64_t> processLifecycleVersions;
    std::map<std::uint32_t, std::uint64_t> threadLifecycleVersions;
    std::map<std::uint32_t, std::uint64_t> cswitchVersions;
    std::string error;
    bool lifecycleAmbiguous = false;
};

struct OsVersion {
    DWORD major = 0;
    DWORD minor = 0;
    DWORD build = 0;
};

struct MachineTopologySnapshot {
    std::uint64_t bootTime100ns = 0;
    std::uint64_t qpcFrequency = 0;
    OsVersion os;
    std::map<std::pair<std::uint16_t, std::uint8_t>, std::uint32_t> coreByLogical;
};

std::uint64_t CurrentBootTime100ns() {
    FILETIME time = {};
    GetSystemTimeAsFileTime(&time);
    ULARGE_INTEGER now = {};
    now.LowPart = time.dwLowDateTime;
    now.HighPart = time.dwHighDateTime;
    const std::uint64_t uptime = GetTickCount64() * 10000ULL;
    if (now.QuadPart < uptime)
        throw std::runtime_error("System uptime exceeds wall clock timestamp");
    return now.QuadPart - uptime;
}

OsVersion CurrentOsVersion() {
    using RtlGetVersionFunction = LONG (WINAPI*)(PRTL_OSVERSIONINFOW);
    const HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    const auto getVersion = reinterpret_cast<RtlGetVersionFunction>(GetProcAddress(ntdll, "RtlGetVersion"));
    if (!getVersion)
        throw std::runtime_error("RtlGetVersion is unavailable");
    RTL_OSVERSIONINFOW version = {};
    version.dwOSVersionInfoSize = sizeof(version);
    if (getVersion(&version) != 0)
        throw std::runtime_error("RtlGetVersion failed");
    return {version.dwMajorVersion, version.dwMinorVersion, version.dwBuildNumber};
}

std::wstring MetadataString(const TRACE_EVENT_INFO* info, ULONG offset) {
    if (offset == 0)
        return std::wstring();
    const auto* value = reinterpret_cast<const wchar_t*>(reinterpret_cast<const BYTE*>(info) + offset);
    return std::wstring(value);
}

std::string EventDiagnostic(PEVENT_RECORD event, ULONG status, const char* phase) {
    const GUID& guid = event->EventHeader.ProviderId;
    std::ostringstream out;
    out << phase << " failed: TDH_STATUS=" << status << " (0x" << std::hex << status << std::dec << ")"
        << " provider={" << std::hex << std::setfill('0') << std::setw(8) << guid.Data1 << '-'
        << std::setw(4) << guid.Data2 << '-' << std::setw(4) << guid.Data3 << '-';
    for (unsigned i = 0; i < 8; ++i) {
        if (i == 2) out << '-';
        out << std::setw(2) << static_cast<unsigned>(guid.Data4[i]);
    }
    out << std::dec << "} descriptor_id=" << event->EventHeader.EventDescriptor.Id
        << " opcode=" << static_cast<unsigned>(event->EventHeader.EventDescriptor.Opcode)
        << " version=" << static_cast<unsigned>(event->EventHeader.EventDescriptor.Version)
        << " channel=" << static_cast<unsigned>(event->EventHeader.EventDescriptor.Channel)
        << " task=" << event->EventHeader.EventDescriptor.Task
        << " header_flags=0x" << std::hex << event->EventHeader.Flags << std::dec
        << " ext_count=" << event->ExtendedDataCount
        << " pid=" << event->EventHeader.ProcessId << " tid=" << event->EventHeader.ThreadId
        << " qpc=" << event->EventHeader.TimeStamp.QuadPart
        << " userdata_length=" << event->UserDataLength
        << " buffer_processor=" << static_cast<unsigned>(event->BufferContext.ProcessorIndex)
        << " buffer_logger_id=" << event->BufferContext.LoggerId;
    if (event->ExtendedDataCount != 0 && event->ExtendedData != nullptr) {
        out << " ext_items=[";
        for (USHORT i = 0; i < event->ExtendedDataCount; ++i) {
            if (i) out << ',';
            out << "{type:" << event->ExtendedData[i].ExtType
                << ",size:" << event->ExtendedData[i].DataSize
                << ",link:" << event->ExtendedData[i].Linkage << '}';
        }
        out << ']';
    }
    return out.str();
}

std::vector<BYTE> EventInformation(PEVENT_RECORD event) {
    TDH_CONTEXT context = {};
    const ULONG contextCount = TdhContextFor(event, context);
    ULONG size = 0;
    ULONG status = TdhGetEventInformation(event, contextCount, contextCount ? &context : nullptr, nullptr, &size);
    if (status != ERROR_INSUFFICIENT_BUFFER || size < sizeof(TRACE_EVENT_INFO))
        throw std::runtime_error(EventDiagnostic(event, status, "TdhGetEventInformation(size)"));
    std::vector<BYTE> buffer(size);
    status = TdhGetEventInformation(event, contextCount, contextCount ? &context : nullptr,
        reinterpret_cast<PTRACE_EVENT_INFO>(buffer.data()), &size);
    if (status != ERROR_SUCCESS)
        throw std::runtime_error(EventDiagnostic(event, status, "TdhGetEventInformation(read)"));
    return buffer;
}

const EVENT_PROPERTY_INFO* FindProperty(const TRACE_EVENT_INFO* info, const wchar_t* name, ULONG expectedType) {
    for (ULONG i = 0; i < info->TopLevelPropertyCount; ++i) {
        const EVENT_PROPERTY_INFO* property = &info->EventPropertyInfoArray[i];
        if (MetadataString(info, property->NameOffset) == name) {
            if ((property->Flags & (PropertyStruct | PropertyParamCount)) != 0 ||
                property->nonStructType.InType != expectedType)
                throw std::runtime_error("TDH property type or shape differs from expected event schema");
            return property;
        }
    }
    throw std::runtime_error("TDH event schema is missing a required property");
}

template<class T>
T PropertyValue(PEVENT_RECORD event, const wchar_t* name, ULONG expectedType) {
    const auto metadata = EventInformation(event);
    const auto* info = reinterpret_cast<const TRACE_EVENT_INFO*>(metadata.data());
    (void)FindProperty(info, name, expectedType);
    PROPERTY_DATA_DESCRIPTOR descriptor = {};
    descriptor.PropertyName = reinterpret_cast<ULONGLONG>(name);
    descriptor.ArrayIndex = ULONG_MAX;
    ULONG size = 0;
    TDH_CONTEXT context = {};
    const ULONG contextCount = TdhContextFor(event, context);
    ULONG status = TdhGetPropertySize(event, contextCount, contextCount ? &context : nullptr, 1, &descriptor, &size);
    if (status != ERROR_SUCCESS || size != sizeof(T))
        throw std::runtime_error("TDH property size differs from its metadata type");
    T value = 0;
    status = TdhGetProperty(event, contextCount, contextCount ? &context : nullptr, 1, &descriptor,
        sizeof(T), reinterpret_cast<PBYTE>(&value));
    if (status != ERROR_SUCCESS)
        throw std::runtime_error("TDH could not read an event property");
    return value;
}

std::wstring EventName(PEVENT_RECORD event) {
    const auto metadata = EventInformation(event);
    const auto* info = reinterpret_cast<const TRACE_EVENT_INFO*>(metadata.data());
    return MetadataString(info, info->EventNameOffset);
}

void BuildTopology(TraceData& data) {
    DWORD size = 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore, nullptr, &size);
    if (GetLastError() != ERROR_INSUFFICIENT_BUFFER || size == 0)
        throw std::runtime_error("Could not size logical processor topology");
    std::vector<BYTE> bytes(size);
    if (!GetLogicalProcessorInformationEx(RelationProcessorCore,
            reinterpret_cast<PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX>(bytes.data()), &size))
        throw std::runtime_error("Could not read logical processor topology");

    std::uint32_t coreIndex = 0;
    for (DWORD offset = 0; offset < size;) {
        const auto* entry = reinterpret_cast<const SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*>(bytes.data() + offset);
        if (entry->Relationship == RelationProcessorCore) {
            const WORD groupCount = entry->Processor.GroupCount;
            for (WORD groupIndex = 0; groupIndex < groupCount; ++groupIndex) {
                const GROUP_AFFINITY& affinity = entry->Processor.GroupMask[groupIndex];
                for (BYTE bit = 0; bit < sizeof(KAFFINITY) * 8; ++bit) {
                    if ((affinity.Mask & (static_cast<KAFFINITY>(1) << bit)) != 0) {
                        const auto logical = std::make_pair(affinity.Group, bit);
                        if (!data.coreByLogical.emplace(logical, coreIndex).second)
                            throw std::runtime_error("CPU topology contains a duplicate logical processor");
                    }
                }
            }
            ++coreIndex;
        }
        if (entry->Size == 0 || offset + entry->Size > size)
            throw std::runtime_error("CPU topology entry has an invalid size");
        offset += entry->Size;
    }
}

MachineTopologySnapshot CurrentTopologySnapshot(const TraceData& topology) {
    LARGE_INTEGER frequency = {};
    if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0)
        throw std::runtime_error("QueryPerformanceFrequency failed");
    MachineTopologySnapshot snapshot;
    snapshot.bootTime100ns = CurrentBootTime100ns();
    snapshot.qpcFrequency = static_cast<std::uint64_t>(frequency.QuadPart);
    snapshot.os = CurrentOsVersion();
    snapshot.coreByLogical = topology.coreByLogical;
    if (snapshot.coreByLogical.empty() ||
        snapshot.coreByLogical.size() != GetActiveProcessorCount(ALL_PROCESSOR_GROUPS))
        throw std::runtime_error("Processor topology is incomplete or inconsistent");
    return snapshot;
}

void WriteTopologySnapshot(const wchar_t* path) {
    TraceData topology;
    BuildTopology(topology);
    const MachineTopologySnapshot snapshot = CurrentTopologySnapshot(topology);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out)
        throw std::runtime_error("Could not create topology sidecar");
    out << "{\"schema\":\"zerosiscitysite.topology.v1\",\"boot_time_100ns\":" << snapshot.bootTime100ns
        << ",\"qpc_frequency\":" << snapshot.qpcFrequency
        << ",\"os_version\":{\"major\":" << snapshot.os.major << ",\"minor\":" << snapshot.os.minor
        << ",\"build\":" << snapshot.os.build << "},\"processor_count\":" << snapshot.coreByLogical.size()
        << ",\"topology\":[";
    bool first = true;
    for (const auto& item : snapshot.coreByLogical) {
        if (!first) out << ',';
        first = false;
        out << "{\"group\":" << item.first.first << ",\"logical_processor\":"
            << static_cast<unsigned>(item.first.second) << ",\"physical_core\":" << item.second << '}';
    }
    out << "]}\n";
    out.flush();
    if (!out)
        throw std::runtime_error("Could not finish topology sidecar");
    std::cout << "{\"status\":\"TOPOLOGY_SNAPSHOT_WRITTEN\",\"capture_started\":false,\"etl_opened\":false,\"gamecore_loaded\":false,\"physical_multicore_proven\":false,\"processor_count\":"
              << snapshot.coreByLogical.size() << ",\"qpc_frequency\":" << snapshot.qpcFrequency
              << ",\"boot_time_100ns\":" << snapshot.bootTime100ns << "}\n";
}

std::uint64_t ParseJsonUnsigned(const std::string& token, std::uint64_t maximum) {
    if (token.empty() || (token.size() > 1 && token[0] == '0'))
        throw std::runtime_error("Topology sidecar contains a non-canonical unsigned integer");
    std::uint64_t value = 0;
    for (char ch : token) {
        if (ch < '0' || ch > '9')
            throw std::runtime_error("Topology sidecar contains an invalid integer");
        const unsigned digit = static_cast<unsigned>(ch - '0');
        if (value > (maximum - digit) / 10)
            throw std::runtime_error("Topology sidecar integer overflows its field");
        value = value * 10 + digit;
    }
    return value;
}

MachineTopologySnapshot ReadTopologySnapshot(const wchar_t* path) {
    std::ifstream input(path, std::ios::binary);
    if (!input)
        throw std::runtime_error("Could not open topology sidecar");
    const std::string json((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    if (json.size() > 1024 * 1024)
        throw std::runtime_error("Topology sidecar exceeds the size limit");
    const std::regex document(
        R"(^\s*\{\s*"schema"\s*:\s*"zerosiscitysite\.topology\.v1"\s*,\s*"boot_time_100ns"\s*:\s*([0-9]+)\s*,\s*"qpc_frequency"\s*:\s*([0-9]+)\s*,\s*"os_version"\s*:\s*\{\s*"major"\s*:\s*([0-9]+)\s*,\s*"minor"\s*:\s*([0-9]+)\s*,\s*"build"\s*:\s*([0-9]+)\s*\}\s*,\s*"processor_count"\s*:\s*([0-9]+)\s*,\s*"topology"\s*:\s*\[(.*)\]\s*\}\s*$)");
    std::smatch fields;
    if (!std::regex_match(json, fields, document))
        throw std::runtime_error("Topology sidecar is malformed, has duplicate/unknown keys, or has trailing data");
    MachineTopologySnapshot snapshot;
    snapshot.bootTime100ns = ParseJsonUnsigned(fields[1].str(), (std::numeric_limits<std::uint64_t>::max)());
    snapshot.qpcFrequency = ParseJsonUnsigned(fields[2].str(), (std::numeric_limits<std::uint64_t>::max)());
    snapshot.os.major = static_cast<DWORD>(ParseJsonUnsigned(fields[3].str(), MAXDWORD));
    snapshot.os.minor = static_cast<DWORD>(ParseJsonUnsigned(fields[4].str(), MAXDWORD));
    snapshot.os.build = static_cast<DWORD>(ParseJsonUnsigned(fields[5].str(), MAXDWORD));
    const std::uint64_t count = ParseJsonUnsigned(fields[6].str(), MAXDWORD);
    const std::string entries = fields[7].str();
    const std::regex entry(R"(\s*\{\s*"group"\s*:\s*([0-9]+)\s*,\s*"logical_processor"\s*:\s*([0-9]+)\s*,\s*"physical_core"\s*:\s*([0-9]+)\s*\}\s*)");
    std::size_t offset = 0;
    while (offset < entries.size()) {
        std::smatch match;
        const std::string remaining = entries.substr(offset);
        if (!std::regex_search(remaining, match, entry, std::regex_constants::match_continuous))
            throw std::runtime_error("Topology sidecar contains an invalid topology entry or separator");
        const auto group = ParseJsonUnsigned(match[1].str(), (std::numeric_limits<std::uint16_t>::max)());
        const auto logical = ParseJsonUnsigned(match[2].str(), (std::numeric_limits<std::uint8_t>::max)());
        const auto core = ParseJsonUnsigned(match[3].str(), (std::numeric_limits<std::uint32_t>::max)());
        if (!snapshot.coreByLogical.emplace(std::make_pair(static_cast<std::uint16_t>(group),
                static_cast<std::uint8_t>(logical)), static_cast<std::uint32_t>(core)).second)
            throw std::runtime_error("Topology sidecar contains a duplicate logical processor");
        offset += static_cast<std::size_t>(match.length());
        if (offset < entries.size()) {
            if (entries[offset] != ',')
                throw std::runtime_error("Topology sidecar topology separator is invalid");
            ++offset;
            if (offset == entries.size())
                throw std::runtime_error("Topology sidecar has a trailing separator");
        }
    }
    if (count == 0 || count != snapshot.coreByLogical.size() || snapshot.qpcFrequency == 0 ||
        snapshot.bootTime100ns == 0 || snapshot.coreByLogical.empty())
        throw std::runtime_error("Topology sidecar count or clock values are invalid");
    return snapshot;
}

void ValidateTopologySnapshot(const MachineTopologySnapshot& captured, const TraceData& current) {
    const MachineTopologySnapshot now = CurrentTopologySnapshot(current);
    const std::uint64_t bootDelta = now.bootTime100ns > captured.bootTime100ns
        ? now.bootTime100ns - captured.bootTime100ns : captured.bootTime100ns - now.bootTime100ns;
    if (bootDelta > 20000000ULL || now.qpcFrequency != captured.qpcFrequency ||
        now.os.major != captured.os.major || now.os.minor != captured.os.minor || now.os.build != captured.os.build ||
        now.coreByLogical != captured.coreByLogical)
        throw std::runtime_error("Topology sidecar does not match the current boot, OS, QPC clock, and processor map");
}

bool ResolveProcessor(PEVENT_RECORD event, const TraceData& data, std::uint32_t& index,
                      std::uint16_t& group, std::uint8_t& number, std::uint32_t& core) {
    const ULONG processor = GetEventProcessorIndex(event);
    if ((event->EventHeader.Flags & EVENT_HEADER_FLAG_PROCESSOR_INDEX) == 0) {
        // The legacy byte is group-relative. Map it only when the machine has
        // one group; multiple groups make the processor identity ambiguous.
        std::set<std::uint16_t> groups;
        for (const auto& item : data.coreByLogical)
            groups.insert(item.first.first);
        if (groups.size() != 1)
            return false;
        group = *groups.begin();
        number = static_cast<std::uint8_t>(processor);
        index = processor;
    } else {
        // A processor index is system-wide. Map it only on one group with
        // contiguous group-relative numbers, where it is unambiguous.
        index = processor;
        std::set<std::uint16_t> groups;
        std::uint8_t maxNumber = 0;
        for (const auto& item : data.coreByLogical) {
            groups.insert(item.first.first);
            maxNumber = (std::max)(maxNumber, item.first.second);
        }
        if (groups.size() != 1 || data.coreByLogical.size() != static_cast<std::size_t>(maxNumber) + 1 ||
            processor > maxNumber)
            return false;
        group = *groups.begin();
        number = static_cast<std::uint8_t>(processor);
    }
    const auto foundCore = data.coreByLogical.find(std::make_pair(group, number));
    if (foundCore == data.coreByLogical.end())
        return false;
    core = foundCore->second;
    return true;
}

void MarkerPass(PEVENT_RECORD event, TraceData& data) {
    if (!IsEqualGUID(event->EventHeader.ProviderId, kTraceLoggingProvider))
        return;
    const std::wstring name = EventName(event);
    if (name != L"JobBegin" && name != L"JobEnd")
        return;
    TraceMarker marker = {};
    marker.begin = name == L"JobBegin";
    marker.batchId = PropertyValue<std::uint64_t>(event, L"batchId", TDH_INTYPE_UINT64);
    marker.jobIndex = PropertyValue<std::uint32_t>(event, L"jobIndex", TDH_INTYPE_UINT32);
    marker.workerTid = PropertyValue<std::uint32_t>(event, L"workerTid", TDH_INTYPE_UINT32);
    marker.processId = PropertyValue<std::uint32_t>(event, L"processId", TDH_INTYPE_UINT32);
    marker.siteCount = PropertyValue<std::uint32_t>(event, L"siteCount", TDH_INTYPE_UINT32);
    marker.timestamp = static_cast<std::uint64_t>(event->EventHeader.TimeStamp.QuadPart);
    if (event->EventHeader.ProcessId != marker.processId || event->EventHeader.ThreadId != marker.workerTid)
        throw std::runtime_error("ETW marker header identity differs from its payload");
    data.workers.emplace(marker.processId, marker.workerTid);
    if (!marker.begin) {
        const std::int64_t scoreBegin = PropertyValue<std::int64_t>(event, L"scoreBeginQpc", TDH_INTYPE_INT64);
        const std::int64_t scoreEnd = PropertyValue<std::int64_t>(event, L"scoreEndQpc", TDH_INTYPE_INT64);
        const std::int64_t qpcFrequency = PropertyValue<std::int64_t>(event, L"qpcFrequency", TDH_INTYPE_INT64);
        if (scoreBegin <= 0 || scoreEnd <= scoreBegin || qpcFrequency <= 0 ||
            (data.frequency != 0 && static_cast<std::uint64_t>(qpcFrequency) != data.frequency))
            throw std::runtime_error("Job scoring QPC interval or frequency is invalid");
        marker.timestamp = static_cast<std::uint64_t>(scoreEnd);
        bool foundBegin = false;
        for (auto& earlier : data.markers) {
            if (earlier.begin && earlier.processId == marker.processId && earlier.batchId == marker.batchId &&
                earlier.jobIndex == marker.jobIndex && earlier.workerTid == marker.workerTid) {
                earlier.timestamp = static_cast<std::uint64_t>(scoreBegin);
                foundBegin = true;
                break;
            }
        }
        if (!foundBegin)
            throw std::runtime_error("JobEnd marker precedes its JobBegin marker");
    }
    data.markers.push_back(marker);
}

struct CpuState {
    bool initialized = false;
    std::uint32_t tid = 0;
    std::uint64_t since = 0;
};

std::uint32_t UniqueWorkerProcess(const TraceData& data, std::uint32_t tid) {
    const auto active = data.activeThreadProcess.find(tid);
    if (active == data.activeThreadProcess.end() ||
        data.workers.find(std::make_pair(active->second, tid)) == data.workers.end())
        return 0;
    return active->second;
}

// For classic MOF providers, EVENT_DESCRIPTOR.Id is not the event identity;
// Microsoft documents the identity in Opcode. The local EVENT_DESCRIPTOR has
// the same UCHAR Opcode field, and Thread_V2 defines the event-type values.
UCHAR ClassicEventType(PEVENT_RECORD event) {
    return event->EventHeader.EventDescriptor.Opcode;
}

void LifecyclePass(PEVENT_RECORD event, TraceData& data) {
    const bool processProvider = IsEqualGUID(event->EventHeader.ProviderId, kProcessProvider);
    const bool threadProvider = IsEqualGUID(event->EventHeader.ProviderId, kThreadProvider);
    if (!processProvider && !threadProvider)
        return;
    const UCHAR type = ClassicEventType(event);
    const USHORT id = type;
    if (processProvider && type != 1 && type != 2 && type != 3 && type != 4 && type != 39)
        return;
    if (threadProvider && type != 1 && type != 2 && type != 3 && type != 4)
        return;
    // This Windows build's classic Process_V4/Thread_V3/CSwitch_V5 records
    // have no TDH schema (ERROR_NOT_FOUND). Decode only documented identity
    // prefixes; never read process strings or expose unrelated process IDs.
    if (processProvider) {
        ++data.processLifecycleEventsObserved;
        const UCHAR processVersion = event->EventHeader.EventDescriptor.Version;
        ++data.processLifecycleVersions[processVersion];
        if ((processVersion != 4 && processVersion != 5) || gTracePointerSize != 8 ||
            (event->EventHeader.Flags & EVENT_HEADER_FLAG_CLASSIC_HEADER) == 0 ||
            event->UserData == nullptr || event->UserDataLength < 12 || event->UserDataLength > 4096)
            throw std::runtime_error(EventDiagnostic(event, ERROR_INVALID_DATA, "unsupported Process_V4 lifecycle payload schema"));
        std::uint32_t processId = 0;
        std::memcpy(&processId, static_cast<const BYTE*>(event->UserData) + gTracePointerSize, sizeof(processId));
        bool workerProcess = false;
        for (const auto& worker : data.workers)
            workerProcess = workerProcess || worker.first == processId;
        if (workerProcess) {
            std::ostringstream value;
            value << "{\"event_id\":" << id << ",\"process_id\":" << processId
                  << ",\"timestamp\":" << event->EventHeader.TimeStamp.QuadPart << "}";
            data.processEvents.push_back(value.str());
        }
        return;
    }
    ++data.threadLifecycleEventsDecoded;
    ++data.threadLifecycleVersions[event->EventHeader.EventDescriptor.Version];
    if (event->EventHeader.EventDescriptor.Version != 3 || event->UserData == nullptr ||
        event->UserDataLength < 8 || event->UserDataLength > 512)
        throw std::runtime_error(EventDiagnostic(event, ERROR_INVALID_DATA, "unsupported Thread_V2 lifecycle payload schema"));
    std::uint32_t processId = 0, threadId = 0;
    std::memcpy(&processId, event->UserData, sizeof(processId));
    std::memcpy(&threadId, static_cast<const BYTE*>(event->UserData) + sizeof(processId), sizeof(threadId));
    const auto worker = data.workers.find(std::make_pair(processId, threadId));
    if (worker == data.workers.end())
        return;
    const std::uint64_t timestamp = static_cast<std::uint64_t>(event->EventHeader.TimeStamp.QuadPart);
        if (type == 1 || type == 3) {
            const auto inserted = data.activeThreadProcess.emplace(threadId, processId);
            if (!inserted.second) {
                data.lifecycleAmbiguous = true;
                return;
            }
            data.threadLifetimes.push_back({processId, threadId, timestamp,
                (std::numeric_limits<std::uint64_t>::max)()});
            data.activeThreadLifetime.emplace(threadId, data.threadLifetimes.size() - 1);
        } else {
            const auto active = data.activeThreadProcess.find(threadId);
            const auto lifetime = data.activeThreadLifetime.find(threadId);
            if (active != data.activeThreadProcess.end() && active->second == processId &&
                lifetime != data.activeThreadLifetime.end()) {
                data.threadLifetimes[lifetime->second].end = timestamp;
                data.activeThreadProcess.erase(active);
                data.activeThreadLifetime.erase(lifetime);
            } else if (data.workers.find(std::make_pair(processId, threadId)) != data.workers.end()) {
                data.lifecycleAmbiguous = true;
            }
        }
        std::ostringstream value;
        value << "{\"event_id\":" << id << ",\"process_id\":" << processId
              << ",\"thread_id\":" << threadId << ",\"timestamp\":" << event->EventHeader.TimeStamp.QuadPart << "}";
        data.threadEvents.push_back(value.str());
    }

bool MarkersHaveUniqueThreadLifetimes(const TraceData& data) {
    for (const TraceMarker& begin : data.markers) {
        if (!begin.begin)
            continue;
        const TraceMarker* end = nullptr;
        for (const TraceMarker& marker : data.markers) {
            if (!marker.begin && marker.processId == begin.processId && marker.batchId == begin.batchId &&
                marker.jobIndex == begin.jobIndex && marker.workerTid == begin.workerTid) {
                end = &marker;
                break;
            }
        }
        if (!end)
            return false;
        std::size_t matches = 0;
        for (const auto& life : data.threadLifetimes) {
            if (life.processId == begin.processId && life.threadId == begin.workerTid &&
                life.begin <= begin.timestamp && life.end >= end->timestamp)
                ++matches;
        }
        if (matches != 1)
            return false;
    }
    return true;
}

void SwitchPass(PEVENT_RECORD event, TraceData& data, std::map<std::uint32_t, CpuState>& states) {
    if (!IsEqualGUID(event->EventHeader.ProviderId, kThreadProvider) || ClassicEventType(event) != 36)
        return;
    if (event->EventHeader.EventDescriptor.Version != 5 || event->UserData == nullptr || event->UserDataLength != 28)
        throw std::runtime_error(EventDiagnostic(event, ERROR_INVALID_DATA, "unsupported CSwitch payload schema"));
    ++data.cswitchVersions[event->EventHeader.EventDescriptor.Version];
    // The documented CSwitch class begins with NewThreadId and OldThreadId
    // (uint32 each). This retained build emits version 5, 28-byte records;
    // only the stable identity prefix is read and the rest is ignored.
    std::uint32_t next = 0, previous = 0;
    std::memcpy(&next, event->UserData, sizeof(next));
    std::memcpy(&previous, static_cast<const BYTE*>(event->UserData) + sizeof(next), sizeof(previous));
    ++data.cswitchesSeen;
    const bool workerSwitch = UniqueWorkerProcess(data, next) != 0 || UniqueWorkerProcess(data, previous) != 0;
    if (workerSwitch)
        ++data.workerCswitchesSeen;
    const std::uint64_t timestamp = static_cast<std::uint64_t>(event->EventHeader.TimeStamp.QuadPart);
    std::uint32_t processorIndex = kUnknown, core = kUnknown;
    std::uint16_t group = 0;
    std::uint8_t number = 0;
    if (!ResolveProcessor(event, data, processorIndex, group, number, core)) {
        if (workerSwitch)
            ++data.unmappedWorkerCswitches;
        return;
    }

    CpuState& state = states[processorIndex];
    if (state.initialized && (state.tid != previous || timestamp < state.since)) {
        state.initialized = false;
    }
    if (state.initialized && timestamp > state.since) {
        const std::uint32_t processId = UniqueWorkerProcess(data, state.tid);
        if (processId != 0) {
            CpuSlice slice = {};
            slice.processId = processId;
            slice.workerTid = state.tid;
            slice.processorIndex = processorIndex;
            slice.group = group;
            slice.groupProcessor = number;
            slice.physicalCore = core;
            slice.begin = state.since;
            slice.end = timestamp;
            data.slices.push_back(slice);
        }
    }
    state.initialized = true;
    state.tid = next;
    state.since = timestamp;
}

struct CallbackContext {
    TraceData* data;
    std::map<std::uint32_t, CpuState>* states;
    bool switches;
    std::uint64_t bufferCallbackCount = 0;
    ULONG buffersReadReported = 0;
};

ULONG WINAPI OnBuffer(PEVENT_TRACE_LOGFILEW logfile) {
    if (logfile == nullptr)
        return FALSE;
    auto* context = static_cast<CallbackContext*>(logfile->Context);
    if (context == nullptr || context->data == nullptr)
        return FALSE;
    ++context->bufferCallbackCount;
    context->buffersReadReported = (std::max)(context->buffersReadReported, logfile->BuffersRead);
    context->data->eventsLost = (std::max)(context->data->eventsLost,
        logfile->LogfileHeader.EventsLost);
    context->data->buffersLost = (std::max)(context->data->buffersLost,
        logfile->LogfileHeader.BuffersLost);
    return TRUE;
}

void WINAPI OnDispatch(PEVENT_RECORD event) {
    auto* context = static_cast<CallbackContext*>(event->UserContext);
    if (!context || !context->data)
        return;
    try {
        if (!context->data->error.empty())
            return;
        if (context->switches) {
            SwitchPass(event, *context->data, *context->states);
            LifecyclePass(event, *context->data);
        } else {
            MarkerPass(event, *context->data);
        }
    } catch (const std::exception& error) {
        context->data->error = error.what();
    } catch (...) {
        context->data->error = "Unknown ETW decode failure";
    }
}

void Consume(const wchar_t* path, TraceData& data, std::map<std::uint32_t, CpuState>* states) {
    EVENT_TRACE_LOGFILEW logfile = {};
    logfile.LogFileName = const_cast<LPWSTR>(path);
    logfile.ProcessTraceMode = PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP;
    CallbackContext context = {&data, states, states != nullptr};
    logfile.Context = &context;
    logfile.EventRecordCallback = &OnDispatch;
    logfile.BufferCallback = &OnBuffer;
    TRACEHANDLE handle = OpenTraceW(&logfile);
    if (handle == INVALID_PROCESSTRACE_HANDLE)
        throw std::runtime_error("OpenTraceW could not open the ETL");
    gEtlOpened = true;
    if (data.frequency == 0)
        data.frequency = static_cast<std::uint64_t>(logfile.LogfileHeader.PerfFreq.QuadPart);
    if (logfile.LogfileHeader.PointerSize == 4 || logfile.LogfileHeader.PointerSize == 8)
        gTracePointerSize = logfile.LogfileHeader.PointerSize;
    else
        gTracePointerSize = sizeof(void*);
    data.traceClockIsQpc = data.traceClockIsQpc && logfile.LogfileHeader.ReservedFlags == 1 &&
        logfile.LogfileHeader.PerfFreq.QuadPart > 0;
    data.traceProcessorCount = logfile.LogfileHeader.NumberOfProcessors;
    data.etlBootTime100ns = logfile.LogfileHeader.BootTime.QuadPart > 0
        ? static_cast<std::uint64_t>(logfile.LogfileHeader.BootTime.QuadPart) : 0;
    data.etlClockType = logfile.LogfileHeader.ReservedFlags;
    FILETIME currentFileTime = {};
    GetSystemTimeAsFileTime(&currentFileTime);
    ULARGE_INTEGER current = {};
    current.LowPart = currentFileTime.dwLowDateTime;
    current.HighPart = currentFileTime.dwHighDateTime;
    const std::uint64_t uptime100ns = GetTickCount64() * 10000ULL;
    const std::uint64_t currentBoot = current.QuadPart >= uptime100ns ? current.QuadPart - uptime100ns : 0;
    const std::uint64_t traceBoot = logfile.LogfileHeader.BootTime.QuadPart > 0
        ? static_cast<std::uint64_t>(logfile.LogfileHeader.BootTime.QuadPart) : 0;
    const std::uint64_t bootDelta = currentBoot > traceBoot ? currentBoot - traceBoot : traceBoot - currentBoot;
    const bool bootMatches = traceBoot != 0 && bootDelta <= 20000000ULL;
    data.traceTopologyBound = data.traceTopologyBound && bootMatches &&
        logfile.LogfileHeader.NumberOfProcessors == data.coreByLogical.size();
    const ULONG result = ProcessTrace(&handle, 1, nullptr, nullptr);
    CloseTrace(handle);
    data.readEventsLost = (std::max)(data.readEventsLost, logfile.EventsLost);
    const std::uint64_t buffersObserved = (std::max)(context.bufferCallbackCount,
        static_cast<std::uint64_t>(context.buffersReadReported));
    data.readBuffers = (std::max)(data.readBuffers, static_cast<ULONG>(
        (std::min)(buffersObserved, static_cast<std::uint64_t>((std::numeric_limits<ULONG>::max)()))));
    data.eventsLost = (std::max)(data.eventsLost, logfile.LogfileHeader.EventsLost);
    data.buffersLost = (std::max)(data.buffersLost, logfile.LogfileHeader.BuffersLost);
    if (result != ERROR_SUCCESS)
        throw std::runtime_error("ProcessTrace failed while reading the ETL");
    if (!data.error.empty())
        throw std::runtime_error(data.error);
}

std::string JsonProof(const ConcurrencyProof& proof) {
    std::ostringstream out;
    out << "{\"batch_id\":" << proof.batchId << ",\"first_job\":" << proof.firstJob
        << ",\"first_tid\":" << proof.firstTid << ",\"first_core\":" << proof.firstCore
        << ",\"second_job\":" << proof.secondJob << ",\"second_tid\":" << proof.secondTid
        << ",\"second_core\":" << proof.secondCore << ",\"begin_qpc\":" << proof.begin
        << ",\"end_qpc\":" << proof.end << "}";
    return out.str();
}

std::string JsonVersionCounts(const std::map<std::uint32_t, std::uint64_t>& versions) {
    std::ostringstream out;
    out << '[';
    bool first = true;
    for (const auto& item : versions) {
        if (!first) out << ',';
        first = false;
        out << "{\"version\":" << item.first << ",\"count\":" << item.second << '}';
    }
    out << ']';
    return out.str();
}

void PrintHelp() {
    std::cout << "{\"status\":\"HELP\",\"usage\":\"city_site_cpu_trace_reader.exe <trace.etl> --topology <sidecar> | --write-topology <sidecar> | --check-topology <sidecar>\","
                 "\"capture_started\":false,\"etl_opened\":false,\"gamecore_loaded\":false,\"physical_multicore_proven\":false,"
                 "\"parses\":[\"TraceLogging job markers\",\"kernel CSwitch via TDH\",\"process/thread lifecycle via TDH\"]}\n";
}

int ReadTrace(const wchar_t* path, const wchar_t* topologyPath) {
    TraceData data;
    const MachineTopologySnapshot captured = ReadTopologySnapshot(topologyPath);
    data.coreByLogical = captured.coreByLogical;
    data.expectedBootTime100ns = captured.bootTime100ns;
    ValidateTopologySnapshot(captured, data);
    Consume(path, data, nullptr);
    data.traceTopologyBound = data.traceTopologyBound && data.frequency == captured.qpcFrequency;
    if (data.markers.empty())
        throw std::runtime_error("ETL contains no city-site job markers");
    std::map<std::uint32_t, CpuState> states;
    Consume(path, data, &states);
    ConcurrencyProof proof = {};
    const bool workerLifetimesValid = !data.lifecycleAmbiguous && MarkersHaveUniqueThreadLifetimes(data);
    const bool overlap = data.eventsLost == 0 && data.buffersLost == 0 && data.readEventsLost == 0 &&
        data.traceClockIsQpc && data.traceTopologyBound && workerLifetimesValid &&
        FindDistinctCoreOverlap(data.markers.data(), data.markers.size(), data.slices.data(), data.slices.size(), &proof);

    std::cout << "{\"schema\":\"zerosiscitysitecpu.v1\",\"capture_started\":false,\"etl_opened\":true,\"gamecore_loaded\":false,\"physical_multicore_proven\":" << (overlap ? "true" : "false") << ",\"status\":\""
              << (overlap ? "ETW_DISTINCT_CORE_OVERLAP_PROVEN" : "ETW_TRACE_READ_NO_PROOF")
              << "\",\"qpc_frequency\":" << data.frequency << ",\"clock_is_qpc\":" << (data.traceClockIsQpc ? "true" : "false")
              << ",\"topology_binding\":{\"same_current_boot\":" << (data.traceTopologyBound ? "true" : "false")
              << ",\"etl_boot_time_100ns\":" << data.etlBootTime100ns
              << ",\"etl_perf_frequency\":" << data.frequency
              << ",\"etl_clock_type_reserved_flags\":" << data.etlClockType
              << ",\"etl_processor_count\":" << data.traceProcessorCount
              << ",\"captured_sidecar_boot_time_100ns\":" << data.expectedBootTime100ns
              << ",\"topology_source\":\"captured_sidecar\"},\"kernel_event_decode\":{\"tdh_error_not_found_fallback\":true,\"process_provider_guid\":\"{3d6fa8d0-fe05-11d0-9dda-00c04fd7ba7c}\",\"process_lifecycle_versions\":" << JsonVersionCounts(data.processLifecycleVersions)
              << ",\"process_lifecycle_records_observed\":" << data.processLifecycleEventsObserved
              << ",\"process_events_emitted_worker_pid_only\":" << data.processEvents.size()
              << ",\"process_payload_strings_read\":false,\"thread_provider_guid\":\"{3d6fa8d1-fe05-11d0-9dda-00c04fd7ba7c}\",\"thread_lifecycle_versions\":" << JsonVersionCounts(data.threadLifecycleVersions)
              << ",\"thread_lifecycle_records_observed\":" << data.threadLifecycleEventsDecoded
              << ",\"thread_worker_lifecycle_rows_emitted\":" << data.threadEvents.size()
              << ",\"cswitch_versions\":" << JsonVersionCounts(data.cswitchVersions)
              << ",\"cswitch_records_observed\":" << data.cswitchesSeen
              << ",\"identity_prefix_contract\":\"ProcessId after pointer-sized UniqueProcessKey; thread ProcessId,TThreadId; CSwitch NewThreadId,OldThreadId\"},\"loss\":{\"events_lost\":" << data.eventsLost
              << ",\"buffers_lost\":" << data.buffersLost << ",\"reader_events_lost\":" << data.readEventsLost
              << ",\"buffers_read\":" << data.readBuffers << "},\"cswitch_counts\":{\"all\":"
              << data.cswitchesSeen << ",\"worker_related\":" << data.workerCswitchesSeen
              << ",\"worker_related_unmapped_cpu\":" << data.unmappedWorkerCswitches
              << "},\"topology\":[";
    bool first = true;
    for (const auto& logical : data.coreByLogical) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"group\":" << logical.first.first << ",\"logical_processor\":"
                  << static_cast<unsigned>(logical.first.second) << ",\"physical_core\":" << logical.second << "}";
    }
    std::cout << "],\"markers\":[";
    for (std::size_t i = 0; i < data.markers.size(); ++i) {
        if (i) std::cout << ',';
        const TraceMarker& marker = data.markers[i];
        std::cout << "{\"phase\":\"" << (marker.begin ? "begin" : "end") << "\",\"batch_id\":" << marker.batchId
                  << ",\"job_index\":" << marker.jobIndex << ",\"process_id\":" << marker.processId
                  << ",\"worker_tid\":" << marker.workerTid << ",\"site_count\":" << marker.siteCount
                  << ",\"qpc\":" << marker.timestamp << "}";
    }
    std::cout << "],\"thread_events\":[";
    for (std::size_t i = 0; i < data.threadEvents.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << data.threadEvents[i];
    }
    std::cout << "],\"process_events\":[";
    for (std::size_t i = 0; i < data.processEvents.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << data.processEvents[i];
    }
    std::cout << "],\"worker_cpu_slices\":[";
    for (std::size_t i = 0; i < data.slices.size(); ++i) {
        if (i) std::cout << ',';
        const CpuSlice& slice = data.slices[i];
        std::cout << "{\"process_id\":" << slice.processId << ",\"worker_tid\":" << slice.workerTid
                  << ",\"processor_index\":" << slice.processorIndex << ",\"group\":" << slice.group
                  << ",\"group_processor\":" << static_cast<unsigned>(slice.groupProcessor)
                  << ",\"physical_core\":" << slice.physicalCore << ",\"begin_qpc\":" << slice.begin
                  << ",\"end_qpc\":" << slice.end << "}";
    }
    std::cout << "],\"proof\":" << (overlap ? JsonProof(proof) : "null") << "}\n";
    return overlap ? 0 : 3;
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    gEtlOpened = false;
    if (argc == 1 || (argc == 2 && wcscmp(argv[1], L"--help") == 0)) {
        PrintHelp();
        return 0;
    }
    try {
        if (argc == 3 && wcscmp(argv[1], L"--write-topology") == 0) {
            WriteTopologySnapshot(argv[2]);
            return 0;
        }
        if (argc == 3 && wcscmp(argv[1], L"--check-topology") == 0) {
            const MachineTopologySnapshot snapshot = ReadTopologySnapshot(argv[2]);
            TraceData current;
            BuildTopology(current);
            ValidateTopologySnapshot(snapshot, current);
            std::cout << "{\"status\":\"TOPOLOGY_SIDECAR_VALID\",\"capture_started\":false,\"etl_opened\":false,\"gamecore_loaded\":false,\"physical_multicore_proven\":false,\"processor_count\":" << snapshot.coreByLogical.size() << "}\n";
            return 0;
        }
        if (argc == 4 && wcscmp(argv[2], L"--topology") == 0)
            return ReadTrace(argv[1], argv[3]);
        PrintHelp();
        return 2;
    } catch (const std::exception& error) {
        std::cout << "{\"schema\":\"zerosiscitysitecpu.v1\",\"status\":\"ETL_READ_FAILED\","
                     "\"capture_started\":false,\"etl_opened\":" << (gEtlOpened ? "true" : "false")
                  << ",\"gamecore_loaded\":false,\"physical_multicore_proven\":false,\"error\":\"" << error.what() << "\"}\n";
        return 2;
    }
}
