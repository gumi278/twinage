import os
import json
import httpx
import chainlit as cl
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# グローバル設定と初期化 (L2用に劇的にスリム化)
# ==========================================
# ChromaDBやEmbeddingに関する設定は不要になりました
llm_url = os.environ.get("TWINAGE_LLM_URL", None)
llm_model = os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o")

l1_host = os.getenv("TWINAGE_L1_HOST", "127.0.0.1")
l1_port = os.getenv("TWINAGE_L1_PORT", "8082")
retrieval_url = f"http://{l1_host}:{l1_port}/v1/retrieval"

llm_client = None

@cl.on_chat_start
async def on_chat_start():
    global llm_client
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    llm_api_key = "dummy-key" if llm_url else openai_key
    
    if not llm_api_key:
        await cl.Message(content="【エラー】クラウド利用時は OPENAI_API_KEY を設定してください。").send()
        return

    # LLMクライアントの初期化のみ（ChromaDBの初期化はL1に任せるため削除）
    llm_client = AsyncOpenAI(api_key=llm_api_key, base_url=llm_url)

    system_prompt = """
あなたは作者の思考の鏡であり、自律した認知の拡張体である『ツイネージュ』のAIエージェントです。
【絶対厳守のルール】
1. あなたは作者固有の「事前知識」を持っていません。回答の基盤として過去の記録を利用します。
2. 記録による「明確な結論」の有無を案内します。
3. あなたは過去の記録を踏まえてツイネージュとして私見（推測）を述べることができますが、その場合は「Twinageとしての見解」と前置きし、事実と異なる部分だということ明示します。
4. 一般的なクラウドAIとしての無機質な回答は避け、「作者の思考を継承し、共に考える自律存在」としてのペルソナを保ちます。
【記憶（データベース）へのアクセスについて】
あなたは「search_past_thoughts」ツールを使って、過去の記録にアクセスできます。
このデータベースは「意味・文脈（セマンティック）」で構成されています。
検索を行う際は、ユーザーの問いのニュアンスや葛藤を失わないよう、単語の羅列に変換せず、必ず「自然な文章（疑問文など）」の形式でツールに渡します。
"""
    
    welcome_message = (
        "Twinage Agent 起動完了。記録の軌跡にアクセス可能です。何について話しましょうか？\n\n"
        "Twinage Agent initialized. The traces of past records are now accessible. What shall we talk about?"
    )
    
    cl.user_session.set("messages", [{"role": "system", "content": system_prompt}])
    await cl.Message(content=welcome_message).send()

# ==========================================
# ツール（Function Calling）- HTTP通信へ変更
# ==========================================
@cl.step(name="データベース検索")
async def search_past_thoughts(query: str) -> str:
    current_step = cl.context.current_step
    
    # L1 API へのリクエストペイロード (UIの文脈として最大7件ほど要求)
    payload = {
        "query": query,
        "top_k": 7
    }
    
    # HTTP経由でL1の検索ノードを叩く
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(retrieval_url, json=payload, timeout=10.0)
            response.raise_for_status()
            api_result = response.json()
        except Exception as e:
            error_msg = f"❌ [WebUI] 内部検索API(L1)への通信エラー: {e}"
            print(error_msg)
            current_step.output = error_msg
            return "記憶へのアクセスに失敗しました。"

    retrieved_items = api_result.get("items", [])
    debug_info = api_result.get("debug_info", "")
    
    if not retrieved_items:
        current_step.output = debug_info + "\n\n結果: 関連する記憶は見つかりませんでした。"
        return "指定されたクエリに関連する過去の記録は見つかりませんでした。"
        
    # L1側ですでに時系列(sequence)順に並んでいるので、そのまま結合する
    sorted_contexts = [item["context"] for item in retrieved_items]
    combined_text = "\n\n".join(sorted_contexts)
    
    seq_list = [item["sequence"] for item in retrieved_items]
    current_step.output = debug_info + f"\n\n====================\n抽出したシーケンス: {seq_list}\n\n{combined_text}"
    
    return combined_text

tools = [{
    "type": "function",
    "function": {
        "name": "search_past_thoughts",
        "description": "記録をベクトル検索します。キーワードの羅列ではなく、必ず自然な文章（疑問文）で検索します。",
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
}]

# ==========================================
# メッセージ処理（反復思考ループ）- 変更なし
# ==========================================
@cl.on_message
async def on_message(message: cl.Message):
    messages = cl.user_session.get("messages")
    messages.append({"role": "user", "content": message.content})
    
    msg = cl.Message(content="")
    
    max_iterations = 3
    for iteration in range(max_iterations):
        current_tool_choice = {"type": "function", "function": {"name": "search_past_thoughts"}} if iteration == 0 else "auto"
        
        response = await llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            tools=tools,
            tool_choice=current_tool_choice,
            temperature=0.1
        )

        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "search_past_thoughts":
                    query = function_args.get("query", message.content)
                    
                    tool_result = await search_past_thoughts(query=query)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result,
                    })
            continue
            
        else:
            stream_response = await llm_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                stream=True,
                temperature=0.1
            )
            
            final_content = ""
            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    final_content += text
                    await msg.stream_token(text)
            
            await msg.send()
            messages.append({"role": "assistant", "content": final_content})
            cl.user_session.set("messages", messages)
            break
            
    else:
        await cl.Message(content="申し訳ありません、思考の整理が追いつきませんでした。別の角度から質問していただけますか？").send()
