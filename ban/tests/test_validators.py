import pytest

from ban.core import models

from .factories import (AddressBlockFactory, AddressPointFactory,
                        MunicipalityFactory, PositionFactory)


def test_can_create_municipality(session):
    validator = models.Municipality.validator(name="Eu", insee="12345",
                                              siren="12345678")
    assert not validator.errors
    municipality = validator.save()
    assert municipality.name == "Eu"
    assert municipality.insee == "12345"
    assert municipality.siren == "12345678"


def test_can_create_municipality_with_version(session):
    validator = models.Municipality.validator(name="Eu", insee="12345",
                                              siren="12345678", version=1)
    assert not validator.errors
    municipality = validator.save()
    assert municipality.id


def test_create_should_not_consider_bad_versions(session):
    validator = models.Municipality.validator(name="Eu", insee="12345",
                                              siren="12345678", version=10)
    assert not validator.errors
    municipality = validator.save()
    assert municipality.id
    assert municipality.version == 1


def test_cannot_create_municipality_with_missing_fields(session):
    validator = models.Municipality.validator(name="Eu")
    assert validator.errors
    with pytest.raises(validator.ValidationError):
        validator.save()


def test_can_update_municipality(session):
    municipality = MunicipalityFactory(insee="12345")
    validator = models.Municipality.validator(instance=municipality,
                                              name=municipality.name,
                                              siren=municipality.siren,
                                              insee="54321", version=2)
    assert not validator.errors
    municipality = validator.save()
    assert len(models.Municipality.select()) == 1
    assert municipality.insee == "54321"
    assert municipality.version == 2


def test_cannot_update_municipality_without_version(session):
    municipality = MunicipalityFactory(insee="12345")
    validator = models.Municipality.validator(instance=municipality,
                                              update=True,
                                              insee="54321")
    assert 'version' in validator.errors


def test_cannot_duplicate_municipality_insee(session):
    MunicipalityFactory(insee='12345')
    validator = models.Municipality.validator(name='Carbone',
                                              siren='123456789',
                                              insee="12345", version=2)
    assert 'insee' in validator.errors
    assert '12345' in validator.errors['insee']


def test_can_create_municipality_with_alias(session):
    validator = models.Municipality.validator(name="Orvane",
                                              alias=["Moret-sur-Loing"],
                                              insee="12345",
                                              siren="12345678")
    assert not validator.errors
    municipality = validator.save()
    assert 'Moret-sur-Loing' in municipality.alias


def test_can_create_position(session):
    addresspoint = AddressPointFactory()
    validator = models.Position.validator(addresspoint=addresspoint,
                                          center=(1, 2))
    assert not validator.errors
    position = validator.save()
    assert position.center == (1, 2)
    assert position.addresspoint == addresspoint


def test_can_update_position(session):
    position = PositionFactory(center=(1, 2))
    validator = models.Position.validator(instance=position,
                                          addresspoint=position.addresspoint,
                                          center=(3, 4), version=2)
    assert not validator.errors
    position = validator.save()
    assert len(models.Position.select()) == 1
    assert position.center == (3, 4)
    assert position.version == 2


def test_invalid_point_should_raise_an_error(session):
    addresspoint = AddressPointFactory()
    validator = models.Position.validator(addresspoint=addresspoint, center=1)
    assert 'center' in validator.errors


def test_can_create_addressblock(session):
    municipality = MunicipalityFactory(insee="12345")
    validator = models.AddressBlock.validator(name='Rue des Girafes',
                                              kind="street",
                                              municipality=municipality,
                                              attributes={'fantoir': '123456'})
    assert not validator.errors
    street = validator.save()
    assert len(models.AddressBlock.select()) == 1
    assert street.attributes['fantoir'] == "123456"
    assert street.version == 1


def test_can_create_street_with_municipality_insee(session):
    municipality = MunicipalityFactory(insee="12345")
    validator = models.AddressBlock.validator(name='Rue des Girafes',
                                              kind="street",
                                              municipality='insee:12345',
                                              attributes={'fantoir': '123456'})
    assert not validator.errors
    street = validator.save()
    assert len(models.AddressBlock.select()) == 1
    assert street.attributes['fantoir'] == "123456"
    assert street.version == 1
    assert street.municipality == municipality


def test_can_create_street_with_municipality_old_insee(session):
    municipality = MunicipalityFactory(insee="12345")
    # This should create a redirect.
    municipality.insee = '54321'
    municipality.increment_version()
    municipality.save()
    # Call it with old insee.
    validator = models.AddressBlock.validator(name='Rue des Girafes',
                                              kind="street",
                                              municipality='insee:12345')
    assert not validator.errors
    street = validator.save()
    assert len(models.AddressBlock.select()) == 1
    assert street.municipality == municipality


def test_can_create_addresspoint(session):
    street = AddressBlockFactory()
    validator = models.AddressPoint.validator(primary_block=street, number='11')
    assert not validator.errors
    addresspoint = validator.save()
    assert addresspoint.number == '11'


def test_can_create_addresspoint_with_secondary_blocks(session):
    district = AddressBlockFactory(kind="district")
    street = AddressBlockFactory()
    validator = models.AddressPoint.validator(primary_block=street, number='11',
                                              secondary_blocks=[district])
    assert not validator.errors
    addresspoint = validator.save()
    assert district in addresspoint.secondary_blocks


def test_can_create_addresspoint_with_secondary_blocks_ids(session):
    district = AddressBlockFactory(kind="district")
    street = AddressBlockFactory()
    validator = models.AddressPoint.validator(primary_block=street, number='11',
                                              secondary_blocks=[district.id])
    assert not validator.errors
    addresspoint = validator.save()
    assert district in addresspoint.secondary_blocks


def test_can_update_addresspoint_secondary_blocks(session):
    district = AddressBlockFactory(kind="district")
    addresspoint = AddressPointFactory()
    validator = models.AddressPoint.validator(instance=addresspoint,
                                              update=True, version=2,
                                              secondary_blocks=[district])
    assert not validator.errors
    addresspoint = validator.save()
    assert addresspoint.secondary_blocks == [district]
