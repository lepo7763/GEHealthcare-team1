
"""Configuration for TShark network diagnostics."""

import os

TSHARK_NAMESPACE = os.getenv("TSHARK_NAMESPACE", "iomt-dev-2")
TSHARK_POD = os.getenv("TSHARK_POD", "tshark-test")
TSHARK_CONTAINER = os.getenv("TSHARK_CONTAINER", "tshark-test")
TSHARK_INTERFACE = os.getenv("TSHARK_INTERFACE", "eth0")

TSHARK_DURATION = int(os.getenv("TSHARK_DURATION", "30"))
TSHARK_MAX_DURATION = 120
TSHARK_MAX_PACKETS = 10000
TSHARK_REQUEST_TIMEOUT = TSHARK_MAX_DURATION + 20
