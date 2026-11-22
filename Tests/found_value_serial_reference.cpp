// Build the existing dense bridge in this test translation unit so the serial
// reference can use its exact POD decoder without adding a GameCore entry point.
#include "../Source/Concurrency/FoundValueScoreBridge.cpp"

bool evaluate_found_value_serial(const ZeroSisFoundValueInput& input, std::int32_t& score) {
    Snapshot snapshot{};
    if (!CopyInput(input, snapshot)) return false;
    const auto result = zerosis::found_value::evaluate(snapshot);
    if (result.status != Status::ok) return false;
    score = result.score;
    return true;
}
