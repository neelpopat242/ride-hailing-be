from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import APIException
from app.utils.responses import error_response


def register_error_handlers(app):
    @app.errorhandler(APIException)
    def handle_api_exception(exc: APIException):
        return error_response(exc.code, exc.message, exc.status_code)

    @app.errorhandler(ValueError)
    def handle_value_error(_exc):
        return error_response("INVALID_ID", "One or more IDs are not valid UUIDs.", 400)

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(_exc):
        return error_response("DATABASE_ERROR", "Database operation failed.", 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        if getattr(exc, "code", None):
            return exc
        return error_response("INTERNAL_SERVER_ERROR", "Unexpected server error.", 500)
