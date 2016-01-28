import peewee
import pytest

from ban.core import models

from .factories import (AddressBlockFactory, AddressPointFactory,
                        MunicipalityFactory, PositionFactory)


def test_municipality_is_created_with_version_1():
    municipality = MunicipalityFactory()
    assert municipality.version == 1


def test_municipality_is_versioned():
    municipality = MunicipalityFactory(name="Moret-sur-Loing")
    assert len(municipality.versions) == 1
    assert municipality.version == 1
    municipality.name = "Orvanne"
    municipality.increment_version()
    municipality.save()
    assert municipality.version == 2
    assert len(municipality.versions) == 2
    version1 = municipality.versions[0].load()
    version2 = municipality.versions[1].load()
    assert version1.name == "Moret-sur-Loing"
    assert version2.name == "Orvanne"
    assert municipality.versions[0].diff
    diff = municipality.versions[1].diff
    assert len(diff.diff) == 1  # name, version
    assert diff.diff['name']['new'] == "Orvanne"
    municipality.insee = "77316"
    municipality.increment_version()
    municipality.save()
    assert len(municipality.versions) == 3
    diff = municipality.versions[2].diff
    assert diff.old == municipality.versions[1]
    assert diff.new == municipality.versions[2]


def test_municipality_diff_contain_only_changed_data():
    municipality = MunicipalityFactory(name="Moret-sur-Loing", insee="77316")
    municipality.name = "Orvanne"
    # "Changed" with same value.
    municipality.insee = "77316"
    municipality.increment_version()
    municipality.save()
    diff = municipality.versions[1].diff
    assert len(diff.diff) == 1  # name, version
    assert 'insee' not in diff.diff
    assert diff.diff['name']['new'] == "Orvanne"


def test_municipality_as_resource():
    municipality = MunicipalityFactory(name="Montbrun-Bocage", insee="31365",
                                       siren="210100566")
    block = AddressBlockFactory(name="Paris 10e", attributes={"code": "75010"},
                                municipality=municipality)
    assert municipality.as_resource['name'] == "Montbrun-Bocage"
    assert municipality.as_resource['insee'] == "31365"
    assert municipality.as_resource['siren'] == "210100566"
    assert municipality.as_resource['version'] == 1
    assert municipality.as_resource['id'] == municipality.id
    assert municipality.as_resource['addressblocks'] == [block.as_relation]


def test_municipality_as_relation():
    municipality = MunicipalityFactory(name="Montbrun-Bocage", insee="31365",
                                       siren="210100566")
    AddressBlockFactory(name="Paris 10e", attributes={"code": "75010"},
                        municipality=municipality)
    assert municipality.as_relation['name'] == "Montbrun-Bocage"
    assert municipality.as_relation['insee'] == "31365"
    assert municipality.as_relation['siren'] == "210100566"
    assert municipality.as_relation['id'] == municipality.id
    assert 'addressblocks' not in municipality.as_relation
    assert 'version' not in municipality.as_relation


def test_municipality_str():
    municipality = MunicipalityFactory(name="Salsein")
    assert str(municipality) == 'Salsein'


@pytest.mark.parametrize('factory,kwargs', [
    (MunicipalityFactory, {'insee': '12345'}),
    (MunicipalityFactory, {'siren': '123456789'}),
])
def test_unique_fields(factory, kwargs):
    factory(**kwargs)
    with pytest.raises(peewee.IntegrityError):
        factory(**kwargs)


def test_should_allow_deleting_municipality_not_linked():
    municipality = MunicipalityFactory()
    municipality.delete_instance()
    assert not models.Municipality.select().count()


def test_should_not_allow_deleting_municipality_linked_to_addressblock():
    municipality = MunicipalityFactory()
    AddressBlockFactory(municipality=municipality)
    with pytest.raises(peewee.IntegrityError):
        municipality.delete_instance()
    assert models.Municipality.get(models.Municipality.id == municipality.id)


def test_addressblock_is_versioned():
    initial_name = "Rue des Pommes"
    street = AddressBlockFactory(name=initial_name, kind="street")
    assert street.version == 1
    street.name = "Rue des Poires"
    street.increment_version()
    street.save()
    assert street.version == 2
    assert len(street.versions) == 2
    version1 = street.versions[0].load()
    version2 = street.versions[1].load()
    assert version1.name == "Rue des Pommes"
    assert version2.name == "Rue des Poires"
    assert street.versions[0].diff
    diff = street.versions[1].diff
    assert len(diff.diff) == 1  # name, version
    assert diff.diff['name']['new'] == "Rue des Poires"


