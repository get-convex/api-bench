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

    def start(self):
        pass

    def deploy(self):
        pass

    def stop(self):
        pass
