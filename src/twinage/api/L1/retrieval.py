import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

load_dotenv()

# ==========================================
# グローバル設定と初期化
# ==========================================
DB_DIR = os.environ.get("TWINAGE_DB_DIR", "./data/DATABASE")
DATA_DIR = os.environ.get("TWINAGE_DATA_DIR", "./data/engrams")
EMB_URL = os.environ.get("TWINAGE_EMB_URL", None)
EMB_MODEL = os.environ.get("TWINAGE_EMB_MODEL", "text-embedding-3-small")

app = FastAPI(title="Twinage Retrieval API", version="1.2.0")

chroma_client = None
collection = None

@app.on_event("startup")
async def startup_event():
    global chroma_client, collection
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    emb_api_key = "dummy-key" if EMB_URL else openai_key
    
    if not emb_api_key:
        raise RuntimeError("APIキーが設定されていません。")

    emb_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=emb_api_key,
        api_base=EMB_URL,
        model_name=EMB_MODEL
    )
    
    chroma_client = chromadb.PersistentClient(path=DB_DIR)
    try:
        collection = chroma_client.get_collection(name="twinage_engrams", embedding_function=emb_fn)
    except Exception as e:
        raise RuntimeError(f"ChromaDBが見つかりません: {e}")

# ==========================================
# スキーマ定義
# ==========================================
class SearchQuery(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, description="取得件数（0以下はエラー、81以上は80に丸められます）")
    category: Optional[str] = Field(default=None, description="思考カテゴリでの絞り込み")

class SearchResult(BaseModel):
    items: List[Dict[str, Any]]
    debug_info: str

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
                            ctx = f"【カテゴリ】: {engram.get('category', '-')}\n"
                            ctx += f"【記録内容】: {engram.get('description', '詳細なし')}\n"
                            for k, v in engram.items():
                                if k not in ["sequence", "category", "description", "questions"] and not k.startswith("q_") and v:
                                    ctx += f"[{k}]: {v}\n"
                                    
                            retrieved_items.append({
                                "sequence": seq,
                                "context": ctx,
                                "raw_engram": engram
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

# ==========================================
# エンドポイント
# ==========================================
@app.post("/v1/engrams/search", response_model=SearchResult)
async def search_endpoint(request: SearchQuery):
    retrieved_items, debug_text = execute_flat_search(
        query=request.query,
        collection=collection,
        data_dir=DATA_DIR,
        top_k=request.top_k,
        category=request.category
    )
    
    retrieved_items.sort(key=lambda x: x["sequence"])
    
    return SearchResult(
        items=retrieved_items,
        debug_info=debug_text
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8082)