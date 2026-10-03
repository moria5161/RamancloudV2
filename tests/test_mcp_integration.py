"""Real SDK client tests against the installed stdio console script."""

import io
import json
import sys
import zipfile
from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ramancloud_backend import app as api


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def session(tmp_path):
    command = Path(sys.executable).with_name("ramancloud-mcp" + (".exe" if sys.platform == "win32" else ""))
    params = StdioServerParameters(command=str(command), cwd=str(tmp_path))
    with (tmp_path / "server.stderr").open("w+") as stderr:
        async with stdio_client(params, errlog=stderr) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=45)) as client:
                await client.initialize()
                yield client


def result_data(result):
    assert not result.isError, result.content
    assert result.structuredContent is not None
    assert json.loads(result.content[0].text) == result.structuredContent
    return result.structuredContent


def input_bytes(module):
    wave = np.linspace(100, 200, 32)
    base = 4 + 0.05 * wave + 8 * np.exp(-((wave - 150) / 15) ** 2) + np.sin(wave)
    if module == "spectrum":
        return "\n".join(f"{w:.17g}\t{v:.17g}" for w, v in zip(wave, base)).encode()
    if module == "imaging":
        positions = [(20.75, 9.875), (-3.5, 4.125), (8.25, 9.875),
                     (20.75, 4.125), (-3.5, 9.875), (8.25, 4.125)]
        rows = ["\t\t" + "\t".join(f"{w:.17g}" for w in wave)]
        for i, (x, y) in enumerate(positions):
            rows.append(f"{x}\t{y}\t" + "\t".join(f"{v:.17g}" for v in base + i))
    else:
        rows = ["\t" + "\t".join(f"{w:.17g}" for w in wave)]
        for i, time in enumerate([9.25, 2.5, 20.875]):
            rows.append(f"{time}\t" + "\t".join(f"{v:.17g}" for v in base + i))
    return ("\n".join(rows) + "\n").encode()


def expected_export(wave, data, module, coordinates):
    if module == "spectrum":
        return api.download(api.DownloadPayload(wavenumber=wave.tolist(), intensity=data.tolist())).body
    dataset_id = api.register_dataset(wave, data, module, "expected.tsv", coordinates)
    try:
        return api.download(api.DownloadPayload(wavenumber=wave.tolist(), dataset_id=dataset_id, format="mapping")).body
    finally:
        api.DATASETS.pop(dataset_id, None)


@pytest.mark.anyio
async def test_tool_catalog_and_all_packaged_demos(session, tmp_path):
    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
    assert set(tools) == {"inspect_capabilities", "inspect_file", "load_demo", "process_spectrum",
                          "process_batch", "process_imaging", "process_time_series",
                          "split_mapping", "merge_spectra", "convert_mapping"}
    assert tools["inspect_file"].annotations.readOnlyHint is True
    assert tools["process_imaging"].annotations.readOnlyHint is False
    assert all(tool.annotations.openWorldHint is False for tool in tools.values())
    caps = result_data(await session.call_tool("inspect_capabilities"))
    assert caps["modules"] == ["spectrum", "imaging", "time_series"]
    assert set(caps["algorithms"]["denoise"]) == set(api.DENOISE_METHODS)
    assert caps["algorithms"]["denoise"]["sg"]["window_size"]["default"] == 7
    for name, demo in caps["demos"].items():
        output = tmp_path / f"{name}.txt"
        loaded = result_data(await session.call_tool("load_demo", {"name": name, "output_path": str(output)}))
        assert loaded["outputs"] == {"demo": str(output)}
        assert output.read_bytes() == (api.SAMPLES / demo["filename"]).read_bytes()
        assert len(json.dumps(loaded)) < 4000
        inspected = result_data(await session.call_tool("inspect_file", {
            "input_path": str(output), "module": demo["module"], "instrument": demo.get("instrument", "Horiba")}))
        assert inspected["shape"] == loaded["shape"]


