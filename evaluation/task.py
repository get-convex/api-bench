from pydantic import BaseModel

from evaluation.api import ApiDescription


class Task(BaseModel):
    prelude: str
    api_description: list[ApiDescription]
    postlude: str
