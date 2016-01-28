import peewee

from ban import db
from postgis import Point

from .resource import BaseResource, ResourceModel
from .versioning import BaseVersioned, Versioned

__all__ = ['Municipality', 'AddressBlock', 'AddressPoint', 'Position']


_ = lambda x: x


class BaseModel(BaseResource, BaseVersioned):
    pass


class Model(ResourceModel, Versioned, metaclass=BaseModel):

    resource_fields = ['version']

    class Meta:
        validate_backrefs = False
        # 'version' is validated by us.
        resource_schema = {'version': {'required': False}}


class NamedModel(Model):
    name = db.CharField(max_length=200)
    alias = db.ArrayField(db.CharField, null=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<{} {} ({})>'.format(self.__class__.__name__, self.name,
                                     self.id)

    class Meta:
        abstract = True
        ordering = ('name', )


class Municipality(NamedModel):
    identifiers = ['siren', 'insee']
    resource_fields = ['name', 'alias', 'insee', 'siren', 'addressblocks']

    insee = db.CharField(max_length=5, unique=True)
    siren = db.CharField(max_length=9, unique=True)


class AddressBlock(NamedModel):
    resource_fields = ['name', 'alias', 'municipality', 'attributes', 'kind']

    KIND = (
        ('street', 'Street'),
        ('locality', 'Locality'),
        ('old_municipality', 'Old Municipality'),
        ('district', 'District'),
        ('postcode', 'Postal Code'),
    )

    kind = db.CharField(max_length=50, choices=KIND, null=False)
    attributes = db.HStoreField(null=True)
    municipality = db.ForeignKeyField(Municipality,
                                      related_name='addressblocks')


class AddressPoint(Model):
    identifiers = ['cia']
    resource_fields = ['number', 'ordinal', 'cia', 'laposte',
                       'secondary_blocks', 'center', 'primary_block']

    number = db.CharField(max_length=16)
    ordinal = db.CharField(max_length=16, null=True)
    primary_block = db.ForeignKeyField(AddressBlock,
                                       related_name='addresspoints')
    secondary_blocks = db.ManyToManyField(AddressBlock)
    cia = db.CharField(max_length=100, null=True)
    laposte = db.CharField(max_length=10, null=True)

    class Meta:
        resource_schema = {'cia': {'required': False},
                           'version': {'required': False}}
        order_by = ('number', 'ordinal')

    def __str__(self):
        return ' '.join([self.number, self.ordinal])

    @property
    def parent(self):
        return self.primary_block

    def save(self, *args, **kwargs):
        if not getattr(self, '_clean_called', False):
            self.clean()
        # self.cia = self.compute_cia()
        super().save(*args, **kwargs)
        self._clean_called = False

    def clean(self):
        qs = AddressPoint.select().where(
            AddressPoint.number == self.number,
            AddressPoint.ordinal == self.ordinal,
            AddressPoint.primary_block == self.primary_block)
        if self.id:
            qs = qs.where(AddressPoint.id != self.id)
        if qs.exists():
            raise ValueError('Row with same number, ordinal and primary_block '
                             'already exists')
        self._clean_called = True

    def compute_cia(self):
        return '_'.join([
            str(self.parent.municipality.insee),
            self.street.get_fantoir() if self.street else '',
            self.locality.get_fantoir() if self.locality else '',
            self.number.upper(),
            self.ordinal.upper()
        ])

    @property
    def center(self):
        position = self.position_set.first()
        return position.center.geojson if position else None

    @property
    def secondary_blocks_resource(self):
        return [d.as_relation for d in self.secondary_blocks]


class Position(Model):
    resource_fields = ['center', 'source', 'addresspoint', 'attributes',
                       'kind', 'comment']

    center = db.PointField(verbose_name=_("center"))
    addresspoint = db.ForeignKeyField(AddressPoint)
    source = db.CharField(max_length=64, null=True)
    kind = db.CharField(max_length=64, null=True)
    attributes = db.HStoreField(null=True)
    comment = peewee.TextField(null=True)

    class Meta:
        unique_together = ('housenumber', 'source')

    @property
    def center_resource(self):
        if not isinstance(self.center, Point):
            self.center = Point(*self.center)
        return self.center.geojson
