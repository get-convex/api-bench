import os

from markdown_it import MarkdownIt
from openai import OpenAI

from backends import Backend
from evaluation.task import Task
from models import ModelResponse

FORMAT_PROMPT = """
# Output format
Output all files within an h1 Files section that has an h2 section
for each necessary file. Include the contents of the file in a code block.

For example, correct output looks like:

# Files
## exampleFile.txt
```
Hello world!
```
## static/anotherFile.c
```
int main() {
  return 0;
}
```
"""


class O1Model:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.braintrust.dev/v1/proxy",
        )

    def execute(self, backend: Backend, task: Task) -> ModelResponse:
        prompt = "# Task\n"
        prompt += task.prelude()
        prompt += f"\n{backend.api_prompt(task.api_description())}\n"
        prompt += task.postlude()
        prompt += f"\n{backend.description()}\n"
        prompt += FORMAT_PROMPT

        response = self.client.chat.completions.create(
            model="o1",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=16384,
            seed=1,
        )
        text = response.choices[0].message.content

        md = MarkdownIt()
        tokens = md.parse(text)

        files = {}
        current_file = None
        in_files_section = False

        for i, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag == "h1":
                title_token = tokens[i + 1]
                if title_token.content == "Files":
                    in_files_section = True
                    continue

            if not in_files_section:
                continue

            if token.type == "heading_open" and token.tag == "h2":
                title_token = tokens[i + 1]
                current_file = title_token.content.strip()
            elif token.type == "fence" and current_file:
                files[current_file] = token.content.strip()
                current_file = None

        return ModelResponse(prompt=prompt, response_text=text, files=files)
