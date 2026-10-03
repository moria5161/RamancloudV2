"""Official Python MCP SDK server; stdout is reserved for the stdio protocol."""

import argparse
import sys
from contextlib import redirect_stdout
from functools import wraps
from typing import Any, Literal

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
    from mcp.types import ToolAnnotations
except ModuleNotFoundError as exc:
    if exc.name == "mcp":
        raise SystemExit("MCP support is optional. Install RamanCloud with the [mcp] extra.") from exc
    raise

from . import operations as ops
from .operations import Instrument, Module, PipelineStep

mcp = FastMCP(
    "RamanCloud",
    instructions=("Raman spectrum, imaging, and time-series processing using the shared RamanCloud API. "
                  "Inspect capabilities first. Use only input/output paths explicitly requested by the user. "
                  "Do not overwrite unless requested. Tools return summaries and absolute written paths, "
                  "never full spectral arrays. Mapping output is coordinate-preserving Horiba TSV; "
                  "request processing JSON to retain full metadata such as Nanophoton time labels."),
    host="127.0.0.1",
    json_response=True,
    stateless_http=True,
    log_level="WARNING",
)


def register(read_only=False):
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            # Third-party/backend diagnostics must not corrupt JSON-RPC on stdout.
            with redirect_stdout(sys.stderr):
                try:
                    return function(*args, **kwargs)
                except ToolError:
                    raise
                except Exception as exc:
                    detail = getattr(exc, "detail", str(exc))
                    raise ToolError(f"{type(exc).__name__}: {detail}") from exc
        return mcp.tool(structured_output=True, annotations=ToolAnnotations(
            readOnlyHint=read_only, destructiveHint=not read_only,
            idempotentHint=read_only, openWorldHint=False,
        ))(guarded)
    return decorate


@register(read_only=True)
def inspect_capabilities() -> dict[str, Any]:
    """List modules, accepted file layouts, algorithms, defaults, bounds, aliases, demos, and output policy."""
    return ops.inspect_capabilities()


@register(read_only=True)
def inspect_file(input_path: str, module: Module, instrument: Instrument = "Horiba") -> dict[str, Any]:
    """Read one explicitly requested file and report shape, numeric ranges, and coordinate counts; no arrays."""
    return ops.inspect_file(input_path, module, instrument)


@register()
def load_demo(name: str, output_path: str, overwrite: bool = False) -> dict[str, Any]:
    """Copy a named packaged demo to an explicit output file; report its module/instrument and summary."""
    return ops.load_demo(name, output_path, overwrite)


@register()
def process_spectrum(
    input_path: str, output_path: str, steps: list[PipelineStep] | None = None,
    processing_json_path: str | None = None, baseline_path: str | None = None,
    summary_path: str | None = None, preview_path: str | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Process one spectrum into backend TSV. Optional explicit paths write full JSON, baseline TSV,
    summary JSON, or SVG preview. Steps are ordered cut/denoise/baseline; empty steps copy numeric data.
    """
    return ops.process_file(input_path, output_path, "spectrum", "Horiba", steps,
                            processing_json_path, baseline_path, summary_path, preview_path, overwrite)


@register()
def process_batch(
    input_paths: list[str], output_paths: list[str], steps: list[PipelineStep] | None = None,
    processing_json_path: str | None = None, baseline_paths: list[str] | None = None,
    summary_path: str | None = None, preview_paths: list[str] | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Process 1-100 explicit spectrum files, with one output path per input in the same order.
    Uses the API batch pipeline, including joint TSVD (identical axes required).
    Optional baseline/SVG path lists also correspond one-to-one; JSON paths cover the whole batch.
    """
    return ops.process_batch(input_paths, output_paths, steps, processing_json_path,
                             baseline_paths, summary_path, preview_paths, overwrite)


@register()
def process_imaging(
    input_path: str, output_path: str, instrument: Literal["Horiba", "Nanophoton"] = "Horiba",
    steps: list[PipelineStep] | None = None, processing_json_path: str | None = None,
    baseline_path: str | None = None, summary_path: str | None = None,
    preview_path: str | None = None, preview_wavenumber: float | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Process a complete imaging grid into Horiba TSV preserving physical X/Y coordinates.
    Uses [Y,X,wavenumber] ordering and joint matrix processing. Optional full JSON, coordinate-preserving
    baseline TSV, summary JSON, or bounded SVG heatmap at the nearest preview_wavenumber.
    """
    return ops.process_file(input_path, output_path, "imaging", instrument, steps,
                            processing_json_path, baseline_path, summary_path, preview_path,
                            overwrite, preview_wavenumber)


@register()
def process_time_series(
    input_path: str, output_path: str, instrument: Instrument = "Horiba",
    steps: list[PipelineStep] | None = None, processing_json_path: str | None = None,
    baseline_path: str | None = None, summary_path: str | None = None,
    preview_path: str | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Process a time-series matrix into Horiba TSV preserving time coordinates/order.
    Optional full processing JSON retains time_kind, time_unit, and original Nanophoton time_labels,
    which numeric Horiba TSV cannot represent. Optional baseline TSV, summary JSON, and SVG heatmap.
    """
    return ops.process_file(input_path, output_path, "time_series", instrument, steps,
                            processing_json_path, baseline_path, summary_path, preview_path, overwrite)


@register()
def split_mapping(input_path: str, output_path: str, instrument: Instrument = "Horiba", overwrite: bool = False) -> dict[str, Any]:
    """Use the backend mapping splitter; write a ZIP to the explicit output path without extracting.
    Backend split formats: Horiba/Nanophoton imaging or Renishaw time series. Rounded spectrum files
    do not carry mapping coordinates; keep the original mapping for those coordinates.
    """
    return ops.split_mapping(input_path, output_path, instrument, overwrite)


@register()
def merge_spectra(input_paths: list[str], output_path: str, overwrite: bool = False) -> dict[str, Any]:
    """Merge 1-100 explicit numeric spectrum files using the backend; write a matrix TSV.
    The backend rounds to four decimals and uses the first axis; supply matching axes.
    This matrix is not a coordinate-bearing Horiba imaging/time-series file.
    """
    return ops.merge_spectra(input_paths, output_path, overwrite)


@register()
def convert_mapping(
    input_path: str, output_path: str,
    conversion: Literal["horiba_to_nanophoton", "nanophoton_to_horiba"], overwrite: bool = False,
) -> dict[str, Any]:
    """Convert imaging layouts using the backend's Horiba/Nanophoton conversion functions.
    Matches API rounding (one decimal) and zero-based grid indices, not physical coordinate preservation.
    Use process_imaging for coordinate-preserving exports.
    """
    return ops.convert_mapping(input_path, output_path, conversion, overwrite)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RamanCloud file-based MCP server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
