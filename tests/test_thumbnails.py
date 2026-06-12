import pytest


def test_thumbnails_404_for_nonexistent_dir(client):
    resp = client.get("/api/pdf/nonexistent/some.pdf/thumbnails")
    assert resp.status_code == 404


def test_thumbnails_404_for_nonexistent_file(client, sample_pdf_path):
    resp = client.get("/api/pdf/books/nonexistent.pdf/thumbnails")
    assert resp.status_code == 404


def test_thumbnails_returns_valid_json(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "thumbnails" in data
    assert "total_pages" in data
    assert isinstance(data["thumbnails"], list)
    assert data["total_pages"] > 0


def test_thumbnails_range_support(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails?start=1&end=3")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["thumbnails"]) == 3
    for t in data["thumbnails"]:
        assert "page" in t
        assert "image" in t
        assert t["image"].startswith("data:image/png;base64,")


def test_thumbnails_range_clamped_to_total(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails?start=1&end=99999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["end"] == data["total_pages"]
