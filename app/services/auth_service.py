from app.auth.jwt_auth import JWTAuth
from app.repositories.driver_repository import DriverRepository
from app.repositories.user_repository import UserRepository
from app.utils.responses import success_response


class AuthService:
    def __init__(self, session):
        self.user_repo = UserRepository(session)
        self.driver_repo = DriverRepository(session)
        self.jwt_auth = JWTAuth()

    def rider_auth(self, payload):
        email = payload.get("email")
        user = self.user_repo.get_by_email(email)
        if not user:
            user = self.user_repo.create(email=email, name=email.split("@")[0])
        token = self.jwt_auth.generate_token(str(user.id), "rider")
        return success_response({"token": token, "id": str(user.id), "role": "rider"})

    def driver_auth(self, payload):
        email = payload.get("email")
        driver = self.driver_repo.get_by_email(email)
        if not driver:
            driver = self.driver_repo.create_with_email(email)
        token = self.jwt_auth.generate_token(str(driver.id), "driver")
        return success_response({"token": token, "id": str(driver.id), "role": "driver"})
