import json

from src.market_intel.logging_utils import to_json_safe


def test_bytes_are_json_serializable_after_sanitization():
    payload = {"upload": b"abc", "nested": [b"xyz"]}
    safe = to_json_safe(payload)
    encoded = json.dumps(safe)
    assert '"type": "bytes"' in encoded
