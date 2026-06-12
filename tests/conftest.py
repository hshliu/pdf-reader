import os
import pytest
from app import app as flask_app


@pytest.fixture
def app():
    os.environ["CONFIG_PATH"] = "config.json"
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_pdf_path():
    """Find any available PDF for testing."""
    import app
    for d in app.PDF_DIRECTORIES:
        path = d["path"]
        if os.path.isdir(path):
            for f in sorted(os.listdir(path)):
                if f.lower().endswith(".pdf"):
                    return os.path.join(path, f)
    pytest.skip("No PDF files available for testing")
