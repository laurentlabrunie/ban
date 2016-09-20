from datetime import timezone
from io import StringIO
from urllib.parse import urlencode

import peewee
from dateutil.parser import parse as parse_date
from werkzeug.exceptions import HTTPException
from flask import request, url_for, Response
from werkzeug.routing import BaseConverter, ValidationError

from ban.auth import models as amodels
from ban.commands.bal import bal
from ban.core import models, versioning, context
from ban.core.encoder import dumps
from ban.http.auth import auth
from ban.http.wsgi import app


def abort(code, **kwargs):
    response = Response(status=code, mimetype='application/json',
                        response=dumps(kwargs))
    raise HTTPException(description=dumps(kwargs), response=response)


def get_bbox(args):
    bbox = {}
    params = ['north', 'south', 'east', 'west']
    for param in params:
        try:
            bbox[param] = float(args.get(param))
        except ValueError:
            abort(400, 'Invalid value for {}: {}'.format(param,
                                                         args.get(param)))
        except TypeError:
            # None (param not set).
            continue
    if not len(bbox) == 4:
        return None
    return bbox


class DateTimeConverter(BaseConverter):

    def to_python(self, value):
        try:
            value = parse_date(value)
        except ValueError:
            raise ValidationError
        # Be smart, imply that naive dt are in the same tz the API
        # exposes, which is UTC.
        if not value.tzinfo:
            value = value.replace(tzinfo=timezone.utc)
        return value


app.url_map.converters['datetime'] = DateTimeConverter


class CollectionMixin:

    filters = []
    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    def get_limit(self):
        return min(int(request.args.get('limit', self.DEFAULT_LIMIT)),
                   self.MAX_LIMIT)

    def get_offset(self):
        try:
            return int(request.args.get('offset'))
        except (ValueError, TypeError):
            return 0

    def collection(self, queryset):
        limit = self.get_limit()
        offset = self.get_offset()
        end = offset + limit
        count = len(queryset)
        data = {
            'collection': list(queryset[offset:end]),
            'total': count,
        }
        headers = {}
        url = request.base_url
        if count > end:
            query_string = request.args.copy()
            query_string['offset'] = end
            uri = '{}?{}'.format(url, urlencode(sorted(query_string.items())))
            data['next'] = uri
            # resp.add_link(uri, 'next')
        if offset >= limit:
            query_string = request.args.copy()
            query_string['offset'] = offset - limit
            uri = '{}?{}'.format(url, urlencode(sorted(query_string.items())))
            data['previous'] = uri
            # resp.add_link(uri, 'previous')
        return data, 200, headers


class ModelEndpoint(CollectionMixin):
    endpoints = {}
    order_by = None

    def get_object(self, identifier):
        try:
            instance = self.model.coerce(identifier)
        except self.model.DoesNotExist:
            # TODO Flask changes the 404 message, which we don't want.
            abort(404)
        return instance

    def save_object(self, instance=None, update=False):
        validator = self.model.validator(update=update, instance=instance,
                                         **request.json)
        if validator.errors:
            abort(422, errors=validator.errors)
        try:
            instance = validator.save()
        except models.Model.ForcedVersionError as e:
            abort(409, str(e))
        return instance

    def get_queryset(self):
        qs = self.model.select()
        for key in self.filters:
            values = request.args.getlist(key)
            if values:
                func = 'filter_{}'.format(key)
                if hasattr(self, func):
                    qs = getattr(self, func)(qs)
                    continue
                field = getattr(self.model, key)
                try:
                    values = list(map(field.coerce, values))
                except ValueError:
                    abort('400', 'Invalid value for filter {}'.format(key))
                except peewee.DoesNotExist:
                    # Return an empty collection as the fk is not found.
                    return None
                qs = qs.where(field << values)
        return qs

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('', methods=['GET'])
    def get_collection(self):
        qs = self.get_queryset()
        if qs is None:
            return self.collection([])
        if not isinstance(qs, list):
            order_by = (self.order_by if self.order_by is not None
                        else [self.model.pk])
            qs = qs.order_by(*order_by).as_resource_list()
        return self.collection(qs)

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>', methods=['GET'])
    def get_resource(self, identifier):
        instance = self.get_object(identifier)
        return instance.as_resource

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>', methods=['POST'])
    def post_resource(self, identifier):
        instance = self.get_object(identifier)
        instance = self.save_object(instance, update=True)
        return instance.as_resource()

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('', methods=['POST'])
    def post(self):
        instance = self.save_object()
        endpoint = '{}-get-resource'.format(self.__class__.__name__.lower())
        headers = {'Location': url_for(endpoint, identifier=instance.id)}
        return instance.as_resource, 201, headers

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>', methods=['PATCH'])
    def patch(self, identifier):
        instance = self.get_object(identifier)
        instance = self.save_object(instance, update=True)
        return instance.as_resource

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>', methods=['PUT'])
    def put(self, identifier):
        instance = self.get_object(identifier)
        instance = self.save_object(instance)
        return instance.as_resource

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>', methods=['DELETE'])
    def delete(self, identifier):
        instance = self.get_object(identifier)
        try:
            instance.delete_instance()
        except peewee.IntegrityError:
            # This model was still pointed by a FK.
            abort(409)
        return {'resource_id': identifier}


