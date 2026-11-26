"""Collect one bounded multipart upload per user before parsing the original file."""
from dataclasses import dataclass
from tempfile import TemporaryFile
from threading import Lock
from time import monotonic
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException

CHUNK_BYTES = 900 * 1024
EXPIRE_SECONDS = 600


@dataclass
class Upload:
    identifier: str
    descriptor: tuple
    stream: BinaryIO
    size: int = 0
    expires_at: float = 0


# The uploaded cube cache and its upload sessions belong to the same API process.
uploads: dict[str, Upload] = {}
lock = Lock()


def accept_chunk(directory, owner, identifier, index, total, chunk, maximum, descriptor):
    try:
        if str(UUID(identifier)) != identifier:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(400, '无效的高光谱上传编号。') from exc
    if total is None or not 0 < total <= maximum or index < 0:
        raise HTTPException(400, '高光谱文件为空、超过 128 MB 或分片无效。')
    offset = index * CHUNK_BYTES
    if offset >= total or len(chunk) != min(CHUNK_BYTES, total - offset):
        raise HTTPException(400, '高光谱文件分片大小不正确。')

    descriptor = (total, *descriptor)
    with lock:
        now = monotonic()
        if index == 0:
            for key in [key for key, value in uploads.items() if value.expires_at <= now]:
                uploads.pop(key).stream.close()
            if owner in uploads:
                uploads.pop(owner).stream.close()
            uploads[owner] = Upload(identifier, descriptor, TemporaryFile(dir=directory))
        upload = uploads.get(owner)
        if not upload or upload.identifier != identifier or upload.descriptor != descriptor:
            raise HTTPException(409, '高光谱上传已中断，请重新选择文件。')
        if offset != upload.size or (index and upload.expires_at <= now):
            raise HTTPException(409, '高光谱上传缺少分片或已超时，请重新选择文件。')
        try:
            upload.stream.write(chunk)
        except OSError:
            uploads.pop(owner).stream.close()
            raise
        upload.size += len(chunk)
        upload.expires_at = now + EXPIRE_SECONDS
        if upload.size < total:
            return None
        uploads.pop(owner)

    with upload.stream:
        upload.stream.seek(0)
        return upload.stream.read()
