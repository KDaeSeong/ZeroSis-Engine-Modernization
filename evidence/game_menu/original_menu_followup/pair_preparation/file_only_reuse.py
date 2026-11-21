"""Exact local Python-tool reuse; no native process/module entry point."""
from pathlib import Path
import hashlib
import importlib.util
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
BUILDER_SHA = 'cfec8148813495309ee1a2d1e1fcba053e671f1e79a63f6e39a360fcc4555c65'


def load(relative, digest, name):
    if not __debug__ or not sys.dont_write_bytecode:
        raise RuntimeError('Use Python -B without optimized assertions')
    path = PROJECT / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Reviewed local tool changed: ' + str(path))
    sys.path.insert(0,str(PROJECT/'tools'))
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_builder():
    path = PROJECT/'tools/build_menu_suite_host.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != BUILDER_SHA:
        raise RuntimeError('The explicitly reviewed current menu builder changed')
