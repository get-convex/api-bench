lint:
    ruff check .

format:
    ruff check --fix .

elle *args:
    java -jar ../elle-cli/target/elle-cli-0.1.8-standalone.jar {{args}}
