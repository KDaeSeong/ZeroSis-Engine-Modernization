"""Independent malformed/edge examples for the retained GPU picking proof."""
from pathlib import Path
import shutil
import struct
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from verify_interactive_game import pixel_key


def main():
    total = 1920 * 1080
    key = 0x5A57000100000028
    scene = {'plots': [[40, 4, 4, 1, 1]], 'pixelHitKeys': [key], 'pixelHitCount': total}
    root = (PROJECT / 'Build').resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix='terrain-pick-test-', dir=root)).resolve(strict=True)
    if directory.parent != root or directory.is_symlink():
        raise RuntimeError('Test scratch directory escaped the owned Build root')
    path = directory / 'test.pick'
    prefix = b'ZSTPICK1' + struct.pack('<IIIQ', 1920, 1080, 1, key)
    valid = prefix + struct.pack('<6I', 10, 0, 20, 1, total - 30, 0)
    checks = 0
    try:
        path.write_bytes(valid)
        for x, expected in ((9.99, 0), (10, key), (29.99, key), (30, 0)):
            assert pixel_key(path, scene, x, 0) == expected
            checks += 1
        bad_packets = [valid[:-1], valid + b'X', prefix + struct.pack('<2I', 0, 0),
                       prefix + struct.pack('<2I', total + 1, 0),
                       prefix + struct.pack('<2I', total, 2),
                       prefix + struct.pack('<2I', total - 1, 0)]
        for data, document, x in [(p, scene, 10) for p in bad_packets] + [
                (valid, {**scene, 'plots': [[40, 4, 4, 1, 0]]}, 10), (valid, scene, -0.1),
                (valid, scene, 1920), (valid, {**scene, 'pixelHitCount': total - 1}, 10)]:
            path.write_bytes(data)
            try:
                pixel_key(path, document, x, 0)
            except RuntimeError:
                checks += 1
            else:
                raise AssertionError('Malformed picking evidence accepted')
        print(f'TERRAIN_PICK_PACKET_PASS checks={checks}')
    finally:
        # Delete only the unique ordinary scratch directory created above.
        assert directory.resolve(strict=True).parent == root and not directory.is_symlink()
        shutil.rmtree(directory)


if __name__ == '__main__':
    main()
