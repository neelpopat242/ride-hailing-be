from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    def get_by_email(self, email):
        return self.session.query(User).filter_by(email=email).first()

    def create(self, email, name):
        user = User(email=email, name=name)
        self.session.add(user)
        self.session.flush()
        return user
