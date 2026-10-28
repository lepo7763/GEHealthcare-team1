import pytest
from pydantic import ValidationError

from app.Tshark.schemas import WiresharkCaptureParams


def test_defaults_are_valid():
    params = WiresharkCaptureParams()

    assert params.interface == "any"
    assert params.duration_seconds == 60
    assert params.max_file_size_mb == 50
    assert params.resource_cpu_limit == "250m"
    assert params.resource_memory_limit == "128Mi"
    assert params.resource_cpu_request == "50m"
    assert params.resource_memory_request == "64Mi"


@pytest.mark.parametrize("duration", [10, 120])
def test_duration_bounds_are_valid(duration):
    params = WiresharkCaptureParams(duration_seconds=duration)
    assert params.duration_seconds == duration


@pytest.mark.parametrize("duration", [9, 121])
def test_duration_outside_bounds_is_rejected(duration):
    with pytest.raises(ValidationError):
        WiresharkCaptureParams(duration_seconds=duration)


@pytest.mark.parametrize("size", [1, 100])
def test_file_size_bounds_are_valid(size):
    params = WiresharkCaptureParams(max_file_size_mb=size)
    assert params.max_file_size_mb == size


@pytest.mark.parametrize("size", [0, 101])
def test_file_size_outside_bounds_is_rejected(size):
    with pytest.raises(ValidationError):
        WiresharkCaptureParams(max_file_size_mb=size)


def test_invalid_interface_is_rejected():
    with pytest.raises(ValidationError):
        WiresharkCaptureParams(interface="eth0; rm -rf")


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        WiresharkCaptureParams(extra_option="unexpected")
