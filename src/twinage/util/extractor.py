import os
import json
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import argparse
from openai import OpenAI

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
# 2. システムロジック
# ==========================================
def generate_opaque_id(date_str: str, session_num: int, turn_num: int, index_num: int) -> int:
    """
    Twinageの仕様に従い、15桁の整数Opaque IDを生成する
    [DATE:8][SESSION:2][TURN:3][INDEX:2]
    """
    date_part = date_str[:8]
    session_part = f"{session_num:02d}"
    turn_part = f"{turn_num:03d}"
    index_part = f"{index_num:02d}"
    
    return int(f"{date_part}{session_part}{turn_part}{index_part}")

def extract_engrams(client: OpenAI, chat_log_text: str) -> list:
    """LLMを呼び出して思考の成分分離を実行する"""
    print("AIが対話ログを解析し、成分分離（Engram Extraction）を行っています...")
    
    response = client.chat.completions.create(
        model="gpt-4o",  # gpt-4o-mini 等でも動作します
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下の対話ログからEngramを抽出してください:\n\n{chat_log_text}"}
        ],
        response_format={"type": "json_object"}
    )
    
    raw_output = response.choices[0].message.content
    parsed_json = json.loads(raw_output)
    
    return parsed_json.get("engrams", [])

# ==========================================
# 3. メイン処理 (ファイルI/Oとデータ整形)
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Twinage Public Extractor - チャットログから成分分離を行います")
    parser.add_argument("input_file", help="入力するチャットログファイル（.txt または .md 等）へのパス")
    parser.add_argument("-o", "--output", default="engrams_output.json", help="出力するJSONファイル名（デフォルト: engrams_output.json）")
    parser.add_argument("-s", "--session", type=int, default=1, help="セッション番号（1〜99, デフォルト: 1）")
    parser.add_argument("-t", "--turn", type=int, default=1, help="ターン番号（1〜999, デフォルト: 1）")
    parser.add_argument("--base_url", type=str, default=os.environ.get("TWINAGE_LLM_URL", None), help="カスタムエンドポイント (例: http://localhost:1234/v1)")
    parser.add_argument("--model", type=str, default=os.environ.get("TWINAGE_LLM_MODEL", "gpt-4o"), help="使用するモデル名")
    args = parser.parse_args()

    # 1. APIキーの取得
    api_key = os.environ.get("OPENAI_API_KEY", "dummy-key-for-local")

    # 2. 入力ファイルの読み込み
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            chat_log = f.read()
    except FileNotFoundError:
        print(f"【エラー】入力ファイル '{args.input_file}' が見つかりません。")
        return

    client = OpenAI(
        api_key=api_key,
        base_url=args.base_url
    )

    # 3. 成分分離の実行
    try:
        extracted_items = extract_engrams(client, chat_log)
    except Exception as e:
        print(f"【エラー】LLMの抽出中にエラーが発生しました: {e}")
        return

    # 4. Twinageフォーマットへの最終成形とID採番
    # 日付は現時点を採用しているが、任意。
    today_str = datetime.now().strftime("%Y%m%d")
    final_engrams = []
    
    for index, item in enumerate(extracted_items, start=1):
        # Opaque IDの採番
        sequence_id = generate_opaque_id(today_str, args.session, args.turn, index)
        
        # 共通型スキーマの構築
        engram = {
            "sequence": sequence_id,
            "category": item.get("category", "undecided"),
            "content": item.get("content", ""),
            "description": item.get("description", ""),
            "feel": item.get("feel", ""),
            "origin_point": item.get("origin_point", ""),
            "story_path": item.get("story_path", "")
        }
        
        # LLMが生成した 'questions' 配列を q_1 ~ q_6 に展開
        questions = item.get("questions", [])
        for i, q in enumerate(questions[:6], start=1):
            engram[f"q_{i}"] = q
            
        final_engrams.append(engram)

    # 5. ファイル出力
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(final_engrams, f, ensure_ascii=False, indent=2)
        
    print(f"\n【成功】{len(final_engrams)}件のEngram成分を '{args.output}' に保存しました。")
    print("このJSONファイルをTwinage（ChromaDB）のインデクサーに読み込ませることで、RAG検索が可能になります。")

if __name__ == "__main__":
    main()
