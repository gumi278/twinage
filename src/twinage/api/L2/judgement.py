import os
import json
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# スキーマ定義
# ==========================================
class JudgmentRequest(BaseModel):
    """外部システム（Dify等）からの判定リクエスト"""
    proposal: str = Field(..., description="判定対象となる提案や行動計画")
    context_info: Optional[str] = Field(default=None, description="判定の補助となる背景情報")
    category_filter: Optional[str] = Field(default=None, description="検索時のカテゴリ絞り込み")

class JudgmentResponse(BaseModel):
    """APIが返却する判定結果の構造"""
    judgment: Literal["ACCEPT", "REJECT", "UNKNOWN"] = Field(description="判定結果")
    reasoning: str = Field(description="判定の根拠となった推論")
    cited_sequences: List[int] = Field(default_factory=list, description="引用した記憶のシーケンス番号")

# ==========================================
# サービス設定
# ==========================================
app = FastAPI(title="Twinage Judgment API", version="1.0.0")

# 内部に秘匿された検索API（第2層）のエンドポイント
INTERNAL_SEARCH_API_URL = os.environ.get("TWINAGE_SEARCH_API_URL", "http://127.0.0.1:8082/v1/engrams/search")

LLM_URL = os.environ.get("TWINAGE_LLM_URL", None)
LLM_MODEL = os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o")

openai_key = os.environ.get("OPENAI_API_KEY")
llm_api_key = "dummy-key" if LLM_URL else openai_key
llm_client = AsyncOpenAI(api_key=llm_api_key, base_url=LLM_URL)

# ==========================================
# エンドポイント
# ==========================================
@app.post("/v1/evaluate", response_model=JudgmentResponse)
async def evaluate_endpoint(request: JudgmentRequest):
    """
    外部からの提案を受け取り、内部のRetrieval APIを叩いて記憶を引き出し、
    LLMによる3値判定(ACCEPT/REJECT/UNKNOWN)を下して返却します。
    """
    print(f"\n🔄 [Judgment API] 判定リクエスト受信: {request.proposal[:40]}...")
    
    # 1. 内部のRetrieval APIへのリクエスト構築
    search_query = request.proposal
    if request.context_info:
        search_query += f"\n背景: {request.context_info}"
        
    payload = {"query": search_query, "top_k": 15}
    if request.category_filter:
        payload["category"] = request.category_filter

    # 2. 内部HTTP通信（多段API）
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(INTERNAL_SEARCH_API_URL, json=payload, timeout=10.0)
            response.raise_for_status()
            api_result = response.json()
        except Exception as e:
            print(f"❌ [Judgment API] 内部検索API通信エラー: {e}")
            raise HTTPException(status_code=500, detail=f"内部記憶ノードへのアクセスに失敗しました: {e}")

    items = api_result.get("items", [])
    
    if not items:
        memory_context = "関連する過去の記憶は見つかりませんでした。"
    else:
        memory_context = "\n\n---\n\n".join(
            [f"[Sequence: {item['sequence']}]\n{item['context']}" for item in items]
        )

    # 3. LLMプロンプトの構築
    system_prompt = """
あなたはTwinageの「判定ノード」です。提供された過去の記憶（Engram）のみに基づき、以下のJSONフォーマットで判定を下してください。
余計なテキストは一切含めず、純粋なJSONオブジェクトのみを出力してください。

【出力フォーマット (JSON)】
{
  "judgment": "ACCEPT" | "REJECT" | "UNKNOWN",
  "reasoning": "判定の根拠となった推論の解説（自然言語）",
  "cited_sequences": [引用した記憶のSequence番号の数値リスト]
}

【判定ルール】
- 記憶と照らし合わせて作者の思想・決定に合致し、明確に肯定できる場合は "ACCEPT"
- 記憶にある作者の制約(constraint)や過去に棄却した方針(rejection)に抵触する場合は "REJECT"
- 判断するための明確な記憶が存在しない、または判断が分かれる場合は必ず "UNKNOWN" とすること
"""
    user_prompt = f"【評価対象の提案】\n{request.proposal}\n\n【背景情報】\n{request.context_info or 'なし'}\n\n【過去の記憶（古い順）】\n{memory_context}"

    # 4. LLM推論 (Single-Shot)
    try:
        completion = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        raw_json_str = completion.choices[0].message.content
        parsed_data = json.loads(raw_json_str)
        return JudgmentResponse(**parsed_data)
        
    except Exception as e:
        print(f"❌ [Judgment API] LLM推論エラー: {e}")
        raise HTTPException(status_code=500, detail=f"LLMによる判定処理に失敗しました: {e}")

if __name__ == "__main__":
    import uvicorn
    # Retrieval API(8082)と衝突しないようにポート8083で起動
    uvicorn.run(app, host="127.0.0.1", port=8083)
