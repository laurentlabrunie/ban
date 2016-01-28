import json

import falcon
import pytest
from ban.core import models

from ..factories import (AddressBlockFactory, AddressPointFactory,
                         MunicipalityFactory)
from .utils import authorize


def test_get_addressblock(get, url):
    street = AddressBlockFactory(name="Rue des Boulets")
    resp = get(url('addressblock-resource', id=street.id, identifier="id"))
    assert resp.json['name'] == "Rue des Boulets"


def test_get_addressblock_without_explicit_identifier(get, url):
    street = AddressBlockFactory(name="Rue des Boulets")
    resp = get(url('addressblock-resource', identifier=street.id))
    assert resp.json['name'] == "Rue des Boulets"


@pytest.mark.xfail
def test_get_addressblock_with_fantoir(get, url):
    street = AddressBlockFactory(name="Rue des Boulets")
    resp = get(url('addressblock-resource', id=street.fantoir, identifier="fantoir"))
    assert resp.json['name'] == "Rue des Boulets"


@pytest.mark.xfail
def test_get_addressblock_addresspoints(get, url):
    street = AddressBlockFactory()
    hn1 = AddressPointFactory(number="1", primary_block=street)
    hn2 = AddressPointFactory(number="2", primary_block=street)
    hn3 = AddressPointFactory(number="3", primary_block=street)
    resp = get(url('addressblock-addresspoints', identifier=street.id))
    assert resp.json['total'] == 3
    assert resp.json['collection'][0] == hn1.as_list
    assert resp.json['collection'][1] == hn2.as_list
    assert resp.json['collection'][2] == hn3.as_list


@authorize
def test_create_addressblock(client, url):
    municipality = MunicipalityFactory(name="Cabour")
    assert not models.AddressBlock.select().count()
    data = {
        "name": "Rue de la Plage",
        "municipality": municipality.id,
        "kind": "street",
    }
    resp = client.post('/addressblock', data)
    assert resp.status == falcon.HTTP_201
    assert resp.json['id']
    assert resp.json['name'] == 'Rue de la Plage'
    assert resp.json['municipality']['id'] == municipality.id
    assert models.AddressBlock.select().count() == 1
    uri = "https://falconframework.org{}".format(url('addressblock-resource',
                                                 identifier=resp.json['id']))
    assert resp.headers['Location'] == uri


@authorize
def test_create_addressblock_with_attributes(client, url):
    assert not models.AddressBlock.select().count()
    municipality = MunicipalityFactory()
    data = {
        "name": "Rue du Train",
        "attributes": {"key": "value"},
        "municipality": municipality.id,
        "kind": "street"
    }
    # As attributes is a dict, we need to send form as json.
    headers = {'Content-Type': 'application/json'}
    resp = client.post(url('addressblock'), data, headers=headers)
    assert resp.status == falcon.HTTP_201
    assert resp.json['id']
    assert resp.json['name'] == 'Rue du Train'
    assert resp.json['attributes'] == {"key": "value"}
    assert models.AddressBlock.select().count() == 1
    uri = "https://falconframework.org{}".format(url('addressblock-resource',
                                                 identifier=resp.json['id']))
    assert resp.headers['Location'] == uri


@authorize
def test_create_addressblock_with_json_string_as_attribute(client, url):
    assert not models.AddressBlock.select().count()
    municipality = MunicipalityFactory()
    data = {
        "name": "Rue de la Route",
        "attributes": json.dumps({"key": "value"}),
        "municipality": municipality.id,
        "kind": "street"
    }
    resp = client.post(url('addressblock'), data)
    assert resp.status == falcon.HTTP_201
    assert resp.json['attributes'] == {"key": "value"}


@authorize
def test_cannot_create_addressblock_without_kind(client, url):
    assert not models.AddressBlock.select().count()
    municipality = MunicipalityFactory()
    data = {
        "name": "Rue de la Route",
        "municipality": municipality.id,
    }
    resp = client.post(url('addressblock'), data)
    assert resp.status == falcon.HTTP_422
    assert "kind" in resp.json['errors']


