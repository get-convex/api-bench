from dotenv.main import load_dotenv

from backends.convex import ConvexBackend
from evaluation.tasks.kv_store import kv_store_task
from graders.filesystem import write_files
from models.openai.o1 import O1Model

load_dotenv()

model = O1Model()
response = model.execute(ConvexBackend, kv_store_task)

temp_dir = write_files(response)
print(f"Wrote files to {temp_dir}")

backend = ConvexBackend(temp_dir)
try:
    backend.start()
    backend.deploy()
finally:
    backend.stop()