@pytest.mark.anyio
@pytest.mark.parametrize("module", ["spectrum", "imaging", "time_series"])
async def test_three_workflows_match_backend_and_preserve_coordinates(session, tmp_path, module):
    source = tmp_path / "input.tsv"
    original = input_bytes(module)
    source.write_bytes(original)
    if module == "spectrum":
        wave, data = api.read_spectrum(original)
        coordinates = {}
    else:
        reader = api.read_imaging if module == "imaging" else api.read_time_series
        wave, data, coordinates = reader(original, "Horiba")
    steps = [{"type": "cut", "params": {"start": float(wave[3]), "end": float(wave[-4])}},
             {"type": "denoise", "method": "sg", "params": {"window_size": 5, "order": 2}},
             {"type": "baseline", "method": "imodpoly", "params": {"poly_order": 2}}]
    flat = data.reshape(-1, data.shape[-1]) if data.ndim == 3 else data
    out_wave, out_data, baseline, history = api.apply_pipeline(wave, flat, [api.Step(**s) for s in steps])
    shape = (*data.shape[:-1], len(out_wave))
    out_data, baseline = out_data.reshape(shape), baseline.reshape(shape)
    paths = {"output_path": str(tmp_path / "processed.tsv"), "processing_json_path": str(tmp_path / "processing.json"),
             "baseline_path": str(tmp_path / "baseline.tsv"), "summary_path": str(tmp_path / "summary.json"),
             "preview_path": str(tmp_path / "preview.svg")}
    response = result_data(await session.call_tool(f"process_{module}", {
        "input_path": str(source), "steps": steps, **paths}))
    assert len(json.dumps(response)) < 6000
    assert response["shape"] == list(shape)
    assert response["history"] == history
    assert response["baseline_available"] is True
    assert all(Path(path).is_absolute() and Path(path).is_file() for path in response["outputs"].values())
    assert Path(paths["output_path"]).read_bytes() == expected_export(out_wave, out_data, module, coordinates)
    assert Path(paths["baseline_path"]).read_bytes() == expected_export(out_wave, baseline, module, coordinates)
    full = json.loads(Path(paths["processing_json_path"]).read_text())
    np.testing.assert_array_equal(full["wavenumber"], out_wave)
    np.testing.assert_allclose(full["intensity" if module == "spectrum" else "spectra"], out_data, atol=1e-12)
    np.testing.assert_allclose(full["baseline"], baseline, atol=1e-12)
    assert full["coordinates"] == coordinates
    assert json.loads(Path(paths["summary_path"]).read_text()) == response
    assert ET.parse(paths["preview_path"]).getroot().tag.endswith("svg")
    if module != "spectrum":
        _, exported_data, exported_coords = reader(Path(paths["output_path"]).read_bytes(), "Horiba")
        _, _, baseline_coords = reader(Path(paths["baseline_path"]).read_bytes(), "Horiba")
        assert exported_coords == baseline_coords == coordinates
        np.testing.assert_allclose(exported_data, out_data, atol=1e-12)
    assert source.read_bytes() == original
    assert set(path.name for path in tmp_path.iterdir()) == {
        "input.tsv", "processed.tsv", "baseline.tsv", "processing.json", "summary.json", "preview.svg", "server.stderr"}


@pytest.mark.anyio
@pytest.mark.parametrize("joint", [False, True])
async def test_batch_api_parity_including_joint_tsvd(session, tmp_path, joint):
    sources, spectra = [], []
    wave, base = api.read_spectrum(input_bytes("spectrum"))
    for i in range(5):
        source = tmp_path / f"spectrum-{i}.tsv"
        intensity = base + np.sin(wave * (i + 1)) * (i + 1)
        source.write_bytes(expected_export(wave, intensity, "spectrum", {}))
        actual_wave, actual_data = api.read_spectrum(source.read_bytes())
        sources.append(str(source))
        spectra.append(api.BatchSpectrum(filename=source.name, wavenumber=actual_wave.tolist(), intensity=actual_data.tolist()))
    steps = [{"type": "denoise", "method": "tsvd" if joint else "sg",
              "params": {"threshold": 0.6} if joint else {"window_size": 5, "order": 2}},
             {"type": "baseline", "method": "imodpoly", "params": {"poly_order": 2}}]
    expected = api.process_batch(api.BatchPayload(spectra=spectra, steps=[api.Step(**s) for s in steps]))["data"]["spectra"]
    outputs = [str(tmp_path / f"processed-{i}.tsv") for i in range(5)]
    baselines = [str(tmp_path / f"baseline-{i}.tsv") for i in range(5)]
    previews = [str(tmp_path / f"preview-{i}.svg") for i in range(5)]
    processing = tmp_path / "batch.json"
    response = result_data(await session.call_tool("process_batch", {
        "input_paths": sources, "output_paths": outputs, "steps": steps, "baseline_paths": baselines,
        "preview_paths": previews, "processing_json_path": str(processing)}))
    assert response["spectrum_count"] == 5
    assert len(json.dumps(response)) < 12000
    full = json.loads(processing.read_text())["results"]
    for i, expected_item in enumerate(expected):
        np.testing.assert_allclose(full[i]["intensity"], expected_item["intensity"], atol=1e-12)
        np.testing.assert_allclose(full[i]["baseline"], expected_item["baseline"], atol=1e-12)
        assert full[i]["history"] == expected_item["history"]
        assert Path(outputs[i]).read_bytes() == expected_export(
            np.asarray(expected_item["wavenumber"]), np.asarray(expected_item["intensity"]), "spectrum", {})
        assert ET.parse(previews[i]).getroot().tag.endswith("svg")


