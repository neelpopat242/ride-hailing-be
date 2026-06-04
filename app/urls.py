from flask import Blueprint

from app.views.auth_views import AuthViewSet
from app.views.driver_views import DriverViewSet
from app.views.payment_views import PaymentViewSet
from app.views.ride_views import RideViewSet
from app.views.trip_views import TripViewSet


def register_blueprints(app):
    api = Blueprint("api", __name__)

    AuthViewSet.register(api, prefix="/v1/auth")
    RideViewSet.register(api, prefix="/v1/rides")
    DriverViewSet.register(api, prefix="/v1/drivers")
    TripViewSet.register(api, prefix="/v1/trips")
    PaymentViewSet.register(api, prefix="/v1/payments")

    app.register_blueprint(api)
