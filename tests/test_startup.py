from app import __main__ as startup
from app import bootstrap_catalog


def test_production_startup_uses_host_and_environment_port(monkeypatch):
    calls = []
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setattr(
        startup.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    startup.main()

    assert calls == [
        (
            ("app.main:app",),
            {
                "host": "0.0.0.0",
                "port": 9123,
                "proxy_headers": True,
                "forwarded_allow_ips": "*",
            },
        )
    ]


def test_production_startup_defaults_to_port_8000(monkeypatch):
    calls = []
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(startup.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    startup.main()
    assert calls[0]["port"] == 8000


def test_web_startup_never_bootstraps_catalog(monkeypatch):
    monkeypatch.setattr(
        bootstrap_catalog,
        "prepare_catalog",
        lambda: (_ for _ in ()).throw(AssertionError("web startup downloaded a catalog")),
    )
    monkeypatch.setattr(startup.uvicorn, "run", lambda *args, **kwargs: None)

    startup.main()
