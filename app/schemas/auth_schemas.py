from pydantic import EmailStr

from app.schemas.common import BaseSchema


class AuthSchema(BaseSchema):
    email: EmailStr
