from app.schemas.trip_schemas import TripEndSchema
from app.services.trip_service import TripService
from app.views.base import ViewSet, route


class TripViewSet(ViewSet):

    def __init__(self, session):
        super().__init__(session)
        self.trip_service = TripService(session)

    @route("POST", "/<string:trip_id>/start", auth=["driver"])
    def start(self, trip_id: str):
        return self.trip_service.start_trip(trip_id)

    @route("POST", "/<string:trip_id>/end", schema=TripEndSchema, auth=["driver"])
    def end(self, trip_id: str):
        return self.trip_service.end_trip(trip_id, self.validated_data)