def test_should_allow_deleting_addressblock_not_linked():
    street = AddressBlockFactory()
    street.delete_instance()
    assert not models.AddressBlock.select().count()


def test_should_not_allow_deleting_addressblock_linked_to_housenumber():
    street = AddressBlockFactory()
    AddressPointFactory(primary_block=street)
    with pytest.raises(peewee.IntegrityError):
        street.delete_instance()
    assert models.AddressBlock.get(models.AddressBlock.id == street.id)


def test_addresspoint_is_versioned():
    street = AddressBlockFactory()
    hn = AddressPointFactory(primary_block=street, ordinal="b")
    assert hn.version == 1
    hn.ordinal = "bis"
    hn.increment_version()
    hn.save()
    assert hn.version == 2
    assert len(hn.versions) == 2
    version1 = hn.versions[0].load()
    version2 = hn.versions[1].load()
    assert version1.ordinal == "b"
    assert version2.ordinal == "bis"
    assert version2.primary_block == street


def test_cannot_duplicate_addresspoint_on_same_addressblock():
    street = AddressBlockFactory()
    AddressPointFactory(primary_block=street, ordinal="b", number="10")
    with pytest.raises(ValueError):
        AddressPointFactory(primary_block=street, ordinal="b", number="10")


def test_addresspoint_str():
    hn = AddressPointFactory(ordinal="b", number="10")
    assert str(hn) == '10 b'


def test_can_create_two_addresspoints_with_same_number_but_different_blocks():
    street = AddressBlockFactory()
    street2 = AddressBlockFactory()
    AddressPointFactory(street=street, ordinal="b", number="10")
    AddressPointFactory(street=street2, ordinal="b", number="10")


def test_addresspoint_center():
    addresspoint = AddressPointFactory()
    position = PositionFactory(addresspoint=addresspoint)
    assert addresspoint.center == position.center_resource


def test_addresspoint_center_without_position():
    addresspoint = AddressPointFactory()
    assert addresspoint.center is None


def test_create_addresspoint_with_secondary_block():
    municipality = MunicipalityFactory()
    district = AddressBlockFactory(municipality=municipality)
    addresspoint = AddressPointFactory(
        secondary_blocks=[district],
        primary_block__municipality=municipality)
    assert district in addresspoint.secondary_blocks
    assert addresspoint in district.addresspoints


def test_add_secondary_block_to_addresspoint():
    addresspoint = AddressPointFactory()
    district = AddressBlockFactory(
                municipality=addresspoint.primary_block.municipality)
    addresspoint.secondary_blocks.add(district)
    assert district in addresspoint.secondary_blocks
    assert addresspoint in district.addresspoints


def test_should_allow_deleting_addresspoint_not_linked():
    addresspoint = AddressPointFactory()
    addresspoint.delete_instance()
    assert not models.AddressPoint.select().count()


def test_should_not_allow_deleting_addresspoint_if_linked():
    addresspoint = AddressPointFactory()
    PositionFactory(addresspoint=addresspoint)
    with pytest.raises(peewee.IntegrityError):
        addresspoint.delete_instance()
    assert models.AddressPoint.get(models.AddressPoint.id == addresspoint.id)


def test_position_is_versioned():
    addresspoint = AddressPointFactory()
    position = PositionFactory(addresspoint=addresspoint, center=(1, 2))
    assert position.version == 1
    position.center = (3, 4)
    position.increment_version()
    position.save()
    assert position.version == 2
    assert len(position.versions) == 2
    version1 = position.versions[0].load()
    version2 = position.versions[1].load()
    assert version1.center == [1, 2]  # json only knows about lists.
    assert version2.center == [3, 4]
    assert version2.addresspoint == addresspoint


def test_position_attributes():
    position = PositionFactory(attributes={'foo': 'bar'})
    assert position.attributes['foo'] == 'bar'
    assert models.Position.select().where(models.Position.attributes.contains({'foo': 'bar'})).exists()  # noqa


def test_get_instantiate_object_properly():
    original = PositionFactory()
    loaded = models.Position.get(models.Position.id == original.id)
    assert loaded.id == original.id
    assert loaded.version == original.version
    assert loaded.center == original.center
    assert loaded.addresspoint == original.addresspoint


@pytest.mark.parametrize('given,expected', [
    ((1, 2), (1, 2)),
    ((1.123456789, 2.987654321), (1.123456789, 2.987654321)),
    ([1, 2], (1, 2)),
    ("(1, 2)", (1, 2)),
])
def test_position_center_coerce(given, expected):
    position = PositionFactory(center=given)
    center = models.Position.get(models.Position.id == position.id).center
    assert center.coords == expected
