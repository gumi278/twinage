import os
import json
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

load_dotenv()

# ==========================================
# グローバル設定と遅延初期化
# ==========================================
DB_DIR = os.environ.get("TWINAGE_DB_DIR", "./data/DATABASE")
DATA_DIR = os.environ.get("TWINAGE_DATA_DIR", "./data/engrams")
EMB_URL = os.environ.get("TWINAGE_EMB_URL", None)
EMB_MODEL = os.environ.get("TWINAGE_EMB_MODEL", "text-embedding-3-small")

_collection = None


def get_collection():
    """
    ChromaDBコレクションを取得する（シングルトン / 遅延評価）
    """
    global _collection
    if _collection is None:
        openai_key = os.environ.get("OPENAI_API_KEY")
        emb_api_key = openai_key or "dummy-key"

        emb_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=emb_api_key,
            api_base=EMB_URL,
            model_name=EMB_MODEL
        )
        
        chroma_client = chromadb.PersistentClient(path=DB_DIR)
        try:
            _collection = chroma_client.get_collection(name="twinage_engrams", embedding_function=emb_fn)
        except Exception as e:
            raise RuntimeError(f"ChromaDBのコレクション取得に失敗しました: {e}")
            
    return _collection


# ==========================================
# ツール定義 (Function Calling用)
# ==========================================
SEARCH_PAST_THOUGHTS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_past_thoughts",
        "description": "記録をベクトル検索します。キーワードの羅列ではなく、必ず自然な文章（疑問文など）で検索クエリを構成してください。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然な文章で記述された検索クエリ"
                }
            },
            "required": ["query"],
        },
    }
}


# ==========================================
# 探索コアロジック
# ==========================================
def execute_flat_search(query: str, collection, data_dir: str, top_k: int = 20, category: Optional[str] = None):
    debug_logs = [f"🔍 [Debug] クエリ: {query}"]
    retrieved_items = []
    seen_sequences = set()  # 重複排除用のセット
    
    # 要求上限の丸め込み（最大80）
    actual_top_k = min(top_k, 80)
    debug_logs.append(f"  ℹ️ 要求件数: {top_k} -> 適用件数: {actual_top_k}")
    
    total_docs = collection.count()
    if total_docs == 0:
        return [], "データベースに記憶がありません。"
        
    try:
        # 重複を見越して最大160件取得
        search_limit = min(160, total_docs)
        
        where_clause = {"category": category} if category else None
        if where_clause:
            debug_logs.append(f"  ℹ️ フィルタ: {where_clause}")
            
        results = collection.query(
            query_texts=[query],
            n_results=search_limit,
            where=where_clause
        )
        
        hits = len(results['metadatas'][0]) if results['metadatas'] and results['metadatas'][0] else 0
        debug_logs.append(f"  ✅ DBヒット候補: {hits}件")
        
        if hits > 0:
            for meta in results['metadatas'][0]:
                seq = int(meta["sequence"])
                
                # ★ すでに取得済みのシーケンスならスキップ
                if seq in seen_sequences:
                    continue
                    
                engram_file = str(meta["engram_file"])
                file_path = os.path.join(data_dir, engram_file)
                
                if not os.path.exists(file_path):
                    continue
                    
                with open(file_path, "r", encoding="utf-8") as f:
                    engrams = json.load(f)
                    for engram in engrams:
                        if str(engram.get("sequence")) == str(seq):
                            
                            # --- データのクレンジングと変換 ---
                            # 1. "q_" で始まるキーと "questions" を除外した新しい辞書を作成
                            filtered_engram = {
                                k: v for k, v in engram.items() 
                                if not k.startswith("q_") and k != "questions"
                            }
                            
                            # 2. sequence (例: 202608150100511) から日付を生成して追加
                            seq_str = str(seq)
                            if len(seq_str) >= 8:
                                date_str = f"{seq_str[:4]}-{seq_str[4:6]}-{seq_str[6:8]}"
                                filtered_engram["date"] = date_str
                            # ----------------------------------

                            retrieved_items.append({
                                "sequence": seq,
                                "raw_engram": filtered_engram
                            })
                            # ★ 重複管理セットに登録
                            seen_sequences.add(seq)
                            break

                # ★ 要求件数に達したら打ち切り
                if len(retrieved_items) >= actual_top_k:
                    debug_logs.append(f"  🎯 ユニーク件数が {actual_top_k} 件に達したため走査を終了")
                    break
                            
    except Exception as e:
        debug_logs.append(f"  ❌ エラー発生: {e}")
        
    return retrieved_items, "\n".join(debug_logs)


def search_engrams(query: str, top_k: int = 5, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Twinageの記憶データベース（ChromaDB）を検索し、シーケンス番号順のアイテムリストを返す。
    
    戻り値:
        List[Dict[str, Any]]: 各要素は {"sequence": int, "raw_engram": dict}
    """
    collection = get_collection()
    retrieved_items, _ = execute_flat_search(
        query=query,
        collection=collection,
        data_dir=DATA_DIR,
        top_k=top_k,
        category=category
    )
    retrieved_items.sort(key=lambda x: x["sequence"])
    return retrieved_items
