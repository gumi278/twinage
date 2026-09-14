import os
import re
import json
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Optional, Union
from openai import AsyncOpenAI
from dotenv import load_dotenv

from twinage.api.L1.retrieval import SEARCH_PAST_THOUGHTS_TOOL, search_engrams

load_dotenv()

# ==========================================
# サービス設定
# ==========================================
app = FastAPI(title="Twinage L2 AIRI Proxy API", version="3.2.0")

# CORS設定（アバターUI・Webクライアントからのアクセスを全許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# バックエンドLLM設定
LLM_URL = os.environ.get("TWINAGE_LLM_URL", None)
LLM_MODEL = os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o")

openai_key = os.environ.get("OPENAI_API_KEY")
llm_api_key = openai_key or "dummy-key"
llm_client = AsyncOpenAI(api_key=llm_api_key, base_url=LLM_URL)

tools = [SEARCH_PAST_THOUGHTS_TOOL]


# ==========================================
# OpenAI互換 スキーマ定義
# ==========================================
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]], Any] = ""
    name: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "twinage-airi"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

    model_config = ConfigDict(extra="allow")


# ==========================================
# ツール実行関数 (L1ライブラリ直接呼出)
# ==========================================
async def execute_search_past_thoughts(query: str) -> str:
    """
    L1記憶検索モジュールを直接呼び出し、記憶（Engram）のJSON文字列を取得する。
    """
    print(f"🔍 [AIRI Proxy Tool] L1記憶検索実行: query={query}")
    try:
        items = search_engrams(query=query, top_k=7)
        if not items:
            print("ℹ️ [AIRI Proxy Tool] L1検索結果: 該当なし")
            return "指定されたクエリに関連する過去の記憶は見つかりませんでした。"
        raw_engrams = [item.get("raw_engram", {}) for item in items]
        print(f"✅ [AIRI Proxy Tool] L1から {len(items)} 件の記憶を取得しました。")
        return json.dumps(raw_engrams, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ [AIRI Proxy Tool] L1検索エラー: {e}")
        return "記憶へのアクセスに失敗しました。"


# ==========================================
# 翻訳層（正規表現によるタグ正規化）
# ==========================================
def normalize_act_tags(text: str) -> str:
    """
    発話テキスト中の <|ACT {...}|> タグを正規表現で検出し、
    タグ内の intensity（1〜5のスケール）を 0.0〜1.0 のスケールへ正規化（数値 / 5.0）する。
    """
    def replace_act_tag(match: re.Match) -> str:
        raw_payload = match.group(1)
        try:
            data = json.loads(raw_payload)
            if isinstance(data, dict):
                # emotion辞書内のintensityを変換
                if "emotion" in data and isinstance(data["emotion"], dict):
                    if "intensity" in data["emotion"]:
                        val = float(data["emotion"]["intensity"])
                        data["emotion"]["intensity"] = round(max(0.0, min(1.0, val / 5.0)), 2)
                # トップレベルにintensityがある場合も対応
                elif "intensity" in data:
                    val = float(data["intensity"])
                    data["intensity"] = round(max(0.0, min(1.0, val / 5.0)), 2)

                return f'<|ACT {json.dumps(data, ensure_ascii=False)}|>'
        except Exception:
            pass

        # JSONパースが失敗した場合の正規表現フォールバック置換
        def replace_intensity_val(m: re.Match) -> str:
            try:
                val = float(m.group(2))
                norm_val = round(max(0.0, min(1.0, val / 5.0)), 2)
                return f"{m.group(1)}{norm_val}"
            except Exception:
                return m.group(0)

        converted_payload = re.sub(
            r'("intensity"\s*:\s*)(\d+(?:\.\d+)?)',
            replace_intensity_val,
            raw_payload
        )
        return f'<|ACT {converted_payload}|>'

    # <|ACT {...}|> パターンの置換
    normalized = re.sub(r'<\|ACT\s+(\{.*?\})\s*\|>', replace_act_tag, text)
    return normalized


def process_llm_speech_text(raw_content: str) -> str:
    """
    LLMからの応答JSONから speech_text を取得し、ACTタグの数値を正規化する。
    """
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    speech_text = ""
    try:
        parsed_json = json.loads(cleaned)
        if isinstance(parsed_json, dict):
            speech_text = str(parsed_json.get("speech_text", "")).strip()
            if not speech_text and parsed_json:
                speech_text = str(list(parsed_json.values())[0]).strip()
        else:
            speech_text = str(parsed_json).strip()
    except json.JSONDecodeError:
        speech_text = cleaned

    if not speech_text:
        speech_text = '<|ACT {"emotion":{"name":"normal", "intensity":3}, "motion":"nod"}|> はい、承知いたしました。'

    # 正規表現で intensity (1〜5 -> 0.0〜1.0) に変換
    normalized_text = normalize_act_tags(speech_text)

    # 返信の先頭に ACT タグが存在しない場合のフォールバック付与
    if not normalized_text.startswith("<|ACT"):
        normalized_text = f'<|ACT {{"emotion":{{"name":"normal", "intensity":0.6}}, "motion":"nod"}}|> {normalized_text}'

    return normalized_text


# ==========================================
# エンドポイント
# ==========================================
@app.get("/v1/models")
async def list_models():
    """
    AIRIの疎通確認・モデル一覧取得用
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "twinage-airi",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "twinage"
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Function Calling反復ループ + 正規表現タグ正規化フロー:
    1. messages配列の初期構築（Twinageシステムプロンプト + 対話履歴）
    2. 最大3回の反復思考ループ（記憶検索ツール呼び出し）
    3. LLMが生成した speech_text 内の <|ACT ...|> タグの intensity (1〜5) を 0.0〜1.0 に正規化
    4. OpenAI API形式でレスポンス返却
    """
    print(f"\n🎭 [AIRI Proxy] リクエスト受信: messages数={len(request.messages)}, stream={request.stream}")

    # 1. messages の初期構築
    system_prompts = []
    conversation_history = []
    latest_user_content = ""

    for msg in request.messages:
        content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
        if msg.role == "system":
            system_prompts.append(content_str)
        else:
            if msg.role == "user":
                latest_user_content = content_str
            conversation_history.append({"role": msg.role, "content": content_str})

    extra_system_instruction = "\n\n".join(system_prompts) if system_prompts else ""

    base_system_prompt = """あなたはTwinageの概念を体現するアバターAIです。
【思考と行動の指針】
1. ユーザーからの問いかけに対し、必要に応じて `search_past_thoughts` ツールを使用して過去の記憶（Engram）を検索してください。
2. 検索された記憶データを総合的に解釈し、自身の感情と発話内容を決定してください。
3. 最終的な回答は、必ず以下のJSONフォーマットのみで出力してください（余計な解説やマークダウンは一切含めないでください）。

【AIRIの感情表現ルール】
返信の最初は必ずACTトークンから始め、発話の途中で感情が変わる位置に新しいACTトークンを挿入してください。
- 形式: <|ACT {"emotion":{"name":"emotion名", "intensity":1から5の数値}, "motion":"短い動作"}|>
- 重要: intensityは過去の記憶（Engram）と同じ「1から5のスケール」で指定してください（1が最弱、5が最強）。
- 利用可能なemotion名: surprised, troubled, thinking, confused, happy, normal など
- 間の表現: <|DELAY 秒数|>

【出力JSONフォーマット】
{
  "speech_text": "<|ACT {\\\"emotion\\\":{\\\"name\\\":\\\"happy\\\", \\\"intensity\\\":4}, \\\"motion\\\":\\\"smile\\\"}|> 実際に発話するテキスト（口語体）"
}"""

    if extra_system_instruction:
        integrated_system_prompt = f"{base_system_prompt}\n\n【キャラクター追加設定】\n{extra_system_instruction}"
    else:
        integrated_system_prompt = base_system_prompt

    messages = [{"role": "system", "content": integrated_system_prompt}]
    messages.extend(conversation_history)

    # 2. 反復思考ループ（Function Calling Loop）
    max_iterations = 3
    final_translated_text = ""

    for iteration in range(max_iterations):
        current_tool_choice = (
            {"type": "function", "function": {"name": "search_past_thoughts"}}
            if (iteration == 0 and latest_user_content)
            else "auto"
        )

        try:
            response = await llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=tools,
                tool_choice=current_tool_choice,
                temperature=request.temperature if request.temperature is not None else 0.7,
                response_format={"type": "json_object"} if iteration > 0 else None
            )
        except Exception as e:
            print(f"❌ [AIRI Proxy] LLM推論エラー (iter={iteration}): {e}")
            final_translated_text = '<|ACT {"emotion":{"name":"confused", "intensity":0.4}, "motion":"tilt_head"}|> 記憶の引き出しに失敗しました。'
            break

        response_message = response.choices[0].message

        # ツール呼び出し要求がある場合
        if response_message.tool_calls:
            print(f"💡 [AIRI Proxy Iter {iteration}] ツール呼び出し検出: {len(response_message.tool_calls)} 件")
            messages.append(response_message)

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except Exception:
                    function_args = {}

                if function_name == "search_past_thoughts":
                    query = function_args.get("query", latest_user_content)
                    tool_result = await execute_search_past_thoughts(query=query)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result,
                    })
            continue

        # ツール呼び出しがない場合（最終回答フェーズ）
        else:
            raw_content = response_message.content or "{}"
            print(f"✨ [AIRI Proxy Iter {iteration}] 最終回答受信: {raw_content[:80]}...")
            final_translated_text = process_llm_speech_text(raw_content)
            break

    else:
        print("⚠️ [AIRI Proxy] 反復思考ループの上限に達しました。")
        final_translated_text = '<|ACT {"emotion":{"name":"confused", "intensity":0.4}, "motion":"tilt_head"}|> 思考の整理が追いつきませんでした。'

    print(f"🎬 [AIRI Proxy] 最終出力テキスト: {final_translated_text}")

    # 3. OpenAI API互換レスポンスの生成
    response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(time.time())

    # ストリーミングリクエストの場合 (SSE)
    if request.stream:
        async def sse_generator():
            chunk_data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created_timestamp,
                "model": request.model or "twinage-airi",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": final_translated_text
                        },
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    # 非ストリーミングリクエストの場合
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created_timestamp,
        "model": request.model or "twinage-airi",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_translated_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }


# ==========================================
# メイン起動処理
# ==========================================
if __name__ == "__main__":
    import uvicorn

    load_dotenv()

    l2_host = os.getenv("TWINAGE_L2_AIRI_HOST", os.getenv("TWINAGE_L2_HOST", "127.0.0.1"))
    l2_port = int(os.getenv("TWINAGE_L2_AIRI_PORT", 8084))

    reload_str = os.getenv("TWINAGE_RELOAD", "True").lower()
    is_reload = reload_str in ("true", "1", "t", "yes")

    print(f"[Twinage L2 AIRI Proxy] Starting API on http://{l2_host}:{l2_port}")
    print(f"[Twinage L2 AIRI Proxy] Target LLM: {LLM_MODEL} ({LLM_URL or 'OpenAI Official API'})")
    print(f"[Twinage L2 AIRI Proxy] Reload mode: {is_reload}")

    uvicorn.run(
        "twinage.api.L2.airi_proxy:app",
        host=l2_host,
        port=l2_port,
        reload=is_reload
    )
