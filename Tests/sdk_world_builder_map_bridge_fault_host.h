#pragma once
#include "sdk_world_builder_map_file_host.h"
// Test-only FIFile fault transport, separate from production map code.
enum class MapIoFault {None,CreateNull,CreateClosed,CreateThrow,ReadZero,ReadOver,ReadThrow,WriteZero,WriteOver,WriteThrow,CloseBad,CloseThrow,LengthZero,LengthThrow};
struct MapIoControl {
    MapIoFault fault=MapIoFault::None;
    uint chunk=UINT_MAX,failAfter=0,created=0,closed=0;
    int live=0;
};
extern MapIoControl mapIo;
void InstallFaultMapFileHost();
