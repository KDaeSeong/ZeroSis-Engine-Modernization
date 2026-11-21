#pragma once

#include "FoundValueScoreBridge.h"

#include <stddef.h>
#include <stdint.h>

#define ZEROSIS_FOUND_VALUE_SHARED_ABI_VERSION 1u
#define ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT UINT32_MAX

#pragma pack(push, 8)
/* Exactly the common, tile-free 240-byte prefix of ZeroSisFoundValueInput.
   Per-center flags and center_area are zero placeholders; center_present is one. */
typedef struct ZeroSisFoundValueSharedCommon {
    uint32_t abi_version;
    uint32_t config_version;
    uint32_t path;
    uint32_t valid;
    uint32_t has_player;
    uint32_t center_present;
    uint32_t capital_present;
    uint32_t center_can_found_visible;
    uint32_t center_can_found_full;
    uint32_t center_has_unique_luxury;
    uint32_t center_has_resource_for_team;
    uint32_t center_is_river;
    uint32_t center_is_coastal;
    uint32_t coastal_civilization;
    uint32_t human_player;
    uint32_t faith_from_unimproved_forest;
    uint32_t move_friendly_woods_as_road;
    uint32_t gets_natural_wonder_yield_modifier;
    uint32_t is_inca;
    uint32_t is_brazil;
    uint32_t is_morocco;
    uint32_t is_netherlands;
    int32_t center_area;
    int32_t capital_area;
    int32_t naval_flavor;
    int32_t growth_flavor;
    int32_t expansion_flavor;
    int32_t boldness;
    int32_t ring_modifier[8];
    int32_t settler_food_multiplier;
    int32_t settler_happiness_multiplier;
    int32_t settler_production_multiplier;
    int32_t settler_gold_multiplier;
    int32_t settler_science_multiplier;
    int32_t settler_faith_multiplier;
    int32_t faith_flavor_multiplier;
    int32_t settler_resource_multiplier;
    int32_t settler_strategic_multiplier;
    int32_t build_on_resource_percent;
    int32_t build_on_river_percent;
    int32_t build_on_coast_percent;
    int32_t min_city_range;
    int32_t min_water_size_for_ocean;
    int32_t brazil_multiplier;
    int32_t spain_multiplier;
    int32_t morocco_multiplier;
    int32_t netherlands_multiplier;
    int32_t inca_multiplier;
    int32_t major_civ_count;
    uint32_t reserved[4];
} ZeroSisFoundValueSharedCommon;

typedef struct ZeroSisFoundValueSharedPlot {
    ZeroSisFoundValueTile tile;
    int32_t strategic_by_distance[8];
} ZeroSisFoundValueSharedPlot;

typedef struct ZeroSisFoundValueSharedSlot {
    uint32_t map_plot_index;
    int32_t distance;
} ZeroSisFoundValueSharedSlot;

typedef struct ZeroSisFoundValueSharedCandidate {
    uint32_t center_plot_index;
    uint32_t center_can_found_visible;
    uint32_t center_can_found_full;
    uint32_t center_has_unique_luxury;
    uint32_t center_has_resource_for_team;
    uint32_t center_is_river;
    uint32_t center_is_coastal;
    int32_t center_area;
    uint32_t reserved[4];
    ZeroSisFoundValueSharedSlot slots[ZEROSIS_FOUND_VALUE_TILE_COUNT];
} ZeroSisFoundValueSharedCandidate;
#pragma pack(pop)

#ifdef __cplusplus
static_assert(sizeof(ZeroSisFoundValueSharedCommon) == 240, "Found-value shared common ABI changed");
static_assert(offsetof(ZeroSisFoundValueSharedCommon, reserved) ==
              offsetof(ZeroSisFoundValueInput, reserved), "Found-value shared common prefix changed");
static_assert(sizeof(ZeroSisFoundValueSharedPlot) == 116, "Found-value shared plot ABI changed");
static_assert(sizeof(ZeroSisFoundValueSharedSlot) == 8, "Found-value shared slot ABI changed");
static_assert(sizeof(ZeroSisFoundValueSharedCandidate) == 1848, "Found-value shared candidate ABI changed");
static_assert(offsetof(ZeroSisFoundValueSharedCandidate, slots) == 48,
              "Found-value shared candidate slot offset changed");
extern "C" {
#endif

/*
 * Synchronous shared-facts batch. Every argument range must be disjoint.
 * Caller memory is fully copied and validated on the owner thread before any
 * jobs launch. Jobs carry candidate indices only; no SDK pointers are accepted.
 * On any failure, result records remain unchanged. Metrics may describe a
 * failed invocation after disjoint ranges have been validated.
 */
int32_t ZeroSisFoundValueEvaluateSharedBatch(
    const ZeroSisFoundValueSharedCommon* common,
    const ZeroSisFoundValueSharedPlot* plots,
    uint32_t plot_count,
    const ZeroSisFoundValueSharedCandidate* candidates,
    uint32_t candidate_count,
    const ZeroSisFoundValueConfig* config,
    ZeroSisFoundValueResult* results,
    ZeroSisFoundValueMetrics* metrics);

/* Owner-thread-only diagnostic accessor; returns zero outside a successful nonempty batch. */
uint64_t ZeroSisFoundValueSharedLastBatchId(void);

#ifdef __cplusplus
}
#endif
