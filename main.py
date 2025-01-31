from dotenv import load_dotenv

from backends.convex import ConvexBackend
from evaluation.tasks.list_append import list_append_task
from graders.filesystem import write_files
from models.openai.o1 import O1Model

load_dotenv()

model = O1Model()
task = list_append_task

response = model.execute(ConvexBackend, task)

temp_dir = write_files(response)
print(f"Wrote files to {temp_dir}")

backend = ConvexBackend(temp_dir)
try:
    backend.start()
    backend.deploy()
    scores = task.grade(backend)
    print(scores)
finally:
    backend.stop()
