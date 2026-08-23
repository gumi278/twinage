import os
import glob
import json
import time
from dotenv import load_dotenv
load_dotenv()

import argparse
import chromadb
import chromadb.utils.embedding_functions as embedding_functions

def main():
    parser = argparse.ArgumentParser(description="Twinage Public Indexer - ディレクトリ内のEngramを一括でベクトルDBに登録します")

    parser.add_argument("data_dir", help="登録するJSONファイル群(*.json)が含まれるディレクトリ (例: ./data/engrams)")

    parser.add_argument("-d", "--db_dir", default=os.environ.get("TWINAGE_DB_DIR", "./data/DATABASE"), help="ChromaDBの保存先ディレクトリ")
    parser.add_argument("-b", "--batch_size", type=int, default=1000, help="1回あたりの登録件数（デフォルト: 1000）")
    parser.add_argument("-u", "--base_url", type=str, default=os.environ.get("TWINAGE_EMB_URL", None), help="カスタムエンドポイント (例: http://localhost:8081/v1)")
    parser.add_argument("-m", "--model", type=str, default=os.environ.get("TWINAGE_EMB_MODEL", "text-embedding-3-small"), help="使用するモデル名")
    args = parser.parse_args()

    # ディレクトリの存在確認
    if not os.path.isdir(args.data_dir):
        print(f"【エラー】ディレクトリ '{args.data_dir}' が見つかりません。")
        return

    # 指定ディレクトリ内の全 .json ファイルを検索
    search_pattern = os.path.join(args.data_dir, "*.json")
    json_files = glob.glob(search_pattern)

    if not json_files:
        print(f"【エラー】ディレクトリ '{args.data_dir}' 内にJSONファイルが見つかりません。")
        return

    # ==========================================
    # 1. 埋め込みモデル（Embedding Function）の設定
    # ==========================================
    api_key = os.environ.get("OPENAI_API_KEY", "dummy-key-for-local")
    emb_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key,
        api_base=args.base_url,
        model_name=args.model
    )

    # ==========================================
    # 2. ChromaDBの初期化
    # ==========================================
    os.makedirs(args.db_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=args.db_dir)
    collection = client.get_or_create_collection(
        name="twinage_engrams",
        embedding_function=emb_fn
    )

    # ==========================================
    # 3. データの読み込みと成分リストの作成 (全ファイル走破)
    # ==========================================
    ids_to_add = []
    documents_to_add = []
    metadatas_to_add = []

    print(f"ディレクトリ '{args.data_dir}' から {len(json_files)} 個のJSONファイルを検出しました。読み込みを開始します...")

    for file_path in json_files:
        file_name = os.path.basename(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                engrams = json.load(f)

            # JSONのフォーマットチェック（リスト形式であることを期待）
            if not isinstance(engrams, list):
                print(f"【警告】ファイル '{file_name}' は有効なEngramリストではないためスキップします。")
                continue

            for engram in engrams:
                sequence_id = str(engram.get("sequence"))
                keys_to_index = [k for k in engram.keys() if k not in ["sequence", "category", "description"]]

                for key in keys_to_index:
                    text_content = engram.get(key)
                    if not text_content:
                        continue

                    ids_to_add.append(f"{sequence_id}#{key}")
                    documents_to_add.append(str(text_content))
                    metadatas_to_add.append({
                        "sequence": int(sequence_id),
                        "category": str(engram.get("category", "-")),
                        "component_type": str(key),
                        "engram_file": file_name  # Agentと同じく、ファイル名のみをメタデータに刻む
                    })
        except Exception as e:
            print(f"【エラー】ファイル '{file_name}' の処理中にエラーが発生しました: {e}")

    # ==========================================
    # 4. バッチ処理（一定数ごとの分割登録）
    # ==========================================
    total_components = len(ids_to_add)

    if total_components == 0:
        print("登録する成分が見つかりませんでした。")
        return

    print(f"\n合計 {total_components} 件の成分を、{args.batch_size}件ずつChromaDBに登録します...")

    for i in range(0, total_components, args.batch_size):
        start_time = time.perf_counter()

        batch_ids = ids_to_add[i : i + args.batch_size]
        batch_docs = documents_to_add[i : i + args.batch_size]
        batch_metas = metadatas_to_add[i : i + args.batch_size]

        # 分割したリスト単位で upsert を実行
        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas
        )

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # 進捗と処理時間の表示（例: "  [1000 / 5432]： (3.45秒)"）
        current_done = min(i + args.batch_size, total_components)
        print(f"  [{current_done} / {total_components}]： {elapsed_time:.2f}秒")

    print("【成功】すべてのインデックス登録が完了しました！\n")

    # ==========================================
    # 5. テスト検索（Hello, World!）
    # ==========================================
    print("--- 動作テスト：検索してみましょう ---")
    query_text = input("検索したい言葉（未入力で終了）：")

    if query_text:
        results = collection.query(query_texts=[query_text], n_results=3)
        print("\n【検索結果】")
        for i in range(len(results['ids'][0])):
            seq, comp_type = results['ids'][0][i].split("#")
            meta = results['metadatas'][0][i]
            doc = results['documents'][0][i]
            file_ref = meta['engram_file']
            print(f"- [Seq: {seq}] [{meta['category']}] ({comp_type}) from {file_ref}\n  内容: {doc}\n")

if __name__ == "__main__":
    main()
