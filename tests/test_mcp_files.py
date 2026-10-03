"""File policy, cleanup, preview bounds, and in-process backend parity."""

import json
from xml.etree import ElementTree as ET

import numpy as np
import pytest

pytest.importorskip("mcp")
from ramancloud_backend import app as api
from ramancloud_mcp import operations as ops
from ramancloud_mcp.files import FilePlan


def test_explicit_paths_duplicates_aliases_and_preflight(tmp_path):
    source = tmp_path / "input.tsv"
    source.write_text("100\t1\n200\t2\n")
    output = tmp_path / "output.tsv"
    with pytest.raises(ValueError, match="distinct"):
        FilePlan([source], {"a": str(output), "b": str(output)}, False)
    with pytest.raises(ValueError, match="input"):
        FilePlan([source], {"a": str(source)}, True)
    with pytest.raises(FileNotFoundError):
        FilePlan([source], {"a": str(tmp_path / "unrequested-dir" / "result.tsv")}, False)
    assert not (tmp_path / "unrequested-dir").exists()
    with pytest.raises(ValueError, match="non-empty"):
        FilePlan([source], {"a": ""}, False)
    with pytest.raises(ValueError, match="symlink"):
        output.symlink_to(source)
        FilePlan([source], {"a": str(output)}, True)
    output.unlink()
    output.hardlink_to(source)
    with pytest.raises(ValueError, match="input"):
        FilePlan([source], {"a": str(output)}, True)
    assert source.read_text() == "100\t1\n200\t2\n"


def test_concurrent_collision_does_not_overwrite_and_releases_reservations(tmp_path):
    a, b = tmp_path / "a.tsv", tmp_path / "b.tsv"
    plan = FilePlan([], {"a": str(a), "b": str(b)}, False)
    b.write_text("appeared after preflight")
    with pytest.raises(FileExistsError):
        plan.write({"a": b"first", "b": b"second"})
    assert not a.exists()
    assert b.read_text() == "appeared after preflight"


def test_overwrite_checks_opened_file_identity_before_truncating(tmp_path):
    source, target = tmp_path / "source.tsv", tmp_path / "target.tsv"
    source.write_text("preserve input")
    plan = FilePlan([source], {"processed": str(target)}, True)
    target.hardlink_to(source)
    with pytest.raises(ValueError, match="alias"):
        plan.write({"processed": b"replacement"})
    assert source.read_text() == target.read_text() == "preserve input"


def test_mapping_export_releases_only_its_own_dataset_even_on_failure(monkeypatch):
    wave, data = np.arange(10, dtype=float), np.arange(20, dtype=float).reshape(2, 10)
    keep = api.register_dataset(wave, data, "time_series", "keep.tsv", {"time": [2.5, 9]})
    result = ops.Processed("time_series", wave, data, {"time": [2.5, 9]}, None, [])
    before = set(api.DATASETS)
    try:
        assert ops.export_tsv(result)
        assert set(api.DATASETS) == before
        def failure(_payload):
            raise ValueError("simulated download failure")
        monkeypatch.setattr(api, "download", failure)
        with pytest.raises(ValueError, match="simulated"):
            ops.export_tsv(result)
        assert set(api.DATASETS) == before
    finally:
        api.DATASETS.pop(keep, None)


def test_large_imaging_summary_and_preview_are_bounded():
    wave = np.arange(20, dtype=float)
    data = np.arange(120 * 130 * 20, dtype=float).reshape(120, 130, 20)
    coordinates = {"x": np.arange(130).tolist(), "y": np.arange(120).tolist()}
    result = ops.Processed("imaging", wave, data, coordinates, None, [])
    assert len(json.dumps(result.summary())) < 1000
    assert result.summary()["coordinates"]["x"]["count"] == 130
    preview = ET.fromstring(ops.preview_svg(result, 15))
    cells = [item for item in preview if item.tag.endswith("rect")]
    assert len(cells) <= 1 + 96 * 96
    assert b"Wavenumber: 15" in ET.tostring(preview)


def test_extreme_finite_values_have_finite_summary_statistics():
    summary = ops.summarize([100, 200], [1e308, 1e308], "spectrum")
    assert summary["intensity"]["mean"] == 1e308
    json.dumps(summary, allow_nan=False)


def test_large_batch_returns_bounded_summaries_and_all_output_paths(tmp_path):
    source = tmp_path / "input.tsv"
    source.write_text("100\t1\n200\t2\n")
    outputs = [str(tmp_path / f"output-{i}.tsv") for i in range(20)]
    result = ops.process_batch([str(source)] * 20, outputs)
    assert result["spectrum_count"] == 20
    assert len(result["results"]) == ops.MAX_BATCH_SUMMARIES
    assert result["results_truncated"] is True
    assert len(result["outputs"]) == 20
    assert len(json.dumps(result)) < 8000


def test_batch_tsvd_rejects_mismatched_axes_without_outputs(tmp_path):
    a, b, out_a, out_b = (tmp_path / name for name in ("a.tsv", "b.tsv", "out-a.tsv", "out-b.tsv"))
    a.write_text("100\t1\n200\t2\n")
    b.write_text("101\t1\n201\t2\n")
    with pytest.raises(ValueError, match="identical wavenumber"):
        ops.process_batch([str(a), str(b)], [str(out_a), str(out_b)],
                          [ops.PipelineStep(type="denoise", method="tsvd")])
    assert not out_a.exists() and not out_b.exists()


def test_input_and_optional_artifact_validation_has_no_writes(tmp_path):
    source, output = tmp_path / "input.tsv", tmp_path / "output.tsv"
    source.write_text("100\t1\n200\t2\n")
    with pytest.raises(ValueError, match="regular file"):
        ops.inspect_file(str(tmp_path), "spectrum")
    with pytest.raises(ValueError, match=".svg"):
        ops.process_file(str(source), str(output), "spectrum", "Horiba", preview_path=str(tmp_path / "bad.png"))
    with pytest.raises(ValueError, match="32"):
        ops.process_file(str(source), str(output), "spectrum", "Horiba",
                         steps=[ops.PipelineStep(type="denoise")] * 33)
    assert not output.exists()


def test_backend_diagnostics_go_to_stderr_not_protocol_stdout(monkeypatch, capsys):
    from ramancloud_mcp import server
    def noisy():
        print("backend diagnostic")
        return {"ok": True}
    monkeypatch.setattr(ops, "inspect_capabilities", noisy)
    assert server.inspect_capabilities() == {"ok": True}
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "backend diagnostic\n"
