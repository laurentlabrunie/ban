from ban.core import models

from .factories import AddressBlockFactory, MunicipalityFactory


def test_municipality_as_resource():
    municipality = MunicipalityFactory()
    assert list(models.Municipality.select().as_resource()) == [municipality.as_resource]  # noqa


def test_addressblock_as_resource():
    street = AddressBlockFactory()
    assert list(models.AddressBlock.select().as_resource()) == [street.as_resource]


def test_municipality_street_as_resource():
    municipality = MunicipalityFactory()
    street = AddressBlockFactory(municipality=municipality)
    assert list(municipality.addressblocks.as_resource()) == [street.as_resource]
