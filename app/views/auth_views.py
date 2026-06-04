from app.schemas.auth_schemas import AuthSchema
from app.services.auth_service import AuthService
from app.views.base import ViewSet, route


class AuthViewSet(ViewSet):

    def __init__(self, session):
        super().__init__(session)
        self.auth_service = AuthService(session)

    @route("POST", "/rider", schema=AuthSchema)
    def rider_auth(self):
        return self.auth_service.rider_auth(self.validated_data)

    @route("POST", "/driver", schema=AuthSchema)
    def driver_auth(self):
        return self.auth_service.driver_auth(self.validated_data)
