import json

import pytest
import falcon
from ban.core import models

from ..factories import (AddressPointFactory, MunicipalityFactory,
                         PositionFactory, AddressBlockFactory)
from .utils import authorize


def test_get_addresspoint(get, url):
    housenumber = AddressPointFactory(number="22")
    resp = get(url('addresspoint-resource', identifier=housenumber.id))
    assert resp.json['number'] == "22"
    assert resp.json['id'] == housenumber.id
    assert resp.json['primary_block']['name'] == housenumber.primary_block.name


def test_get_addresspoint_without_explicit_identifier(get, url):
    housenumber = AddressPointFactory(number="22")
    resp = get(url('addresspoint-resource', identifier=housenumber.id))
    assert resp.json['number'] == "22"
    assert resp.json['id'] == housenumber.id
    assert resp.json['primary_block']['name'] == housenumber.primary_block.name


def test_get_addresspoint_with_unknown_id_is_404(get, url):
    resp = get(url('addresspoint-resource', identifier=22))
    assert resp.status == falcon.HTTP_404


def test_get_addresspoint_with_cia(get, url):
    housenumber = AddressPointFactory(number="22")
    resp = get(url('addresspoint-resource', id=housenumber.cia,
                   identifier="cia"))
    assert resp.json['number'] == "22"


def test_get_addresspoint_with_secondary_blocks(get, url):
    municipality = MunicipalityFactory()
    district = AddressBlockFactory(municipality=municipality, kind="district")
    housenumber = AddressPointFactory(secondary_blocks=[district],
                                      municipality=municipality)
    resp = get(url('addresspoint-resource', identifier=housenumber.id))
    assert resp.status == falcon.HTTP_200
    assert 'secondary_blocks' in resp.json
    assert resp.json['secondary_blocks'][0]['id'] == district.id
    assert resp.json['secondary_blocks'][0]['name'] == district.name
    assert 'version' not in resp.json['secondary_blocks'][0]


def test_get_addresspoint_collection(get, url):
    objs = AddressPointFactory.create_batch(5)
    resp = get(url('addresspoint'))
    assert resp.json['total'] == 5
    for i, obj in enumerate(objs):
        assert resp.json['collection'][i] == obj.as_list


def test_get_addresspoint_collection_can_be_filtered_by_bbox(get, url):
    position = PositionFactory(center=(1, 1))
    PositionFactory(center=(-1, -1))
    bbox = dict(north=2, south=0, west=0, east=2)
    resp = get(url('addresspoint', query_string=bbox))
    assert resp.json['total'] == 1
    # JSON transform internals tuples to lists.
    resource = position.addresspoint.as_list
    resource['center']['coordinates'] = list(resource['center']['coordinates'])  # noqa
    assert resp.json['collection'][0] == resource


def test_missing_bbox_param_makes_bbox_ignored(get, url):
    PositionFactory(center=(1, 1))
    PositionFactory(center=(-1, -1))
    bbox = dict(north=2, south=0, west=0)
    resp = get(url('addresspoint', query_string=bbox))
    assert resp.json['total'] == 2


def test_invalid_bbox_param_returns_bad_request(get, url):
    PositionFactory(center=(1, 1))
    PositionFactory(center=(-1, -1))
    bbox = dict(north=2, south=0, west=0, east='invalid')
    resp = get(url('addresspoint', query_string=bbox))
    assert resp.status == falcon.HTTP_400


def test_get_addresspoint_collection_filtered_by_bbox_is_paginated(get, url):
    PositionFactory.create_batch(9, center=(1, 1))
    params = dict(north=2, south=0, west=0, east=2, limit=5)
    PositionFactory(center=(-1, -1))
    resp = get(url('addresspoint', query_string=params))
    page1 = resp.json
    assert len(page1['collection']) == 5
    assert page1['total'] == 9
    assert 'next' in page1
    assert 'previous' not in page1
    resp = get(page1['next'])
    page2 = resp.json
    assert len(page2['collection']) == 4
    assert page2['total'] == 9
    assert 'next' not in page2
    assert 'previous' in page2
    resp = get(page2['previous'])
    assert resp.json == page1


def test_addresspoint_with_two_positions_is_not_duplicated_in_bbox(get, url):
    position = PositionFactory(center=(1, 1))
    PositionFactory(center=(1.1, 1.1), addresspoint=position.addresspoint)
    bbox = dict(north=2, south=0, west=0, east=2)
    resp = get(url('addresspoint', query_string=bbox))
    assert resp.json['total'] == 1
    # JSON transform internals tuples to lists.
    data = position.addresspoint.as_list
    data['center']['coordinates'] = list(data['center']['coordinates'])
    assert resp.json['collection'][0] == data


def test_get_addresspoint_with_position(get, url):
    housenumber = AddressPointFactory()
    PositionFactory(addresspoint=housenumber, center=(1, 1))
    resp = get(url('addresspoint-resource', identifier=housenumber.id))
    assert resp.json['center'] == {'coordinates': [1, 1], 'type': 'Point'}


