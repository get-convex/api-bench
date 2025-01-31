from abc import ABC, abstractmethod

from evaluation.api import ApiDescription


class Backend(ABC):
    @classmethod
    @abstractmethod
    def api_prompt(cls, api: list[ApiDescription]) -> str:
        pass

    @classmethod
    @abstractmethod
    def description(cls) -> str:
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def deploy(self):
        pass

    @abstractmethod
    def call_api(self, task, name: str, input):
        pass

    @abstractmethod
    def stop(self):
        pass
