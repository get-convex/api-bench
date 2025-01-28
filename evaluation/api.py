import re
from enum import Enum

from pydantic import BaseModel, validator


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"


class ApiDescription(BaseModel):
    """Describes an API endpoint with name, HTTP method, and JSON schema
    validation."""

    name: str
    method: HttpMethod
    description: str

    @validator("name")
    def validate_name_format(cls, v):
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError("name must be snake_case, lowercase, and contain no whitespace")
        return v

    @validator("description")
    def clean_description(cls, v):
        return "\n".join(line.strip() for line in v.strip().splitlines())

    class Config:
        frozen = True  # Makes instances immutable
