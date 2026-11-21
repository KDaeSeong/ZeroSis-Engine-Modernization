#pragma once

// Original and x64 BNW CvPlot::write bodies are identical for version 7.
// Primitive widths follow CvPlot.h, not the size of an aligned native object.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// No script, no build-progress table, no unit IDs; archaeology version 2.
// This is a lower bound for budgeting, never a replacement for walking fields.
constexpr std::size_t MapPlotMinimumBytes = 1569u;

inline void ReadMapPlot(Reader& reader) {
    reader.Version(7);

    // CvPlot.cpp:9586-9604; member types in CvPlot.h:749-805,823-828.
    reader.Fixed(2, 2); // signed i16 x/y
    reader.I32(); // area
    reader.Skip(1); // feature variety
    reader.Fixed(4, 2); // ownership/improvement duration, upgrade progress, culture
    reader.Fixed(6, 1); // revealed/radius/recon/river/resource counts, scratch player
    reader.Fixed(2, 2); // builder scratch turn/value
    reader.Fixed(3, 4); // scratch RouteTypes, landmass, trade-route bit flags
    for (unsigned i = 0; i < 12; ++i) reader.Bool();

    // CvPlot.cpp:9621-9637. Stored owner/plot/terrain and these route/player
    // fields are chars; the four standalone info hashes always occupy u32.
    reader.Fixed(3, 1);
    reader.Fixed(4, 4); // feature, resource, improvement, under-construction hashes
    reader.Fixed(10, 1); // players, route, anchor/data, three river directions
    reader.Fixed(5, 8); // IDInfo city pairs: full i32 owner and i32 ID

    // CvPlot.cpp:9650-9687. Plot arrays use REALLY_MAX=80, not Game's 64.
    reader.Fixed(6, 2); // NUM_YIELD_TYPES signed shorts
    reader.Fixed(80, 4); // player found values
    reader.Fixed(80, 1); // player city-radius counts
    reader.Fixed(80, 2); // team visibility counts (negative values are on wire)
    reader.Fixed(80, 1); // revealed owners
    reader.Skip(1); // river-crossing bit mask
    reader.Fixed(4, 4); // PlotBoolField::eCount DWORDs, not bool array/padding
    for (unsigned i = 0; i < 80; ++i) reader.Bool(); // resource force reveal
    reader.Fixed(80, 4); // standalone revealed-improvement hashes
    reader.Fixed(80, 2); // revealed route types
    for (unsigned i = 0; i < 22; ++i) reader.Bool(); // no-settling flags

    if (reader.Bool()) reader.String(); // optional std::string script data

    // CvPlot::read uses the OUTER value only as a positive presence check.
    // Budget both declared counts, without inventing an equality requirement.
    const auto buildPresence = reader.SignedCount(0);
    if (buildPresence != 0) {
        const auto builds = reader.SignedCount(4);
        for (std::uint32_t i = 0; i < builds; ++i) {
            // BuildArrayHelpers::Write emits a short only for nonzero hashes.
            // Its Read unknown-hash error branch incorrectly reads an int;
            // reproducing that error recovery would corrupt canonical framing.
            if (reader.U32() != 0) reader.Skip(2);
        }
    }

    // CvPlot.h:43,785 and FDataStream.h:221-228: raw C short[80][1],
    // recursively serialized without either an outer or inner length word.
    reader.Fixed(80, 2);
    const auto units = reader.Count(8);
    reader.Fixed(units, 8); // IDInfo owner/ID pairs, not native pointer/list nodes
    reader.Skip(1); // continent type

    // CvArchaeologyData writer at CvPlot.cpp:130-141.
    reader.Version(2);
    reader.Fixed(5, 4); // artifact class, era, player1, player2, great-work type
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