@authorize
def test_create_addressblock_with_municipality_insee(client, url):
    municipality = MunicipalityFactory(name="Cabour")
    assert not models.AddressBlock.select().count()
    data = {
        "name": "Rue de la Plage",
        "municipality": "insee:{}".format(municipality.insee),
        "kind": "street",
    }
    resp = client.post('/addressblock', data)
    assert resp.status == falcon.HTTP_201
    assert models.AddressBlock.select().count() == 1
    uri = "https://falconframework.org{}".format(url('addressblock-resource',
                                                 identifier=resp.json['id']))
    assert resp.headers['Location'] == uri


@authorize
def test_create_addressblock_with_municipality_siren(client):
    municipality = MunicipalityFactory(name="Cabour")
    assert not models.AddressBlock.select().count()
    data = {
        "name": "Rue de la Plage",
        "municipality": "siren:{}".format(municipality.siren),
        "kind": "street",
    }
    resp = client.post('/addressblock', data)
    assert resp.status == falcon.HTTP_201
    assert models.AddressBlock.select().count() == 1


@authorize
def test_create_addressblock_with_bad_municipality_siren(client):
    MunicipalityFactory(name="Cabour")
    assert not models.AddressBlock.select().count()
    data = {
        "name": "Rue de la Plage",
        "municipality": "siren:{}".format('bad'),
        "kind": "street",
    }
    resp = client.post('/addressblock', data)
    assert resp.status == falcon.HTTP_422
    assert not models.AddressBlock.select().count()


@authorize
def test_create_addressblock_with_invalid_municipality_identifier(client):
    municipality = MunicipalityFactory(name="Cabour")
    assert not models.AddressBlock.select().count()
    data = {
        "name": "Rue de la Plage",
        "municipality": "invalid:{}".format(municipality.insee),
        "kind": "street",
    }
    resp = client.post('/addressblock', data)
    assert resp.status == falcon.HTTP_422
    assert not models.AddressBlock.select().count()


def test_get_addressblock_versions(get, url):
    street = AddressBlockFactory(name="Rue de la Paix")
    street.version = 2
    street.name = "Rue de la Guerre"
    street.save()
    uri = url('addressblock-versions', identifier=street.id)
    resp = get(uri)
    assert resp.status == falcon.HTTP_200
    assert len(resp.json['collection']) == 2
    assert resp.json['total'] == 2
    assert resp.json['collection'][0]['name'] == 'Rue de la Paix'
    assert resp.json['collection'][1]['name'] == 'Rue de la Guerre'


def test_get_addressblock_version(get, url):
    street = AddressBlockFactory(name="Rue de la Paix")
    street.version = 2
    street.name = "Rue de la Guerre"
    street.save()
    uri = url('addressblock-version', identifier=street.id, version=1)
    resp = get(uri)
    assert resp.status == falcon.HTTP_200
    assert resp.json['name'] == 'Rue de la Paix'
    assert resp.json['version'] == 1
    uri = url('addressblock-version', identifier=street.id, version=2)
    resp = get(uri)
    assert resp.status == falcon.HTTP_200
    assert resp.json['name'] == 'Rue de la Guerre'
    assert resp.json['version'] == 2


def test_get_addressblock_unknown_version_should_go_in_404(get, url):
    street = AddressBlockFactory(name="Rue de la Paix")
    uri = url('addressblock-version', identifier=street.id, version=2)
    resp = get(uri)
    assert resp.status == falcon.HTTP_404


@authorize
def test_delete_addressblock(client, url):
    street = AddressBlockFactory()
    uri = url('addressblock-resource', identifier=street.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_204
    assert not models.AddressBlock.select().count()


def test_cannot_delete_addressblock_if_not_authorized(client, url):
    street = AddressBlockFactory()
    uri = url('addressblock-resource', identifier=street.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_401
    assert models.AddressBlock.get(models.AddressBlock.id == street.id)


@authorize
def test_cannot_delete_addressblock_if_linked_to_addresspoint(client, url):
    street = AddressBlockFactory()
    AddressPointFactory(primary_block=street)
    uri = url('addressblock-resource', identifier=street.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_409
    assert models.AddressBlock.get(models.AddressBlock.id == street.id)
