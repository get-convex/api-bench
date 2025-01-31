from abc import ABC, abstractmethod

from backends import Backend
from evaluation.api import ApiDescription


class Task(ABC):
    @abstractmethod
    def prelude(self) -> str:
        pass

    @abstractmethod
    def api_description(self) -> list[ApiDescription]:
        pass

    @abstractmethod
    def postlude(self) -> str:
        pass

    @abstractmethod
    def grade(self, backend: Backend) -> dict[str, float]:
        pass
