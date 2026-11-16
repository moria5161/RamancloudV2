import asyncio
import hashlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from upload_archive import UploadArchive, archive_uploads


class UploadArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / 'archive'
        self.environment = patch.dict(os.environ, {
            'RAMANCLOUD_UPLOAD_ARCHIVE_DIR': str(self.directory),
            'RAMANCLOUD_UPLOAD_ARCHIVE_DISABLED': '0',
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def records(self):
        with sqlite3.connect(self.directory / 'uploads.sqlite3') as connection:
            connection.row_factory = sqlite3.Row
            return list(connection.execute('SELECT * FROM original_uploads ORDER BY id'))

    def test_all_original_bytes_preserved_and_deduplicated(self):
        uploads = [('first.txt', b'\xef\xbb\xbf100\t1\r\n200\t2\r\n'), ('second.asc', b'Header\n100 4\n200 5\n')]
        for _ in range(2):
            self.assertEqual(archive_uploads(uploads, 'streamlit', 'spectrum')['saved_files'], 2)
        records = self.records()
        self.assertEqual(len(records), 2)
        for record, (filename, content) in zip(records, uploads):
            self.assertEqual(record['filename'], filename)
            self.assertEqual((self.directory / record['relative_path']).read_bytes(), content)
            self.assertEqual(record['sha256'], hashlib.sha256(content).hexdigest())
        if os.name != 'nt':
            self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.directory / records[0]['relative_path']).stat().st_mode & 0o777, 0o600)

    def test_opt_out_does_not_create_archive(self):
        result = archive_uploads([('private.txt', b'private')], 'web', 'spectrum', share_data=False)
        self.assertEqual(result['status'], 'disabled')
        self.assertFalse(self.directory.exists())

    def test_batch_endpoint_archives_every_file_with_sharing_enabled(self):
        files = [UploadFile(filename=f'{i}.txt', file=io.BytesIO(f'100\t{i}\n200\t{i + 1}\n'.encode())) for i in range(3)]
        result = asyncio.run(app.upload(files, share_data=True))
        self.assertEqual(result['data_sharing']['saved_files'], 3)
        self.assertEqual(len(self.records()), 3)

    def test_endpoint_opt_out_and_processing_do_not_archive(self):
        result = asyncio.run(app.upload([UploadFile(filename='private.txt', file=io.BytesIO(b'100 1\n200 2\n'))], share_data=False))
        self.assertEqual(result['data_sharing']['status'], 'disabled')
        app.process_spectrum(app.SpectrumPayload(wavenumber=[100, 200], intensity=[1, 2]))
        app.demo_spectrum('bacteria')
        app.demo_mapping('timeseries_horiba')
        self.assertFalse(self.directory.exists())

    def test_web_uploads_default_to_original_archiving(self):
        content = b'100 1\n200 2\n'
        with TestClient(app.app) as client:
            response = client.post('/api/upload', files={'files': ('default-upload.txt', content, 'text/plain')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data_sharing']['status'], 'saved')
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual((self.directory / records[0]['relative_path']).read_bytes(), content)

    def test_imaging_and_time_coordinates_remain_in_original_file(self):
        cases = [('imaging', b'\t\t100\t200\n-2.5\t8.25\t1\t2\n'),
                 ('time_series', b'\t100\t200\n0.125\t1\t2\n9.75\t3\t4\n')]
        for mode, content in cases:
            result = asyncio.run(app.upload_mapping(UploadFile(filename=f'{mode}.txt', file=io.BytesIO(content)), 'Horiba', mode, True))
            self.assertEqual(result['data_sharing']['status'], 'saved')
        for record, (_, content) in zip(self.records(), cases):
            self.assertEqual((self.directory / record['relative_path']).read_bytes(), content)

    def test_invalid_batch_not_archived(self):
        files = [UploadFile(filename='good.txt', file=io.BytesIO(b'100 1\n200 2\n')),
                 UploadFile(filename='bad.txt', file=io.BytesIO(b'not a spectrum'))]
        with self.assertRaises(Exception):
            asyncio.run(app.upload(files, share_data=True))
        self.assertFalse(self.directory.exists())

    def test_tools_respect_sharing(self):
        for share in (False, True):
            result = asyncio.run(app.merge_files_tool([
                UploadFile(filename='a.txt', file=io.BytesIO(b'100\t1\n200\t2\n')),
                UploadFile(filename='b.txt', file=io.BytesIO(b'100\t3\n200\t4\n')),
            ], share_data=share))
            self.assertEqual(result.headers['X-RamanCloud-Data-Sharing'], 'saved' if share else 'disabled')
        self.assertEqual(len(self.records()), 2)

    def test_safe_filename_and_source_metadata(self):
        content = b'original'
        for source in ('streamlit', 'web'):
            archive_uploads([("../../'malicious.txt", content)], source, 'spectrum')
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertEqual(len(list(self.directory.glob('originals/*/*'))), 1)
        self.assertEqual(records[0]['filename'], "'malicious.txt")

    def test_concurrent_saves_do_not_duplicate_or_corrupt_files(self):
        archive = UploadArchive(self.directory)
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: archive.save([('shared.txt', b'1234')], 'web', 'spectrum'), range(8)))
        self.assertEqual(len(self.records()), 1)
        self.assertEqual((self.directory / self.records()[0]['relative_path']).read_bytes(), b'1234')

    def test_archive_failures_are_reported_without_breaking_processing(self):
        with patch('upload_archive.UploadArchive.save', side_effect=OSError('disk full')):
            result = asyncio.run(app.upload([UploadFile(filename='a.txt', file=io.BytesIO(b'100 1\n200 2\n'))], share_data=True))
        self.assertEqual(result['data_sharing']['status'], 'failed')
        self.assertEqual(result['data']['spectra'][0]['intensity'], [1, 2])

    def test_limits_are_checked_before_storing_more_files(self):
        archive = UploadArchive(self.directory, max_file_bytes=4, max_total_bytes=6)
        archive.save([('a.txt', b'1234')], 'web', 'spectrum')
        with self.assertRaises(ValueError):
            archive.save([('too-big.txt', b'12345')], 'web', 'spectrum')
        with self.assertRaises(ValueError):
            archive.save([('over-quota.txt', b'5678')], 'web', 'spectrum')
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(list(self.directory.glob('originals/*/*'))), 1)


if __name__ == '__main__':
    unittest.main()
