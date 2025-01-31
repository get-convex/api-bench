# api-bench (WIP)

This is an automated benchmark for solving hard backend systems problems.

Each task has the agent implement an API specification for a specific backend.
Currently, we support Convex and Python/FastAPI/Postgres on Modal.

Then, the implementation is graded on a few categories:

1. Unit tests: Each task specifies some direct correctness tests.
2. Model testing: We use [Elle](https://github.com/jepsen-io/elle) (Jepsen's model checker) to test
   that the implementation behaves correctly under high concurrency.
3. Performance testing (TODO): Maximum throughput before congestion collapse.

## Installation
```
pdm install
```
Also, put `OPENAI_API_KEY`, `BRAINTRUST_API_KEY`, and `ANTHROPIC_API_KEY` in `.env`.

We depend on `elle-cli` (TODO: Find a better way to use this dependency).
```
brew install leiningen
cd ../
git clone https://github.com/ligurio/elle-cli
cd elle-cli
lein deps
lein uberjar
```
