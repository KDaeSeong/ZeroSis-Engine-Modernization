"""Pin public BNW river getters, representative edges and neighbour coordinates."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
ORIGINAL = PROJECT / 'Source/SDK_BNW_Original'
CURRENT = PROJECT / 'Source/SDK_BNW_x64'


def ref(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def body(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[begin + 1:end - 1].strip()


def main():
    names = ['CvGameCoreDLLUtil/include/CvDllInterfaces.h', 'CvGameCoreDLLUtil/include/CvEnums.h',
             'CvGameCoreDLL_Expansion2/CvDllPlot.cpp', 'CvGameCoreDLL_Expansion2/CvPlot.cpp',
             'CvGameCoreDLL_Expansion2/CvPlot.h', 'CvGameCoreDLL_Expansion2/CvGlobals.cpp',
             'CvGameCoreDLL_Expansion2/CvGameCoreUtils.h']
    texts = {name: (ORIGINAL / name).read_bytes().decode('latin1') for name in names}
    dll, plot, header, enums, globals_, utility = [texts[name] for name in names[2:3] + names[3:5] + names[1:2] + names[5:]]
    interface = texts[names[0]]
    checks = {}
    public_to_body = [('IsNEOfRiver', 'isNEOfRiver'), ('IsWOfRiver', 'isWOfRiver'), ('IsNWOfRiver', 'isNWOfRiver'),
                      ('GetRiverEFlowDirection', 'getRiverEFlowDirection'),
                      ('GetRiverSEFlowDirection', 'getRiverSEFlowDirection'),
                      ('GetRiverSWFlowDirection', 'getRiverSWFlowDirection')]
    current_dll = (CURRENT / names[2]).read_bytes().decode('latin1')
    for public, member in public_to_body:
        signature = ('bool' if public.startswith('Is') else 'FlowDirectionTypes') + ' CvDllPlot::' + public + '() const'
        checks[public + '_public'] = ('DLLCALL ' + public + '() const = 0;') in interface
        checks[public + '_value_getter'] = body(dll, signature) == 'return m_pPlot->' + member + '();'
        checks[public + '_current_adapter_same'] = body(current_dll, signature) == body(dll, signature)
    edges = [dict(flag='IsWOfRiver', member='W', edge='E', neighbour='EAST', neighbour_direction=1,
                  flow_getter='GetRiverEFlowDirection', storage='m_eRiverEFlowDirection',
                  allowed_flow=[-1, 0, 3], allowed_flow_names=['NO_FLOWDIRECTION', 'NORTH', 'SOUTH']),
             dict(flag='IsNWOfRiver', member='NW', edge='SE', neighbour='SOUTHEAST', neighbour_direction=2,
                  flow_getter='GetRiverSEFlowDirection', storage='m_eRiverSEFlowDirection',
                  allowed_flow=[-1, 1, 4], allowed_flow_names=['NO_FLOWDIRECTION', 'NORTHEAST', 'SOUTHWEST']),
             dict(flag='IsNEOfRiver', member='NE', edge='SW', neighbour='SOUTHWEST', neighbour_direction=3,
                  flow_getter='GetRiverSWFlowDirection', storage='m_eRiverSWFlowDirection',
                  allowed_flow=[-1, 5, 2], allowed_flow_names=['NO_FLOWDIRECTION', 'NORTHWEST', 'SOUTHEAST'])]
    for edge in edges:
        text = body(plot, 'void CvPlot::set' + edge['member'] + 'OfRiver(bool bNewValue, FlowDirectionTypes eRiverDir)')
        checks[edge['edge'] + '_field_assignment'] = re.search(re.escape(edge['storage']) + r'\s*=\s*eRiverDir;', text) is not None
        checks[edge['edge'] + '_allowed_flow_assert'] = all('eRiverDir == ' + ('NO_FLOWDIRECTION' if value == -1 else 'FLOWDIRECTION_' + name)
            in text for value, name in zip(edge['allowed_flow'], edge['allowed_flow_names']))
        checks[edge['edge'] + '_field_comment'] = re.search(re.escape(edge['storage']) + r'; // flow direction on the ' + edge['edge'] + r' edge', header) is not None
    directions = ['NORTHEAST', 'EAST', 'SOUTHEAST', 'SOUTHWEST', 'WEST', 'NORTHWEST']
    flows = ['NORTH', 'NORTHEAST', 'SOUTHEAST', 'SOUTH', 'SOUTHWEST', 'NORTHWEST']
    checks['direction_enum_order'] = re.search(r'NO_DIRECTION\s*=\s*-1,\s*' + r'\s*'.join('DIRECTION_' + x + ',' for x in directions), enums) is not None
    checks['flow_enum_order'] = re.search(r'NO_FLOWDIRECTION\s*=\s*-1,\s*' + r'\s*'.join('FLOWDIRECTION_' + x + ',' for x in flows), enums) is not None
    dx = [0, 1, 1, 0, -1, -1]
    dy = [1, 0, -1, -1, 0, 1]
    for axis, expected in [('X', dx), ('Y', dy)]:
        array = re.search(r'int aiPlotDirection' + axis + r'\[NUM_DIRECTION_TYPES\]\s*=\s*\{([^}]+)\}', globals_)[1]
        values = [int(x) for x in re.findall(r'^\s*(-?\d+),', array, re.M)]
        checks['hex_direction_' + axis] = values == expected
    checks['negative_floor_half_conversion'] = '(iY - 1)/2' in body(utility, 'inline int xToHexspaceX(')
    checks['conversion_before_and_after_direction'] = all(x in body(utility, 'inline CvPlot* plotDirection(')
        for x in ['xToHexspaceX(iX , iY)', 'GC.getPlotDirectionX()[eDirection]', 'GC.getPlotDirectionY()[eDirection]', 'hexspaceXToX(iX, iY)'])
    crossing = body(plot, 'void CvPlot::updateRiverCrossing(DirectionTypes eIndex)')
    for direction, expression in [('EAST', 'isWOfRiver()'), ('SOUTHEAST', 'isNWOfRiver()'), ('SOUTHWEST', 'isNEOfRiver()')]:
        checks['crossing_owner_' + direction] = re.search(r'case DIRECTION_' + direction + r':\s*bValid = ' + re.escape(expression) + ';', crossing) is not None
    assert all(checks.values()), [name for name, passed in checks.items() if not passed]
    neighbour_cases = []
    for y in (-3, -2, -1, 0, 1, 2, 3):
        for x in (-1, 0, 1):
            h = x - y // 2
            neighbours = [(h + dx[i] + (y + dy[i]) // 2, y + dy[i]) for i in range(6)]
            p = y & 1
            reference = [(x+p,y+1),(x+1,y),(x+p,y-1),(x+p-1,y-1),(x-1,y),(x+p-1,y+1)]
            assert neighbours == reference
            neighbour_cases.append(dict(x=x, y=y, neighbours=neighbours))
    result = dict(schema='zerosis.original_water.phase3.sdk_river_contract.v1',
        status='PASS_READ_ONLY_PUBLIC_SDK_RIVER_EDGE_CONTRACT', source_checks=checks,
        sources=[ref(ORIGINAL/name) for name in names] + [ref(CURRENT/names[2])],
        representative_edges=edges, direction_enum={name:i for i,name in enumerate(directions)},
        flow_enum=dict(NO_FLOWDIRECTION=-1, **{name:i for i,name in enumerate(flows)}),
        axial_directions=[dict(direction=directions[i], dh=dx[i], dy=dy[i]) for i in range(6)],
        offset_neighbours=['(x+p,y+1)','(x+1,y)','(x+p,y-1)','(x+p-1,y-1)','(x-1,y)','(x+p-1,y+1)'],
        offset_parity='p=y&1, xToHexspaceX=x-floor(y/2), original +Y is north; negative-row floor handling is explicit',
        current_world_orientation='World X=x+0.5*(y&1), World Z=-y*sqrt(3)/2. Therefore original NORTH flow decreases current World Z.',
        arithmetic_cases=len(neighbour_cases), arithmetic_reference='Independent offset-neighbour expressions compared to SDK axial conversions for both row parities and negative rows.',
        proposed_snapshot=['bool riverW=false, riverNW=false, riverNE=false', 'int flowE=-1, flowSE=-1, flowSW=-1'],
        snapshot_policy='Capture these existing public value getters only after IsRevealed. Do not query hidden terrain/river fields. No new ABI slot, save key or schema is needed.',
        geometry_policy='Normalise the three representative flags to E/SE/SW. A visible physical shared edge is generated once by its representative owner; require both endpoints explored before using neighbour terrain/river data.',
        caveats=['River-crossing land-only filters belong to gameplay movement. They establish ownership but do not prove renderer river-mouth or water-adjacent suppression rules.',
                 'Render widths, elevation, joins/caps, texture-coordinate scale and motion remain candidates unless independently matched to renderer evidence.',
                 'Vertical wrapping must preserve odd-row parity; existing controlled V2 path rejects odd map heights for vertical wrap.'],
        source_or_original_files_modified=False, host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    with (STAGE/'sdk_river_contract.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], source_checks=len(checks), arithmetic_cases=len(neighbour_cases),
                         source_files=len(result['sources']), representative_edges=3)))


if __name__ == '__main__':
    main()
