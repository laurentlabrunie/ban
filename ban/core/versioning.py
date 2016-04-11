from datetime import datetime
import json

import peewee

from ban import db
from ban.auth.models import Client, Session
from ban.core.encoder import dumps

from . import context


class ForcedVersionError(Exception):
    pass


class BaseVersioned(peewee.BaseModel):

    registry = {}

    def __new__(mcs, name, bases, attrs, **kwargs):
        cls = super().__new__(mcs, name, bases, attrs, **kwargs)
        BaseVersioned.registry[name] = cls
        return cls


class Versioned(db.Model, metaclass=BaseVersioned):

    ForcedVersionError = ForcedVersionError

    version = db.IntegerField(default=1)
    created_at = db.DateTimeField()
    created_by = db.ForeignKeyField(Session)
    modified_at = db.DateTimeField()
    modified_by = db.ForeignKeyField(Session)

    class Meta:
        abstract = True
        validate_backrefs = False
        unique_together = ('pk', 'version')

    def prepared(self):
        self.lock_version()
        super().prepared()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prepared()

    def _serialize(self, fields):
        data = {}
        for name, field in fields.items():
            value = getattr(self, field.name)
            value = field.db_value(value)
            data[field.name] = value
        return data

    def serialize(self, fields=None):
        return dumps(self._serialize(self._meta.fields))

    def store_version(self):
        old = None
        if self.version > 1:
            old = self.load_version(self.version - 1)
        new = Version.create(
            model_name=self.__class__.__name__,
            model_pk=self.pk,
            sequential=self.version,
            raw=self.serialize()
        )
        if Diff.ACTIVE:
            Diff.create(old=old, new=new, created_at=self.modified_at)

    @property
    def versions(self):
        return Version.select().where(
            Version.model_name == self.__class__.__name__,
            Version.model_pk == self.pk)

    def load_version(self, id=None):
        if id is None:
            id = self.version
        return self.versions.where(Version.sequential == id).first()

    @property
    def locked_version(self):
        return getattr(self, '_locked_version', None)

    @locked_version.setter
    def locked_version(self, value):
        # Should be set only once, and never updated.
        assert not hasattr(self, '_locked_version'), 'locked_version is read only'  # noqa
        self._locked_version = value

    def lock_version(self):
        if not self.pk:
            self.version = 1
        self._locked_version = self.version if self.pk else 0

    def increment_version(self):
        self.version = self.version + 1

    def check_version(self):
        if self.version != self.locked_version + 1:
            raise ForcedVersionError('wrong version number: {}'.format(self.version))  # noqa

    def update_meta(self):
        session = context.get('session')
        if session:
            try:
                getattr(self, 'created_by', None)
            except Session.DoesNotExist:
                # Field is not nullable, we can't access it when it's not yet
                # defined.
                self.created_by = session
            self.modified_by = session
        now = datetime.now()
        if not self.created_at:
            self.created_at = now
        self.modified_at = now

    def save(self, *args, **kwargs):
        self.check_version()
        self.update_meta()
        super().save(*args, **kwargs)
        self.store_version()
        self.lock_version()


class ResourceQueryResultWrapper(peewee.ModelQueryResultWrapper):

    def process_row(self, row):
        instance = super().process_row(row)
        return instance.as_resource


class SelectQuery(db.SelectQuery):

    @peewee.returns_clone
    def as_resource(self):
        self._result_wrapper = ResourceQueryResultWrapper


class Version(db.Model):
    model_name = db.CharField(max_length=64)
    model_pk = db.IntegerField()
    sequential = db.IntegerField()
    raw = db.BinaryJSONField()

    class Meta:
        manager = SelectQuery

    def __repr__(self):
        return '<Version {} of {}({})>'.format(self.sequential,
                                               self.model_name, self.model_pk)

    @property
    def data(self):
        return json.loads(self.raw)

    @property
    def as_resource(self):
        return {
            "data": self.data,
            "flags": list(self.flags.as_resource())
        }

    @property
    def model(self):
        return BaseVersioned.registry[self.model_name]

    def load(self):
        return self.model(**self.data)

    @property
    def diff(self):
        return Diff.first(Diff.new == self.pk)

    def flag(self):
        """Flag current version with current client."""
        session = context.get('session')
        if not session:
            raise ValueError('Must be logged in.')
        if not session.client:
            raise ValueError('Token must be linked to a client.')
        if not session.client.flag_id:
            raise ValueError('Client must have a valid flag_id.')
        Flag.create(version=self, session=session, client=session.client)

class Diff(db.Model):

    # Allow to skip diff at very first data import.
    ACTIVE = True

    # old is empty at creation.
    old = db.ForeignKeyField(Version, null=True)
    # new is empty after delete.
    new = db.ForeignKeyField(Version, null=True)
    diff = db.BinaryJSONField()
    created_at = db.DateTimeField()

    class Meta:
        validate_backrefs = False
        manager = SelectQuery
        order_by = ('pk', )

    def save(self, *args, **kwargs):
        if not self.diff:
            meta = set(['pk', 'id', 'created_by', 'modified_by', 'created_at',
                        'modified_at', 'version'])
            old = self.old.data if self.old else {}
            new = self.new.data if self.new else {}
            keys = set(list(old.keys()) + list(new.keys())) - meta
            self.diff = {}
            for key in keys:
                old_value = old.get(key)
                new_value = new.get(key)
                if new_value != old_value:
                    self.diff[key] = {
                        'old': str(old_value),
                        'new': str(new_value)
                    }
        super().save(*args, **kwargs)
        IdentifierRedirect.from_diff(self)

    @property
    def as_resource(self):
        version = self.new or self.old
        return {
            'increment': self.pk,
            'old': self.old.data if self.old else None,
            'new': self.new.data if self.new else None,
            'diff': self.diff,
            'resource': version.model_name.lower(),
            'resource_pk': version.model_pk,
            'created_at': self.created_at
        }


class IdentifierRedirect(db.Model):
    model_name = peewee.CharField(max_length=64)
    identifier = peewee.CharField(max_length=64)
    old = peewee.CharField(max_length=255)
    new = peewee.CharField(max_length=255)

    @classmethod
    def from_diff(cls, diff):
        if not diff.new or not diff.old:
            # Only update makes sense for us, no creation nor deletion.
            return
        model = diff.new.model
        identifiers = [i for i in model.identifiers if i in diff.diff]
        for identifier in identifiers:
            old = diff.diff[identifier]['old']
            new = diff.diff[identifier]['new']
            if not old or not new:
                continue
            cls.get_or_create(model_name=diff.new.model_name,
                              identifier=identifier, old=old, new=new)
            cls.refresh(model, identifier, old, new)

    @classmethod
    def follow(cls, model, identifier, old):
        row = cls.select().where(cls.model_name == model.__name__,
                                 cls.identifier == identifier,
                                 cls.old == old).first()
        return row.new if row else None

    @classmethod
    def refresh(cls, model, identifier, old, new):
        """An identifier was a target and it becomes itself a target."""
        cls.update(new=new).where(cls.new == old,
                                  cls.model_name == model.__name__,
                                  cls.identifier == identifier).execute()


class Flag(db.Model):
    version = db.ForeignKeyField(Version, related_name='flags')
    client = db.ForeignKeyField(Client)
    session = db.ForeignKeyField(Session)
    created_at = db.DateTimeField()

    class Meta:
        manager = SelectQuery

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = datetime.now()
        super().save(*args, **kwargs)

    @property
    def as_resource(self):
        return {
            'at': self.created_at,
            'by': self.client.flag_id
        }
