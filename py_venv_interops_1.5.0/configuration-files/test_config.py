"""Server, port and application settings for every test suite.

The values live in test_environment.json; this module turns them into a typed TestTarget
so tests read attributes (CFG.server_host) instead of nested dictionary keys.

Usage in a test:
    import test_config
    CFG = test_config.for_test("smoke", "MSQ-SMK-001")
    MOSAIQ_SERVER = CFG.server_host

To run against another lab without editing the committed file, point MSQ_TEST_CONFIG at
a copy of test_environment.json before starting the run:
    $env:MSQ_TEST_CONFIG = "C:\\path\\to\\lab2_environment.json"
"""

import json
import os
from dataclasses import dataclass

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "test_environment.json")
CONFIG_PATH = os.environ.get("MSQ_TEST_CONFIG", DEFAULT_CONFIG_PATH)


@dataclass(frozen=True)
class TestTarget:
    test_id: str
    server_name: str
    server_host: str
    squish_port: int
    app: str
    aut_name: str


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as config_file:
        raw = json.load(config_file)

    # Validate every reference up front, so a typo fails at import with a clear message
    # rather than as a KeyError halfway through a test.
    servers = raw["servers"]
    applications = raw["applications"]
    for server_name, server in servers.items():
        if server["app"] not in applications:
            raise ValueError(f"{path}: server '{server_name}' uses unknown app '{server['app']}'")
    for suite_name, suite in raw["suites"].items():
        referenced = [suite["default_server"], *suite.get("overrides", {}).values()]
        for server_name in referenced:
            if server_name not in servers:
                raise ValueError(f"{path}: suite '{suite_name}' references unknown server '{server_name}'")
    return raw


_RAW = _load(CONFIG_PATH)


def for_test(suite: str, test_id: str) -> TestTarget:
    """Resolve the server, Squish port and AUT a test case runs against."""
    if suite not in _RAW["suites"]:
        raise KeyError(f"Unknown suite '{suite}' in {CONFIG_PATH}")
    suite_config = _RAW["suites"][suite]
    server_name = suite_config.get("overrides", {}).get(test_id, suite_config["default_server"])
    server_config = _RAW["servers"][server_name]
    app_config = _RAW["applications"][server_config["app"]]
    return TestTarget(
        test_id=test_id,
        server_name=server_name,
        server_host=server_config["host"],
        squish_port=server_config.get("squish_port", _RAW["squish"]["default_port"]),
        app=server_config["app"],
        aut_name=app_config.get("aut_name", ""),
    )
