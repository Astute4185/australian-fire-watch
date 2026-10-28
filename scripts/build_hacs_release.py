#!/usr/bin/env python3
"""Build and verify the HACS ZIP from an exact Git commit's integration tree.

The archive stores the *contents* of custom_components/australian_fire_watch/
at the ZIP root, including manifest.json. It never uses the working tree (and
therefore never collects stray build artifacts or locally modified files).
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

COMPONENT = "custom_components/australian_fire_watch"
ARCHIVE_NAME = "australian_fire_watch.zip"
RELEASE_TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")


def git(*args: str) -> str:
    """Run git and return the stripped stdout text."""
    return subprocess.check_output(["git", *args], text=True).strip()


def manifest_version(ref: str) -> str:
    """Validate manifest and const.py versions at the same ref."""
    manifest = json.loads(git("show", f"{ref}:{COMPONENT}/manifest.json"))
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Invalid integration manifest version: {version!r}")
    if manifest.get("domain") != "australian_fire_watch":
        raise ValueError("Unexpected integration domain")

    tree = ast.parse(git("show", f"{ref}:{COMPONENT}/const.py"))
    constant_versions = [
        ast.literal_eval(statement.value)
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in statement.targets)
    ]
    if constant_versions != [version]:
        raise ValueError(f"Manifest version {version!r} differs from const.VERSION: {constant_versions!r}")
    return version


def verify_zip(path: Path, version: str) -> int:
    """Validate HACS's expected root layout and exact integration metadata."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if archive.testzip() is not None or len(names) != len(set(names)):
            raise ValueError("ZIP is corrupt or contains duplicate entries")
        if any(
            name.startswith("/")
            or "\\" in name
            or ".." in PurePosixPath(name).parts
            or "__pycache__" in PurePosixPath(name).parts
            or name.endswith((".pyc", ".pyo"))
            for name in names
        ):
            raise ValueError("ZIP contains unsafe or generated members")
        required = {"manifest.json", "__init__.py", "const.py"}
        if not required.issubset(names):
            raise ValueError(f"ZIP is missing required root files: {sorted(required - set(names))}")
        packaged = json.loads(archive.read("manifest.json"))
        if packaged.get("domain") != "australian_fire_watch" or packaged.get("version") != version:
            raise ValueError("Packaged manifest does not match the source version/domain")
        return len(names)


def build(ref: str, output: Path, expected_tag: str | None) -> None:
    """Package a pinned commit, never a dirty or untracked working tree."""
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    version = manifest_version(commit)
    hacs = json.loads(git("show", f"{commit}:hacs.json"))
    if hacs.get("zip_release") is not True or hacs.get("filename") != ARCHIVE_NAME:
        raise ValueError("hacs.json must enable zip_release with filename australian_fire_watch.zip")

    if expected_tag is not None:
        if RELEASE_TAG.fullmatch(expected_tag) is None:
            raise ValueError(f"Release tags must use vMAJOR.MINOR.PATCH: {expected_tag}")
        if expected_tag[1:] != version:
            raise ValueError(f"Release tag {expected_tag} does not match manifest version {version}")
        tag_commit = git("rev-parse", "--verify", f"refs/tags/{expected_tag}^{{commit}}")
        if tag_commit != commit:
            raise ValueError("Tag does not point to the checked-out release commit")

    output.parent.mkdir(parents=True, exist_ok=True)
    # A Git archive from a subtree contains the subtree's files at ZIP root.
    subprocess.run(
        ["git", "archive", "--format=zip", "--output", str(output), f"{commit}:{COMPONENT}"],
        check=True,
    )
    count = verify_zip(output, version)
    print(f"Verified HACS ZIP: {output} ({count} members, version {version}, commit {commit})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Source Git ref or commit")
    parser.add_argument("--output", type=Path, required=True, help="Destination ZIP file")
    parser.add_argument("--expected-tag", help="Require this tag and manifest version to match")
    args = parser.parse_args()
    try:
        build(args.ref, args.output.resolve(), args.expected_tag)
    except (ValueError, OSError, json.JSONDecodeError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
