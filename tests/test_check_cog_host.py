from email.message import Message
from pathlib import Path
import runpy
import sys
from unittest.mock import MagicMock

import pytest


def check_host(monkeypatch, expose=None, origin="https://viewer.example", allow="*"):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 206
    response.read.return_value = bytes(1024)
    response.headers = Message()
    response.headers["Content-Range"] = "bytes 0-1023/2048"
    response.headers["Access-Control-Allow-Origin"] = allow
    if expose is not None:
        for value in expose if isinstance(expose, list) else [expose]:
            response.headers["Access-Control-Expose-Headers"] = value
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: response)
    args = ["check_cog_host.py", "https://data.example/test.tif"]
    if origin:
        args += ["--origin", origin]
    monkeypatch.setattr(sys, "argv", args)
    runpy.run_path(str(Path(__file__).parents[1] / "scripts/check_cog_host.py"), run_name="__main__")


@pytest.mark.parametrize("expose", [None, "", "Content-Length, Accept-Ranges", "X-Content-Range"])
def test_rejects_a_header_that_python_can_read_but_the_browser_cannot(monkeypatch, capsys, expose):
    with pytest.raises(SystemExit, match="must expose Content-Range"):
        check_host(monkeypatch, expose)
    assert "PASS" not in capsys.readouterr().out


@pytest.mark.parametrize("expose", ["Content-Range", " Content-Length, cOnTeNt-RaNgE ", "*",
                                   ["Content-Length", "Content-Range"]])
def test_accepts_exposed_range_headers_for_cross_origin_fetches(monkeypatch, capsys, expose):
    check_host(monkeypatch, expose)
    assert "Content-Range is exposed" in capsys.readouterr().out


def test_same_origin_check_does_not_require_cors_exposure(monkeypatch, capsys):
    check_host(monkeypatch, origin=None)
    assert "PASS" in capsys.readouterr().out


def test_exposed_headers_do_not_replace_origin_authorization(monkeypatch):
    with pytest.raises(SystemExit, match="cross-origin access is not allowed"):
        check_host(monkeypatch, "Content-Range", allow="https://other.example")
