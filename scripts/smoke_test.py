#!/usr/bin/env python3
import argparse
import json
import time
import urllib.error
import urllib.request
from uuid import uuid4


def get(base: str, path: str) -> object:
    with urllib.request.urlopen(base + path, timeout=5) as response:
        return json.load(response)


def wait_for(base: str, path: str, predicate, timeout: float = 30) -> object:
    deadline = time.monotonic() + timeout
    error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = get(base, path)
            if predicate(value):
                return value
        except (OSError, urllib.error.URLError) as exc:
            error = exc
        time.sleep(1)
    raise RuntimeError(f"timeout waiting for {path}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--publish-detection", action="store_true")
    args = parser.parse_args()
    print(
        "health:",
        wait_for(args.base_url, "/api/v1/system/health", lambda x: x.get("status") == "ok"),
    )
    print("services:", wait_for(args.base_url, "/api/v1/system/services", lambda x: len(x) >= 3))
    print(
        "position:",
        wait_for(args.base_url, "/api/v1/drone/position", lambda x: bool(x.get("position"))),
    )
    if args.publish_detection:
        import paho.mqtt.publish as publish

        identifier = str(uuid4())
        payload = {
            "schema_version": "1.0",
            "detection_id": identifier,
            "timestamp": "2026-01-01T00:00:00Z",
            "class_name": "package",
            "number": "SMOKE",
            "world": {"x_m": 1.0, "y_m": 1.0},
            "grid": {"cell": "C3", "column": 2, "row": 2},
            "confidence": 0.99,
        }
        publish.single(
            "grideye/detection/confirmed", json.dumps(payload), hostname="localhost", qos=1
        )
        print(
            "detection:",
            wait_for(
                args.base_url,
                f"/api/v1/detections/{identifier}",
                lambda x: x.get("id") == identifier,
            ),
        )
    print("Grideye smoke test passed")


if __name__ == "__main__":
    main()
