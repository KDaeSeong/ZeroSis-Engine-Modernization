#pragma once

#include <stdint.h>

#define ZEROSIS_FOUND_VALUE_ABI_VERSION 1u
#define ZEROSIS_FOUND_VALUE_CONFIG_VERSION 1u
#define ZEROSIS_FOUND_VALUE_TILE_COUNT 225u
#define ZEROSIS_FOUND_VALUE_WORKER_SLOTS 4u
#define ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY 0u
#define ZEROSIS_FOUND_VALUE_OWNER_UNOWNED 0u
#define ZEROSIS_FOUND_VALUE_OWNER_PLAYER 1u
#define ZEROSIS_FOUND_VALUE_OWNER_OTHER 2u

#define ZEROSIS_FOUND_VALUE_OK 0
#define ZEROSIS_FOUND_VALUE_INVALID_INPUT 1
#define ZEROSIS_FOUND_VALUE_WRONG_OWNER_THREAD 2
#define ZEROSIS_FOUND_VALUE_BATCH_FAILURE 3
#define ZEROSIS_FOUND_VALUE_OVERFLOW 4
#define ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT 5
#define ZEROSIS_FOUND_VALUE_UNSUPPORTED_PATH 6

/* Fixed-width C POD mirror of zerosis::found_value::Tile. Boolean fields are 0 or 1. */
#pragma pack(push, 8)
typedef struct ZeroSisFoundValueTile {
    uint32_t present;
    int32_t distance;
    uint32_t owner;
    uint32_t city;
    uint32_t city_owner_is_major;
    int32_t food_value;
    int32_t happiness_value;
    int32_t production_value;
    int32_t gold_value;
    int32_t science_value;
    int32_t faith_value;
    int32_t resource_value;
    int32_t strategic_value;
    uint32_t forest;
    uint32_t jungle;
    uint32_t wetlands;
    uint32_t natural_wonder;
    uint32_t desert_without_resource;
    uint32_t hills;
    int32_t adjacent_mountains;
    uint32_t unimproved;
} ZeroSisFoundValueTile;

/* Fixed-width C POD mirror of the supported Snapshot path. */
typedef struct ZeroSisFoundValueInput {
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
    ZeroSisFoundValueTile tiles[ZEROSIS_FOUND_VALUE_TILE_COUNT];
} ZeroSisFoundValueInput;

typedef struct ZeroSisFoundValueConfig {
    uint32_t abi_version;
    uint32_t config_version;
    uint32_t requested_workers;
    uint32_t owner_thread_id;
    uint32_t reserved[4];
} ZeroSisFoundValueConfig;

typedef struct ZeroSisFoundValueResult {
    int32_t score;
    uint32_t status;
} ZeroSisFoundValueResult;

typedef struct ZeroSisFoundValueMetrics {
    uint32_t abi_version;
    uint32_t config_version;
    uint32_t requested_workers;
    uint32_t status;
    uint32_t jobs_total;
    uint32_t jobs_started;
    uint32_t jobs_completed;
    uint32_t workers_started;
    uint32_t worker_threads_used;
    uint32_t maximum_overlapping_jobs;
    uint32_t owner_thread_id;
    uint32_t reserved;
    uint64_t worker_batch_us;
    uint32_t worker_thread_ids[ZEROSIS_FOUND_VALUE_WORKER_SLOTS];
    uint32_t worker_job_counts[ZEROSIS_FOUND_VALUE_WORKER_SLOTS];
} ZeroSisFoundValueMetrics;
#pragma pack(pop)

#ifdef __cplusplus
static_assert(sizeof(ZeroSisFoundValueTile) == 84, "Found-value tile ABI changed");
static_assert(sizeof(ZeroSisFoundValueInput) == 19140, "Found-value input ABI changed");
static_assert(sizeof(ZeroSisFoundValueConfig) == 32, "Found-value config ABI changed");
static_assert(sizeof(ZeroSisFoundValueResult) == 8, "Found-value result ABI changed");
static_assert(sizeof(ZeroSisFoundValueMetrics) == 88, "Found-value metrics ABI changed");
extern "C" {
#endif

/*
 * Synchronous all-or-nothing scoring. Caller-owned SDK observations are copied
 * before workers start; no SDK pointers enter worker code. `config` must name
 * the current calling OS thread as owner. Config, input, results, and metrics
 * ranges must be pairwise nonoverlapping.
 * On any failure, result records are left unchanged; metrics may still describe
 * the failed invocation when its range is disjoint from all other arguments.
 */
int32_t ZeroSisFoundValueEvaluateBatch(const ZeroSisFoundValueInput* inputs,
                                       uint32_t count,
                                       const ZeroSisFoundValueConfig* config,
                                       ZeroSisFoundValueResult* results,
                                       ZeroSisFoundValueMetrics* metrics);

#ifdef __cplusplus
}
#endif
