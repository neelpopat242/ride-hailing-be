from app.schemas.driver_schemas import DriverAcceptSchema, DriverDeclineSchema, DriverLocationSchema
from app.services.driver_service import DriverService
from app.views.base import ViewSet, route


class DriverViewSet(ViewSet):

    def __init__(self, session):
        super().__init__(session)
        self.driver_service = DriverService(session)

    @route("POST", "/location", schema=DriverLocationSchema, auth=["driver"])
    def update_location(self):
        driver_id = self.actor["user_id"]
        return self.driver_service.update_location(driver_id, self.validated_data)

    @route("POST", "/accept", schema=DriverAcceptSchema, auth=["driver"])
    def accept(self):
        driver_id = self.actor["user_id"]
        return self.driver_service.accept_ride(driver_id, self.validated_data)

    @route("POST", "/decline", schema=DriverDeclineSchema, auth=["driver"])
    def decline(self):
        driver_id = self.actor["user_id"]
        return self.driver_service.decline_ride(driver_id, self.validated_data)
