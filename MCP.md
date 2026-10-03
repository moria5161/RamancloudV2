# RamanCloud MCP

RamanCloud exposes spectrum, Raman imaging, and time-series processing to any
MCP client through the **official Python `mcp` SDK's FastMCP**. The default
transport is stdio. It runs locally without starting the web API, frontend, or
desktop app, and calls the same backend readers, algorithms, pipeline, file
utilities, and download exporter as the web API.

Requires Python 3.11 or newer. MCP is an optional `[mcp]` dependency extra,
using `mcp>=1.26,<2` and Pydantic 2. Install into an isolated environment, not
an existing production backend environment that pins Pydantic 1.

## Install A Release

Download the wheel from [GitHub Releases](https://github.com/moria5161/RamancloudV2/releases/latest),
or install the versioned download directly in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'ramancloud[mcp] @ https://github.com/moria5161/RamancloudV2/releases/download/desktop-v2.2.0/ramancloud-2.2.0-py3-none-any.whl'
.venv/bin/ramancloud-mcp --help
```

On Windows use `py -3.11 -m venv .venv`, `.venv\Scripts\python.exe`, and
`.venv\Scripts\ramancloud-mcp.exe`. The wheel works on Windows, macOS, and Linux;
pip installs each platform's numerical dependencies. Git is not required.

## Install From Source

With pip, from any directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'ramancloud[mcp] @ git+https://github.com/moria5161/RamancloudV2.git'
.venv/bin/ramancloud-mcp --help
```

On Windows use `py -3.11 -m venv .venv`, `.venv\Scripts\python.exe`, and
`.venv\Scripts\ramancloud-mcp.exe` instead of the corresponding POSIX commands.
Git is required for a GitHub source install. For reproducibility, append
`@<release-tag-or-commit>` after `.git` in the package URL.

With uv, without cloning or activating an environment:

```sh
uvx --python 3.11 --from 'ramancloud[mcp] @ git+https://github.com/moria5161/RamancloudV2.git' ramancloud-mcp
```

This starts a stdio server, so it normally waits for an MCP client rather than
printing a banner. `--help` prints CLI help and exits.

For an existing checkout:

```sh
python -m pip install -e '.[mcp]'
ramancloud-mcp
# Equivalent module entry point:
python -m ramancloud_mcp
```

Published wheel or source archives can also be installed with their extra:

```sh
python -m pip install 'ramancloud[mcp] @ file:///absolute/path/ramancloud-2.2.0-py3-none-any.whl'
```

The installed package includes the bundled demos; it does not need a working
directory inside the repository. A local stdio client must run on the machine
that holds the requested files. A hosted agent cannot access another machine's
files merely by receiving their path.

## Add To Codex

Use the absolute console-script path from the environment you installed:

```sh
codex mcp add ramancloud -- /absolute/path/.venv/bin/ramancloud-mcp
codex mcp list
```

Alternatively let uv resolve the installation:

```sh
codex mcp add ramancloud -- uvx --python 3.11 --from 'ramancloud[mcp] @ git+https://github.com/moria5161/RamancloudV2.git' ramancloud-mcp
codex mcp list
```

The CLI registration format and `mcp list` are documented in the
[official OpenAI MCP documentation](https://developers.openai.com/codex/mcp/).
For long mappings, configure an appropriate tool timeout in Codex's
`~/.codex/config.toml` (or project `.codex/config.toml`):

```toml
[mcp_servers.ramancloud]
command = "/absolute/path/.venv/bin/ramancloud-mcp"
startup_timeout_sec = 30
tool_timeout_sec = 600
```

Other clients use the same command and optional arguments. A common client
configuration shape is:

```json
{
  "mcpServers": {
    "ramancloud": {
      "command": "/absolute/path/.venv/bin/ramancloud-mcp",
      "args": []
    }
  }
}
```

## Tools

| Tool | Input and result |
| --- | --- |
| `inspect_capabilities` | Lists supported layouts, algorithms, parameter defaults/bounds, constraints, aliases, demos, and output policy. |
| `inspect_file` | Explicit input path, module, and instrument; returns shape, spectral/intensity ranges, and bounded coordinate summaries. |
| `load_demo` | Named bundled demo and explicit output path; copies original bytes and summarizes them. |
| `process_spectrum` | One explicit input/output pair and ordered steps; exports backend spectrum TSV. |
| `process_batch` | 1-100 explicit input paths and corresponding output paths; calls the API batch pipeline, including joint TSVD. |
| `process_imaging` | Horiba or Nanophoton file; exports Horiba TSV preserving physical X/Y coordinates. |
| `process_time_series` | Horiba, Nanophoton, or Renishaw file; exports Horiba TSV preserving numeric time coordinates and order. |
| `split_mapping` | Explicit mapping input and ZIP output; uses the backend splitter without extracting files. |
| `merge_spectra` | Explicit spectrum input list and matrix TSV output; uses the backend merger. |
| `convert_mapping` | Explicit imaging input/output and `horiba_to_nanophoton` or `nanophoton_to_horiba`; uses the backend converter. |

Module identifiers are `spectrum`, `imaging`, and `time_series`. Instrument
identifiers are case-sensitive: `Horiba`, `Nanophoton`, and `Renishaw`.
`inspect_capabilities` is the authoritative discovery tool for parameters.
Cut bounds are inclusive. Steps execute in the order supplied, with at most
32 steps. Empty or omitted steps preserve numeric data without processing.

Processing accepts optional explicit artifact paths:

- `processing_json_path`: full-precision processed arrays, baseline, history,
  and complete coordinates/metadata in a versioned JSON envelope.
- `baseline_path`: separate baseline TSV; for mappings it preserves the same
  coordinates. Requesting it without a baseline-producing step is an error.
- `summary_path`: the same bounded summary and output paths returned to the client.
- `preview_path`: self-contained `.svg` chart or heatmap; no external assets
  or additional rendering dependencies. Imaging accepts `preview_wavenumber`
  and chooses the nearest processed wavenumber. Heatmaps sample at most 96 by
  96 cells, and spectra sample at most 1024 points. Heatmap cells represent
  array positions, not a physical interpolation of irregular coordinates.

Batch processing uses `baseline_paths` and `preview_paths` lists in the same
order as `input_paths`, and one combined processing/summary JSON path.
TSVD requires identical input axes and operates on the batch jointly.
Batch responses return every output path but only the first eight per-spectrum
summaries, with `results_truncated` indicating omission. Full per-spectrum
arrays and histories remain available in a requested processing JSON file.

## Example Calls

First discover capabilities, then call `load_demo` with a desired demo name
and a user-selected destination. Available names include `bacteria`, `ulf`,
`tutorial`, `timeseries_horiba`, `timeseries_nanophoton`, `imaging_horiba`, and
`imaging_nanophoton`.

Single spectrum, as MCP `tools/call` arguments for `process_spectrum`:

```json
{
  "input_path": "/data/spectrum.txt",
  "output_path": "/data/results/spectrum.tsv",
  "steps": [
    {"type": "cut", "params": {"start": 400, "end": 1800}},
    {"type": "denoise", "method": "sg", "params": {"window_size": 7, "order": 3}},
    {"type": "baseline", "method": "airpls", "params": {"lam": 10000000, "diff_order": 3}}
  ],
  "processing_json_path": "/data/results/spectrum.json",
  "baseline_path": "/data/results/baseline.tsv",
  "preview_path": "/data/results/spectrum.svg"
}
```

Imaging, for `process_imaging`:

```json
{
  "input_path": "/data/imaging_Nanophoton.txt",
  "output_path": "/data/results/imaging_Horiba.tsv",
  "instrument": "Nanophoton",
  "steps": [{"type": "denoise", "method": "tsvd", "params": {"threshold": 0.001}}],
  "processing_json_path": "/data/results/imaging.json",
  "preview_path": "/data/results/imaging.svg",
  "preview_wavenumber": 1580
}
```

Time series, for `process_time_series`:

```json
{
  "input_path": "/data/time_series.txt",
  "output_path": "/data/results/time_series_Horiba.tsv",
  "instrument": "Horiba",
  "steps": [{"type": "denoise", "method": "wtd", "params": {"wavelet": "db3", "level": 3}}],
  "processing_json_path": "/data/results/time_series.json",
  "summary_path": "/data/results/time_summary.json",
  "preview_path": "/data/results/time_series.svg"
}
```

Pipeline constraints still apply to input lengths; for example a wavelet
level may be too high for a short or heavily cut spectrum.

## Data And Safety

MCP responses contain numeric summaries and **absolute written file paths**,
not full arrays or huge coordinate lists. Full data goes only to requested
files. Mapping arrays use `[Y, X, wavenumber]` for imaging and
`[time, wavenumber]` for time series. Imaging coordinates are reordered using
the backend's grid lookup; nonzero, negative, fractional, and shuffled
coordinates survive processing/export. Numeric time coordinates and their
backend reader order survive unchanged.

Horiba TSV cannot encode Nanophoton timestamp labels, time units, or
`time_kind`. Request `processing_json_path` to preserve this metadata in
addition to the numeric coordinate-bearing TSV. Spectrum exports use the
backend's eight-significant-digit precision; mapping exports use seventeen.

Split/merge/conversion intentionally match the API's behavior. Split outputs
and merges round to four decimal places. Merges emit a wavenumber-plus-spectra
matrix, use the first input axis, and do not carry physical coordinates.
Supply matching axes. The current imaging conversion routines use zero-based
grid indices and round to one decimal; they are **not** coordinate-preserving
processing exports. Keep the original file or use `process_imaging` when
physical coordinates matter.

Every operation takes explicit file paths. There is no directory scanning,
glob expansion, arbitrary URL download, automatic output naming, or ZIP
extraction. Named demos read only packaged sample files. Relative paths resolve
against the server working directory; absolute paths are recommended. Output
parent directories must already exist. All requested destinations are checked
before output is written; duplicate paths, output symlinks, and input/output
aliases (including hardlinks) are rejected.

Existing files are refused unless the caller explicitly passes
`overwrite: true`. Inputs are never replaced, even with that flag. Exclusive
file creation also catches collisions occurring after validation. Failures
clean up newly created outputs; explicitly overwritten preexisting outputs
are not transactionally restored if a write fails. Temporary backend datasets
are in-memory only and released after export.

File, validation, and processing failures produce MCP tool error results
(`isError: true`), not fake successful JSON. A failed tool call does not close
the session. The SDK reserves stdout for JSON-RPC; backend diagnostics are
redirected to stderr. Filesystem access is governed by the process's OS
permissions, not an MCP sandbox: connect only trusted clients and have agents
use paths explicitly authorized by the user.

## Optional Loopback HTTP

```sh
ramancloud-mcp --transport streamable-http --host 127.0.0.1 --port 8765
codex mcp add ramancloud-http --url http://127.0.0.1:8765/mcp
```

This uses the SDK's stateless Streamable HTTP transport and DNS-rebinding
protection. The CLI accepts only `127.0.0.1`, `localhost`, or `::1`, never a
public bind address. It has no authentication and is intended for trusted
local clients only; do not expose it through a proxy or port-forward.
The [official Python SDK documentation](https://py.sdk.modelcontextprotocol.io/v1/)
describes FastMCP and these transports.

## Verification And Packaging

```sh
python -m pip install -e '.[mcp,dev]'
python -m pytest -q tests/test_mcp*.py
```

The tests initialize a real stdio SDK client against the installed console
script, list tools, call all three workflows and file utilities, load all
packaged demos, compare results with backend processing/export, verify physical
and time coordinate preservation, and exercise protocol errors and file policy.

Root packaging is responsible for including `ramancloud_mcp` and the backend
package mapping (`backend/` to `ramancloud_backend`), the `[mcp]` dependencies,
the `ramancloud-mcp = ramancloud_mcp.server:main` console script, packaged
`backend/samples/*.txt`, and wheel/sdist release publishing. No frontend or
desktop dependency is required to run the MCP server.
