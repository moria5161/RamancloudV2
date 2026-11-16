"""Private, byte-preserving upload archive shared by the two web applications."""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

POLICY_VERSION = 'original-uploads-2026-10-03'
CONFIG_PATH = Path(__file__).resolve().parent / 'runtime' / 'upload-archive.json'
LOGGER = logging.getLogger(__name__)


class UploadArchive:
    def __init__(self, directory, max_file_bytes=200 * 1024 * 1024, max_total_bytes=20 * 1024 ** 3):
        self.directory = Path(directory)
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        path = self.directory / 'uploads.sqlite3'
        connection = sqlite3.connect(path, timeout=30)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('''CREATE TABLE IF NOT EXISTS original_uploads (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            module TEXT NOT NULL,
            instrument TEXT NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            byte_count INTEGER NOT NULL,
            relative_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            UNIQUE(source, module, instrument, filename, sha256)
        )''')
        os.chmod(path, 0o600)
        return connection

    def save(self, uploads, source, module, instrument=''):
        if not uploads:
            return 0
        if any(len(content) > self.max_file_bytes for _, content in uploads):
            raise ValueError('Upload exceeds archive file size limit')
        connection = self.connect()
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                total = connection.execute('SELECT COALESCE(SUM(byte_count), 0) FROM original_uploads').fetchone()[0]
                pending = set()
                for filename, content in uploads:
                    key = (source, module, instrument, Path(filename).name, hashlib.sha256(content).hexdigest())
                    existing = connection.execute('''SELECT 1 FROM original_uploads
                        WHERE source=? AND module=? AND instrument=? AND filename=? AND sha256=?''', key).fetchone()
                    if not existing and key not in pending:
                        total += len(content)
                        pending.add(key)
                if total > self.max_total_bytes:
                    raise ValueError('Upload archive quota exceeded')
                for filename, content in uploads:
                    digest = hashlib.sha256(content).hexdigest()
                    relative_path = f'originals/{digest[:2]}/{digest}'
                    destination = self.directory / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if destination.is_symlink():
                        raise ValueError('Invalid archive destination')
                    if destination.exists():
                        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                            raise ValueError('Archive checksum mismatch')
                    else:
                        temporary = None
                        try:
                            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                                temporary = Path(handle.name)
                                handle.write(content)
                                handle.flush()
                                os.fsync(handle.fileno())
                            os.link(temporary, destination)
                        finally:
                            if temporary:
                                temporary.unlink(missing_ok=True)
                    connection.execute('''INSERT OR IGNORE INTO original_uploads
                        (source, module, instrument, filename, sha256, byte_count,
                         relative_path, created_at, policy_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (source, module, instrument, Path(filename).name, digest, len(content),
                         relative_path, datetime.now(timezone.utc).isoformat(), POLICY_VERSION))
            return len(uploads)
        finally:
            connection.close()


def configured_archive():
    # No config is shipped in desktop/MCP distributions: those stay local-only.
    if os.environ.get('RAMANCLOUD_UPLOAD_ARCHIVE_DISABLED') == '1':
        return None
    directory = os.environ.get('RAMANCLOUD_UPLOAD_ARCHIVE_DIR')
    if directory:
        return UploadArchive(directory)
    if not CONFIG_PATH.exists():
        return None
    config = json.loads(CONFIG_PATH.read_text())
    return UploadArchive(config['directory'], config.get('max_file_bytes', 200 * 1024 * 1024),
                         config.get('max_total_bytes', 20 * 1024 ** 3))


def archive_uploads(uploads, source, module, instrument='', share_data=True):
    if share_data is not True:
        return {'status': 'disabled', 'saved_files': 0}
    try:
        archive = configured_archive()
        if archive is None:
            return {'status': 'unavailable', 'saved_files': 0}
        count = archive.save(uploads, source, module, instrument)
        return {'status': 'saved', 'saved_files': count}
    except Exception as error:
        LOGGER.error('Original upload archive failed (%s)', type(error).__name__)
        return {'status': 'failed', 'saved_files': 0}