class VersionedModelEnpoint(ModelEndpoint):
    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>/versions', methods=['GET'])
    def get_versions(self, identifier):
        instance = self.get_object(identifier)
        return self.collection(instance.versions.as_resource())

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>/versions/<datetime:ref>', methods=['GET'])
    @app.endpoint('/<identifier>/versions/<int:ref>', methods=['GET'])
    def get_version(self, identifier, ref):
        instance = self.get_object(identifier)
        version = instance.load_version(ref)
        if not version:
            abort(404)
        return version.as_resource

    @auth.require_oauth()
    @app.jsonify
    @app.endpoint('/<identifier>/versions/<int:ref>', methods=['POST'])
    @app.endpoint('/<identifier>/versions/<datetime:ref>', methods=['POST'])
    def post_version(self, identifier, ref):
        instance = self.get_object(identifier)
        version = instance.load_version(ref)
        if not version:
            abort(404)
        flag = request.json.get('flag')
        if flag is True:
            version.flag()
        elif flag is False:
            version.unflag()
        else:
            abort(400, message='Body should contain a "flag" boolean key')


@app.resource
class Municipality(VersionedModelEnpoint):
    endpoint = '/municipality'
    model = models.Municipality
    order_by = [model.insee]


@app.resource
class PostCode(VersionedModelEnpoint):
    endpoint = '/postcode'
    model = models.PostCode
    order_by = [model.code, model.municipality]
    filters = ['code', 'municipality']


@app.resource
class Group(VersionedModelEnpoint):
    endpoint = '/group'
    model = models.Group
    filters = ['municipality']


@app.resource
class HouseNumber(VersionedModelEnpoint):
    endpoint = '/housenumber'
    model = models.HouseNumber
    filters = ['parent', 'postcode', 'ancestors', 'group']
    order_by = [peewee.SQL('number ASC NULLS FIRST'),
                peewee.SQL('ordinal ASC NULLS FIRST')]

    def filter_ancestors_and_group(self, qs):
        # ancestors is a m2m so we cannot use the basic filtering
        # from self.filters.
        ancestors = request.args.getlist('ancestors')
        group = request.args.getlist('group')  # Means parent + ancestors.
        values = group or ancestors
        values = list(map(self.model.ancestors.coerce, values))
        parent_qs = qs.where(self.model.parent << values) if group else None
        if values:
            m2m = self.model.ancestors.get_through_model()
            qs = (qs.join(m2m, on=(m2m.housenumber == self.model.pk))
                    .where(m2m.group << values))
            if parent_qs:
                qs = (parent_qs | qs)
            # We evaluate the qs ourselves here, because it's a CompoundSelect
            # that does not know about our SelectQuery custom methods (like
            # `as_resource_list`), and CompoundSelect is hardcoded in peewee
            # SelectQuery, and we'd need to copy-paste code to be able to use
            # a custom CompoundQuery class instead.
            qs = [h.as_relation for h in qs.order_by(*self.order_by)]
        return qs

    def filter_ancestors(self, qs):
        return self.filter_ancestors_and_group(qs)

    def filter_group(self, qs):
        return self.filter_ancestors_and_group(qs)

    def get_queryset(self):
        qs = super().get_queryset()
        bbox = get_bbox(request.args)
        if bbox:
            qs = (qs.join(models.Position)
                    .where(models.Position.center.in_bbox(**bbox))
                    .group_by(models.HouseNumber.pk)
                    .order_by(models.HouseNumber.pk))
        return qs


@app.resource
class Position(VersionedModelEnpoint):
    endpoint = '/position'
    model = models.Position
    filters = ['kind', 'housenumber']

    def get_queryset(self):
        qs = super().get_queryset()
        bbox = get_bbox(request.args)
        if bbox:
            qs = qs.where(models.Position.center.in_bbox(**bbox))
        return qs


@app.resource
class User(ModelEndpoint):
    endpoint = '/user'
    model = amodels.User


@app.route('/import/bal/')
class Bal:

    @auth.require_oauth()
    def post(self):
        """Import file at BAL format."""
        data = request.files['data']
        bal(StringIO(data.read().decode('utf-8-sig')))
        reporter = context.get('reporter')
        return {'report': reporter}


@app.route('/diff/')
class Diff(CollectionMixin):

    @auth.require_oauth()
    def get(self):
        """Get database diffs.

        Query parameters:
        increment   the minimal increment value to retrieve
        """
        qs = versioning.Diff.select()
        try:
            increment = int(request.args.get('increment'))
        except ValueError:
            abort(400, 'Invalid value for increment')
        except TypeError:
            pass
        else:
            qs = qs.where(versioning.Diff.pk > increment)
        return self.collection(qs.as_resource())