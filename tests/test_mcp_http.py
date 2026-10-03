"""Optional Streamable HTTP uses the SDK and stays on loopback."""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_loopback_http_client_and_dns_rebinding_protection(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = Path(sys.executable).with_name("ramancloud-mcp" + (".exe" if sys.platform == "win32" else ""))
    url = f"http://127.0.0.1:{port}/mcp"
    with (tmp_path / "http.stderr").open("w+") as stderr, (tmp_path / "http.stdout").open("w+") as stdout:
        process = subprocess.Popen([str(command), "--transport", "streamable-http", "--port", str(port)],
                                   cwd=tmp_path, stderr=stderr, stdout=stdout)
        try:
            async with httpx.AsyncClient(timeout=1) as http:
                for _ in range(100):
                    assert process.poll() is None, "HTTP server exited before it was ready"
                    try:
                        await http.get(url)
                        break
                    except httpx.ConnectError:
                        await anyio.sleep(0.1)
                else:
                    pytest.fail("HTTP server did not become ready")
                assert (await http.get(url, headers={"Host": "untrusted.invalid"})).status_code == 421
                assert (await http.get(url, headers={"Origin": "https://untrusted.invalid"})).status_code == 403
            async with streamable_http_client(url) as (reader, writer, _):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    assert len((await client.list_tools()).tools) == 10
                    result = await client.call_tool("inspect_capabilities")
                    assert not result.isError
                    assert result.structuredContent["modules"] == ["spectrum", "imaging", "time_series"]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    assert (tmp_path / "http.stdout").read_text() == ""


def test_cli_refuses_public_bind_addresses():
    result = subprocess.run([sys.executable, "-m", "ramancloud_mcp", "--transport", "streamable-http",
                             "--host", "0.0.0.0"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "invalid choice" in result.stderr
