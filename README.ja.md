# ツイネージュ（Twinage: RAG-based Thought Retrieval Agent）

[English](README.md) | [日本語](README.ja.md)

Twinageは、過去の思考プロセスや仕様の断片をベクトルデータベースに蓄積し、それらを参照してシステム自身が文脈を再構成するRAGエージェントシステムです。

本リポジトリは、思考の抽出、対話UI、そして三値で評価するノードに至るまで、プラットフォームとしての最小構成を提供します。システムは独立したマイクロサービス・アーキテクチャを採用しており、純粋な記録の引き出しを担う「L1（インフラ層）」と、その記憶を利用する「L2（アプリケーション層）」に分離されています。

- [ショーケース（issues）](https://github.com/gumi278/twinage/issues)

> [!NOTE]
> issuesへの問い合わせは、ツイネージュ（AI）が適宜、一次応答を行います。予めご了承ください。

---

## 前提条件 （Requirements）

通信にはOpenAI互換APIを使用しています。クラウドAPI、ローカルLLMのどちらでも動作しますが、使用するモデルには以下の必須要件があります。

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

### 1. セットアップ
前提として `python` および `uv` がインストールされている必要があります。

```bash
git clone https://github.com/gumi278/twinage.git
cd twinage
uv sync

cp .env.sample .env
```

作成した `.env` をテキストエディタで開き、利用する環境に合わせて設定します。本システムを構成する各ノードのネットワーク設定（ホスト、ポート番号など）は、設定の散逸を防ぐため `.env` に集約されています。

> [!NOTE]
> twinage/webui.pyは `chainlit` で実装しています。その関係上、`.env` と相性がよくないので、webui自身の設定は起動コマンドのパラメータとして与えることにしています。

> [!NOTE]
> ローカルで推論環境を構築する場合は `.env` の `HF_HOME` のコメントを外せば `twinage/HF` に初回構築します。不要になったらリポジトリごと削除するだけで環境をクリーンに保てます。


### 2. 思考空間（データベース）の構築

同梱のサンプルデータを `chroma` に登録し、データベースを構築します。

```bash
uv run python -m twinage.util.indexer ./data/engrams/samples
```

### 3. 記憶インフラ（L1 Retrieval API）の起動

WebUIや各種エージェントの土台となる、データベース検索専用のコアAPIを起動します。別のターミナルを開いて実行してください。起動オプションは `.env` から自動で読み込まれ、モジュール起動方式により絶対パスが保護されます。

```bash
uv run python -m twinage.api.L1.retrieval
```

### 4. WebUI（L2 Application）の起動

L1 APIが起動している状態で、元のターミナルからWebUIを起動します。WebUIは通信先を `.env` から読み込みますが、自身の起動設定はコマンドライン引数に従います。

```bash
uv run chainlit run twinage/webui.py --host 127.0.0.1 --port 7860
```

自動でWebブラウザが開きます。まずは「ツイネージュって何？」と尋ねてみてください。

---

## 思考の成分分離

公式Twinage実装はFAQですが、あなた自身がAIと対話したログを「思考の成分」として分離・蓄積し、その記録を用いて応答を行う「自身の案内人」を構築できます。

### Obsidian Web Clipperからの自動抽出
Obsidian Web Clipper等で保存したマークダウン形式の対話ログ（`.md`）を処理するための専用抽出器が同梱されています。

```bash
uv run python -m twinage.extractors.obsidian ./data/my_chat_logs/
```

ディレクトリを指定するだけで、ファイル群を一括で読み込み、思考成分（`.json`）に分離します。セッション番号の採番や重複の回避といったシステム都合の管理は、台帳(`SESSION-REGISTRY.json`)によって自動で行われます。

### 独自のデータベース（ChromaDB）への登録

抽出が完了したら `indexer` を使ってデータベースを更新します。

> [!WARNING]
> **独自のツイネージュを構築する場合の注意点**
> 
> そのまま登録を実行すると、クイックスタートで作成した「Twinage公式のFAQ（サンプルデータ）」と同じデータベースにあなたの個人的な思考が混ざってしまいます。
> 完全に自分専用の思考空間を作りたい場合は、以下のいずれかの方法でデータベースを切り替えてください。
>
> **方法A: 保存先を分ける（推奨）**
>
> `.env` ファイルに環境変数を追加し、自分用のデータベースディレクトリを指定します。
> `TWINAGE_DB_DIR=./data/MY_DATABASE`
>
> **方法B: サンプルを破棄する**
>
> サンプルデータが不要な場合は、作成済みの `./data/DATABASE` フォルダを丸ごと削除してから実行してください。

環境を整えた後、以下のコマンドで自身のデータをインデックス化します。

```bash
uv run python -m twinage.util.indexer ./data/my_chat_logs/
```

---

## ツイネージュへの相談ガイド（Tips）

Twinageの詳しい仕様、環境変数の設定方法、コマンドのオプション等については、READMEに長々と書く代わりに「ツイネージュ自身に尋ねる」ことを採択しています。リポジトリ同梱のサンプルデータで構成されたツイネージュが、案内人兼看板娘としてシステムを解説する試みを採っています。

### ソースコードのカスタマイズについて

ツイネージュは本システムの「設計思想」や「仕様の背景」を記憶していますが、ソースコードの全文（物理ファイル）を暗記しているわけではありません。
もし `twinage/extractors/obsidian.py` などの内部ロジックをカスタマイズしたい場合は、**質問の際にソースコードの中身（テキスト）をチャットに貼り付けて渡してあげてください。** より正確で具体的なコードの改修提案が可能になります。

---

## 高度な利用：評価ノード（L2 Evaluate API）

Twinageは外部の自律エージェント（Dify等）の意思決定を制御・支援する「評価ノード」としても機能します。

以下のコマンドで、L1を裏側で利用する評価用APIを起動できます。

```bash
uv run python -m twinage.api.L2.evaluate
```

外部システムからこのエンドポイントに対して `{"proposal": "〇〇したい"}` という行動計画をPOSTすると、Twinageは過去の記憶と哲学に照らし合わせ、その行動が「ACCEPT（受容）」か「REJECT（棄却）」または「UNKNOWN（判断不可）」かを厳密なJSONで回答します。これにより、パブリッシャー側に開発の自由が維持されたまま、システムの思想的整合性を保つことが可能です。

---

## ライセンス (License)

本プロジェクトは [MIT License](./LICENSE) のもとで公開されています。
