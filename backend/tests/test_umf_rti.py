"""Unit tests for the UMF-RTI XML builders (pure functions, no cluster)."""

import xml.etree.ElementTree as ET

from app.umf_rti.config import UmfRtiConfig
from app.umf_rti.service import (
    CAPTURE_QOS_PROFILE,
    build_override_xml,
    build_recording_cfg_xml,
)

config = UmfRtiConfig()


# --- override.xml (the Cap::universal QoS profile) ---------------------------


def test_override_xml_is_well_formed():
    ET.fromstring(build_override_xml(config))


def test_override_lists_all_initial_peers():
    xml = build_override_xml(config)
    peers = config.initial_peers()
    assert len(peers) == 4  # router pod + 3 WAN ports
    for peer in peers:
        assert f"<element>{peer}</element>" in xml


def test_override_accepts_unknown_peers():
    assert "<accept_unknown_peers>true</accept_unknown_peers>" in build_override_xml(
        config
    )


def test_override_raises_type_object_limit():
    # MANDATORY: without this the recorder silently drops umfnum/umfwav.
    xml = build_override_xml(config)
    assert (
        f"<type_object_max_serialized_length>{config.type_object_max_serialized_length}"
        f"</type_object_max_serialized_length>"
    ) in xml


def test_override_unbounds_reader_resource_limits():
    # max_samples / max_instances / max_samples_per_instance all unbounded.
    assert build_override_xml(config).count("LENGTH_UNLIMITED") >= 3


# --- rec.xml (the rtirecordingservice config) --------------------------------


def test_recording_cfg_is_well_formed():
    ET.fromstring(build_recording_cfg_xml(13, config))


def test_recording_cfg_uses_json_sqlite():
    assert "<storage_format>JSON_SQLITE</storage_format>" in build_recording_cfg_xml(
        13, config
    )


def test_recording_cfg_substitutes_domain():
    assert "<domain_id>13</domain_id>" in build_recording_cfg_xml(13, config)
    assert "<domain_id>32</domain_id>" in build_recording_cfg_xml(32, config)


def test_recording_cfg_sets_wildcard_partition():
    # MANDATORY: viewpod umfnum/umfwav writers are in a named partition.
    xml = build_recording_cfg_xml(13, config)
    assert f"<element>{config.partition}</element>" in xml
    # Element order is strict: subscriber_qos must precede topic_group.
    assert xml.index("<subscriber_qos>") < xml.index("<topic_group")


def test_recording_cfg_references_capture_profile():
    assert CAPTURE_QOS_PROFILE == "Cap::universal"
    assert f'base_name="{CAPTURE_QOS_PROFILE}"' in build_recording_cfg_xml(13, config)
