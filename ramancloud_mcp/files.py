"""Explicit file plans, with collision checks before any output is written."""

import os
import stat
from contextlib import ExitStack
from pathlib import Path


def input_file(value: str) -> Path:
    if not value or not value.strip():
        raise ValueError("An explicit input file path is required")
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Input must be a regular file: {path}")
    return path


class FilePlan:
    def __init__(self, inputs: list[Path], outputs: dict[str, str | None], overwrite: bool):
        self.paths: dict[str, Path] = {}
        self.overwrite = overwrite
        self.inputs = inputs
        for key, value in outputs.items():
            if value is None:
                continue
            if not value.strip():
                raise ValueError("An explicit, non-empty output path is required")
            raw = Path(value).expanduser()
            path = raw.parent.resolve(strict=True) / raw.name
            if not path.parent.is_dir():
                raise ValueError(f"Output parent must be an existing directory: {path.parent}")
            if path.is_symlink():
                raise ValueError(f"Output symlinks are not allowed: {path}")
            if path in self.paths.values():
                raise ValueError(f"Output paths must be distinct: {path}")
            if any(path == source or (path.exists() and path.samefile(source)) for source in inputs):
                raise ValueError(f"Output must not replace an input file: {path}")
            if path.exists():
                if not path.is_file():
                    raise ValueError(f"Output must be a regular file: {path}")
                if not overwrite:
                    raise FileExistsError(f"Output exists; choose a new path or set overwrite=true: {path}")
                if any(path.samefile(other) for other in self.paths.values() if other.exists()):
                    raise ValueError(f"Output paths must not alias the same file: {path}")
            self.paths[key] = path

    def written_paths(self) -> dict[str, str]:
        return {key: str(path) for key, path in self.paths.items()}

    def write(self, contents: dict[str, bytes]) -> None:
        if set(contents) != set(self.paths):
            raise ValueError("Output content does not match the requested file plan")
        created: list[Path] = []
        try:
            with ExitStack() as stack:
                streams = {}
                input_ids = {(source.stat().st_dev, source.stat().st_ino) for source in self.inputs}
                output_ids = set()
                # Reserve every destination before writing, including concurrent collisions.
                for key, path in self.paths.items():
                    existed = path.exists()
                    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                    if not self.overwrite:
                        flags |= os.O_EXCL
                    fd = os.open(path, flags, 0o600)
                    stream = stack.enter_context(os.fdopen(fd, "wb"))
                    if not existed:
                        created.append(path)
                    info = os.fstat(stream.fileno())
                    identity = (info.st_dev, info.st_ino)
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError(f"Output must be a regular file: {path}")
                    if identity in input_ids or identity in output_ids:
                        raise ValueError(f"Output became an input/output alias after validation: {path}")
                    output_ids.add(identity)
                    streams[key] = stream
                for key, content in contents.items():
                    if self.overwrite:
                        streams[key].truncate(0)
                    streams[key].write(content)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
