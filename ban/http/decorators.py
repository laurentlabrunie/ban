from functools import wraps

from oauthlib.oauth2 import Server
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.oauth2_backends import OAuthLibCore


def protected(method, scopes=None):
    scopes = scopes or []

    @wraps(method)
    def inner(view, request, *args, **kwargs):
        validator = OAuth2Validator()
        core = OAuthLibCore(Server(validator))
        valid, oauthlib_req = core.verify_request(request, scopes=scopes)
        if valid:
            request.resource_owner = oauthlib_req.user
            return method(view, request, *args, **kwargs)
        return view.error(403, 'Forbidden')

    return inner
