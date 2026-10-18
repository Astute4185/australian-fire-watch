"""Retain an exact-source private candidate; never create a tag or release."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import unittest
import zipfile

PREFIX = 'custom_components/australian_fire_watch/'


def git(*args):
    return subprocess.check_output(['git', *args])


def package(files, output):
    if not files:
        raise ValueError('Empty candidate refused')
    for name in files:
        path = PurePosixPath(name)
        if ('\\' in name or path.is_absolute() or '..' in path.parts
                or '__pycache__' in path.parts or name.endswith(('.pyc', '.pyo'))):
            raise ValueError('Unsafe or generated archive member')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() or sorted(archive.namelist()) != sorted(files):
            raise ValueError('Archive members differ')
        if any(archive.read(name) != data for name, data in files.items()):
            raise ValueError('Archive contents differ')


class PackagingRegressions(unittest.TestCase):
    def test_rejects_unsafe_generated_or_empty_members(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('../escape', '/absolute', 'bad\\path', '__pycache__/bad.pyc'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    package({name: b'bad'}, Path(directory) / 'candidate.zip')
            with self.assertRaises(ValueError):
                package({}, Path(directory) / 'empty.zip')

    def test_refuses_existing_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'candidate.zip'
            target.write_bytes(b'existing-public-asset')
            with self.assertRaises(FileExistsError):
                package({'manifest.json': b'{}'}, target)
            self.assertEqual(target.read_bytes(), b'existing-public-asset')

    def test_deterministic_posix_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = [Path(directory) / name for name in ('first.zip', 'second.zip')]
            files = {'manifest.json': b'{}', 'frontend/panel.js': b'// fixture'}
            package(files, first)
            package(dict(reversed(list(files.items()))), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PackagingRegressions))
        raise SystemExit(not result.wasSuccessful())
    sha = git('rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or os.getenv('GITHUB_SHA') != sha:
        raise SystemExit('Exact workflow source required')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Tracked source must remain clean')
    for gate in ('UNIT', 'RUNTIME', 'HASSFEST'):
        if os.getenv('GATE_' + gate) != 'success':
            raise SystemExit('All original source gates must pass')
    manifest = json.loads(git('show', sha + ':' + PREFIX + 'manifest.json'))
    constants = ast.parse(git('show', sha + ':' + PREFIX + 'const.py').decode())
    versions = [ast.literal_eval(node.value) for node in constants.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    version = manifest['version']
    if versions != [version] or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise SystemExit('Manifest and constant versions must agree')
    files = {}
    for entry in git('ls-tree', '-rz', sha, '--', PREFIX).split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise SystemExit('Only regular tracked files are allowed')
        files[name.decode().removeprefix(PREFIX)] = git('cat-file', 'blob', oid)
    # HACS expects this integration's original root-layout ZIP, not a renamed
    # top-level directory. Existing published assets are never overwritten.
    out = Path('dist')
    out.mkdir(exist_ok=True)
    archive = out / 'australian_fire_watch.zip'
    package(files, archive)
    receipt = {'repository': 'hallyaus/australian-fire-watch', 'source_server': 'http://192.168.1.130:3000',
               'source_sha': sha, 'source_tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
               'version': version, 'archive': archive.name, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'members': len(files), 'run_id': os.getenv('GITHUB_RUN_ID'), 'published': False,
               'posix_paths_verified': True, 'hacs_external_validation': 'required before public release',
               'gitea_gates': {name.lower(): 'success' for name in ('UNIT', 'RUNTIME', 'HASSFEST')}}
    (out / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
