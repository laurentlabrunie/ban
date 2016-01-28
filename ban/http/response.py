from ban.core.encoder import dumps
from falcon.response import Response as BaseResponse


class Response(BaseResponse):

    def json(self, **kwargs):
        self.body = dumps(kwargs)
