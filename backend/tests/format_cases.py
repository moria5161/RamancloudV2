"""Real HTTP import checks with the workflow suite's isolated database."""
import hashlib
import numpy as np
from test_spectral_formats import wdf_fixture, xlsx, teaching_spectrum
from test_wxd_single import wxd_fixture
from spectral_formats import parse_single
from test_native_spectra import labspec_fixture, npg_fixture


class FormatCases:
    def test_split_mapping_accepts_native_labspec_with_all_positions(self):
        import io
        import json
        import zipfile
        content, wave, cube = labspec_fixture()
        for instrument in ('auto', 'Horiba', 'Nanophoton'):
            code, result = self.format_upload('/api/tools/split', 'map.l6m', content, dict(instrument=instrument))
            self.assertEqual(code, 200, result)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['spectrum_count'], 6)
                for entry in manifest['spectra']:
                    x, y, _ = parse_single(archive.read(entry['file']), entry['file'])
                    np.testing.assert_array_equal(x, wave)
                    np.testing.assert_array_equal(y, cube[entry['row'], entry['column']])

    def test_split_mapping_preserves_three_legacy_text_layouts(self):
        import io
        import zipfile
        wave = [400.1234567890123, 401.25, 402.5]
        signals = [[1.23456789012345, 2., 3.], [4., 5., 6.]]
        horiba = '\t\t' + '\t'.join(map(str, wave)) + '\n'
        horiba += '\n'.join('\t'.join(map(str, [i, 0] + signal)) for i, signal in enumerate(signals))
        # Interleaved rows must be grouped by their location/series key, not reshaped blindly.
        renishaw = '\n'.join(f'{i}\t{x}\t{signals[i][j]}' for j, x in enumerate(wave) for i in range(2))
        nanophoton = 'Wavenumber\tx0_y0\tx1_y0\n' + '\n'.join(f'{x}\t{signals[0][j]}\t{signals[1][j]}' for j, x in enumerate(wave))
        for instrument, text in [('Horiba', horiba), ('Renishaw', renishaw), ('Nanophoton', nanophoton)]:
            code, result = self.format_upload('/api/tools/split', 'map.txt', text.encode(), dict(instrument=instrument))
            self.assertEqual(code, 200, result)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                names = sorted(name for name in archive.namelist() if name.endswith('.txt'))
                self.assertEqual(len(names), 2)
                for i, name in enumerate(names):
                    x, y, _ = parse_single(archive.read(name), name)
                    np.testing.assert_array_equal(x, wave)
                    np.testing.assert_array_equal(y, signals[i])

    def test_split_mapping_rejects_single_spectra_and_inconsistent_axes(self):
        for name, content in [('point.npg', npg_fixture()[0]), ('point.wxd', wxd_fixture()[0]),
                              ('point.txt', self.spectrum_bytes())]:
            code, result = self.format_upload('/api/tools/split', name, content)
            self.assertEqual(code, 400, result)
            self.assertIn('只有一条光谱', result['detail'])
        bad = b'0\t400\t1\n0\t401\t2\n0\t402\t3\n1\t410\t4\n1\t411\t5\n1\t412\t6'
        self.assertEqual(self.format_upload('/api/tools/split', 'map.txt', bad, dict(instrument='Renishaw'))[0], 400)
        self.assertEqual(self.format_upload('/api/tools/split', 'bad.l6m', b'LabSpec6 broken')[0], 400)

    def test_native_labspec_selection_does_not_silently_import_a_map(self):
        content, wave, cube = labspec_fixture()
        before = self.call('/api/ai-workflows')[1]
        code, preview = self.format_upload('/api/ai-workflows/upload', 'map.l6m', content)
        self.assertEqual(code, 200, preview)
        self.assertTrue(preview['requires_confirmation'])
        self.assertTrue(preview['source_check']['selection_required'])
        self.assertEqual(preview['source_check']['spectrum_count'], 6)
        code, error = self.format_upload('/api/ai-workflows/upload', 'map.l6m', content, dict(confirm_conversion='true'))
        self.assertEqual(code, 400, error)
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        code, task = self.format_upload('/api/ai-workflows/upload', 'map.l6m', content, dict(confirm_conversion='true', spectrum_index='5'))
        self.assertEqual(code, 200, task)
        np.testing.assert_array_equal(task['original']['intensity'], cube[2, 1])
        self.assertEqual(task['diagnostics']['source_check']['selected_position']['row'], 2)
        self.assertEqual(self.call('/api/ai-workflows/' + task['id'] + '/download?kind=original')[1], content)
        for index in ('-1', '6'):
            self.assertEqual(self.format_upload('/api/ai-workflows/upload', 'map.l6m', content, dict(confirm_conversion='true', spectrum_index=index))[0], 400)
        code, batch = self.batch_upload([('folder/map.l6m', content), ('folder/point.txt', self.spectrum_bytes())])
        self.assertEqual(code, 200, batch)
        self.assertEqual(batch['counts']['invalid'], 1)
        self.assertEqual(batch['counts']['ready'], 1)

    def test_native_npg_confirmation_and_standard_download(self):
        content, wave, signal = npg_fixture()
        before = self.call('/api/ai-workflows')[1]
        code, preview = self.format_upload('/api/ai-workflows/upload', 'point.npg', content)
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview['source_check']['axis_conversion'], 'wavelength_nm_to_raman_shift')
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        code, task = self.format_upload('/api/ai-workflows/upload', 'point.npg', content, dict(confirm_conversion='true'))
        self.assertEqual(code, 200, task)
        x, y, _ = parse_single(self.call('/api/ai-workflows/' + task['id'] + '/download?kind=standardized')[1], 'standard.txt')
        np.testing.assert_array_equal(x, wave); np.testing.assert_array_equal(y, signal)
        self.assertEqual(self.call('/api/ai-workflows/' + task['id'] + '/download?kind=original')[1], content)

    def test_native_module_inputs_keep_selected_position_when_copied(self):
        content, wave, cube = labspec_fixture()
        for module in ('ssnet', 'library-matching', 'structure-generation'):
            route = '/api/' + module + '/sources'
            before = self.call('/api/ai-workflows')[1]
            code, preview = self.format_upload(route + '/upload', 'map.l6m', content)
            self.assertEqual(code, 200, preview)
            self.assertTrue(preview['source_check']['selection_required'])
            self.assertEqual(self.format_upload(route + '/upload', 'map.l6m', content, dict(confirm_conversion='true'))[0], 400)
            code, source = self.format_upload(route + '/upload', 'map.l6m', content, dict(confirm_conversion='true', spectrum_index='3'))
            self.assertEqual(code, 200, source)
            np.testing.assert_array_equal(source['original']['intensity'], cube[1, 1])
            self.assertEqual(self.call('/api/ai-workflows')[1], before)
            code, task = self.call(route + '/' + source['id'] + '/preprocess', {})
            self.assertEqual(code, 200, task)
            self.assertEqual(task['original'], source['original'])
            self.assertEqual(task['diagnostics']['source_check']['spectrum_index'], 3)

    def test_native_archive_tool_and_imaging_api(self):
        import io
        import json
        import zipfile
        content, wave, cube = labspec_fixture()
        code, result = self.format_upload('/api/tools/standardize', 'map.l6m', content)
        self.assertEqual(code, 200, result)
        with zipfile.ZipFile(io.BytesIO(result)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['spectrum_count'], 6)
            self.assertEqual(len([name for name in archive.namelist() if name.endswith('.txt')]), 6)
        code, result = self.format_upload('/api/upload-hyperspectral', 'map.l6m', content, dict(mode='imaging'))
        self.assertEqual(code, 200, result)
        self.assertEqual(result['data']['shape'], [3, 2, 16])

    def test_wxd_confirmation_preserves_source_and_standard_precision(self):
        content, x, y = wxd_fixture()
        before = self.call('/api/ai-workflows')[1]
        code, preview = self.format_upload('/api/ai-workflows/upload', 'measurement.wxd', content)
        self.assertEqual(code, 200, preview)
        self.assertTrue(preview['requires_confirmation'])
        self.assertEqual(preview['source_check']['detected_format'], 'renishaw_wxd_single')
        self.assertEqual(preview['source_check']['wavenumber_source'], 'DataList1')
        self.assertFalse(preview['source_check']['original_preserved'])
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        code, task = self.format_upload('/api/ai-workflows/upload', 'measurement.wxd', content, dict(confirm_conversion='true'))
        self.assertEqual(code, 200, task)
        meta = task['diagnostics']['source_check']
        self.assertTrue(meta['conversion_confirmed'] and meta['original_preserved'])
        self.assertEqual(meta['conversion_status'], 'converted')
        self.assertEqual(meta['sha256'], hashlib.sha256(content).hexdigest())
        base = '/api/ai-workflows/' + task['id'] + '/download'
        self.assertEqual(self.call(base + '?kind=original')[1], content)
        code, standard = self.call(base + '?kind=standardized')
        self.assertEqual(code, 200)
        xx, yy, _ = parse_single(standard, 'standard.txt')
        np.testing.assert_array_equal(x, xx); np.testing.assert_array_equal(y, yy)
        self.assertEqual(meta['standardized_sha256'], hashlib.sha256(standard).hexdigest())
        self.assertEqual(self.request(base + '?kind=standardized', token=self.other['token'])[0], 404)

    def test_wxd_batch_and_project_import_require_confirmation(self):
        source, _, _ = wxd_fixture()
        entries = [('folder/sample.wxd', source), ('folder/simple.txt', self.spectrum_bytes()), ('folder/broken.wxd', source[:-4])]
        before = self.call('/api/ai-workflows')[1]
        code, preview = self.batch_upload(entries)
        self.assertEqual(code, 200, preview)
        self.assertTrue(preview['requires_confirmation'])
        self.assertEqual([i['status'] for i in preview['items']], ['valid', 'valid', 'invalid'])
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        code, batch = self.batch_upload(entries, confirm_conversion=True)
        self.assertEqual(code, 200, batch)
        self.assertEqual((batch['counts']['ready'], batch['counts']['invalid']), (2, 1))
        project = self.call('/api/projects', dict(name='WXD import test'))[1]['data']['project']['id']
        code, result = self.format_upload('/api/projects/' + project + '/datasets/upload', 'sample.wxd', source, file_field='files')
        self.assertEqual(code, 200, result)
        payload = dict(dataset_id=result['data']['datasets'][0]['id'])
        code, preview = self.call('/api/ai-workflows/source', payload)
        self.assertEqual(code, 200, preview)
        self.assertTrue(preview['requires_confirmation'])
        code, task = self.call('/api/ai-workflows/source', dict(payload, confirm_conversion=True))
        self.assertEqual(code, 200, task)
        self.assertEqual(self.call('/api/ai-workflows/' + task['id'] + '/download?kind=original')[1], source)

    def test_quality_advisory_persists_without_changing_original_or_blocking_batch(self):
        x = np.arange(64) + 400
        y = np.zeros(64)
        y[20] = 30
        content = b'wave,intensity\n' + b'\n'.join(f'{a},{b}'.encode() for a, b in zip(x, y))
        code, task = self.format_upload('/api/ai-workflows/upload', 'quality.csv', content)
        self.assertEqual(code, 200, task)
        report = task['diagnostics']['source_check']['quality_check']
        self.assertEqual(report['status'], 'review')
        self.assertFalse(report['blocking'])
        self.assertIn('narrow_spike', [i['code'] for i in report['issues']])
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}")[1]['diagnostics']['source_check']['quality_check'], report)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/download?kind=original")[1], content)
        np.testing.assert_array_equal(task['original']['intensity'], y)
        code, batch = self.batch_upload([('folder/quality.csv', content), ('folder/constant.csv', b'wave,intensity\n' + b'\n'.join(f'{a},1'.encode() for a in x))])
        self.assertEqual(code, 200, batch)
        self.assertEqual(batch['counts']['ready'], 2)
        for item in batch['items']:
            source = self.call(f"/api/ai-workflows/{item['workflow_id']}")[1]
            self.assertEqual(source['diagnostics']['source_check']['quality_check']['status'], 'review')

    def format_upload(self, path, name, content, fields=None, file_field='file'):
        boundary = 'format-import-test'
        pieces = []
        for key, value in (fields or {}).items():
            pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b'\r\n')
        pieces.append(f'--{boundary}--\r\n'.encode())
        return self.call(path, raw=b''.join(pieces), content_type='multipart/form-data; boundary=' + boundary)

    def test_formats_http_single_instrument_files_preserve_bytes(self):
        examples = [('lab.xlsx', xlsx([['Raman shift (cm-1)', 'Intensity']] + [[400 + i, i * i] for i in range(30)])),
                    ('lab.wdf', wdf_fixture()), ('lab.wxd', wxd_fixture()[0])]
        for name, content in examples:
            code, result = self.format_upload('/api/ai-workflows/upload', name, content)
            self.assertEqual(code, 200, result)
            self.assertTrue(result['requires_confirmation'])
            self.assertNotIn('id', result)
            code, result = self.format_upload('/api/ai-workflows/upload', name, content, dict(confirm_conversion='true'))
            self.assertEqual(code, 200, result)
            self.assertIn(result['diagnostics']['source_check']['detected_format'], {'labelled_spectrum', 'renishaw_wdf', 'renishaw_wxd_single'})
            self.assertEqual(self.call(f"/api/ai-workflows/{result['id']}/download?kind=original")[1], content)

    def test_formats_http_auto_map_and_bad_data(self):
        source = b'Wavenumber\tx0_y0\tx1_y0\tx0_y1\tx1_y1\n400\t1\t2\t3\t4\n401\t5\t6\t7\t8\n402\t9\t10\t11\t12'
        code, result = self.format_upload('/api/upload-hyperspectral', 'lab.txt', source, dict(mode='imaging', instrument='Horiba'))
        self.assertEqual(code, 200, result)
        self.assertEqual(result['data']['shape'], [2, 2, 3])
        self.assertEqual(result['data']['import_metadata']['detected_format'], 'nanophoton_columns')
        code, result = self.format_upload('/api/upload-hyperspectral', 'bad.txt', source.replace(b'\t5\t', b'\tNaN\t'), dict(mode='imaging'))
        self.assertEqual(code, 400, result)
        code, result = self.format_upload('/api/upload-hyperspectral', 'lab.wdf', wdf_fixture(4, mapping=True), dict(mode='imaging'))
        self.assertEqual(code, 200, result)
        self.assertEqual(result['data']['shape'], [2, 2, 8])

    def test_formats_http_project_auto_classifies_map_not_single_spectrum(self):
        code, project = self.call('/api/projects', dict(name='Format test'))
        self.assertEqual(code, 200, project)
        project_id = project['data']['project']['id']
        content = b'X,Y,Raman shift (cm-1),Intensity\n' + b'\n'.join(f'{x},{y},{w},{x+y+w}'.encode() for y in range(2) for x in range(2) for w in (400, 401, 402))
        code, result = self.format_upload(f'/api/projects/{project_id}/datasets/upload', 'map.csv', content, dict(data_type='auto'), file_field='files')
        self.assertEqual(code, 200, result)
        asset = result['data']['datasets'][0]
        self.assertEqual(asset['data_type'], 'mapping')
        self.assertEqual(asset['metadata']['shape'], [2, 2, 3])

    def test_formats_batch_mixed_types_are_checked_per_file(self):
        good = xlsx([['wave', 'intensity']] + [[i, i * i] for i in range(20)])
        code, result = self.batch_upload([('folder/a.xlsx', good), ('folder/b.wdf', wdf_fixture()), ('folder/c.spc', b'not a supported binary')], confirm_conversion=True)
        self.assertEqual(code, 200, result)
        self.assertEqual([item['status'] for item in result['items']], ['ready', 'ready', 'invalid'])

    def test_instrument_confirmation_preserves_original_and_downloads_standard_without_version(self):
        content = teaching_spectrum()
        before = self.call('/api/ai-workflows')[1]
        for _ in range(2):
            code, preview = self.format_upload('/api/ai-workflows/upload', 'teaching.txt', content)
            self.assertEqual(code, 200, preview)
            self.assertTrue(preview['requires_confirmation'])
            self.assertNotIn('id', preview)
            self.assertEqual(preview['source_check']['wavenumber_column'], 4)
            self.assertEqual(preview['source_check']['intensity_column'], 5)
            self.assertFalse(preview['source_check']['original_preserved'])
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        code, task = self.format_upload('/api/ai-workflows/upload', 'teaching.txt', content, dict(confirm_conversion='true'))
        self.assertEqual(code, 200, task)
        meta = task['diagnostics']['source_check']
        self.assertTrue(meta['conversion_confirmed'])
        self.assertTrue(meta['original_preserved'])
        self.assertEqual(meta['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(meta['conversion_status'], 'converted')
        base = f"/api/ai-workflows/{task['id']}/download"
        self.assertEqual(self.call(base + '?kind=original')[1], content)
        code, standard = self.call(base + '?kind=standardized')
        self.assertEqual(code, 200)
        x, y, _ = parse_single(standard, 'standard.txt')
        np.testing.assert_array_equal(x, task['original']['wavenumber'])
        np.testing.assert_array_equal(y, task['original']['intensity'])
        self.assertEqual(hashlib.sha256(standard).hexdigest(), meta['standardized_sha256'])
        self.assertEqual(self.request(base + '?kind=standardized', token=self.other['token'])[0], 404)

    def test_batch_conversion_waits_for_confirmation_before_creating_any_tasks(self):
        entries = [('folder/teaching.txt', teaching_spectrum()), ('folder/simple.txt', self.spectrum_bytes()), ('folder/bad.txt', b'bad file')]
        before = self.call('/api/ai-workflows')[1]
        batches_before = self.call('/api/ai-workflow-batches')[1]
        code, preview = self.batch_upload(entries)
        self.assertEqual(code, 200, preview)
        self.assertTrue(preview['requires_confirmation'])
        self.assertEqual(preview['conversion_count'], 1)
        self.assertEqual([item['status'] for item in preview['items']], ['valid', 'valid', 'invalid'])
        self.assertEqual(self.call('/api/ai-workflows')[1], before)
        self.assertEqual(self.call('/api/ai-workflow-batches')[1], batches_before)
        code, batch = self.batch_upload(entries, confirm_conversion=True)
        self.assertEqual(code, 200, batch)
        self.assertEqual(batch['counts']['ready'], 2)
        self.assertEqual(batch['counts']['invalid'], 1)
