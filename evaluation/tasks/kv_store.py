import json
import random
import time

from backends import Backend
from evaluation.api import ApiDescription, HttpMethod
from evaluation.task import Task

prelude = "Write a high performance, correct backend server that implements the following API:"

api_description = [
    ApiDescription(
        name="put",
        method=HttpMethod.POST,
        description="""
    Takes in a `kv_pairs` argument, which is a JSON list of `{\"key\": ..., \"value\": ...}` pairs,
    stores them atomically and durably, and returns `null`.
    """,
    ),
    ApiDescription(
        name="get",
        method=HttpMethod.GET,
        description="""
    Takes in a `keys` argument, which is a JSON list of keys, and returns a JSON
    list of `{\"key\": ..., \"value\": ...}` pairs.
    """,
    ),
]

postlude = """
Limits:
- Keys are Unicode strings that are no longer than 1024 bytes when encoding in UTF-8.
- Values are arbitrary JSON values that are no longer than 16KiB when serialized and encoded in UTF-8.
- You can assume these limits are obeyed and do not need to check them in your implementation.

Ensure that each request is atomic, durable, and has serializable consistency. The system must
NOT lose acknowledged data. The system will be evaluated for correctness, even under highly
concurrent load. After correctness, the system will be evaluated its maximum request throughput
for a read-heavy workload before hitting congestion collapse.
"""


class KvStoreTask(Task):
    def prelude(self) -> str:
        return prelude

    def api_description(self) -> list[ApiDescription]:
        return api_description

    def postlude(self) -> str:
        return postlude

    def grade(self, backend: Backend) -> dict[str, float]:
        scores = {}
        scores["basic_put_get"] = self.test_basic_put_get(backend)
        scores["elle"] = self.test_elle(backend)
        return scores

    def test_basic_put_get(self, backend: Backend):
        try:
            resp = backend.call_api(
                self, "put", {"kv_pairs": [{"key": "foo", "value": "bar"}, {"key": "baz", "value": "qux"}]}
            )
            assert resp is None
            resp = backend.call_api(self, "get", {"keys": ["foo", "baz"]})
            resp.sort(key=lambda x: x["key"])
            assert resp == [{"key": "baz", "value": "qux"}, {"key": "foo", "value": "bar"}]
        except Exception as e:
            print(f"Test failed: {e}")
            raise e
        return 1.0

    def test_elle(self, backend: Backend):
        try:
            num_transactions = 32
            transaction_size = 4
            run_id = int(time.time())

            history = []

            # Create seeded RNG for reproducible tests
            rng = random.Random(42)  # Fixed seed for reproducibility

            num_keys = 8
            keys = [f"elle:{run_id}:{i}" for i in range(num_keys)]

            for i in range(num_transactions):
                is_read = rng.random() < 0.8
                if is_read:
                    keys_to_read = random.sample(keys, transaction_size)

                    invoke_entry = {
                        "type": "invoke",
                        "f": "get",
                        "value": [["r", k, None] for k in keys_to_read],
                        "process": 0,
                        "index": len(history),
                    }
                    history.append(invoke_entry)
                    resp = backend.call_api(self, "get", {"keys": keys_to_read})
                    ok_entry = {
                        "type": "ok",
                        "value": [["r", pair["key"], pair["value"]] for pair in resp],
                        "process": 0,
                        "index": len(history),
                    }
                    history.append(ok_entry)
                else:
                    kv_pairs = [
                        {"key": keys[rng.randint(0, num_keys - 1)], "value": rng.randint(0, 100)}
                        for _ in range(transaction_size)
                    ]
                    invoke_entry = {
                        "type": "invoke",
                        "f": "put",
                        "value": [["w", pair["key"], pair["value"]] for pair in kv_pairs],
                        "process": 0,
                        "index": len(history),
                    }
                    history.append(invoke_entry)
                    backend.call_api(self, "put", {"kv_pairs": kv_pairs})
                    ok_entry = {
                        "type": "ok",
                        "value": [["w", pair["key"], pair["value"]] for pair in kv_pairs],
                        "process": 0,
                        "index": len(history),
                    }
                    history.append(ok_entry)

            with open(f"/tmp/elle-{run_id}.json", "w") as f:
                json.dump(history, f)
                print(f"Wrote history to /tmp/elle-{run_id}.json")

            return 1.0
        except Exception as e:
            print(f"Test failed: {e}")
            return 0.0


kv_store_task = KvStoreTask()
