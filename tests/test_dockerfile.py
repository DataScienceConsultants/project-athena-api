from pathlib import Path


def test_container_starts_only_the_api_and_copies_prepared_catalog():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "app"]' in dockerfile
    assert "app.bootstrap_catalog" not in dockerfile
    assert "COPY data ./data" in dockerfile
    assert "COPY tests" not in dockerfile