@pytest.mark.anyio
async def test_nanophoton_time_metadata_and_renishaw_coordinates(session, tmp_path):
    inputs = {
        "Nanophoton": b"WN\t2026/10/3 10:00:09 Cycle:1\tWN2\t2026/10/3 10:00:00 Cycle:0\n100\t2\t100\t1\n200\t4\t200\t3\n",
        "Renishaw": b"20\t300\t23\n5\t100\t11\n20\t100\t21\n5\t300\t13\n",
    }
    for instrument, content in inputs.items():
        source, output, processing = (tmp_path / f"{instrument}{suffix}" for suffix in ("-input.tsv", "-output.tsv", ".json"))
        source.write_bytes(content)
        wave, data, coords = api.read_time_series(content, instrument)
        response = result_data(await session.call_tool("process_time_series", {
            "input_path": str(source), "output_path": str(output), "instrument": instrument,
            "processing_json_path": str(processing)}))
        assert response["coordinates"]["time"]["count"] == 2
        full = json.loads(processing.read_text())
        assert full["coordinates"] == coords
        w2, d2, c2 = api.read_time_series(output.read_bytes(), "Horiba")
        np.testing.assert_array_equal(w2, wave)
        np.testing.assert_array_equal(d2, data)
        assert c2["time"] == coords["time"]
    assert json.loads((tmp_path / "Nanophoton.json").read_text())["coordinates"]["time_unit"] == "s"


@pytest.mark.anyio
async def test_split_merge_and_both_conversions_use_backend(session, tmp_path):
    source = tmp_path / "mapping.tsv"
    content = input_bytes("imaging")
    source.write_bytes(content)
    archive = tmp_path / "split.zip"
    result_data(await session.call_tool("split_mapping", {"input_path": str(source), "output_path": str(archive)}))
    expected_zip = api.split_mapping_file(content, "Horiba", source.name)
    with zipfile.ZipFile(archive) as actual, zipfile.ZipFile(io.BytesIO(expected_zip)) as expected:
        assert actual.namelist() == expected.namelist()
        split_paths = []
        for name in actual.namelist():
            assert actual.read(name) == expected.read(name)
            path = tmp_path / name
            path.write_bytes(actual.read(name))
            split_paths.append(str(path))
    merged = tmp_path / "merged.tsv"
    result_data(await session.call_tool("merge_spectra", {"input_paths": split_paths, "output_path": str(merged)}))
    assert merged.read_bytes() == api.merge_spectrum_files([(Path(p).name, Path(p).read_bytes()) for p in split_paths])
    nano, horiba = tmp_path / "nanophoton.tsv", tmp_path / "horiba.tsv"
    result_data(await session.call_tool("convert_mapping", {
        "input_path": str(source), "output_path": str(nano), "conversion": "horiba_to_nanophoton"}))
    assert nano.read_bytes() == api.horiba_to_nanophoton(content)
    result_data(await session.call_tool("convert_mapping", {
        "input_path": str(nano), "output_path": str(horiba), "conversion": "nanophoton_to_horiba"}))
    assert horiba.read_bytes() == api.nanophoton_to_horiba(nano.read_bytes())


@pytest.mark.anyio
async def test_errors_are_mcp_errors_session_stays_usable_and_files_are_unchanged(session, tmp_path):
    source, output, sidecar = (tmp_path / name for name in ("input.tsv", "output.tsv", "sidecar.json"))
    original = input_bytes("spectrum")
    source.write_bytes(original)
    sidecar.write_text("existing user file")
    cases = [
        ("process_spectrum", {"input_path": str(source), "output_path": str(output), "summary_path": str(sidecar)}),
        ("process_spectrum", {"input_path": str(source), "output_path": str(source), "overwrite": True}),
        ("process_spectrum", {"input_path": str(source), "output_path": str(output),
                              "steps": [{"type": "denoise", "method": "sg", "params": {"window_size": 4}}]}),
        ("process_spectrum", {"input_path": str(source), "output_path": str(output),
                              "steps": [{"type": "unknown"}]}),
        ("process_spectrum", {"input_path": str(source), "output_path": str(output), "baseline_path": str(tmp_path / "baseline.tsv")}),
        ("process_batch", {"input_paths": [str(source)], "output_paths": []}),
        ("load_demo", {"name": "../not-a-demo", "output_path": str(output)}),
        ("inspect_file", {"input_path": str(tmp_path / "absent"), "module": "spectrum"}),
        ("unknown_tool", {}),
    ]
    for name, arguments in cases:
        error = await session.call_tool(name, arguments)
        assert error.isError is True, (name, error)
        assert error.content[0].type == "text" and error.content[0].text
        assert not output.exists()
        assert source.read_bytes() == original
        assert sidecar.read_text() == "existing user file"
    output.write_text("old output")
    error = await session.call_tool("process_spectrum", {"input_path": str(source), "output_path": str(output)})
    assert error.isError and output.read_text() == "old output"
    result_data(await session.call_tool("process_spectrum", {
        "input_path": str(source), "output_path": str(output), "overwrite": True}))
    assert output.read_bytes() != b"old output"
    result_data(await session.call_tool("inspect_capabilities"))
