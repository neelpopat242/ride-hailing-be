from app.schemas.ride_schemas import RideCreateSchema
from app.services.ride_service import RideService
from app.views.base import ViewSet, route


class RideViewSet(ViewSet):

    def __init__(self, session):
        super().__init__(session)
        self.ride_service = RideService(session)

    @route("POST", "", schema=RideCreateSchema, auth=["rider"])
    def create(self):
        return self.ride_service.create_ride(self.validated_data, self.actor.get("user_id"))

    @route("GET", "/<string:ride_id>", auth=["rider", "driver"])
    def retrieve(self, ride_id: str):
        return self.ride_service.get_ride(ride_id)

    @route("GET", "/<string:ride_id>/location", auth=["rider"])
    def get_location(self, ride_id: str):
        """
        Returns the current driver location for an active ride.
        Client polls this every 5 seconds to track the driver.
        """
        return self.ride_service.get_driver_location(ride_id)
