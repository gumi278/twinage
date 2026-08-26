# Twinage: RAG-based Thought Retrieval Agent

[English](README.md) | [日本語](README.ja.md)

Twinage is a RAG agent system that accumulates fragments of past thought processes and specifications in a vector database, referring to them to reconstruct context on its own.

This repository provides a minimal platform configuration, spanning from thought extraction and conversational UI to a decision node that judges using three values. The system adopts an independent microservices architecture, separated into "L1 (Infrastructure Layer)" responsible for pure record retrieval, and "L2 (Application Layer)" which utilizes those memories.

- [Showcase (issues)](https://github.com/gumi278/twinage/issues)
*Please note: The Twinage (AI) will occasionally provide initial responses to inquiries in the issues section. We appreciate your understanding.*

---

## Requirements

The system uses an OpenAI-compatible API for communication. It operates with both Cloud APIs and local LLMs, but the model used must meet the following requirements.

### Model Requirements
- Reasoning process support
- Function Calling (Tool Calling) support

### Tested Environment
The author develops under the following configuration:
- `MacBook Pro M1Pro UMA16GB/SSD512GB`
- `macOS Tahoe`
- `llama.cpp/llama-server`
- `unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL`
- `gpustack/bge-m3-GGUF`

> [!NOTE]
> Equivalent operation can be expected in a 16GB VRAM environment (it is very tight).
> By selecting a model size suited to your VRAM capacity, the system should operate even with smaller capacities.

---

## Quick Start

The fastest steps to get the chat-type Twinage running.

### 1. Setup
As a prerequisite, `python` and `uv` must be installed.

```bash
git clone https://github.com/gumi278/twinage.git
cd twinage
uv sync

cp .env.sample .env
```

Open the created `.env` file in a text editor and configure it according to your environment.

```sh
# A valid key is required if using a Cloud API
OPENAI_API_KEY=sk-...
```

> [!NOTE]
> If building a local inference environment, uncomment `HF_HOME` in the `.env` file to build it initially in `twinage/HF`. If no longer needed, simply deleting the repository will keep your environment clean.


### 2. Building the Thought Space (Database)

Register the included sample data to `chroma` and build the database.

```bash
uv run python -m twinage.util.indexer ./data/engrams/samples
```

### 3. Starting the Memory Infrastructure (L1 Retrieval API)

Start the core API dedicated to database search, which serves as the foundation for the WebUI and various agents. Please execute this in a separate terminal.

```bash
uv run uvicorn twinage.api.L1.retrieval:app --port 8082
```

### 4. Starting the WebUI (L2 Application)

With the L1 API running, start the WebUI from the original terminal.

```bash
uv run chainlit run twinage/webui.py
```

Your web browser will automatically open `127.0.0.1:8000`. Try asking, "What is Twinage?"

---

## Thought Component Separation

While the official Twinage implementation is an FAQ, you can separate and accumulate your own chat logs with AI as "thought components," building a "personal guide" that uses those records to respond.

### Automatic Extraction from Obsidian Web Clipper
A dedicated extractor is included to process markdown-formatted chat logs (`.md`) saved via Obsidian Web Clipper or similar tools.

```bash
uv run python -m twinage.extractors.obsidian ./data/my_chat_logs/
```

Simply by specifying the directory, it reads a batch of files and separates them into thought components (`.json`). System management tasks, such as assigning session numbers and avoiding duplicates, are handled automatically by the registry (`SESSION-REGISTRY.json`).

### Registering to a Custom Database (ChromaDB)

Once extraction is complete, update the database using the `indexer`.

> [!WARNING]
> **Notes on Building Your Own Twinage**
> If you execute the registration as-is, your personal thoughts will be mixed into the same database as the "Official Twinage FAQ (sample data)" created in the Quick Start.
> If you wish to create a completely personal thought space, please switch the database using one of the following methods:
> **Method A: Separate the Save Location (Recommended)**
> Add an environment variable to the `.env` file and specify the directory for your personal database.
> `TWINAGE_DB_DIR=./data/MY_DATABASE`
> **Method B: Discard the Samples**
> If the sample data is unnecessary, delete the entire created `./data/DATABASE` folder before running.

After preparing the environment, index your data with the following command.

```bash
uv run python -m twinage.util.indexer ./data/my_chat_logs/
```

---

## Guide to Consulting Twinage (Tips)

For detailed specifications, environment variable settings, command options, etc., we have adopted the approach of "asking Twinage itself" instead of writing at length in the README. The Twinage configured with the repository's sample data acts as both a guide and mascot to explain the system.

### Customizing the Source Code

Twinage remembers the "design philosophy" and "specification background" of this system, but it has not memorized the entire source code (physical files).
If you want to customize internal logic such as `twinage/extractors/obsidian.py`, **please paste the content (text) of the source code into the chat when asking your question.** This will enable more accurate and specific code modification proposals.

---

## Advanced Use: Judgment Node (L2 Judgment API)

Twinage also functions as a "judgment node" to control the decision-making of external autonomous agents (such as Dify).

With the following command, you can start the evaluation API that uses L1 in the background (Port 8083).

```bash
uv run uvicorn twinage.api.L2.judgement:app --port 8083
```

When an external system POSTs an action plan like `{"proposal": "I want to do X"}` to this endpoint, Twinage compares it against past memories and philosophy, replying with strict JSON stating whether the action is "ACCEPT", "REJECT", or "UNKNOWN" (Undecidable). This makes it possible to maintain the ideological consistency of the system while allowing publishers freedom in development.

---

## License

This project is published under the [MIT License](./LICENSE).
