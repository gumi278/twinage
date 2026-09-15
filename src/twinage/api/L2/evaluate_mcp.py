from mcp.server.fastmcp import FastMCP
from fastapi import HTTPException

from twinage.api.L2.evaluate import evaluate_endpoint, EvaluateRequest

mcp = FastMCP("Twinage Decision Node")

@mcp.tool()
async def evaluate_architecture(proposal: str, context: str = "") -> str:
    """
    ユーザーの過去の記憶（Engram）に基づいて、提案された実装方針やアーキテクチャが適切かどうかを判断し、ACCEPT/REJECT/UNKNOWNと理由を返します。
    """
    try:
        request = EvaluateRequest(proposal=proposal, context_info=context)
        response = await evaluate_endpoint(request)
        
        result = (
            f"【判定結果】: {response.evaluate}\n"
            f"【推論理由】: {response.reasoning}\n"
            f"【引用記憶シーケンス】: {response.cited_sequences}"
        )
        return result

    except HTTPException as e:
        return f"Twinage内部エラー: {e.detail}"
    except Exception as e:
        return f"予期せぬエラーが発生しました: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
    