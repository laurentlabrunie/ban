from . import factories


def test_user_can_be_instanciated():
    user = factories.UserFactory()
    assert user.username


def test_client_can_be_instanciated():
    client = factories.ClientFactory()
    assert client.client_id
    assert client.client_secret


def test_token_can_be_instanciated():
    token = factories.TokenFactory()
    assert token.session
    assert token.user
    assert token.access_token


def test_municipality_can_be_instanciated():
    municipality = factories.MunicipalityFactory()
    assert municipality.name


def test_addressblock_can_be_instanciated():
    street = factories.AddressBlockFactory()
    assert street.name


def test_addresspoint_can_be_instanciated():
    hn = factories.AddressPointFactory()
    assert hn.number


def test_position_can_be_instanciated():
    position = factories.PositionFactory()
    assert position.center
