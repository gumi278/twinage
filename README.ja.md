# ツイネージュ（Twinage: RAG-based Thought Retrieval Agent）

[English](README.md) | [日本語](README.ja.md)

Twinageは、過去の思考プロセスや仕様の断片をベクトルデータベースに蓄積し、それらを参照して再構成するためのRAG（Retrieval-Augmented Generation）エージェントシステムです。本リポジトリは、構成を最小限に留めた初期実装（Hello World版）を提供します。

- [ショーケース（issues）](https://github.com/gumi278/twinage/issues)

issuesへの問い合わせはツイネージュが適宜、一次応答を行います。
予めご了承ください。

---
## 前提条件 （Requirements）

通信にはOpenAI互換APIを使用しています。そのためクラウドの外部API、ローカルLLMのどちらでも動作しますが、使用するモデルには以下の必須要件があります。

### LLM必須要件（Model Requirements）

- Reasoning（思考プロセス）対応
- Function Calling (Tool Calling) 対応

### 動作確認済み環境（Tested Environment）

作者は以下の構成で開発を行っています：
- `MacBook Pro M1Pro UMA16GB/SSD512GB`
- `macOS Tahoe`
- `llama.cpp/llama-server`
- `unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL`
- `gpustack/bge-m3-GGUF`

> [!NOTE]
> VRAM16GB環境であれば同等の動作が見込めます（非常にタイトです）。
> VRAM量に合わせてモデルの大きさを選定すれば、より小さな容量でも稼働できるはずです。

---

## クイックスタート

チャット型ツイネージュを動かすための最短手順です。

### 前提条件

- `python`
- `uv`

次の前提で話を進めます。

- OpenAIのAPI利用( `gpt-4o` / `text-embedding-3-small` )
- チャットは `127.0.0.1:8000`
- 作業ディレクトリ（カレントディレクトリ）は `twinage`
- 同梱のサンプルデータ

> [!NOTE]
> 共通理解として外部APIの利用を前提にしています。
> Twinageは外部API依存ではなく、推論環境を整備すればローカルでも動作します。

### セットアップ

```bash
git clone https://github.com/gumi278/twinage.git
cd twinage
uv sync

cp .env.sample .env
```

作成した .env をテキストエディタで開き、利用する環境に合わせて設定を編集します。

```sh
# 外部APIを利用する場合（OpenAI等）
OPENAI_API_KEY=sk-...
```

> [!IMPORTANT]
> クラウドAPIを利用する場合、有効な `OPENAI_API_KEY` の設定が必須です。

> [!NOTE]
> ローカルで推論環境を構築する場合は `.env` の `HF_HOME` のコメントを外せば `twinage/HF` に初回構築します。
> これにより `twinage` ディレクトリの下に環境が集結するので、不要になったらリポジトリを削除するだけです。
> 副作用としては、`twinage/HF` に再取得するので初回はダウンロードから始まります。

#### RAG

サンプルのデータを `chroma` に登録します。

```bash
uv run python -m twinage.util.indexer ./data/engrams/samples
```

`./data/engrams/samples` にある `*.json` ファイルを `Engram Schema` と解釈して `./data/DATABASE` にデータベースを構築します。

### 実行

```bash
uv run chainlit run twinage/webui.py
```

自動でWebブラウザが`127.0.0.1:8000`を開くはずです。
「ツイネージュって何？」と尋ねてみてください。

## 発展

登録するJSONを差し替えてデータベースを更新して稼働できます。

### 成分分離

生成AIとの対話（１ターン）を保存したファイルを用意（txtまたはmd形式）、`extractor` に入力として与えます。
その後に `indexer` を使って登録します。

```bash
uv run python -m twinage.util.extractor chat-log.txt -o ./data/engrams/output.json
uv run python -m twinage.util.indexer ./data/engrams
```

> [!NOTE]
> `extractor` では `--session` と `--turn` を適切に指定することが前提です。
> 
> `--session` は *同日の対話スレッドを識別する10進数２桁の数値*、 `--turn` は *対話スレッド内の対話ターン数を示す10進数3桁の数値* です。
> これらと日付を組み合わせて内部でユニークIDを生成する都合上、同一が存在するとシステムとして不整合を起こします。
> 
> 日付は `extractor` 実行時の日付がつきますが、必要であれば変更してください。

---

細かいところはツイネージュに尋ねてみてください。更新はマイペースに行うので遅いかもしれません、少しずつやっていきます。

[Issues](https://github.com/gumi278/twinage/issues)でも受け付けています、お気軽にどうぞ。

---

## ライセンス (License)

本プロジェクトは [MIT License](./LICENSE) のもとで公開されています。
