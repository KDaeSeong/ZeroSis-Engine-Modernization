"""Verify the retail terrain cell builder and centered transform without loading the game."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude_geometry"))
from basis_retail_probe import Image, REGIONS, REGION_SHA256

# Disassembled and checked on the local DX11 image. Only rendering spans are pinned.
SPANS = {
    "cell_count_ceil_intervals_over_64": (0x5df275, 0x5df291, "c90dffaae630d86212fe9026177d84cdac16cb67941c4b07a6a20f0e409e8648"),
    "iteration_starts_at_zero_with_n_minus_one": (0x5df2d1, 0x5df307, "38c30e9aa08d6d3f224e48fd900964315caceac47e408915c39f4d39087cc3b9"),
    "cell_stride_64_and_clipped_inclusive_dimensions": (0x5df365, 0x5df3d9, "eeb8123cb69b76d24d29b35f590474841b4b5243731a7293210c8d68efea288f"),
    "pass_renderer_base_plus_eight": (0x5df332, 0x5df365, "4848ef55f58c31fac646704b8e7b2eab771a2e6c58bb2c2326d404d98200f4a9"),
    "store_chunk_owner": (0x679af0, 0x679b06, "5ba7a6ff8678231dcfc87a644d1118d1fc0eba84953b7c118f846319e080e981"),
    "assign_cell_origin_size_and_world_minimum": (0x5c4ab9, 0x5c4b3a, "9128e4567e21c0785b1b552e7ad8c5900ec7575c6a6a472ac9f7dbfdb849466f"),
    "center_from_halved_integer_dimensions": (0x678303, 0x678356, "b4c9b824c89b65f88d427f7f6a1f13d51008ad1e32e8170b72bf66f7d4ad1b75"),
    "negated_center_to_world_translation": (0x5c3806, 0x5c3853, "43747be126ba09e2c1f57ab452999c3dd9f87f1e5b7a2245c9f1d197b038d7db"),
    "independent_lod_axis_steps": (0x5c3961, 0x5c39e0, "ea3ffc5bdec8fb4375daddafbbf3a348b5ca0d9a0179d7a02f2d96bf91300f5c"),
    "height_texture_page_bias": (0x79c210, 0x79c277, "5a40d065dacdc4ab505064bcd1abb3d651b16c17155c19c810d97aff9d7fdefc"),
}


def verify(executable):
    data = executable.read_bytes()
    image = Image(data)
    spans = dict(SPANS)
    for name in ("patch_index_generator", "patch_draw_cb0_writer", "lod_draw_item_builder"):
        spans[name] = (*REGIONS[name], REGION_SHA256[name])
    for name, (start, end, expected) in spans.items():
        if hashlib.sha256(image.read(start, end - start)).hexdigest() != expected:
            raise ValueError("Retail terrain instructions differ at " + name)
    if (image.u32(0xb9a6d4), image.u32(0xb9a6d8)) != (0x3f800000, 0x3f5db22d):
        raise ValueError("Unexpected retail XY metrics")
    return {"status": "PASS_RETAIL_TERRAIN_PATCH_LAYOUT", "exe_sha256": hashlib.sha256(data).hexdigest(),
            "checked_spans": len(spans), "cell_intervals": 64, "maximum_level": 4,
            "world_origin": "(-floor(W/2)*metricX, -floor(H/2)*metricY, 0)",
            "height_page_bias_is_separate": True, "scope": "static on-disk instructions and default metrics"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    print(json.dumps(verify(parser.parse_args().executable)))
