#pragma once

#include <stdint.h>

// Stable C ABI shared by the SDK's C++14 translation unit and the isolated
// C++17 worker bridge. Keep this header free of STL and C++17 declarations.
#pragma pack(push, 8)
typedef struct ZeroSisExploreNeighborValue {
    uint8_t exists;
    uint8_t revealed;
    int32_t distance_from_origin;
} ZeroSisExploreNeighborValue;

typedef struct ZeroSisExplorePlotValue {
    int8_t offset_x;
    int8_t offset_y;
    uint8_t exists;
    uint8_t is_center_plot;
    uint8_t revealed;
    uint8_t adjacent_revealed;
    int32_t distance_from_origin;
    uint8_t origin_can_see_candidate;
    ZeroSisExploreNeighborValue adjacent_plots[6];
    uint8_t water;
    uint8_t mountain;
    uint8_t hills;
    uint8_t has_feature;
    uint8_t feature_impassable;
    uint8_t feature_see_through_change_positive;
} ZeroSisExplorePlotValue;

typedef struct ZeroSisExploreScoreInput {
    uint8_t domain; /* 0=land, 1=sea, 2=unsupported */
    ZeroSisExplorePlotValue plots[9];
} ZeroSisExploreScoreInput;

typedef struct ZeroSisExploreBatchMetrics {
    uint64_t worker_batch_us; /* snapshot-free bridge entry through joined results */
    uint32_t workers_started; /* thread creation metric only */
    uint32_t jobs_started;
    uint32_t jobs_completed;
    uint32_t worker_threads_used; /* distinct threads that actually scored a job */
    uint32_t maximum_overlapping_jobs;
    uint32_t worker_ids[64]; /* per-batch IDs assigned on first actual invocation */
} ZeroSisExploreBatchMetrics;
#pragma pack(pop)

#ifdef __cplusplus
static_assert(sizeof(ZeroSisExploreNeighborValue) == 8, "Explore ABI neighbor size changed");
static_assert(sizeof(ZeroSisExplorePlotValue) == 72, "Explore ABI plot size changed");
static_assert(sizeof(ZeroSisExploreScoreInput) == 652, "Explore ABI score input size changed");
static_assert(sizeof(ZeroSisExploreBatchMetrics) == 288, "Explore ABI metrics size changed");
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Returns 0 on a complete ordered result, 1 on invalid input, 2 on batch failure. */
int32_t ZeroSisEvaluateExploreScores(const ZeroSisExploreScoreInput* inputs,
                                     uint32_t count,
                                     uint32_t worker_count,
                                     int32_t* scores,
                                     ZeroSisExploreBatchMetrics* metrics);

#ifdef __cplusplus
}
#endif
