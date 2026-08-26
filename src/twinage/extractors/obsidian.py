import os
import re
import json
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

from openai import OpenAI

load_dotenv()

# ==========================================
# 1. プロンプト定義 (Twinage Core Framework)
# ==========================================
SYSTEM_PROMPT = """
あなたは「認知アナリスト（Cognitive Analyst）」です。
提供されたユーザーとAIの対話ログを読み解き、ユーザーの思考プロセスを分解し、特定のフォーマット（Engram Schema）に従ってJSON形式で抽出してください。

# MISSION
単なる「会話の要約」をしてはいけません。会話の背後にあるユーザーの「悩み（起点）」「葛藤」「感情」「決断」などを切り出し、独立した成分として抽出することがあなたの任務です。

# EXTRACTION RULES (成分の定義)
対話の中から、意味の塊ごとに以下の項目を抽出してください。（1回の対話から数個の塊が抽出されることを想定しています）

- origin_point: この対話や思考が始まるきっかけとなった最初の「問い」や「出来事」。
- category: 以下の13の型から、その塊の性質に最も適合するものを1つ選択してください。
  1. "decision" (決定事項): 確定した方針や選択。
  2. "undecided" (未決定事項): 今後の課題、保留中のタスク。
  3. "constraint" (制約・前提条件): 思考を縛る物理的・論理的・時間的な壁。
  4. "rejection" (棄却): 検討したが、明確な理由で捨てた選択肢。
  5. "shift" (価値観・感情変化): 感情の起伏や、重要視するポイントの変化。
  6. "implicit" (暗黙の仮説): 無意識に「こうであるはずだ」と思い込んでいる前提。
  7. "tradeoff" (葛藤・トレードオフ): あちらを立てればこちらが立たず、という悩み。
  8. "workaround" (暫定措置・回避策): 根本解決ではないが、一時的に凌ぐための妥協案。
  9. "epiphany" (転換点・ひらめき): それまでの前提が覆ったアハ体験。
  10. "analogy" (思考の比喩): 複雑な事象を理解するために用いた別の概念への例え。
  11. "unknown" (既知の未知): 「これが分からないということが分かった」という発見。
  12. "hindsight" (反省・後知恵): 過去の判断に対する「今思えばこうだった」という振り返り。
  13. "wish" (望み・祈り・願い・理想): 現実の制約や技術的な実現可能性を一旦度外視した、純粋な欲求。
- content: その塊の端的な要約（1文）。
- description: なぜその思考に至ったかの客観的な説明。
- feel: その時ユーザーが感じていた主観的な感情や思想。
- story_path: 起点からそのカテゴリに至るまでの、対話を通じた思考の推移。
- questions: 後からこの思考に辿り着くための、未来の自分やユーザーが抱くであろう「自然な問い（疑問文）」を3〜6個の配列で生成。

# OUTPUT FORMAT
JSONモードでの確実な出力を保証するため、必ず以下の構造を持つJSONオブジェクトを出力してください。
{
  "engrams": [
    {
      "category": "tradeoff",
      "content": "...",
      "description": "...",
      "feel": "...",
      "origin_point": "...",
      "story_path": "...",
      "questions": ["疑問1?", "疑問2?"]
    }
  ]
}
"""

# ==========================================
# 2. システムロジック・ヘルパー関数
# ==========================================
REGISTRY_FILE = Path("SESSION-REGISTRY.json")

def check_environment():
    """環境変数 TWINAGE_ASSISTANT_NAME のチェック"""
    assistant_name = os.getenv("TWINAGE_ASSISTANT_NAME")
    if not assistant_name:
        raise ValueError(
            "[エラー] 環境変数 'TWINAGE_ASSISTANT_NAME' が設定されていません。\n"
            ".env ファイルに利用しているAIの名前（例: Gemini, Assistant, Claude）を定義してください。"
        )
    return assistant_name

