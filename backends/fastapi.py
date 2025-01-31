import os

import modal

from backends import Backend
from evaluation.api import ApiDescription


class FastAPIBackend(Backend):
    @classmethod
    def api_prompt(cls, endpoints: list[ApiDescription]) -> str:
        out = []
        for endpoint in endpoints:
            out.append(f"- {endpoint.method} /api/{endpoint.name}: {endpoint.description}")
        return "\n".join(out)

    @classmethod
    def description(cls) -> str:
        lines = []
        lines.append("Use Python 3.9, FastAPI for the API server, and Postgres for storage.")
        lines.append("You can assume POSTGRES_URL is provided as an environment variable.")
        lines.append("Write out a `requirements.txt` for any dependencies you need.")
        lines.append("Use `fastapi[standard]` for the FastAPI package.")
        lines.append("Your server will be started by running `fastapi run main.py`")
        return "\n".join(lines)

    def __init__(self, temp_dir: str):
        self.project_dir = os.path.join(temp_dir, "project")

    def start(self):
        image = modal.Image.debian_slim()
        requirements_path = os.path.join(self.project_dir, "requirements.txt")
        if os.path.exists(requirements_path):
            contents = open(requirements_path).read()
            image = image.pip_install_from_requirements(contents)

        app = modal.App.lookup("api-bench-fastapi", create_if_missing=True)
        self.sb = modal.Sandbox.create(
            "python",
            "-m",
            "fastapi",
            "run",
            "main.py",
            app=app,
            image=image,
            mounts=[
                modal.Mount.from_local_dir(self.project_dir, remote_path="/app"),
            ],
            workdir="/app",
            timeout=5 * 60,
        )

    def deploy(self):
        pass
