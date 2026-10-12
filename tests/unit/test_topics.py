import pytest

from grideye_shared.mqtt import TOPICS, service_status_topic


def test_topics_are_namespaced_and_unique() -> None:
    values = list(TOPICS.__dict__.values())
    assert all(topic.startswith("grideye/") for topic in values)
    assert len(values) == len(set(values))


def test_service_topic_rejects_wildcards() -> None:
    assert service_status_topic("backend") == "grideye/system/services/backend/status"
    with pytest.raises(ValueError):
        service_status_topic("bad/child")
