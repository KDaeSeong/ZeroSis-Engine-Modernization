"""Independent regression for the D3D11 CityView integer-ID raster overlay."""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))
from ui_pixel_scene import Compiler, city_view_raster_projection, city_view_raster_rgba  # noqa: E402


def raster_projection():
    return {
        'policy': 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1',
        'cameraX': 4, 'cameraY': 4, 'gridWidth': 9, 'gridHeight': 9,
        'wrapX': False, 'wrapY': False, 'tileWidth': 84,
        'centerX': 960, 'centerY': 540,
        'viewportWidth': 1920, 'viewportHeight': 1080, 'mapWidth': 1920,
        'frameGeneration': 27,
        'plots': {
            '0': {'centerX': 600.5, 'centerY': 400.25, 'anchorVisible': False,
                  'spans': [[100, 100, 3], [101, 100, 2]]},
            '21': {'centerX': 1200, 'centerY': 700, 'anchorVisible': True,
                   'spans': [[200, 300, 2]]},
        },
    }


def highlight(x, y, color):
    return {'hex': {'x': x, 'y': y},
            'color': dict(zip(('x', 'y', 'z', 'w'), color))}


class CityViewRasterProjectionTests(unittest.TestCase):
    def test_full_viewport_overlay_uses_only_depth_winning_spans(self):
        projection = raster_projection()
        highlights = [highlight(0, 0, (1, 0, .5, .5)),
                      highlight(0, 1, (0, 0, 1, 1)),  # axial -> grid (0,1), absent row
                      highlight(2, 2, (0, 1, 0, 1))]  # axial -> grid (3,2), index 21
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            game = base / 'game'
            output = base / 'candidate'
            game.mkdir()
            compiler = object.__new__(Compiler)
            compiler.game_root = game.resolve()
            compiler.destination = output
            compiler.width, compiler.height = 1920, 1080
            compiler.textures, compiler.texture_ids, compiler.sprites = [], {}, []
            compiler.derived_textures = []
            compiler.city_view_projection = None
            compiler.city_view_hexes = []
            compiler.city_view_policy = None
            compiler.city_view_hex_overlay({
                'viewingMode': True, 'retailWorldProjectionVerified': False,
                'projection': projection, 'hexCoordinatePolicy': 'ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1',
                'hexHighlights': highlights,
            })
            self.assertEqual(len(compiler.sprites), 1)
            sprite = compiler.sprites[0]
            self.assertEqual(sprite[2:6], (0, 0, 1920, 1080))
            self.assertEqual(sprite[6:10], (0, 0, 1920, 1080))
            self.assertEqual(compiler.city_view_policy['projection_policy'],
                             'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1')
            self.assertEqual(compiler.city_view_policy['pixel_policy'],
                             'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1')
            self.assertFalse(compiler.city_view_policy['retail_shader_equivalence_verified'])
            self.assertEqual(compiler.city_view_policy['frame_generation'], 27)
            self.assertEqual(compiler.city_view_policy['hex_count'], 3)
            self.assertEqual(compiler.city_view_policy['rasterized_hex_count'], 2)
            self.assertEqual(compiler.city_view_policy['rasterized_pixel_count'], 7)
            self.assertFalse(compiler.city_view_hexes[0]['anchor_visible'])
            self.assertEqual(compiler.city_view_hexes[0]['spans'], [[100, 100, 3], [101, 100, 2]])
            self.assertFalse(compiler.city_view_hexes[1]['plot_present'])

            dds_path = Path(compiler.textures[0])
            dds = dds_path.read_bytes()
            words = struct.unpack('<32I', dds[:128])
            self.assertEqual((words[3], words[4], words[5]), (1080, 1920, 7680))
            payload = dds[128:]
            self.assertEqual(len(payload), 1920 * 1080 * 4)
            self.assertEqual(payload[(100 * 1920 + 100) * 4:(100 * 1920 + 100) * 4 + 4],
                             bytes((128, 0, 255, 128)))
            self.assertEqual(payload[(100 * 1920 + 103) * 4:(100 * 1920 + 103) * 4 + 4], bytes(4))
            self.assertEqual(payload[(200 * 1920 + 300) * 4:(200 * 1920 + 300) * 4 + 4],
                             bytes((0, 255, 0, 255)))
            self.assertEqual(compiler.derived_textures[0]['pixel_policy'],
                             'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1')

    def test_schema_and_span_validation_reject_malformed_data(self):
        base = raster_projection()
        self.assertEqual(len(city_view_raster_projection(base)), 2)
        lexical = copy.deepcopy(base)
        lexical['gridWidth'], lexical['gridHeight'] = 4, 4
        lexical['cameraX'], lexical['cameraY'] = 1, 1
        lexical['plots'] = {'10': {'centerX': 2, 'centerY': 2, 'anchorVisible': True, 'spans': []},
                            '2': {'centerX': 2, 'centerY': 2, 'anchorVisible': True, 'spans': []}}
        self.assertEqual(set(city_view_raster_projection(lexical)), {'10', '2'})
        cases = []
        bad = copy.deepcopy(base); bad['frameGeneration'] = True; cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['0']['centerX'] = float('nan'); cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['01'] = bad['plots'].pop('0'); cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['0']['spans'] = [[100, 100, 3], [100, 102, 2]]; cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['0']['spans'] = [[1080, 0, 1]]; cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['0']['spans'] = [[100, 1, True]]; cases.append(bad)
        bad = copy.deepcopy(base); bad['plots']['0']['anchorVisible'] = 1; cases.append(bad)
        bad = copy.deepcopy(base); bad['extra'] = 1; cases.append(bad)
        for projection in cases:
            with self.subTest(projection=projection):
                with self.assertRaises(ValueError):
                    city_view_raster_projection(projection)

    def test_highlights_require_order_and_nonoverlapping_contours(self):
        projection = raster_projection()
        with self.assertRaisesRegex(ValueError, 'deterministic y/x order'):
            city_view_raster_rgba(projection, [highlight(0, 1, (1, 1, 1, 1)),
                                               highlight(0, 0, (1, 1, 1, 1))])
        overlap = copy.deepcopy(projection)
        overlap['plots']['21']['spans'] = [[100, 101, 1]]
        with self.assertRaisesRegex(ValueError, 'spans overlap'):
            city_view_raster_rgba(overlap, [highlight(0, 0, (1, 1, 1, 1)),
                                            highlight(2, 2, (0, 1, 0, 1))])

    def test_existing_2d_policy_still_uses_hex_outline_path(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            compiler = object.__new__(Compiler)
            compiler.game_root = (base / 'game').resolve()
            compiler.game_root.mkdir()
            compiler.destination = base / 'candidate'
            compiler.width, compiler.height = 1920, 1080
            compiler.textures, compiler.texture_ids, compiler.sprites = [], {}, []
            compiler.derived_textures = []
            compiler.city_view_projection = None
            compiler.city_view_hexes = []
            compiler.city_view_policy = None
            compiler.city_view_hex_overlay({
                'viewingMode': True, 'retailWorldProjectionVerified': False,
                'projection': {'policy': 'ZEROSIS_2D_CITY_VIEW_V1', 'cameraX': 4, 'cameraY': 4,
                               'gridWidth': 9, 'gridHeight': 9, 'wrapX': False, 'wrapY': False,
                               'tileWidth': 84, 'centerX': 960, 'centerY': 540},
                'hexCoordinatePolicy': 'ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1',
                'hexHighlights': [highlight(0, 0, (1, 0, 0, 1))],
            })
            self.assertEqual(compiler.city_view_policy['pixel_policy'],
                             'ZEROSIS_CITYVIEW_D2D_HEX_OUTLINE_RGBA_COVERAGE_V1')
            self.assertEqual(len(compiler.sprites), 1)
            self.assertEqual(compiler.sprites[0][2:6], (0, 0, 84, 97))


if __name__ == '__main__':
    unittest.main(verbosity=2)
