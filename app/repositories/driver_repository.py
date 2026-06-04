import uuid
from datetime import UTC, datetime

from app.constants import DriverStatus
from app.models.driver import Driver
from app.repositories.base_repository import BaseRepository


class DriverRepository(BaseRepository):
    def get_by_id(self, driver_id):
        return self.session.get(Driver, uuid.UUID(driver_id))

    def get_by_email(self, email):
        return self.session.query(Driver).filter_by(email=email).first()

    def create_with_email(self, email):
        driver = Driver(email=email, status=DriverStatus.AVAILABLE.value)
        self.session.add(driver)
        self.session.flush()
        return driver

    def update_status(self, driver_id, status):
        driver = self.session.get(Driver, uuid.UUID(driver_id))
        if driver:
            driver.status = status
            driver.updated_at = datetime.now(UTC)
        return driver

    def update_location(self, driver_id, payload):
        driver = self.session.get(Driver, uuid.UUID(driver_id))
        if driver:
            driver.lat = payload.get("lat")
            driver.lng = payload.get("lng")
            driver.location_updated_at = payload.get("updated_at") or datetime.now(UTC)
            self.session.flush()
        return driver

    def find_available_candidates(self):
        return (
            self.session.query(Driver)
            .filter(
                Driver.status == DriverStatus.AVAILABLE.value,
                Driver.lat.isnot(None),
                Driver.lng.isnot(None),
            )
            .all()
        )
