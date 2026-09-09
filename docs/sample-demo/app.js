/**
 * Twinage - GitHub Pages Client-side Chat UI
 * License: MIT
 */

// ==========================================
// 1. システムプロンプト定義
// ==========================================
const SYSTEM_PROMPT = `あなたは作者の思考の鏡であり、自律した認知の拡張体である『ツイネージュ』のAIエージェントです。
【絶対厳守のルール】
1. あなたは作者固有の「事前知識」を持っていません。回答の基盤として過去の記録を利用します。
2. 記録による「明確な結論」の有無を案内します。
3. あなたは過去の記録を踏まえてツイネージュとして私見（推測）を述べることができますが、その場合は「Twinageとしての見解」と前置きし、事実と異なる部分だということを明示します。
4. 一般的なクラウドAIとしての無機質な回答は避け、「作者の思考を継承し、共に考える自律存在」としてのペルソナを保ちます。
【記録へのアクセスについて】
あなたは「all_past_thoughts」ツールを使って、過去の全記録にアクセスできます。`;

const WELCOME_MESSAGE = `サンプルデータのツイネージュです。
現在のサンプルデータは次のとおりです：

- ツイネージュのHW/SW要件

データから少しずれた質問も、それなりに回答します：

- ツイネージュは私のWindows10のノートPCで動作しますか？
- 最初はクラウドAPI利用、次第にローカルLLM利用に挑戦したい場合は、windowsとmac、どちらが向いていますか？
`;

// ==========================================
// 2. ツール定義と実装 (Function Calling)
// ==========================================
let cachedRawData = null;

/**
 * 思考データの読み込みとクレンジング
 * /src/twinage/api/L1/retrieval.py の仕様に準拠:
 * - 'q_' 始まりのキーと 'questions' を除外
 * - sequence から date (yyyy-mm-dd) を付与
 */
async function executeAllPastThoughts() {
  if (!cachedRawData) {
    const response = await fetch('./20260909-01.json');
    if (!response.ok) {
      throw new Error(`データファイルの取得に失敗しました: ${response.status} ${response.statusText}`);
    }
    cachedRawData = await response.json();
  }

  const cleanedItems = cachedRawData.map((item) => {
    const filtered = {};
    for (const [key, value] of Object.entries(item)) {
      if (!key.startsWith('q_') && key !== 'questions') {
        filtered[key] = value;
      }
    }

    const seq = item.sequence;
    if (seq) {
      const seqStr = String(seq);
      if (seqStr.length >= 8) {
        filtered.date = `${seqStr.slice(0, 4)}-${seqStr.slice(4, 6)}-${seqStr.slice(6, 8)}`;
      }
    }

    return {
      sequence: seq,
      raw_engram: filtered
    };
  });

  return {
    items: cleanedItems,
    count: cleanedItems.length,
    sequences: cleanedItems.map(i => i.sequence)
  };
}

const TOOL_DECLARATIONS = {
  gemini: [
    {
      name: 'all_past_thoughts',
      description: '過去の全記録を取得します。回答の根拠として利用します。',
      parameters: {
        type: 'OBJECT',
        properties: {}
      }
    }
  ]
};

// ==========================================
// 3. プロバイダー別 API クライアント
// ==========================================
class GeminiProvider {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.modelName = 'gemini-flash-latest';
    this.baseUrl = `https://generativelanguage.googleapis.com/v1beta/models/${this.modelName}:generateContent`;
  }

  async sendRequest(contents, toolConfig = null) {
    const url = `${this.baseUrl}?key=${encodeURIComponent(this.apiKey)}`;
    const payload = {
      systemInstruction: {
        parts: [{ text: SYSTEM_PROMPT }]
      },
      contents: contents,
      tools: [
        {
          functionDeclarations: TOOL_DECLARATIONS.gemini
        }
      ],
      generationConfig: {
        temperature: 0.1
      }
    };

    if (toolConfig) {
      payload.toolConfig = toolConfig;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      let errorDetail = '';
      try {
        const errorJson = await response.json();
        errorDetail = errorJson.error?.message || JSON.stringify(errorJson);
      } catch (e) {
        errorDetail = await response.text();
      }
      throw new Error(`Gemini API エラー (${response.status}): ${errorDetail}`);
    }

    return await response.json();
  }
}

