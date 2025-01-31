import functools
import os
import platform
import subprocess
import threading
import time
import zipfile
from typing import Union

import requests
from convex import ConvexClient
from portpicker import pick_unused_port

from backends import Backend
from evaluation.api import ApiDescription, HttpMethod
from evaluation.task import Task


class ConvexBackend(Backend):
    @classmethod
    def api_prompt(cls, endpoints: list[ApiDescription]) -> str:
        out = []
        for endpoint in endpoints:
            if endpoint.method == HttpMethod.GET:
                function_type = "Query"
            elif endpoint.method == HttpMethod.POST:
                function_type = "Mutation"
            else:
                raise ValueError(f"Invalid HTTP method: {endpoint.method}")

            path = f"api.answer.{endpoint.name}"
            out.append(f"- {function_type} `{path}`: {endpoint.description}")

        return "\n".join(out)

    @classmethod
    def description(cls) -> str:
        lines = []
        lines.append("Use Convex for building the backend.")
        lines.append("")
        lines.append("".join(render_guidelines(CONVEX_GUIDELINES)))
        lines.append("")
        lines.append("".join(render_examples("../evals-convex/examples/")))
        lines.append("## Versions")
        lines.append("- Always use convex version ^1.17.4 in your package.json")
        return "\n".join(lines)

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.project_dir = os.path.join(self.temp_dir, "project")
        self.backend_dir = os.path.join(self.temp_dir, "backend")
        self.process = None
        os.makedirs(self.backend_dir, exist_ok=True)

    def start(self):
        if self.process:
            raise RuntimeError("Backend already running")

        storage_dir = os.path.abspath(os.path.join(self.backend_dir, "convex_local_storage"))
        os.makedirs(storage_dir, exist_ok=True)
        sqlite_path = os.path.abspath(os.path.join(self.backend_dir, "convex_local_backend.sqlite3"))
        convex_binary = download_convex_binary()
        with port_lock:
            port = pick_unused_port()
            site_proxy_port = pick_unused_port()
            self.process = subprocess.Popen(
                [
                    convex_binary,
                    "--port",
                    str(port),
                    "--site-proxy-port",
                    str(site_proxy_port),
                    "--instance-name",
                    instance_name,
                    "--instance-secret",
                    instance_secret,
                    "--local-storage",
                    storage_dir,
                    sqlite_path,
                ],
                cwd=self.backend_dir,
                stdout=open(os.path.join(self.backend_dir, "backend.stdout.log"), "w"),
                stderr=open(os.path.join(self.backend_dir, "backend.stderr.log"), "w"),
            )

        deadline = time.time() + 10
        num_attempts = 0
        while True:
            try:
                requests.get(f"http://localhost:{port}/version").raise_for_status()
                break
            except Exception as e:
                remaining = deadline - time.time()
                if remaining < 0:
                    raise e
                time.sleep(min(0.1 * (2**num_attempts), remaining))
                num_attempts += 1

        # Check that our process is still running after passing health checks.abs
        if self.process.poll() is not None:
            raise RuntimeError("Backend process failed to start")

        self.port = port
        self.site_proxy_port = site_proxy_port
        self.client = ConvexClient(f"http://localhost:{port}")

    def deploy(self):
        done = subprocess.run(
            ["bun", "install"],
            cwd=self.project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        if done.returncode != 0:
            raise Exception(f"Failed to install dependencies:\n{done.stdout}")

        done = subprocess.run(
            [
                "bunx",
                "convex",
                "dev",
                "--once",
                "--admin-key",
                admin_key,
                "--url",
                f"http://localhost:{self.port}",
            ],
            cwd=self.project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        if done.returncode != 0:
            raise Exception(f"Failed to deploy:\n{done.stdout}")

    def call_api(self, task: Task, name: str, input):
        endpoint = next((endpoint for endpoint in task.api_description() if endpoint.name == name), None)
        if endpoint is None:
            raise ValueError(f"Endpoint {name} not found in task {task.name}")
        path = f"answer:{endpoint.name}"
        if endpoint.method == HttpMethod.GET:
            result = self.client.query(path, input)
        elif endpoint.method == HttpMethod.POST:
            result = self.client.mutation(path, input)
        else:
            raise ValueError(f"Invalid HTTP method: {endpoint.method}")
        return result

    def stop(self):
        if not self.process:
            raise RuntimeError("Backend not running")
        self.process.terminate()
        self.process = None


port_lock = threading.Lock()
download_binary_lock = threading.Lock()


def download_convex_binary():
    latest = fetch_convex_release()
    version = latest["tag_name"]

    arch = {"x86_64": "x86_64", "arm64": "aarch64", "AMD64": "x86_64"}[platform.machine()]
    triple_os = {
        "Darwin": "apple-darwin",
        "Linux": "unknown-linux-gnu",
        "Windows": "pc-windows-msvc",
    }[platform.system()]
    target_pattern = f"convex-local-backend-{arch}-{triple_os}"

    # Find the matching asset from the release
    matching_asset = None
    for asset in latest["assets"]:
        if target_pattern in asset["name"]:
            matching_asset = asset
            break

    if not matching_asset:
        raise RuntimeError(f"Could not find matching asset for {target_pattern}")

    binary_dir = os.path.expanduser("~/.convex-evals/releases")
    os.makedirs(binary_dir, exist_ok=True)

    # Include version in binary name
    binary_name = f"convex-local-backend-{version}"
    if platform.system() == "Windows":
        binary_name += ".exe"
    binary_path = os.path.join(binary_dir, binary_name)

    if os.path.exists(binary_path):
        return binary_path

    with download_binary_lock:
        if os.path.exists(binary_path):
            return binary_path

        print("Latest release:", version)

        url = matching_asset["browser_download_url"]
        print("Downloading:", url)
        response = requests.get(url, stream=True)
        response.raise_for_status()

        zip_path = os.path.join(binary_dir, matching_asset["name"])
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Downloaded:", matching_asset["name"])

        # Unzip the file
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(binary_dir)

        # Rename the extracted binary to include version
        extracted_binary = os.path.join(binary_dir, "convex-local-backend")
        if platform.system() == "Windows":
            extracted_binary += ".exe"
        os.rename(extracted_binary, binary_path)

        # Make the binary executable on Unix systems
        if platform.system() != "Windows":
            os.chmod(binary_path, 0o755)

        # Clean up zip file
        os.remove(zip_path)
        print("Extracted binary to:", binary_path)

    return binary_path


@functools.cache
def fetch_convex_release():
    releases = requests.get("https://api.github.com/repos/get-convex/convex-backend/releases").json()
    return releases[0]


instance_name = "carnitas"
instance_secret = "4361726e697461732c206c69746572616c6c79206d65616e696e6720226c6974"

admin_key = "0135d8598650f8f5cb0f30c34ec2e2bb62793bc28717c8eb6fb577996d50be5f4281b59181095065c5d0f86a2c31ddbe9b597ec62b47ded69782cd"


class Guideline:
    def __init__(self, content: str):
        self.content = content.strip()


class GuidelineSection:
    def __init__(self, name: str, children: list):
        self.name = name
        self.children = children


def render_guidelines(node: Union[GuidelineSection, Guideline], header="#"):
    if isinstance(node, Guideline):
        yield "- "
        yield "\n".join(line.strip() for line in node.content.strip().splitlines())
        yield "\n"
    else:
        words = node.name.split("_")
        words[0] = words[0].capitalize()
        yield f"{header} {' '.join(words)}\n"
        for child in node.children:
            yield from render_guidelines(child, header + "#")
        yield "\n"


CONVEX_GUIDELINES = GuidelineSection(
    "convex_guidelines",
    [
        GuidelineSection(
            "function_guidelines",
            [
                GuidelineSection(
                    "new_function_syntax",
                    [
                        Guideline(
                            """
      ALWAYS use the new function syntax for Convex functions. For example:
      ```typescript
      import { query } from "./_generated/server";
      import { v } from "convex/values";
      export const f = query({
          args: {},
          returns: v.null(),
          handler: async (ctx, args) => {
          // Function body
          },
      });
      ```
      """
                        ),
                    ],
                ),
                GuidelineSection(
                    "http_endpoint_syntax",
                    [
                        Guideline(
                            """
      HTTP endpoints are defined in `convex/http.ts` and require an `httpAction` decorator. For example:
      ```typescript
      import { httpRouter } from "convex/server";
      import { httpAction } from "./_generated/server";
      const http = httpRouter();
      http.route({
          path: "/echo",
          method: "POST",
          handler: httpAction(async (ctx, req) => {
          const body = await req.bytes();
          return new Response(body, { status: 200 });
          }),
      });
      ```
      """
                        ),
                    ],
                ),
                GuidelineSection(
                    "function_registration",
                    [
                        Guideline(
                            "Use `internalQuery`, `internalMutation`, and `internalAction` to register internal functions. These functions are private and aren't part of an app's API. They can only be called by other Convex functions."
                        ),
                        Guideline(
                            "Use `query`, `mutation`, and `action` to register public functions. These functions are part of the public API and are exposed to the public Internet. Do NOT use `query`, `mutation`, or `action` to register sensitive internal functions that should be kept private."
                        ),
                        Guideline("You CANNOT register a function through the `api` or `internal` objects."),
                        Guideline(
                            "ALWAYS include argument and return validators for all Convex functions. If a function doesn't return anything, include `returns: v.null()` as its output validator."
                        ),
                        Guideline(
                            "If the JavaScript implementation of a Convex function doesn't have a return value, it implicitly returns `null`."
                        ),
                    ],
                ),
                GuidelineSection(
                    "function_calling",
                    [
                        Guideline("Use `ctx.runQuery` to call a query from a query, mutation, or action."),
                        Guideline("Use `ctx.runMutation` to call a mutation from a mutation or action."),
                        Guideline("Use `ctx.runAction` to call an action from an action."),
                        Guideline(
                            "ONLY call an action from another action if you need to cross runtimes (e.g. from V8 to Node). Otherwise, pull out the shared code into a helper async function and call that directly instead."
                        ),
                        Guideline(
                            "Try to use as few calls from actions to queries and mutations as possible. Queries and mutations are transactions, so splitting logic up into multiple calls introduces the risk of race conditions."
                        ),
                        Guideline(
                            "All of these calls take in a `FunctionReference`. Do NOT try to pass the callee function directly into one of these calls."
                        ),
                        Guideline(
                            """
                            When using `ctx.runQuery`, `ctx.runMutation`, or `ctx.runAction` to call a function in the same file, specify a type annotation on the return value to work around TypeScript circularity limitations. For example,
                            ```
                            export const f = query({
                              args: { name: v.string() },
                              returns: v.string(),
                              handler: async (ctx, args) => {
                                return "Hello " + args.name;
                              },
                            });

                            export const g = query({
                              args: {},
                              returns: v.null(),
                              handler: async (ctx, args) => {
                                const result: string = await ctx.runQuery(api.example.f, { name: "Bob" });
                                return null;
                              },
                            });
                            ```
                            """
                        ),
                    ],
                ),
                GuidelineSection(
                    "function_references",
                    [
                        Guideline("Function references are pointers to registered Convex functions."),
                        Guideline(
                            "Use the `api` object defined by the framework in `convex/_generated/api.ts` to call public functions registered with `query`, `mutation`, or `action`."
                        ),
                        Guideline(
                            "Use the `internal` object defined by the framework in `convex/_generated/api.ts` to call internal (or private) functions registered with `internalQuery`, `internalMutation`, or `internalAction`."
                        ),
                        Guideline(
                            "Convex uses file-based routing, so a public function defined in `convex/example.ts` named `f` has a function reference of `api.example.f`."
                        ),
                        Guideline(
                            "A private function defined in `convex/example.ts` named `g` has a function reference of `internal.example.g`."
                        ),
                        Guideline(
                            "Functions can also registered within directories nested within the `convex/` folder. For example, a public function `h` defined in `convex/messages/access.ts` has a function reference of `api.messages.access.h`."
                        ),
                    ],
                ),
                GuidelineSection(
                    "api_design",
                    [
                        Guideline(
                            "Convex uses file-based routing, so thoughtfully organize files with public query, mutation, or action functions within the `convex/` directory."
                        ),
                        Guideline("Use `query`, `mutation`, and `action` to define public functions."),
                        Guideline(
                            "Use `internalQuery`, `internalMutation`, and `internalAction` to define private, internal functions."
                        ),
                    ],
                ),
            ],
        ),
        GuidelineSection(
            "validator_guidelines",
            [
                Guideline(
                    "`v.bigint()` is deprecated for representing signed 64-bit integers. Use `v.int64()` instead."
                ),
                Guideline("Use `v.record()` for defining a record type. `v.map()` and `v.set()` are not supported."),
            ],
        ),
        GuidelineSection(
            "schema_guidelines",
            [
                Guideline("Always define your schema in `convex/schema.ts`."),
                # TODO: Fold back into original guidelines.
                Guideline("""Here's an example of a schema definition:
                    ```ts
                    // convex/schema.ts

                    import { defineSchema, defineTable } from "convex/server";
                    import { v } from "convex/values";

                    export default defineSchema({
                        users: defineTable({
                            name: v.string(),
                        }),
                    });
                    ```
                """),
            ],
        ),
        GuidelineSection(
            "typescript_guidelines",
            [
                Guideline(
                    "You can use the helper typescript type `Id` imported from './_generated/dataModel' to get the type of the id for a given table. For example if there is a table called 'users' you can use `Id<'users'>` to get the type of the id for that table."
                ),
                Guideline(
                    "If you need to define a `Record` make sure that you correctly provide the type of the key and value in the type. For example a validator `v.record(v.id('users'), v.string())` would have the type `Record<Id<'users'>, string>`."
                ),
                Guideline(
                    "Be strict with types, particularly around id's of documents. For example, if a function takes in an id for a document in the 'users' table, take in `Id<'users'>` rather than `string`."
                ),
            ],
        ),
        GuidelineSection(
            "full_text_search_guidelines",
            [
                Guideline(
                    'A query for "10 messages in channel \'#general\' that best match the query \'hello hi\' in their body" would look like:\n\nconst messages = await ctx.db\n  .query("messages")\n  .withSearchIndex("search_body", (q) =>\n    q.search("body", "hello hi").eq("channel", "#general"),\n  )\n  .take(10);'
                ),
            ],
        ),
        GuidelineSection(
            "query_guidelines",
            [
                Guideline(
                    "Do NOT use `filter` in queries. Instead, define an index in the schema and use `withIndex` instead."
                ),
                Guideline(
                    "Convex queries do NOT support `.delete()`. Instead, `.collect()` the results, iterate over them, and call `ctx.db.delete(row._id)` on each result."
                ),
                GuidelineSection(
                    "ordering",
                    [
                        Guideline("By default Convex always returns documents in ascending `_creationTime` order."),
                        Guideline(
                            "You can use `.order('asc')` or `.order('desc')` to pick whether a query is in ascending or descending order. If the order isn't specified, it defaults to ascending."
                        ),
                        Guideline(
                            "Document queries that use indexes will be ordered based on the columns in the index and can avoid slow table scans."
                        ),
                    ],
                ),
            ],
        ),
        GuidelineSection(
            "mutation_guidelines",
            [
                Guideline(
                    "Use `ctx.db.replace` to fully replace an existing document. This method will throw an error if the document does not exist."
                ),
                Guideline(
                    "Use `ctx.db.patch` to shallow merge updates into an existing document. This method will throw an error if the document does not exist."
                ),
            ],
        ),
        GuidelineSection(
            "scheduling_guidelines",
            [
                GuidelineSection(
                    "cron_guidelines",
                    [
                        Guideline(
                            "Only use the `crons.interval` or `crons.cron` methods to schedule cron jobs. Do NOT use the `crons.hourly`, `crons.daily`, or `crons.weekly` helpers."
                        ),
                        Guideline(
                            "Both cron methods take in a FunctionReference. Do NOT try to pass the function directly into one of these methods."
                        ),
                        Guideline(
                            """Define crons by declaring the top-level `crons` object, calling some methods on it, and then exporting it as default. For example,
                            ```ts
                            import { cronJobs } from "convex/server";
                            import { internal } from "./_generated/api";

                            const crons = cronJobs();

                            // Run `internal.users.deleteInactive` every two hours.
                            crons.interval("delete inactive users", { hours: 2 }, internal.users.deleteInactive, {});

                            export default crons;
                            ```
                            """
                        ),
                        Guideline("You can register Convex functions within `crons.ts` just like any other file."),
                        Guideline(
                            "If a cron calls an internal function, always import the `internal` object from '_generated/api`, even if the internal function is registered in the same file."
                        ),
                    ],
                ),
            ],
        ),
        GuidelineSection(
            "file_storage_guidelines",
            [
                Guideline("Convex includes file storage for large files like images, videos, and PDFs."),
                Guideline(
                    "The `ctx.storage.getUrl()` method returns a signed URL for a given file. It returns `null` if the file doesn't exist."
                ),
                Guideline(
                    """
                    Do NOT use the deprecated `ctx.storage.getMetadata` call for loading a file's metadata.

                    Instead, query the `_storage` system table. For example, you can use `ctx.db.system.get` to get an `Id<"_storage">`.
                    ```
                    import { query } from "./_generated/server";
                    import { Id } from "./_generated/dataModel";

                    type FileMetadata = {
                        _id: Id<"_storage">;
                        _creationTime: number;
                        contentType?: string;
                        sha256: string;
                        size: number;
                    }

                    export const exampleQuery = query({
                        args: { fileId: v.id("_storage") },
                        returns: v.null();
                        handler: async (ctx, args) => {
                            const metadata: FileMetadata | null = await ctx.db.system.get(args.fileId);
                            console.log(metadata);
                            return null;
                        },
                    });
                    ```
                    """
                ),
            ],
        ),
    ],
)


def render_examples(example_dir: str):
    yield "# Examples:\n"
    for example in os.listdir(example_dir):
        example_path = os.path.join(example_dir, example)
        if not os.path.isdir(example_path):
            continue

        task_description = open(os.path.join(example_path, "TASK.txt"), "r").read()
        analysis = open(os.path.join(example_path, "ANALYSIS.txt"), "r").read()

        file_paths = []
        for dirpath, _, file_names in os.walk(example_path, topdown=True):
            if "node_modules" in dirpath or "_generated" in dirpath:
                continue
            for file_name in file_names:
                if file_name == "package.json" or file_name.endswith(".ts"):
                    file_paths.append(os.path.join(dirpath, file_name))

        file_paths.sort(key=lambda x: (x.count("/"), x))

        yield f"## Example: {example}\n\n"
        yield "### Task\n"
        yield f"```\n{task_description}\n```\n\n"
        yield "### Analysis\n"
        yield f"{analysis}\n\n"
        yield "### Implementation\n\n"
        for file_path in file_paths:
            rel_path = os.path.relpath(file_path, example_path)
            file_content = open(file_path, "r").read().strip()
            yield f"#### {rel_path}\n"
            yield f"```typescript\n{file_content}\n```\n\n"
