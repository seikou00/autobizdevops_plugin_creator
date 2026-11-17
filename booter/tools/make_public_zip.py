#!/usr/bin/env python3
"""Build the shareable booter skill: python3 booter/tools/make_public_zip.py."""

import argparse
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


BOOTER = Path(__file__).resolve().parents[1]
PUBLIC_FILES = ("SKILL.md", "__main__.py", "modeling-guide.md")
PUBLIC_DIRS = ("references", "runtime", "scaffold", "schemas")
PUBLIC_SUFFIXES = {".json", ".js", ".md", ".py"}


def public_files():
    for name in PUBLIC_FILES:
        path = BOOTER / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected a regular file: {path}")
        yield path

    for name in PUBLIC_DIRS:
        directory = BOOTER / name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Expected a regular directory: {directory}")
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError(f"Unexpected symlink in public files: {path}")
            if path.is_file() and path.suffix in PUBLIC_SUFFIXES:
                yield path


def make_public_zip(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".booter-public-", dir=output.parent) as temporary:
        candidate = Path(temporary) / "booter-public.zip"
        with ZipFile(candidate, "w", compression=ZIP_DEFLATED) as archive:
            for path in public_files():
                member = Path("booter") / path.relative_to(BOOTER)
                archive.write(path, member.as_posix())
        candidate.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the public booter skill without repository examples or tests.")
    parser.add_argument("-o", "--output", type=Path, default=BOOTER.parent / "booter-public.zip")
    args = parser.parse_args()
    make_public_zip(args.output)
    print(f"Created {args.output.resolve()}")


if __name__ == "__main__":
    main()
