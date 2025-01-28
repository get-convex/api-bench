from abc import ABC, abstractmethod

from pydantic import BaseModel
from typing_extensions import TypeAlias

from backends import Backend
from evaluation.task import Task

RelativePath: TypeAlias = str
FileContent: TypeAlias = str


class ModelResponse(BaseModel):
    prompt: str
    response_text: str
    files: dict[RelativePath, FileContent]


class Model(ABC):
    @abstractmethod
    def execute(self, backend: Backend, task: Task) -> ModelResponse:
        pass
