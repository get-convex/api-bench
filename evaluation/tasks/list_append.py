import concurrent.futures
import json
import os
import random
import subprocess
import tempfile
import threading
import time

from pydantic import BaseModel

from backends import Backend
from evaluation.api import ApiDescription, HttpMethod
from evaluation.task import Task

prelude = "Write a high performance, correct backend server that implements the following API:"

api_description = [
    ApiDescription(
        name="append",
        method=HttpMethod.POST,
        description="""
        Takes in a `transaction` argument, which is a list of JSON objects.
          - `{"type": "read", "key": ...}`: Reads the list associated with the given key.
          - `{"type": "append", "key": ..., "value": ...}`: Appends the value to the list associated with the given key.

        Returns a parallel list of JSON objects matching each processed input object:
          - `{"type": "read", "key": ..., "value": ...}`: The value for a corresponding "read" in the input, defaulting
            to the empty list if nonexistent.
          - `{"type": "append", "key": ..., "value": ...}`: The value appended for an "append" in the input.
        """,
    ),
]

postlude = """
- The backend stores a list of JSON numbers for each key.
- Keys are Unicode strings that are no longer than 1024 bytes when encoding in UTF-8.
- The numbers are within range for an f64. Each value's list has no more than 1024 elements.
- You can assume these limits are obeyed and do not need to check them in your implementation.

Ensure that the `append` requests are atomic, durable, and have serializable consistency. Each
read within a call to `append` MUST observe appends within the same request.

The system will be evaluated for correctness, even highly concurrent load.
"""


class ElleConfig(BaseModel):
    num_keys: int
    num_transactions: int
    transaction_size: int
    concurrency: int

    read_probability: float


class ListAppendTask(Task):
    def __init__(self):
        self.elle_config = ElleConfig(
            num_keys=8,
            num_transactions=64,
            transaction_size=8,
            concurrency=4,
            read_probability=0.25,
        )

    def prelude(self) -> str:
        return prelude

    def api_description(self) -> list[ApiDescription]:
        return api_description

    def postlude(self) -> str:
        return postlude

    def grade(self, backend: Backend) -> dict[str, float]:
        scores = {}
        scores["basic_append"] = self.test_basic_append(backend)
        scores["elle"] = self.test_elle(backend)
        return scores

    def test_basic_append(self, backend: Backend):
        try:
            resp = backend.call_api(
                self,
                "append",
                {"transaction": [{"type": "read", "key": "foo"}, {"type": "append", "key": "foo", "value": 1}]},
            )
            assert resp == [
                {"type": "read", "key": "foo", "value": []},
                {"type": "append", "key": "foo", "value": 1},
            ], resp

            resp = backend.call_api(
                self,
                "append",
                {"transaction": [{"type": "append", "key": "foo", "value": 2}, {"type": "read", "key": "foo"}]},
            )
            assert resp == [
                {"type": "append", "key": "foo", "value": 2},
                {"type": "read", "key": "foo", "value": [1, 2]},
            ]
        except Exception as e:
            print(f"Test failed: {e}")
            raise e
        return 1.0

    def test_elle(self, backend: Backend):
        try:
            run_id = int(time.time())

            # Create seeded RNG for reproducible tests
            rng = random.Random(run_id)

            keys = [str(i) for i in range(self.elle_config.num_keys)]
            history = []
            lock = threading.Lock()

            def run_transaction(i, transaction, tuples):
                with lock:
                    invoke_entry = {
                        "type": "invoke",
                        "f": "append",
                        "value": tuples,
                        "process": i,
                        "index": len(history),
                    }
                    history.append(invoke_entry)

                resp = backend.call_api(self, "append", {"transaction": transaction})

                with lock:
                    resp_tuples = []
                    for op in resp:
                        if op["type"] == "read":
                            resp_tuples.append(("r", op["key"], [int(v) for v in op["value"]]))
                        else:
                            resp_tuples.append(("append", op["key"], int(op["value"])))
                    ok_entry = {
                        "type": "ok",
                        "value": resp_tuples,
                        "process": i,
                        "index": len(history),
                    }
                    history.append(ok_entry)

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.elle_config.concurrency) as executor:
                futures = []

                for i in range(self.elle_config.num_transactions):
                    transaction = []
                    tuples = []
                    for j in range(self.elle_config.transaction_size):
                        is_read = rng.random() < self.elle_config.read_probability
                        if is_read:
                            key = keys[rng.randint(0, self.elle_config.num_keys - 1)]
                            transaction.append({"type": "read", "key": key})
                            tuples.append(("r", key, None))
                        else:
                            key = keys[rng.randint(0, self.elle_config.num_keys - 1)]
                            value = rng.randint(0, 1000000)
                            transaction.append({"type": "append", "key": key, "value": value})
                            tuples.append(("append", key, value))

                    futures.append(executor.submit(run_transaction, i, transaction, tuples))

                for future in concurrent.futures.as_completed(futures):
                    future.result()

            tmpdir = tempfile.mkdtemp()

            with open(f"{tmpdir}/history.json", "w") as f:
                json.dump(history, f)

            os.makedirs(f"{tmpdir}/failure")

            subprocess.check_call(
                [
                    "just",
                    "elle",
                    "--model",
                    "list-append",
                    "--format",
                    "json",
                    "--directory",
                    f"{tmpdir}/failure",
                    f"{tmpdir}/history.json",
                ],
            )
            print("Elle passed!")
            return 1.0
        except Exception as e:
            print(f"Test failed: {e}")
            return 0.0


list_append_task = ListAppendTask()
