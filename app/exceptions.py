class APIException(Exception):
    """
    Raise this anywhere in service/repository layer to return a structured error response.
    Flask's error handler catches it and serializes it automatically.

    Usage:
        raise APIException("RIDE_NOT_FOUND", "Ride not found.", 404)
    """

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