def parse_frontmatter(content):
    """フロントマターから created(日付) と source(URL) を抽出する"""
    date_match = re.search(r'^created:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if not date_match:
        raise ValueError("フロントマターに 'created: YYYY-MM-DD' が見つかりません。")
    date_str = date_match.group(1).replace("-", "")

    source_match = re.search(r'^source:\s*(.+)$', content, re.MULTILINE)
    if not source_match:
        raise ValueError("フロントマターに 'source: URL' が見つかりません。")
    # "" や '' で囲まれている場合は除去
    source_url = source_match.group(1).strip('"\'').strip()

    return date_str, source_url

def get_or_create_session(date_str: str, source_url: str, filepath: Path) -> int:
    """台帳を参照し、セッション番号の取得または新規発番を行う"""
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except json.JSONDecodeError:
            registry = {}
    else:
        registry = {}

    filename = filepath.name

    if date_str not in registry:
        registry[date_str] = {}
    day_registry = registry[date_str]

    # 衝突・リトライ判定
    if source_url in day_registry:
        existing = day_registry[source_url]
        if existing["filename"] == filename:
            return existing["session"]
        else:
            raise ValueError(
                f"同じ対話スレッド(URL)が既に '{existing['filename']}' "
                f"として登録されています。重複を防ぐためスキップします。"
            )

    # 新規発番
    if not day_registry:
        next_session = 1
    else:
        next_session = max(item["session"] for item in day_registry.values()) + 1

    day_registry[source_url] = {
        "session": next_session,
        "filename": filename
    }
    
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    return next_session

def generate_opaque_id(date_str: str, session_num: int, turn_num: int, index_num: int) -> int:
    """Opaque IDの生成 (DATE:8, SESSION:2, TURN:3, INDEX:2)"""
    date_part = date_str[:8]
    session_part = f"{session_num:02d}"
    turn_part = f"{turn_num:03d}"
    index_part = f"{index_num:02d}"
    return int(f"{date_part}{session_part}{turn_part}{index_part}")

def extract_engram_from_llm(client: OpenAI, model: str, turn_text: str) -> list:
    """1ターン分のテキストをLLMに投げて成分リストを取得する"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下の対話ログからEngramを抽出してください:\n\n{turn_text}"}
        ],
        response_format={"type": "json_object"}
    )
    raw_output = response.choices[0].message.content
    parsed_json = json.loads(raw_output)
    return parsed_json.get("engrams", [])

# ==========================================
# 3. メインファイル処理
# ==========================================
def process_file(filepath: Path, assistant_name: str, client: OpenAI, model: str):
    """1つのマークダウンファイルを処理し、.tmp を経て .json を生成する"""
    json_path = filepath.with_suffix('.json')
    tmp_path = filepath.with_suffix('.tmp')

    if json_path.exists():
        print(f"スキップ: {json_path.name} は既に処理済みです。")
        return

    print(f"処理開始: {filepath.name}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        # フロントマター解析
        date_str, source_url = parse_frontmatter(content)
        # 台帳によるセッション番号取得
        session_num = get_or_create_session(date_str, source_url, filepath)
    except ValueError as e:
        print(f"  [スキップ/エラー] {e}")
        return

    parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
    body_text = parts[2] if len(parts) >= 3 else content

    # 環境変数からの発話者タグ設定（デフォルトはYou）
    user_name = os.getenv("TWINAGE_USER_NAME", "You")
    user_tag = f"**{user_name}**"
    assistant_tag = f"**{assistant_name}**"
    
    raw_turns = body_text.split(user_tag)
    
    # 有効なターンを抽出してカウント（フェイルファスト）
    valid_turns = []
    for raw_turn in raw_turns:
        raw_turn = raw_turn.strip()
        if not raw_turn or assistant_tag not in raw_turn:
            continue
        valid_turns.append(f"{user_tag}\n{raw_turn}")

    total_turns = len(valid_turns)
    print(f"  日付: {date_str}, セッション: {session_num:02d} (全 {total_turns} ターンを検出)")

    if total_turns == 0:
        print(f"  [スキップ] 有効なターンが見つかりませんでした。タグの設定等を確認してください。")
        return

    final_engrams = []
    turn_num = 1

    for turn_text in valid_turns:
        print(f"  -> Turn {turn_num:03d}/{total_turns:03d} を成分分離中... ", end="", flush=True)
        start_time = time.time()
        
        try:
            extracted_items = extract_engram_from_llm(client, model, turn_text)
            
            for index, item in enumerate(extracted_items, start=1):
                sequence_id = generate_opaque_id(date_str, session_num, turn_num, index)
                
                engram = {
                    "sequence": sequence_id,
                    "category": item.get("category", "undecided"),
                    "content": item.get("content", ""),
                    "description": item.get("description", ""),
                    "feel": item.get("feel", ""),
                    "origin_point": item.get("origin_point", ""),
                    "story_path": item.get("story_path", "")
                }
                
                questions = item.get("questions", [])
                for i, q in enumerate(questions[:6], start=1):
                    engram[f"q_{i}"] = q
                    
                final_engrams.append(engram)
                
            elapsed_time = time.time() - start_time
            minutes, seconds = divmod(int(elapsed_time), 60)
            print(f"完了 ({minutes}分{seconds}秒)")
                
        except Exception as e:
            print(f"\n  [エラー] Turn {turn_num:03d} の抽出に失敗しました: {e}")
            print(f"  [中断] {filepath.name} の処理を中止します。(.tmpは破棄されます)")
            return
            
        turn_num += 1

    print(f"  計 {len(final_engrams)} 件のEngram成分を {tmp_path.name} に書き込みます。")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(final_engrams, f, ensure_ascii=False, indent=2)

    tmp_path.rename(json_path)
    print(f"  完了: {json_path.name} を生成しました。")

def main():
    parser = argparse.ArgumentParser(description="Obsidian Web Clipperのログを一括で成分分離します")
    parser.add_argument("target", help="読み込むMarkdownファイルのパス、またはディレクトリ")
    parser.add_argument("--base_url", type=str, default=os.environ.get("TWINAGE_LLM_URL", None), help="カスタムエンドポイント")
    parser.add_argument("--model", type=str, default=os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o"), help="使用するモデル名")
    args = parser.parse_args()

    assistant_name = check_environment()
    api_key = os.environ.get("OPENAI_API_KEY", "dummy-key-for-local")
    client = OpenAI(api_key=api_key, base_url=args.base_url)
    
    target_path = Path(args.target)

    if target_path.is_file():
        process_file(target_path, assistant_name, client, args.model)
    elif target_path.is_dir():
        for md_file in target_path.glob("*.md"):
            process_file(md_file, assistant_name, client, args.model)
    else:
        print("[エラー] 指定されたパスが存在しません。")

if __name__ == "__main__":
    main()
