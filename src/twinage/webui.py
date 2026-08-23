import os
import json
from dotenv import load_dotenv
load_dotenv()

import chainlit as cl
import chromadb
import chromadb.utils.embedding_functions as embedding_functions
from openai import AsyncOpenAI

# ==========================================
# グローバル設定と初期化
# ==========================================
DB_DIR = os.environ.get("TWINAGE_DB_DIR", "./data/DATABASE")
DATA_DIR = os.environ.get("TWINAGE_DATA_DIR", "./data/engrams")
EMB_URL = os.environ.get("TWINAGE_EMB_URL", None)
EMB_MODEL = os.environ.get("TWINAGE_EMB_MODEL", "text-embedding-3-small")
LLM_URL = os.environ.get("TWINAGE_LLM_URL", None)
LLM_MODEL = os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o")

# 接続クライアント（グローバルで保持）
chroma_client = None
collection = None
llm_client = None

@cl.on_chat_start
async def on_chat_start():
    global chroma_client, collection, llm_client
    
    # OpenAI / Embedding APIキーの設定
    openai_key = os.environ.get("OPENAI_API_KEY")
    emb_api_key = "dummy-key" if EMB_URL else openai_key
    
    if not emb_api_key:
        await cl.Message(content="【エラー】クラウド利用時は OPENAI_API_KEY を設定してください。").send()
        return

    # クライアントの初期化
    emb_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=emb_api_key,
        api_base=EMB_URL,
        model_name=EMB_MODEL
    )
    
    chroma_client = chromadb.PersistentClient(path=DB_DIR)
    try:
        collection = chroma_client.get_collection(name="twinage_engrams", embedding_function=emb_fn)
    except Exception:
        await cl.Message(content="【エラー】ChromaDBが見つかりません。先にインデクサーを実行してください。").send()
        return

    llm_api_key = "dummy-key" if LLM_URL else openai_key
    llm_client = AsyncOpenAI(api_key=llm_api_key, base_url=LLM_URL)

    system_prompt = ("""
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

    )
    
    welcome_message = (
        "Twinage Agent 起動完了。記録の軌跡にアクセス可能です。何について話しましょうか？\n\n"
        "Twinage Agent initialized. The traces of past records are now accessible. What shall we talk about?"
    )
    
    cl.user_session.set("messages", [{"role": "system", "content": system_prompt}])
    await cl.Message(content=welcome_message).send()

# ==========================================
# 探索コアロジック（フラットな全件検索）
# ==========================================
def execute_flat_search(query: str, collection, data_dir: str, top_k: int = 20):
    """
    全データから純粋にベクトル検索を行い、上位結果を返す。
    ※ bge-m3の特性上、queryは自然言語であることを前提とする。
    """
    debug_logs = [f"🔍 [Debug] クエリ: {query}"]
    retrieved_items = []
    
    total_docs = collection.count()
    if total_docs == 0:
        return [], "データベースに記憶がありません。"
        
    try:
        # DBの総件数以上の要求を防ぐ安全装置だけは残す
        safe_n_results = min(top_k, total_docs)
        
        results = collection.query(
            query_texts=[query],
            n_results=safe_n_results
        )
        
        hits = len(results['metadatas'][0]) if results['metadatas'] and results['metadatas'][0] else 0
        debug_logs.append(f"  ✅ DBヒット: {hits}件")
        
        if hits > 0:
            for meta in results['metadatas'][0]:
                seq = int(meta["sequence"])
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
                                    
                            retrieved_items.append({"sequence": seq, "context": ctx})
                            break
                            
    except Exception as e:
        debug_logs.append(f"  ❌ エラー発生: {e}")
        
    return retrieved_items, "\n".join(debug_logs)


# ==========================================
# ツール（Function Calling）
# ==========================================
@cl.step(name="データベース検索")
async def search_past_thoughts(query: str) -> str:
    # --- 重要 ---
    # AgentへのDescriptionで「必ず自然言語で検索すること（例: Twinageの動作環境を教えてください）」
    # と強く指示されていることが、このフラット検索成功の絶対条件です。
    
    current_step = cl.context.current_step
    
    retrieved_items, debug_text = execute_flat_search(query, collection, DATA_DIR, top_k=5)
    
    print(debug_text)
    
    if not retrieved_items:
        current_step.output = debug_text + "\n\n結果: 関連する記憶は見つかりませんでした。"
        return "指定されたクエリに関連する過去の記録は見つかりませんでした。"
        
    retrieved_items.sort(key=lambda x: x["sequence"])
    
    # 最新の7件だけを残す（リストの末尾から7個分を切り出す）
    retrieved_items = retrieved_items[-7:]    
    
    sorted_contexts = [item["context"] for item in retrieved_items]
    combined_text = "\n\n".join(sorted_contexts)
    
    seq_list = [item["sequence"] for item in retrieved_items]
    current_step.output = debug_text + f"\n\n====================\n抽出したシーケンス: {seq_list}\n\n{combined_text}"
    
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
# メッセージ処理（反復思考ループ）
# ==========================================
@cl.on_message
async def on_message(message: cl.Message):
    messages = cl.user_session.get("messages")
    messages.append({"role": "user", "content": message.content})
    
    # ストリーミング表示用の空メッセージを作成
    msg = cl.Message(content="")
    
    max_iterations = 3
    for iteration in range(max_iterations):
        # 1回目の思考では強制的にツールを利用させる (The Nuclear Option)
        current_tool_choice = {"type": "function", "function": {"name": "search_past_thoughts"}} if iteration == 0 else "auto"
        
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=tools,
            tool_choice=current_tool_choice,
            temperature=0.1
        )

        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            # アシスタントのツール呼び出し要求を履歴に追加
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "search_past_thoughts":
                    query = function_args.get("query", message.content)
                    
                    # Chainlitの非同期コンテキストでツールを実行
                    tool_result = await search_past_thoughts(query=query)
                    
                    # ツールの実行結果を履歴に追加
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result,
                    })
            # 検索結果を得たのでループの先頭に戻り、再度LLMに考えさせる
            continue
            
        else:
            # ツール呼び出しがない（回答を生成し始めた）場合、ストリーミング出力
            stream_response = await llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                stream=True,
                temperature=0.1
            )
            
            final_content = ""
            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    final_content += text
                    # Chainlit UIにリアルタイムで反映
                    await msg.stream_token(text)
            
            await msg.send()
            messages.append({"role": "assistant", "content": final_content})
            cl.user_session.set("messages", messages)
            break
            
    else:
        # max_iterationsを使い切った場合
        await cl.Message(content="申し訳ありません、思考の整理が追いつきませんでした。別の角度から質問していただけますか？").send()

