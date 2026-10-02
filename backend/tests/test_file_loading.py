import io
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class FileLoadingTests(unittest.TestCase):
    def setUp(self):
        app.DATASETS.clear()

    def test_spectrum_demo_values(self):
        for name in ("Bacteria.txt", "ULF.txt"):
            content = (app.SAMPLES / name).read_bytes()
            expected = pd.read_csv(io.BytesIO(content), sep="\t", header=None).values
            wave, intensity = app.read_spectrum(content)
            np.testing.assert_array_equal(wave, expected[:, 0])
            np.testing.assert_array_equal(intensity, expected[:, 1])

    def test_spectrum_headers_whitespace_and_blank_columns(self):
        for content in (b"Header\n +100  10\n .200  20\n", b"100\t10\t\n200\t20\t\n", b"\xef\xbb\xbf100\t10\n200\t20\n"):
            wave, intensity = app.read_spectrum(content)
            np.testing.assert_array_equal(intensity, [10, 20])
        wave, intensity = app.read_spectrum(b"1\t2\t100\t10\n3\t4\t200\t20\n")
        np.testing.assert_array_equal(wave, [100, 200])

    def test_missing_spectrum_values_rejected(self):
        with self.assertRaises(ValueError):
            app.read_spectrum(b"100\t1\n200\t\n")

    def test_time_series_demo_values(self):
        wave, data, coordinates = app.read_time_series((app.SAMPLES / "time_series_Horiba.txt").read_bytes(), "Horiba")
        expected = pd.read_csv(str(app.SAMPLES / "time_series_Horiba.txt"), sep="\t", header=None)
        np.testing.assert_array_equal(data, expected.iloc[1:, 1:].values)
        np.testing.assert_array_equal(coordinates["time"], expected.iloc[1:, 0].values)
        wave, data, coordinates = app.read_time_series((app.SAMPLES / "time_series_Nanophoton.txt").read_bytes(), "Nanophoton")
        expected = pd.read_csv(str(app.SAMPLES / "time_series_Nanophoton.txt"), sep="\t")
        np.testing.assert_array_equal(data, expected.iloc[:, 1::2].values.T[::-1])
        self.assertEqual(coordinates["time_unit"], "s")
        self.assertEqual(coordinates["time"][0], 0)
        self.assertEqual(coordinates["time_labels"], [str(c) for c in expected.columns[1::2]][::-1])

    def test_nanophoton_unlabelled_time_uses_indices(self):
        wave, data, coordinates = app.read_time_series(b"WN\tScan2\tWN2\tScan1\n100\t2\t100\t1\n200\t4\t200\t3\n", "Nanophoton")
        self.assertEqual(coordinates["time"], [0, 1])
        self.assertEqual(coordinates["time_kind"], "index")
        self.assertEqual(coordinates["time_labels"], ["Scan1", "Scan2"])
        np.testing.assert_array_equal(data, [[1, 3], [2, 4]])

    def test_horiba_columns_are_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "no wavenumber"):
            app.read_time_series(b"\t100\t\n2\t1\t99\n", "Horiba")
        wave, data, coordinates = app.read_time_series(b"\t100\t\n2\t1\t\n", "Horiba")
        np.testing.assert_array_equal(data, [[1]])

    def test_imaging_demo_coordinate_lookup(self):
        for name, instrument in (("imaging_Horiba_Graphene.txt", "Horiba"), ("imaging_Nanophoton_Hela.txt", "Nanophoton")):
            wave, data, coordinates = app.read_imaging((app.SAMPLES / name).read_bytes(), instrument)
            self.assertEqual(data.shape, (len(coordinates["y"]), len(coordinates["x"]), len(wave)))
            if instrument == "Horiba":
                rows = pd.read_csv(str(app.SAMPLES / name), sep="\t", header=None).values[1:]
                expected = np.empty_like(data)
                for row in rows:
                    expected[coordinates["y"].index(row[1]), coordinates["x"].index(row[0])] = row[2:]
            else:
                frame = pd.read_csv(str(app.SAMPLES / name), sep="\t")
                expected = frame.iloc[:, 1:-1].values.T.reshape(data.shape)
            np.testing.assert_array_equal(data, expected)

    def test_nonzero_nanophoton_grid(self):
        content = b"Wavenumber\tx6_y10\tx5_y10\t\n100\t2\t1\t\n200\t4\t3\t\n"
        wave, data, coordinates = app.read_imaging(content, "Nanophoton")
        self.assertEqual(data.shape, (1, 2, 2))
        self.assertEqual(coordinates, {"x": [5.0, 6.0], "y": [10.0]})
        np.testing.assert_array_equal(data, [[[1, 3], [2, 4]]])

    def test_shuffled_rectangular_horiba_and_pixel(self):
        content = b"\t\t100\t200\n30\t7\t6\t60\n10\t5\t1\t10\n30\t5\t3\t30\n20\t7\t5\t50\n10\t7\t4\t40\n20\t5\t2\t20\n"
        wave, data, coordinates = app.read_imaging(content, "Horiba")
        self.assertEqual(data.shape, (2, 3, 2))
        np.testing.assert_array_equal(data[:, :, 0], [[1, 2, 3], [4, 5, 6]])
        loaded = app.mapping_payload(wave, data, "imaging", "rectangular.txt", coordinates)
        pixel = app.get_hyperspectral_pixel(loaded["dataset_id"], x=2, y=1)["data"]
        self.assertEqual(pixel["intensity"], [6, 60])
        self.assertEqual((pixel["coordinate_x"], pixel["coordinate_y"]), (30, 7))
        self.assertEqual(loaded["mean_spectrum"], [3.5, 35])

    def test_incomplete_and_duplicate_grids_rejected(self):
        for content in (b"\t\t100\n0\t0\t1\n1\t1\t2\n", b"\t\t100\n0\t0\t1\n0\t0\t2\n"):
            with self.assertRaises(ValueError):
                app.read_imaging(content, "Horiba")

    def test_renishaw_time_order(self):
        wave, data, coordinates = app.read_time_series(b"20\t300\t23\n5\t100\t11\n20\t100\t21\n5\t300\t13\n", "Renishaw")
        np.testing.assert_array_equal(wave, [100, 300])
        np.testing.assert_array_equal(data, [[11, 13], [21, 23]])
        self.assertEqual(coordinates["time"], [5, 20])

    def test_coordinates_survive_processing_and_export(self):
        for mode, content in (("time_series", b"\t100\t200\n2.5\t1\t2\n9\t3\t4\n"), ("imaging", b"\t\t100\t200\n6\t10\t2\t4\n5\t10\t1\t3\n")):
            reader = app.read_time_series if mode == "time_series" else app.read_imaging
            wave, data, coordinates = reader(content, "Horiba")
            loaded = app.mapping_payload(wave, data, mode, "original.txt", coordinates)
            payload = app.CubePayload(wavenumber=wave.tolist(), dataset_id=loaded["dataset_id"], steps=[app.Step(type="cut", params={"start": 100, "end": 200})])
            processed = app.process_cube(payload)["data"]
            self.assertEqual(processed["coordinates"], coordinates)
            exported = app.download(app.DownloadPayload(wavenumber=wave.tolist(), dataset_id=processed["processed_dataset_id"], format="mapping"))
            w2, d2, c2 = reader(exported.body, "Horiba")
            np.testing.assert_array_equal(w2, wave)
            np.testing.assert_array_equal(d2, data)
            self.assertEqual(c2, coordinates)
            matrix = app.download(app.DownloadPayload(wavenumber=wave.tolist(), dataset_id=processed["processed_dataset_id"]))
            default_export = pd.read_csv(io.BytesIO(matrix.body), sep="\t", header=None).values
            self.assertEqual(default_export.shape, (len(wave), data.reshape(-1, len(wave)).shape[0] + 1))
            if mode == "time_series":
                selected = app.get_hyperspectral_spectrum(processed["processed_dataset_id"], index=1)["data"]
                self.assertEqual(selected["time"], 9)

    def test_wtd_preview_is_processed_and_raw_is_unchanged(self):
        raw = app.demo_mapping("timeseries_horiba")["data"]
        original = app.DATASETS[raw["dataset_id"]]["data"].copy()
        processed = app.process_cube(app.CubePayload(wavenumber=raw["wavenumber"], dataset_id=raw["dataset_id"], steps=[app.Step(type="denoise", method="wtd", params={"wavelet": "db3", "level": 3})]))["data"]
        output = app.DATASETS[processed["processed_dataset_id"]]["data"]
        self.assertNotEqual(raw["dataset_id"], processed["processed_dataset_id"])
        np.testing.assert_array_equal(app.DATASETS[raw["dataset_id"]]["data"], original)
        self.assertTrue(np.all(np.max(np.abs(output - original), axis=1) > 1e-6))
        self.assertGreater(np.max(np.abs(np.asarray(processed["preview"]) - raw["preview"])), 20)
        np.testing.assert_allclose(output[0], app.denoise_spectrum(original[0], {"wavelet": "db3", "level": 3}, "wtd"))


if __name__ == "__main__":
    unittest.main()
