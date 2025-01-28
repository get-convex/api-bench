import os
import tempfile

from models import ModelResponse


def write_files(response: ModelResponse) -> str:
    temp_dir = tempfile.mkdtemp()

    project_dir = os.path.join(temp_dir, "project")
    os.makedirs(project_dir, exist_ok=True)

    for path, content in response.files.items():
        out_path = os.path.join(project_dir, path)

        if not os.path.abspath(out_path).startswith(os.path.abspath(temp_dir)):
            raise ValueError(f"File path {out_path} is not within the temporary directory {temp_dir}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        with open(out_path, "w") as f:
            f.write(content)

    with open(os.path.join(temp_dir, "PROMPT.txt"), "w") as f:
        f.write(response.prompt)

    with open(os.path.join(temp_dir, "RESPONSE.txt"), "w") as f:
        f.write(response.response_text)

    return temp_dir
