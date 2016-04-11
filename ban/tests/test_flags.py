import pytest

from .factories import GroupFactory


def test_can_flag_current_version(session):
    group = GroupFactory()
    version = group.load_version()
    version.flag()
    assert version.flags.select().count()


def test_can_flag_past_version(session):
    group = GroupFactory()
    group.name = 'Another name'
    group.increment_version()
    group.save()
    version = group.load_version(1)
    version.flag()
    assert version.flags.select().count()
    version = group.load_version(2)
    assert not version.flags.select().count()


def test_cannot_flag_without_session():
    group = GroupFactory()
    with pytest.raises(ValueError):
        group.load_version().flag()

def test_cannot_flag_if_session_has_no_client(session):
    group = GroupFactory()
    session.client = None
    with pytest.raises(ValueError):
        group.load_version().flag()


def test_cannot_flag_if_session_client_has_no_flag_id(session):
    group = GroupFactory()
    session.client.flag_id = None
    with pytest.raises(ValueError):
        group.load_version().flag()


def test_version_flags_attribute_returns_flags(session):
    group = GroupFactory()
    group.load_version().flag()
    version = group.load_version()
    assert version.flags.count()
    flag = version.flags[0]
    assert flag.created_at