def test_get_addresspoint_positions(get, url):
    housenumber = AddressPointFactory()
    pos1 = PositionFactory(addresspoint=housenumber, center=(1, 1))
    pos2 = PositionFactory(addresspoint=housenumber, center=(2, 2))
    pos3 = PositionFactory(addresspoint=housenumber, center=(3, 3))
    resp = get(url('addresspoint-positions', identifier=housenumber.id))
    assert resp.json['total'] == 3

    def check(position):
        data = position.as_list
        # postgis uses tuples for coordinates, while json does not know
        # tuple and transforms everything to lists.
        data['center']['coordinates'] = list(data['center']['coordinates'])
        assert data in resp.json['collection']

    check(pos1)
    check(pos2)
    check(pos3)


@authorize
def test_create_addresspoint(client):
    street = AddressBlockFactory(name="Rue de Bonbons")
    assert not models.AddressPoint.select().count()
    data = {
        "number": 20,
        "primary_block": street.id,
    }
    resp = client.post('/addresspoint', data)
    assert resp.status == falcon.HTTP_201
    assert resp.json['id']
    assert resp.json['number'] == '20'
    assert resp.json['ordinal'] == ''
    assert resp.json['primary_block']['id'] == street.id
    assert models.AddressPoint.select().count() == 1


@pytest.mark.xfail
@authorize
def test_create_addresspoint_with_street_fantoir(client):
    street = AddressBlockFactory(name="Rue de Bonbons")
    assert not models.AddressPoint.select().count()
    data = {
        "number": 20,
        "primary_block": 'fantoir:{}'.format(street.fantoir),
    }
    resp = client.post('/addresspoint', data)
    assert resp.status == falcon.HTTP_201
    assert models.AddressPoint.select().count() == 1


@authorize
def test_create_addresspoint_does_not_honour_version_field(client):
    street = AddressBlockFactory(name="Rue de Bonbons")
    data = {
        "version": 3,
        "number": 20,
        "primary_block": street.id,
    }
    resp = client.post('/addresspoint', data=data)
    assert resp.status == falcon.HTTP_201
    assert resp.json['id']
    assert resp.json['version'] == 1


@authorize
def test_create_addresspoint_with_postcode_id(client):
    postcode = AddressBlockFactory(kind="postcode",
                                   attributes={"code": "12345"})
    street = AddressBlockFactory(name="Rue de Bonbons")
    data = {
        "number": 20,
        "primary_block": street.id,
        "secondary_blocks": [postcode.id]
    }
    headers = {'Content-Type': 'application/json'}
    resp = client.post('/addresspoint', data, headers=headers)
    assert resp.status == falcon.HTTP_201
    assert models.AddressPoint.select().count() == 1
    assert postcode in models.AddressPoint.first().secondary_blocks


@authorize
def test_replace_addresspoint(client, url):
    housenumber = AddressPointFactory(number="22", ordinal="B")
    assert models.AddressPoint.select().count() == 1
    uri = url('addresspoint-resource', identifier=housenumber.id)
    data = {
        "version": 2,
        "number": housenumber.number,
        "ordinal": 'bis',
        "primary_block": housenumber.primary_block.id,
    }
    resp = client.put(uri, body=json.dumps(data))
    assert resp.status == falcon.HTTP_200
    assert resp.json['id']
    assert resp.json['version'] == 2
    assert resp.json['number'] == '22'
    assert resp.json['ordinal'] == 'bis'
    assert resp.json['primary_block']['id'] == housenumber.primary_block.id
    assert models.AddressPoint.select().count() == 1


@authorize
def test_replace_addresspoint_with_missing_field_fails(client, url):
    housenumber = AddressPointFactory(number="22", ordinal="B")
    assert models.AddressPoint.select().count() == 1
    uri = url('addresspoint-resource', identifier=housenumber.id)
    data = {
        "version": 2,
        "ordinal": 'bis',
        "primary_block": housenumber.primary_block.id,
    }
    resp = client.put(uri, body=json.dumps(data))
    assert resp.status == falcon.HTTP_422
    assert 'errors' in resp.json
    assert models.AddressPoint.select().count() == 1


@authorize
def test_patch_addresspoint_with_secondary_blocks(client, url):
    housenumber = AddressPointFactory()
    district = AddressBlockFactory(
        municipality=housenumber.parent.municipality, kind="district")
    postcode = AddressBlockFactory(kind="postcode",
                                   attributes={"code": "12345"})
    data = {
        "version": 2,
        "secondary_blocks": [district.id, postcode.id],
    }
    uri = url('addresspoint-resource', identifier=housenumber.id)
    resp = client.patch(uri, body=json.dumps(data))
    assert resp.status == falcon.HTTP_200
    hn = models.AddressPoint.get(models.AddressPoint.id == housenumber.id)
    assert district in hn.secondary_blocks
    assert postcode in hn.secondary_blocks


@authorize
def test_delete_addresspoint(client, url):
    housenumber = AddressPointFactory()
    uri = url('addresspoint-resource', identifier=housenumber.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_204
    assert not models.AddressPoint.select().count()


def test_cannot_delete_addresspoint_if_not_authorized(client, url):
    housenumber = AddressPointFactory()
    uri = url('addresspoint-resource', identifier=housenumber.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_401
    assert models.AddressPoint.get(models.AddressPoint.id == housenumber.id)


@authorize
def test_cannot_delete_addresspoint_if_linked_to_position(client, url):
    housenumber = AddressPointFactory()
    PositionFactory(addresspoint=housenumber)
    uri = url('addresspoint-resource', identifier=housenumber.id)
    resp = client.delete(uri)
    assert resp.status == falcon.HTTP_409
    assert models.AddressPoint.get(models.AddressPoint.id == housenumber.id)
