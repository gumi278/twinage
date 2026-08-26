# Twinage (RAG-based Thought Retrieval Agent)

[English](README.md) | [日本語](README.ja.md)

Twinage is a RAG agent system that stores fragments of past thought processes and specifications in a vector database, referencing them to reconstruct contexts autonomously.

This repository provides a minimal platform configuration, encompassing thought extraction, an interactive UI, and an evaluation node that makes ternary judgments. The system adopts an independent microservices architecture, separated into "L1 (Infrastructure Layer)" responsible for retrieving pure records, and "L2 (Application Layer)" which utilizes those memories.

- [Showcase (Issues)](https://github.com/gumi278/twinage/issues)

> [!NOTE]
> Please note that inquiries to the issues may receive primary responses directly from Twinage (the AI).

---

## Requirements

The system uses an OpenAI-compatible API for communication. It works with both Cloud APIs and Local LLMs, provided the models meet the following requirements:

### Model Requirements
- Supports Reasoning (Thought processes)
- Supports Function Calling (Tool Calling)

### Tested Environment
The author develops and tests on the following setup:
- `MacBook Pro M1Pro UMA16GB/SSD512GB`
- `macOS Tahoe`
- `llama.cpp/llama-server`
- `unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL`
- `gpustack/bge-m3-GGUF`

> [!NOTE]
> Equivalent operation is expected in a VRAM 16GB environment (though it is very tight).
> By selecting a model size that matches your VRAM, it should be able to run on systems with smaller capacities.

---

## Quick Start

The fastest way to get the chat-based Twinage up and running.

### 1. Setup
Ensure that `python` and `uv` are installed on your system.

```bash
git clone https://github.com/gumi278/twinage.git
cd twinage
uv sync

cp .env.sample .env
```

Open the generated `.env` file in a text editor and configure it according to your environment. The network settings (hosts, ports, etc.) for each node are centralized in `.env` to prevent configuration sprawl.

> [!NOTE]
> `twinage/webui.py` is implemented using `chainlit`. Due to its architecture, it does not align perfectly with `.env` for its own initialization. Therefore, the WebUI's host and port are provided via command-line parameters.

> [!NOTE]
> If you are building a local inference environment, uncomment `HF_HOME` in the `.env` file to build it initially in `twinage/HF`. If you no longer need it, you can keep your environment clean by simply deleting the entire repository.


### 2. Constructing the Thought Space (Database)

Register the bundled sample data into `chroma` to build the database.

```bash
uv run python -m twinage.util.indexer ./data/engrams/samples
```

### 3. Launching the Memory Infrastructure (L1 Retrieval API)

Start the core API dedicated to database retrieval, which serves as the foundation for the WebUI and various agents. Open a separate terminal and execute the following. Launch options are automatically read from `.env`, and absolute paths are protected by using the module execution method.

```bash
uv run python -m twinage.api.L1.retrieval
```

### 4. Launching the WebUI (L2 Application)

With the L1 API running, launch the WebUI from your original terminal. It connects to the APIs based on your `.env` configurations, but binds to its own network settings via command-line arguments.

```bash
uv run chainlit run twinage/webui.py --host 127.0.0.1 --port 7860
```

Your web browser will open automatically. Try asking it, "What is Twinage?" (Note: Sample data is in Japanese).

---

## Separation of Thought Components

While the official Twinage implementation serves as an FAQ, you can build your own "Personal Guide" by isolating and accumulating logs of your personal interactions with AI as "thought components," and using those records to generate responses.

> [!NOTE]
> The interaction logs used here are not limited to Twinage; you can also use conversation logs from cloud AI services such as `ChatGPT` and `Claude`.

### Preparation Before Extraction (Setting Environment Variables)
The extractor identifies AI and user speaking turns by looking for bold name tags (e.g., `**ChatGPT**`) within the interaction logs. To ensure the logs are parsed correctly, please configure the following environment variables in your `.env` file before running the extraction.

*   **`TWINAGE_ASSISTANT_NAME` (Required)**: Specify the name of the AI you interacted with (e.g., `ChatGPT`, `Claude`, `Gemini`, `Assistant`). If this is not set, an error will occur and the process will not start.
*   **`TWINAGE_USER_NAME` (Optional)**: Specify your (the user's) name. If not set, it defaults to `You`.

> [!WARNING]
> If the specified name tags are not found anywhere in the markdown file, the extractor will assume there are no valid turns and skip the file. Please ensure that the exact text in the markdown file perfectly matches your environment variables.

### Automatic Extraction from Obsidian Web Clipper
A dedicated extractor is included to process markdown-formatted chat logs (`.md`) saved via Obsidian Web Clipper or similar tools.

```bash
uv run python -m twinage.extractors.obsidian ./data/my_chat_logs/
```

By simply specifying a directory, it reads all files in bulk and separates them into thought components (`.json`). System-level management, such as assigning session numbers and avoiding duplicates, is handled automatically by the registry (`SESSION-REGISTRY.json`).

### Registering to a Custom Database (ChromaDB)

Once extraction is complete, update the database using the `indexer`.

> [!WARNING]
> **Important Note When Building Your Own Twinage**
> 
> If you run the registration as is, your personal thoughts will be mixed into the same database as the "Twinage Official FAQ (Sample Data)" created in the Quick Start.
> If you want to create a completely private thought space, switch the database using one of the following methods:
>
> **Method A: Separate the Storage Location (Recommended)**
>
> Add an environment variable to your `.env` file to specify a custom database directory.
> `TWINAGE_DB_DIR=./data/MY_DATABASE`
>
> **Method B: Discard the Samples**
>
> If you do not need the sample data, delete the entire `./data/DATABASE` folder that was already created before running the command.

After setting up your environment, index your data with the following command:

```bash
uv run python -m twinage.util.indexer ./data/my_chat_logs/
```

---

## Guide to Consulting Twinage (Tips)

For detailed specifications of Twinage, how to configure environment variables, command options, etc., we have adopted the approach of "asking Twinage itself" rather than writing lengthy explanations in the README. The Twinage configured with the bundled sample data acts as a guide and mascot to explain the system.

### Customizing the Source Code

Twinage remembers the "design philosophy" and "background of specifications" of this system, but it has not memorized the full text (physical files) of the source code.
If you wish to customize internal logic, such as `twinage/extractors/obsidian.py`, **please paste the content (text) of the source code into the chat when asking your question.** This allows for more accurate and specific code modification proposals.

---

## Advanced Usage: Evaluate Node (L2 Evaluate API)

Twinage also functions as an "Evaluate Node" that controls and supports the decision-making of external autonomous agents (like Dify).

You can launch the evaluation API, which utilizes L1 in the background, with the following command:

```bash
uv run python -m twinage.api.L2.evaluate
```

When an external system posts an action plan like `{"proposal": "I want to do X"}` to this endpoint, Twinage checks it against past memories and philosophies, and returns a strict JSON response indicating whether the action is "ACCEPT", "REJECT", or "UNKNOWN". This ensures that the ideological consistency of the system is maintained while preserving development freedom on the publisher's side.

---

## License

This project is licensed under the [MIT License](./LICENSE).
