import sys
import types
from pathlib import Path

import pytest
from flask import Flask


# Ensure project root is on sys.path for "app" and "services" imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub torch so importing app modules doesn't require the heavy dependency in unit tests.
if "torch" not in sys.modules:
    torch_stub = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available():
            return False

    torch_stub.cuda = _Cuda()
    sys.modules["torch"] = torch_stub


@pytest.fixture()
def flask_app():
    return Flask(__name__)


@pytest.fixture()
def flask_ctx(flask_app):
    with flask_app.app_context():
        yield
