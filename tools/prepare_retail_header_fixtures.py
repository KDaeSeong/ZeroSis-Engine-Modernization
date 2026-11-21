"""Retain only verified public metadata prefixes, never local user saves."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/header_prefix'
DESTINATION = PROJECT / 'Tests/Fixtures/RetailSaveHeader'
REPORT = STAGE / 'fixtures.json'
COMMIT = '858ce8532725f634e64fa8acaf355aa8e50829bf'
REPOSITORY = 'bmaupin/js-civ5save'
SAMPLES = (
    ('1.0.3.279.Civ5Save', 'bnw_279.prefix', 418069, '186fb9a84f4e47192e11b8cd98b436a48ccbee16'),
    ('issue8.Civ5Save', 'community_patch.prefix', 15342, 'c34d0d8a66f35d3b4721550626697b5e0838e7d4'),
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def prefix_end(data):
    """Independent wire walk for trimming; expected values come from upstream tests."""
    limit = min(len(data), 16384)
    at = 0

    def take(count):
        nonlocal at
        require(count <= limit - at, 'Public metadata prefix exceeds the 16 KiB retention bound')
        value = data[at:at + count]
        at += count
        return value

    def u32():
        return struct.unpack('<I', take(4))[0]

    def string():
        return take(u32())

    require(take(4) == b'CIV5' and u32() == 8, 'Unexpected public fixture signature/version')
    version, build = string(), string()
    turn, mode = u32(), take(1)[0]
    tokens = [string() for _ in range(7)]
    dlc_count = u32()
    require(dlc_count <= 4096, 'Unexpected public DLC count')
    dlc = []
    for _ in range(dlc_count):
        take(20)
        dlc.append(string().decode('utf-8'))
    mod_count = u32()
    require(mod_count <= 4096, 'Unexpected public mod count')
    mods = []
    for _ in range(mod_count):
        identifier = string().decode('utf-8')
        auxiliary = take(4).hex()
        mods.append(dict(identifier=identifier, auxiliary_hex=auxiliary, name=string().decode('utf-8')))
    require(8 < at < len(data), 'Do not retain a full public save as a metadata fixture')
    return at, dict(game_version=version.decode('utf-8'), raw_game_build=build.decode('utf-8'),
        turn=turn, game_mode=mode, metadata_tokens=[x.decode('utf-8') for x in tokens],
        dlc_names=dlc, mods=mods)


def ordinary_ancestors(path):
    for part in (path, *path.parents):
        if part.exists():
            require(not part.lstat().st_file_attributes & 0x400, 'Reparse fixture output or ancestor')


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected fixture preparation invocation')
    for path in (STAGE, DESTINATION):
        require(path.is_absolute() and path.is_relative_to(PROJECT), 'Fixture output escaped project')
        ordinary_ancestors(path)
        path.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        result = json.loads(REPORT.read_text(encoding='utf-8'))
        require(result['commit'] == COMMIT and result['status'] == 'PASS_PUBLIC_PREFIX_FIXTURES', 'Unexpected fixture cache manifest')
        require([r['upstream_git_blob'] for r in result['fixtures']] == [r[3] for r in SAMPLES], 'Public fixture identity differs')
        for row, sample in zip(result['fixtures'], SAMPLES):
            require(Path(row['retained_prefix']['path']) == DESTINATION / sample[1] and
                    artifact(Path(row['retained_prefix']['path'])) == row['retained_prefix'], 'Public fixture cache changed')
        print(json.dumps(dict(status=result['status'], reused=True, fixtures=2,
            retained_bytes=sum(x['retained_prefix']['bytes'] for x in result['fixtures']))))
        return
    rows = []
    for remote_name, local_name, expected_size, expected_blob in SAMPLES:
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/src/__tests__/resources/{remote_name}'
        request = Request(url, headers={'User-Agent': 'ZeroSis-Retail-Save-Header-Fixture-Preparation'})
        with urlopen(request, timeout=20) as response:
            final_url = urlsplit(response.geturl())
            require(final_url.scheme == 'https' and final_url.netloc == 'raw.githubusercontent.com' and
                    final_url.path == urlsplit(url).path, 'Unexpected public fixture redirect')
            data = response.read(1024 * 1024 + 1)
        require(len(data) == expected_size, 'Unexpected immutable public fixture size')
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
        require(blob == expected_blob, 'Public fixture differs from its pinned Git blob')
        end, observed = prefix_end(data)
        prefix = data[:end]
        target = DESTINATION / local_name
        ordinary_ancestors(target)
        if target.exists():
            require(target.read_bytes() == prefix, 'Do not overwrite an unexpected prefix fixture')
        else:
            with target.open('xb') as stream:
                stream.write(prefix)
        rows.append(dict(source_url=url, upstream_file_bytes=len(data), upstream_git_blob=blob,
            full_blob_verified_in_memory=True, full_file_retained=False,
            retained_prefix=artifact(target), observed_metadata=observed))
    result = dict(schema='zerosis.retail_save.public_header_fixtures.v1', status='PASS_PUBLIC_PREFIX_FIXTURES',
        utc=datetime.now(timezone.utc).isoformat(), repository=REPOSITORY, commit=COMMIT, fixtures=rows,
        user_save_accessed=False, native_host_gamecore_or_window_executed=False,
        dependencies_installed=0, input_bytes_limit_per_file=1024*1024,
        retained_prefix_limit_per_file=16384,
        scope='Only metadata-prefix bytes; not whole-save validity, compressed framing or SDK restore proof.')
    with REPORT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps(dict(status=result['status'], fixtures=2,
        retained_bytes=sum(x['retained_prefix']['bytes'] for x in rows), full_saves_retained=0)))


if __name__ == '__main__':
    main()
