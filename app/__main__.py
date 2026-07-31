"""Production entry point for ``python -m app``."""

import os

import uvicorn


def main() -> None:
    """Run Uvicorn on all interfaces using the platform-provided port."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
