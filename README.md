# Twinage: RAG-based Thought Retrieval Agent

[English](README.md) | [日本語](README.ja.md)

Twinage is a RAG (Retrieval-Augmented Generation) agent system that stores fragments of past thought processes and specifications in a vector database, allowing it to reconstruct and reference them through natural language dialogue. This repository provides an initial implementation (Hello World version) with a minimal configuration.

- [Showcase (Issues)](https://github.com/gumi278/twinage/issues)

Please note that Twinage may provide primary responses to inquiries on the issues page.

---
## Requirements

The system uses an OpenAI-compatible API for communication. Therefore, it can operate with either external cloud APIs or local LLMs. However, the models used must meet the following requirements.

### Model Requirements

- Reasoning (Thought process) support
- Function Calling (Tool Calling) support

### Tested Environment

The author develops on the following configuration:
- `MacBook Pro M1Pro UMA16GB/SSD512GB`
- `macOS Tahoe`
- `llama.cpp/llama-server`
- `unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL`
- `gpustack/bge-m3-GGUF`

> [!NOTE]
> Equivalent operation is expected in a 16GB VRAM environment (it is very tight).
> By selecting a model size that matches your VRAM capacity, it should be possible to run it with even less.

---

## Quick Start

The shortest steps to run the chat-based Twinage.

### Prerequisites

- `python`
- `uv`

The following guide assumes:

- Using OpenAI's API (`gpt-4o` / `text-embedding-3-small`)
- Chat runs on `127.0.0.1:8000`
- The working (current) directory is `twinage`
- Using the bundled sample data

> [!NOTE]
> We assume the use of an external API for common understanding.
> Twinage is not strictly dependent on external APIs and can run locally if the inference environment is properly set up.

### Setup

```bash
git clone https://github.com/gumi278/twinage.git
cd twinage
uv sync

cp .env.sample .env

```

Open the created `.env` file in a text editor and configure it for your environment.

```sh
# When using an external API (e.g., OpenAI)
OPENAI_API_KEY=sk-...

```

> [!IMPORTANT]
> When using a cloud API, setting a valid `OPENAI_API_KEY` is required.

> [!NOTE]
> If building a local inference environment, uncomment `HF_HOME` in `.env` to perform the initial setup in `twinage/HF`.
> This consolidates the environment under the `twinage` directory, so if you no longer need it, you can simply delete the repository.
> As a side effect, it will download models into `twinage/HF` on the first run.

#### RAG

Register the sample data into `chroma`.

```bash
uv run python -m twinage.util.indexer ./data/engrams/samples

```

It interprets the `*.json` files in `./data/engrams/samples` as an `Engram Schema` and builds the database in `./data/DATABASE`.

### Execution

```bash
uv run chainlit run twinage/webui.py

```

The web browser should automatically open `127.0.0.1:8000`.
Try asking it: *"What is Twinage?"* .

## Advanced

You can operate the system by replacing the registered JSON files and updating the database.

### Component Separation (Extractor)

Prepare a file (txt or md format) containing a conversation (1 turn) with generative AI, and feed it as input to the `extractor`.
Then register it using the `indexer`.

```bash
uv run python -m twinage.util.extractor chat-log.txt -o ./data/engrams/output.json
uv run python -m twinage.util.indexer ./data/engrams

```

> [!NOTE]
> The `extractor` assumes that `--session` and `--turn` are specified appropriately.
> `--session` is a *2-digit decimal number identifying the conversation thread on the same day*. `--turn` is a *3-digit decimal number indicating the turn count within that thread*.
> Because these are combined with the date to generate a unique ID internally, duplicate values will cause system inconsistencies.
> The date defaults to the execution date of the `extractor`, but you can change it if necessary.

---

For more details, try asking Twinage. Updates will be made at my own pace, so they might be slow, but I'll improve it little by little.

Feel free to reach out via [Issues](https://github.com/gumi278/twinage/issues).

---

## License

This project is licensed under the [MIT License](./LICENSE).