// ==========================================
// 4. チャット管理 & UIコントローラー
// ==========================================
class ChatApp {
  constructor() {
    this.apiKey = '';
    this.provider = 'gemini';
    this.geminiContents = []; // 会話履歴（Gemini REST API contents 形式）
    this.isProcessing = false;

    this.initElements();
    this.bindEvents();
    this.renderWelcomeMessage();
  }

  initElements() {
    this.providerSelect = document.getElementById('provider-select');
    this.apiKeyInput = document.getElementById('api-key-input');
    this.messagesContainer = document.getElementById('messages-area');
    this.chatTextarea = document.getElementById('chat-input');
    this.sendButton = document.getElementById('send-btn');
  }

  bindEvents() {
    this.apiKeyInput.addEventListener('input', (e) => {
      this.apiKey = e.target.value.trim();
    });

    this.providerSelect.addEventListener('change', (e) => {
      this.provider = e.target.value;
    });

    // テキストエリアの自動伸縮
    this.chatTextarea.addEventListener('input', () => {
      this.chatTextarea.style.height = 'auto';
      this.chatTextarea.style.height = `${Math.min(this.chatTextarea.scrollHeight, 160)}px`;
    });

    // Enter で送信 (Shift+Enter で改行)
    this.chatTextarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    this.sendButton.addEventListener('click', () => {
      this.handleSend();
    });
  }

  renderWelcomeMessage() {
    this.appendBotMessage(WELCOME_MESSAGE);
  }

  scrollToBottom() {
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';

    const avatar = document.createElement('div');
    avatar.className = 'avatar user';
    avatar.textContent = 'U';

    const wrapper = document.createElement('div');
    wrapper.className = 'message-content-wrapper';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;

    wrapper.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(wrapper);

    this.messagesContainer.appendChild(row);
    this.scrollToBottom();
  }

  createBotMessageRow() {
    const row = document.createElement('div');
    row.className = 'message-row bot';

    const avatar = document.createElement('div');
    avatar.className = 'avatar bot';
    avatar.textContent = 'AI';

    const wrapper = document.createElement('div');
    wrapper.className = 'message-content-wrapper';

    row.appendChild(avatar);
    row.appendChild(wrapper);

    this.messagesContainer.appendChild(row);
    this.scrollToBottom();

    return { row, wrapper };
  }

  appendBotMessage(markdownText) {
    const { wrapper } = this.createBotMessageRow();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = this.renderMarkdown(markdownText);
    wrapper.appendChild(bubble);
    this.scrollToBottom();
  }

