"""File-only preflight for one isolated runtime; never starts native code."""
from pathlib import Path
import argparse, hashlib, json, os, re

EXPECTED = {
    'terrain': ('terrain-assets.bin', '02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8', b'ZSTERR02'),
    'fog': ('WorldAssets/fog-assets.bin', '42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc', b'ZSFOG001'),
    'water': ('WorldAssets/water-assets.bin', '2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc', b'ZSWATER1'),
    'lean': ('WorldAssets/water-lean-assets.bin', '69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7', b'ZSWLEAN1'),
    'lighting': ('WorldAssets/lighting-assets.bin', 'd0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424', b'ZSLIGHT1'),
}
HOST = 'fed2c23df266efb74650df573245001b09a21ffaec619baed319ca5f783e0106'
SDK = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'


def require(value, message):
    if not value:
        raise ValueError(message)


def ordinary(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not parent.is_symlink() and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse path is not an isolated input')
    require(path.is_file(), 'Missing ordinary input')
    return path.stat()


def digest(path):
    before = ordinary(path)
    with Path(path).open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = ordinary(path)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return value


def verify(root, manifest, expected_manifest_sha):
    root, manifest = Path(root).absolute(), Path(manifest).absolute()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', root.name), 'Invalid isolated runtime directory')
    require(manifest == root / 'WorldAssets/assets.manifest.json', 'Asset manifest path escaped the runtime')
    require(re.fullmatch(r'[0-9a-f]{64}', expected_manifest_sha) is not None, 'Missing pinned manifest hash')
    require(manifest.stat().st_size <= 65536 and digest(manifest) == expected_manifest_sha, 'Asset manifest hash differs')
    value = json.loads(manifest.read_text('utf8'))
    require(value['schema'] == 'zerosis.world_assets.runtime_binding.v1' and
            os.path.normcase(value['runtime_directory']) == os.path.normcase(str(root)), 'Runtime identity differs')
    require(set(value['packages']) == set(EXPECTED), 'Five original packages are required')
    for role, (name, expected, magic) in EXPECTED.items():
        row = value['packages'][role]
        require(row['relative_path'] == name and row['sha256'] == expected, 'Package binding differs: ' + role)
        path = root / name
        require(ordinary(path).st_size == row['bytes'] and digest(path) == expected, 'Package bytes differ: ' + role)
        with path.open('rb') as stream:
            require(stream.read(8) == magic, 'Package format differs: ' + role)
    for key, name, expected in (('host', 'ZeroSisHost_x64.exe', HOST),
                                ('gamecore', 'CvGameCoreDLL_Expansion2_x64.dll', SDK)):
        row = value[key]
        require(Path(row['path']) == root / name and row['sha256'] == expected and
                ordinary(root / name).st_size == row['bytes'] and digest(root / name) == expected,
                'Native input bytes differ: ' + key)
    validator = value['validator']
    require(validator['relative_path'] == 'WorldAssets/verify_assets.py' and
            digest(root / validator['relative_path']) == validator['sha256'], 'File-only validator differs')
    return dict(status='PASS_FIVE_RUNTIME_PACKS_AND_ATTESTED_PAIR_FILE_ONLY', packages=5,
                runtime=str(root), host_or_sdk_executed=False)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root', type=Path, required=True)
    cli.add_argument('--manifest', type=Path, required=True)
    cli.add_argument('--manifest-sha256', required=True)
    args = cli.parse_args()
    print(json.dumps(verify(args.root, args.manifest, args.manifest_sha256)))


if __name__ == '__main__':
    main()
