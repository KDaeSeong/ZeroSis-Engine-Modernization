#pragma once

#include <stdint.h>

#define ZEROSIS_CITY_SITE_ABI_VERSION 1u
#define ZEROSIS_CITY_SITE_CONFIG_VERSION 1u
#define ZEROSIS_CITY_SITE_MAX_TILES 64u

#define ZEROSIS_CITY_SITE_OK 0
#define ZEROSIS_CITY_SITE_INVALID_INPUT 1
#define ZEROSIS_CITY_SITE_BATCH_FAILURE 2
#define ZEROSIS_CITY_SITE_OVERFLOW 3

/* Stable C POD boundary. SDK/CvCitySpecializationAI owns and captures every value. */
#pragma pack(push, 8)
typedef struct ZeroSisCitySiteCell {
    int32_t ring_distance;
    int32_t yields[4]; /* FOOD, PRODUCTION, GOLD, SCIENCE */
    uint8_t present;
    uint8_t foreign_owned;
    uint8_t science_clear;
    uint8_t reserved;
} ZeroSisCitySiteCell;

typedef struct ZeroSisCitySiteInput {
    uint32_t abi_version;
    uint32_t config_version;
    uint32_t tile_count;
    uint32_t reserved;
    int32_t ring_weights[3];
    ZeroSisCitySiteCell cells[ZEROSIS_CITY_SITE_MAX_TILES];
} ZeroSisCitySiteInput;

typedef struct ZeroSisCitySiteResult {
    int32_t values[4];
} ZeroSisCitySiteResult;

typedef struct ZeroSisCitySiteMetrics {
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
    uint64_t worker_batch_us;
    uint32_t worker_thread_ids[4];
    uint32_t worker_job_counts[4];
} ZeroSisCitySiteMetrics;
#pragma pack(pop)

#ifdef __cplusplus
static_assert(sizeof(ZeroSisCitySiteCell) == 24, "City-site cell ABI changed");
static_assert(sizeof(ZeroSisCitySiteInput) == 1564, "City-site input ABI changed");
static_assert(sizeof(ZeroSisCitySiteResult) == 16, "City-site result ABI changed");
static_assert(sizeof(ZeroSisCitySiteMetrics) == 80, "City-site metrics ABI changed");
extern "C" {
#endif

/* Outputs are copied only after every job completes successfully. */
int32_t ZeroSisEvaluateCitySites(const ZeroSisCitySiteInput* inputs,
                                uint32_t count,
                                uint32_t worker_count,
                                ZeroSisCitySiteResult* results,
                                ZeroSisCitySiteMetrics* metrics);

#ifdef __cplusplus
}
#endif
