from evaluation.api import ApiDescription, HttpMethod
from evaluation.task import Task

prelude = "Write a high performance, correct backend server that implements the following API:"

api_desciption = [
    ApiDescription(
        name="put",
        method=HttpMethod.POST,
        description="""
    Takes in a JSON body indicating a list of `{\"key\": ..., \"value\": ...}` pairs,
    stores them durably and returns `null`.
    """,
    ),
    ApiDescription(
        name="get",
        method=HttpMethod.GET,
        description="""
    Takes in a JSON body indicating a list of keys and returns a JSON
    list of `{\"key\": ..., \"value\": ...}` pairs.
    """,
    ),
]

postlude = """
Limits:
- Keys are Unicode strings that are no longer than 1024 bytes when encoding in UTF-8.
- Values are arbitrary JSON values that are no longer than 16KiB when serialized and encoded in UTF-8.

Ensure that each request is atomic, durable, and has serializable consistency. The system must
NOT lose acknowledged data. The system will be evaluated for correctness, even under highly
concurrent load. After correctness, the system will be evaluated its maximum request throughput
for a read-heavy workload before hitting congestion collapse.
"""

kv_store_task = Task(prelude=prelude, api_description=api_desciption, postlude=postlude)
