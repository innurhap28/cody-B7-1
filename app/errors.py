"""Public application failures; response rendering belongs to app.main."""
from dataclasses import dataclass


@dataclass(eq=False)
class APIError(Exception):
    status_code: int
    error: str
    message: str

    def __post_init__(self):
        Exception.__init__(self, self.message)
