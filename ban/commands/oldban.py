import json

from ban.commands import command, report
from ban.core.models import AddressPoint, AddressBlock, Municipality, Position

from .helpers import batch, iter_file, nodiff, session

__namespace__ = 'import'


@command
@nodiff
def oldban(path, **kwargs):
    """Import from BAN json stream files from
    http://bano.openstreetmap.fr/BAN_odbl/"""
    max_value = sum(1 for line in iter_file(path))
    rows = iter_file(path, formatter=json.loads)
    batch(process_row, rows, chunksize=100, max_value=max_value)


@session
def process_row(metadata):
    name = metadata.get('name')
    id = metadata.get('id')
    insee = metadata.get('citycode')
    fantoir = ''.join(id.split('_')[:2])[:9]

    kind = metadata['type']
    if kind not in ['street', 'locality']:
        return report('Skip bad kind', kind)
    attr = AddressBlock.attributes
    instance = AddressBlock.select().where(
        attr.contains({'fantoir': fantoir}),
        AddressBlock.kind == kind).first()
    if instance:
        return report('Existing AddressBlock',
                      {name: name, fantoir: fantoir},
                      report.WARNING)

    try:
        municipality = Municipality.get(Municipality.insee == insee)
    except Municipality.DoesNotExist:
        return report('Municipality does not exist', insee, report.ERROR)

    data = dict(
        name=name,
        municipality=municipality.id,
        attributes=dict(fantoir=fantoir),
        kind=kind,
        version=1,
    )
    validator = AddressBlock.validator(**data)

    if not validator.errors:
        item = validator.save()
        report(kind, item, report.NOTICE)
        housenumbers = metadata.get('housenumbers')
        if housenumbers:
            for id, metadata in housenumbers.items():
                add_housenumber(item, id, metadata)
    else:
        report('AddressBlock error', validator.errors, report.ERROR)


def add_housenumber(parent, id, metadata):
    number, *ordinal = id.split(' ')
    ordinal = ordinal[0] if ordinal else ''
    center = [metadata['lon'], metadata['lat']]
    data = dict(number=number, ordinal=ordinal, version=1,
                primary_block=parent.id)
    validator = AddressPoint.validator(**data)

    if not validator.errors:
        housenumber = validator.save()
        validator = Position.validator(center=center, version=1,
                                       housenumber=housenumber.id)
        if not validator.errors:
            validator.save()
        report('AddressPoint', housenumber, report.NOTICE)
    else:
        report('AddressPoint error', validator.errors, report.ERROR)
