"""Trim immutable public Pregame examples in memory; never read user saves."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
from prepare_retail_header_fixtures import SAMPLES, COMMIT, REPOSITORY, prefix_end, artifact, require, ordinary_ancestors

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/pregame_boundary'
DESTINATION = PROJECT / 'Tests/Fixtures/RetailSavePregame'
REPORT = STAGE / 'fixtures.json'


def walk(data, begin):
    """Follow active BNW serializers; no scanning for compression signatures."""
    at = begin
    limit = min(len(data), 65536)
    fields = []
    records = 0

    def take(count):
        nonlocal at
        require(0 <= count <= limit - at, f'Truncated public Pregame field at {at}')
        value = data[at:at+count]
        at += count
        return value

    def word():
        return struct.unpack('<I', take(4))[0]

    def string():
        length = word()
        require(length <= 65536, f'Public string exceeds bounded fixture at {at-4}')
        return take(length)

    def field(name, operation):
        start = at
        value = operation()
        row = dict(name=name, offset=start, bytes=at-start)
        if isinstance(value, int):
            row['value'] = value
        fields.append(row)
        return value

    def fixed(count):
        take(count)

    def strings(count):
        for _ in range(count):
            string()

    def array(name, width=0, options=False):
        def read():
            nonlocal records
            count = word()
            minimum = width or (8 if options else 4)
            require(count <= 16384 and count <= (limit-at)//minimum, f'Invalid {name} count at {at-4}')
            records += count
            require(records <= 262144, 'Public fixture record budget exceeded')
            if width:
                fixed(count*width)
            else:
                for _ in range(count):
                    string()
                    if options:
                        fixed(4)
            return count
        return field(name, read)

    def base():
        fixed(4)
        strings(8)

    wrapper_start = at
    field('wrapper.identity_strings', lambda: strings(3))
    field('wrapper.opaque_id_1', lambda: fixed(16))
    field('wrapper.version', string)
    field('wrapper.opaque_id_2_and_word', lambda: fixed(20))
    slot_start = at
    slot_version = field('slot.version', word)
    require(slot_version == 3, 'Unsupported public slot-hints profile')
    field('slot.speed_size_map', lambda: (fixed(8), string()))
    for name, width in (('civilizations',4),('nicknames',0),('status',4),('claims',4),
                        ('teams',4),('handicaps',4),('civilization_keys',0),('leader_keys',0)):
        array('slot.'+name, width)
    archive_start = at
    archive_version = field('archive.version', word)
    observed = dict(metadata_end=begin, player_info_offset=wrapper_start,
        player_info_bytes=slot_start-wrapper_start, slot_hints_offset=slot_start,
        slot_hints_bytes=archive_start-slot_start, slot_hints_version=slot_version,
        archive_offset=archive_start, archive_version=archive_version)
    if archive_version != 6:
        observed.update(status='UNSUPPORTED_PREGAME_PROFILE_WITNESS', retained_end=at,
            unsupported_profile_not_restored=True, array_records=records, fields=fields)
        return observed
    field('archive.player_admin_start_alias', lambda: (fixed(4),string(),fixed(4),string()))
    array('archive.art_styles',4)
    field('archive.autorun_bandwidth_calendar',lambda: fixed(17))
    field('archive.calendar_info',base)
    for name in ('civ_adjectives','civ_descriptions','civ_passwords','civ_short_descriptions'):
        array('archive.'+name)
    field('archive.climate',lambda: (fixed(4),base(),fixed(44)))
    field('archive.era',lambda: fixed(4))
    array('archive.email_addresses')
    field('archive.end_turn_timer',lambda: fixed(4))
    array('archive.flag_decals')
    array('archive.deprecated_controls',1)
    field('archive.game_mode_name',lambda: (fixed(4),string()))
    # Utility-library conformance: GameTypes is one byte; GameMapTypes is four.
    field('archive.game_session',lambda: fixed(18))
    array('archive.handicaps',4)
    array('archive.last_human_handicaps',4)
    field('archive.earth_internet',lambda: fixed(2))
    array('archive.leader_names')
    field('archive.scenario_map',lambda: (strings(2),fixed(7),string(),fixed(12)))
    array('archive.minor_civ_keys')
    array('archive.minor_nation_flags',1)
    field('archive.dummy',lambda: fixed(1))
    array('archive.multiplayer_options',1)
    array('archive.net_ids',4)
    array('archive.nicknames')
    field('archive.victories_pitboss',lambda: fixed(8))
    array('archive.playable_civs',1)
    array('archive.player_color_keys')
    field('archive.quick_random_flags',lambda: fixed(10))
    array('archive.ready_players',1)
    field('archive.sea_level',lambda: (fixed(4),base(),fixed(5)))
    array('archive.slot_claims',4)
    array('archive.slot_status',4)
    field('archive.smtp_seed_score',lambda: (string(),fixed(8)))
    array('archive.teams',4)
    field('archive.transferred_map',lambda: fixed(1))
    field('archive.turn_timer',lambda: (base(),fixed(21)))
    array('archive.victory_flags',1)
    array('archive.white_flags',1)
    world_version=field('archive.world_info_version',word)
    require(world_version in (1,2), f'Unsupported public world-info profile {world_version} at {at-4}')
    field('archive.world_info',lambda: (base(),fixed(76 if world_version==2 else 72)))
    field('archive.world_size',lambda: fixed(4))
    array('archive.game_options',options=True)
    array('archive.map_options',options=True)
    field('archive.version_string',string)
    array('archive.notify_steam',1)
    array('archive.notify_email',1)
    array('archive.notify_addresses')
    compression_start = at
    compression_format = field('compression.format',word)
    compression_chunk = field('compression.chunk_size',word)
    require(compression_format in (1,2) and compression_chunk==65536,
        f'Unsupported public compression descriptor {(compression_format,compression_chunk)} at {compression_start}')
    require(at+2<len(data), 'Public example must include a separate compressed body')
    # Observation only: the parsed field sequence, not a magic-byte scan, sets at.
    observed.update(status='SUPPORTED_BNW6_PREGAME_PREFIX', archive_bytes=compression_start-archive_start,
        world_info_version=world_version, compression_header_offset=compression_start,
        compressed_data_offset=at, compression_format_id=compression_format,
        compression_chunk_size=compression_chunk, compressed_first_two_bytes=data[at:at+2].hex(),
        retained_end=at, array_records=records, fields=fields)
    return observed


def main():
    require(len(sys.argv)==1 and not sys.flags.optimize, 'Unexpected fixture preparation invocation')
    for path in (STAGE,DESTINATION):
        ordinary_ancestors(path)
        require(path.is_relative_to(PROJECT), 'Fixture destination escaped project')
        path.mkdir(parents=True,exist_ok=True)
    if REPORT.exists():
        old=json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status']=='PASS_PUBLIC_PREGAME_FIXTURES' and old['commit']==COMMIT,
            'Inspect the existing fixture report before changing it')
        for row,sample in zip(old['fixtures'],SAMPLES,strict=True):
            require(row['upstream_git_blob']==sample[3] and artifact(Path(row['retained_tail']['path']))==row['retained_tail'],
                'Public Pregame fixture cache changed')
        print(json.dumps(dict(status=old['status'],reused=True,retained_tail_bytes=sum(r['retained_tail']['bytes'] for r in old['fixtures']))))
        return
    rows,outputs=[],[]
    for remote,local,size,blob in SAMPLES:
        url=f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/src/__tests__/resources/{remote}'
        with urlopen(Request(url,headers={'User-Agent':'ZeroSis-Public-Pregame-Fixture'}),timeout=20) as stream:
            require(stream.geturl()==url,'Unexpected public fixture redirect')
            data=stream.read(1024*1024+1)
        require(len(data)==size and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==blob,
            'Public fixture differs from immutable Git blob')
        begin,_=prefix_end(data)
        metadata=PROJECT/'Tests/Fixtures/RetailSaveHeader'/local
        require(metadata.read_bytes()==data[:begin], 'Existing metadata prefix differs')
        observed=walk(data,begin)
        tail=data[begin:observed['retained_end']]
        require(len(tail)<=65536 and begin+len(tail)<len(data),'Do not retain a complete save')
        target=DESTINATION/(local.removesuffix('.prefix')+'.pregame')
        outputs.append((target,tail))
        rows.append(dict(source_url=url,upstream_file_bytes=size,upstream_git_blob=blob,
            full_blob_verified_in_memory=True,full_file_retained=False,
            metadata_prefix_reused=artifact(metadata),retained_range_begin=begin,
            retained_range_end=observed['retained_end'],observed=observed))
    for (target,tail),row in zip(outputs,rows,strict=True):
        ordinary_ancestors(target)
        require(not target.exists(),'Inspect an existing Pregame tail before replacing it')
        with target.open('xb') as stream:
            stream.write(tail)
        row['retained_tail']=artifact(target)
    result=dict(schema='zerosis.retail_save.public_pregame_fixtures.v1',status='PASS_PUBLIC_PREGAME_FIXTURES',
        utc=datetime.now(timezone.utc).isoformat(),repository=REPOSITORY,commit=COMMIT,fixtures=rows,
        user_save_accessed=False,host_gamecore_or_hwnd_executed=False,full_saves_retained=0,
        scope='Disjoint uncompressed tails only; BNW archive 6 supported, other archive words retained only as rejection witnesses.')
    with REPORT.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False)
    print(json.dumps(dict(status=result['status'],retained_tail_bytes=sum(r['retained_tail']['bytes'] for r in rows),
        observed=[{k:v for k,v in r['observed'].items() if k!='fields'} for r in rows])))


if __name__=='__main__':
    main()
