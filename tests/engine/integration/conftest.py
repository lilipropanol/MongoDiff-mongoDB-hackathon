"""Real-MongoDB fixtures for engine semantics checks.

Uses SCHEMA_GUARD_TEST_URI when set (must be a disposable server, never production or the shared Atlas
cluster). Otherwise starts a throwaway local mongod from PATH on a free port with a temp data directory.
Skips cleanly when neither is available. Set SCHEMA_GUARD_SKIP_MONGO=1 to skip on purpose.
"""

import os
import shutil
import socket
import subprocess
import time
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def pytest_configure(config):
    config.addinivalue_line("markers", "mongo: needs a real MongoDB server (local mongod or SCHEMA_GUARD_TEST_URI)")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def mongo_client(tmp_path_factory):
    if os.getenv("SCHEMA_GUARD_SKIP_MONGO"):
        pytest.skip("SCHEMA_GUARD_SKIP_MONGO is set")
    uri = os.getenv("SCHEMA_GUARD_TEST_URI")
    process = None
    if not uri:
        mongod = shutil.which("mongod")
        if not mongod:
            pytest.skip("No MongoDB available: install mongod or set SCHEMA_GUARD_TEST_URI")
        port = _free_port()
        dbpath = tmp_path_factory.mktemp("mongod-data")
        process = subprocess.Popen([mongod, "--dbpath", str(dbpath), "--port", str(port), "--bind_ip", "127.0.0.1",
                                    "--nounixsocket", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        uri = f"mongodb://127.0.0.1:{port}/?directConnection=true"
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    deadline = time.monotonic() + 30
    while True:
        try:
            client.admin.command("ping")
            break
        except PyMongoError:
            if process and process.poll() is not None:
                pytest.skip(f"Local mongod exited early with code {process.returncode}")
            if time.monotonic() > deadline:
                if process:
                    process.terminate()
                pytest.skip("MongoDB did not become ready within 30 seconds")
            time.sleep(0.2)
    yield client
    client.close()
    if process:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def mongo_uri(mongo_client):
    host, port = mongo_client.address
    return os.getenv("SCHEMA_GUARD_TEST_URI") or f"mongodb://{host}:{port}/?directConnection=true"


@pytest.fixture
def fresh_collection(mongo_client):
    db = mongo_client["schema_guard_it"]
    collection = db[f"t_{uuid4().hex[:12]}"]
    yield collection
    collection.drop()


@pytest.fixture(scope="session")
def server_version(mongo_client):
    return mongo_client.server_info()["version"]