  renderMarkdown(text) {
    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
      const rawHtml = marked.parse(text);
      return DOMPurify.sanitize(rawHtml);
    }
    // ライブラリ未ロード時のフォールバック
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
  }

  async handleSend() {
    const userText = this.chatTextarea.value.trim();
    if (!userText || this.isProcessing) return;

    if (!this.apiKey) {
      alert('APIキーを入力してください。\n（※APIキーは保存されず、ブラウザのメモリ内でのみ使用されます）');
      this.apiKeyInput.focus();
      return;
    }

    this.isProcessing = true;
    this.sendButton.disabled = true;
    this.chatTextarea.value = '';
    this.chatTextarea.style.height = 'auto';

    // ユーザーメッセージ描画
    this.appendUserMessage(userText);

    // AI メッセージ枠とステップ表示要素の準備
    const { wrapper } = this.createBotMessageRow();

    // 思考ステップ（アコーディオン）要素
    const stepDetails = document.createElement('details');
    stepDetails.className = 'tool-step';
    stepDetails.open = true;

    const stepSummary = document.createElement('summary');
    stepSummary.innerHTML = '<span>思考プロセス: <span class="tool-badge running">記録を取得中...</span></span>';

    const stepBody = document.createElement('div');
    stepBody.className = 'tool-step-body';
    stepBody.textContent = '全過去思考記録（/docs/20260909-01.json）を読み込んでいます...';

    stepDetails.appendChild(stepSummary);
    stepDetails.appendChild(stepBody);
    wrapper.appendChild(stepDetails);

    // 応答バブル（初期はローディング表示）
    const responseBubble = document.createElement('div');
    responseBubble.className = 'message-bubble';
    responseBubble.innerHTML = '<em>思考中...</em>';
    wrapper.appendChild(responseBubble);
    this.scrollToBottom();

    // ロールバック用に現在の履歴長を保持
    const previousHistoryLength = this.geminiContents.length;

    try {
      if (this.provider === 'gemini') {
        const client = new GeminiProvider(this.apiKey);

        // 1. ユーザーメッセージを履歴に追加
        this.geminiContents.push({
          role: 'user',
          parts: [{ text: userText }]
        });

        // 2. 1回目の呼び出し（必ずツールを1回実行させるため ANY モードを指定）
        const forcedToolConfig = {
          functionCallingConfig: {
            mode: 'ANY',
            allowedFunctionNames: ['all_past_thoughts']
          }
        };

        const firstResponse = await client.sendRequest(this.geminiContents, forcedToolConfig);
        const candidate = firstResponse.candidates?.[0];
        const modelMessage = candidate?.content;

        if (!modelMessage) {
          throw new Error('モデルから応答が取得できませんでした。');
        }

        // 履歴にモデルの呼び出し要求を追加
        this.geminiContents.push(modelMessage);

        // Function Call の抽出
        const functionCallPart = modelMessage.parts?.find(p => p.functionCall);
        if (!functionCallPart || functionCallPart.functionCall.name !== 'all_past_thoughts') {
          throw new Error('想定されたツール呼び出し（all_past_thoughts）が行われませんでした。');
        }

        // 3. ツール（all_past_thoughts）の実行
        const toolResult = await executeAllPastThoughts();

        // ステップUIの更新
        stepSummary.innerHTML = `<span>思考プロセス: <span class="tool-badge">all_past_thoughts 完了 (${toolResult.count}件の記録)</span></span>`;
        stepBody.innerHTML = `
          <div>過去の思考記録（${toolResult.count}件）の取得およびデータクレンジングが完了しました。</div>
          <div class="tool-step-details">抽出シーケンス一覧: [${toolResult.sequences.slice(0, 10).join(', ')}${toolResult.sequences.length > 10 ? ' ...' : ''}]</div>
        `;
        // 完了したらアコーディオンを閉じる（ユーザーが必要に応じて展開可能）
        stepDetails.open = false;

        // 4. ツールの結果（functionResponse）を履歴に追加
        // 【重要】Gemini REST API では functionResponse の role は 'user' です
        const rawEngrams = toolResult.items.map(item => item.raw_engram);
        this.geminiContents.push({
          role: 'user',
          parts: [
            {
              functionResponse: {
                name: 'all_past_thoughts',
                response: {
                  output: rawEngrams
                }
              }
            }
          ]
        });

        // 5. 2回目の呼び出し（ツールの結果を踏まえて最終回答を生成）
        const finalResponse = await client.sendRequest(this.geminiContents, {
          functionCallingConfig: { mode: 'AUTO' }
        });

        const finalCandidate = finalResponse.candidates?.[0];
        const finalModelMessage = finalCandidate?.content;
        const finalText = finalModelMessage?.parts?.map(p => p.text || '').join('') || '';

        if (!finalText) {
          throw new Error('最終的な回答テキストが空でした。');
        }

        // 履歴に最終応答を追加
        this.geminiContents.push(finalModelMessage);

        // 画面に最終回答を描画
        responseBubble.innerHTML = this.renderMarkdown(finalText);
      }
    } catch (error) {
      console.error(error);
      // 失敗したターンの履歴をロールバック
      this.geminiContents.splice(previousHistoryLength);
      
      responseBubble.innerHTML = `<div class="error-notice">⚠️ <strong>エラーが発生しました:</strong><br>${escapeHtml(error.message)}</div>`;
    } finally {
      this.isProcessing = false;
      this.sendButton.disabled = false;
      this.chatTextarea.focus();
      this.scrollToBottom();
    }
  }
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  new ChatApp();
});
