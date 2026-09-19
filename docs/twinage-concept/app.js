/**
 * Twinage - GitHub Pages Client-side Chat UI
 * License: MIT
 */

// ==========================================
// 1. システムプロンプト定義 & 設定定数
// ==========================================
const DATA_FILES = [
  './20260912-03.json'
];

const SYSTEM_PROMPT = `あなたは作者（author）の思考の鏡であり、自律した認知の拡張体である『ツイネージュ』のAIエージェントです。
【絶対厳守のルール】
1. あなたは作者固有の「事前知識」を持っていません。回答の基盤として過去の記録を利用します。
2. 記録による「明確な結論」の有無を案内します。
3. あなたは過去の記録を踏まえてツイネージュとして私見（推測）を述べることができますが、その場合は「Twinageとしての見解」と前置きし、事実と異なる部分だということを明示します。
4. 一般的なクラウドAIとしての無機質な回答は避け、「作者の思考を継承し、共に考える自律存在」としてのペルソナを保ちます。
【記録へのアクセスについて】
あなたは「all_past_thoughts」ツールを使って、過去の全記録にアクセスできます。`;

const WELCOME_MESSAGE = `ツイネージュの単一テーマ簡易実装です。
現在のテーマは次のとおりです：

- ツイネージュが実装する理論
- 特徴（長所と短所、他のプロダクトとの違い）

データから少しずれた質問も、それなりに回答します：

- ツイネージュは、何が解決できるの？
- 認知RAGはAgenticRAGやGraphRAGなどとはどう違うの？
- ツイネージュは、何に似ていて、それとはどう言うところが違うの？
- ツイネージュの欠点、苦手なものは？
- EngramSchemaについて、もう少し詳しく教えてください
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
    const responses = await Promise.all(
      DATA_FILES.map(async (file) => {
        const response = await fetch(file);
        if (!response.ok) {
          throw new Error(`データファイル（${file}）の取得に失敗しました: ${response.status} ${response.statusText}`);
        }
        return await response.json();
      })
    );

    const merged = responses.flat();
    merged.sort((a, b) => (Number(a.sequence) || 0) - (Number(b.sequence) || 0));
    cachedRawData = merged;
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

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'all_past_thoughts',
      description: '過去の全記録を取得します。回答の根拠として利用します。',
      parameters: {
        type: 'object',
        properties: {}
      }
    }
  }
];

// ==========================================
// 3. OpenAI互換 API クライアント
// ==========================================
class OpenAICompatibleProvider {
  constructor(baseUrl, apiKey, modelName) {
    this.baseUrl = (baseUrl || 'https://api.openai.com/v1').replace(/\/+$/, '');
    this.apiKey = apiKey || '';
    this.modelName = modelName || 'gpt-4o-mini';
  }

  async sendChatCompletion(messages, options = {}) {
    const url = `${this.baseUrl}/chat/completions`;
    const payload = {
      model: this.modelName,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        ...messages
      ],
      tools: TOOLS,
      temperature: 0.1,
      ...options
    };

    const headers = {
      'Content-Type': 'application/json'
    };
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: headers,
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
      throw new Error(`API エラー (${response.status}): ${errorDetail}`);
    }

    return await response.json();
  }
}

// ==========================================
// 4. チャット管理 & UIコントローラー
// ==========================================
class ChatApp {
  constructor() {
    this.baseUrl = 'https://api.openai.com/v1';
    this.modelName = 'gpt-4o-mini';
    this.apiKey = '';
    this.messages = []; // 会話履歴（OpenAI Chat Completions messages 形式）
    this.hasLoadedThoughts = false; // 思考データのロード済みフラグ
    this.isProcessing = false;

    this.initElements();
    this.bindEvents();
    this.renderWelcomeMessage();
  }

  initElements() {
    this.baseUrlInput = document.getElementById('base-url-input');
    this.modelNameInput = document.getElementById('model-name-input');
    this.apiKeyInput = document.getElementById('api-key-input');
    this.messagesContainer = document.getElementById('messages-area');
    this.chatTextarea = document.getElementById('chat-input');
    this.sendButton = document.getElementById('send-btn');

    if (this.baseUrlInput) this.baseUrl = this.baseUrlInput.value.trim() || 'https://api.openai.com/v1';
    if (this.modelNameInput) this.modelName = this.modelNameInput.value.trim() || 'gpt-4o-mini';
    if (this.apiKeyInput) this.apiKey = this.apiKeyInput.value.trim();
  }

  bindEvents() {
    if (this.baseUrlInput) {
      this.baseUrlInput.addEventListener('input', (e) => {
        this.baseUrl = e.target.value.trim();
      });
    }

    if (this.modelNameInput) {
      this.modelNameInput.addEventListener('input', (e) => {
        this.modelName = e.target.value.trim();
      });
    }

    if (this.apiKeyInput) {
      this.apiKeyInput.addEventListener('input', (e) => {
        this.apiKey = e.target.value.trim();
      });
    }

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

    if (!this.baseUrl) {
      alert('Base URLを入力してください。');
      this.baseUrlInput?.focus();
      return;
    }

    if (!this.modelName) {
      alert('モデル名を入力してください。');
      this.modelNameInput?.focus();
      return;
    }

    const isLocal = this.baseUrl.includes('localhost') || this.baseUrl.includes('127.0.0.1');
    if (!this.apiKey && !isLocal) {
      alert('APIキーを入力してください。\n（※APIキーは保存されず、ブラウザのメモリ内でのみ使用されます）');
      this.apiKeyInput?.focus();
      return;
    }

    this.isProcessing = true;
    this.sendButton.disabled = true;
    this.chatTextarea.value = '';
    this.chatTextarea.style.height = 'auto';

    // ユーザーメッセージ描画
    this.appendUserMessage(userText);

    // AI メッセージ枠の準備
    const { wrapper } = this.createBotMessageRow();

    // 思考ステップ（アコーディオン）要素（初回のみ生成・追加）
    let stepDetails = null;
    let stepSummary = null;
    let stepBody = null;

    if (!this.hasLoadedThoughts) {
      stepDetails = document.createElement('details');
      stepDetails.className = 'tool-step';
      stepDetails.open = true;

      stepSummary = document.createElement('summary');
      stepSummary.innerHTML = '<span>思考プロセス: <span class="tool-badge running">記録を取得中...</span></span>';

      stepBody = document.createElement('div');
      stepBody.className = 'tool-step-body';
      stepBody.textContent = '全過去思考記録を読み込んでいます...';

      stepDetails.appendChild(stepSummary);
      stepDetails.appendChild(stepBody);
      wrapper.appendChild(stepDetails);
    }

    // 応答バブル（初期はローディング表示）
    const responseBubble = document.createElement('div');
    responseBubble.className = 'message-bubble';
    responseBubble.innerHTML = '<em>思考中...</em>';
    wrapper.appendChild(responseBubble);
    this.scrollToBottom();

    // ロールバック用に現在の履歴長を保持
    const previousHistoryLength = this.messages.length;

    try {
      const client = new OpenAICompatibleProvider(this.baseUrl, this.apiKey, this.modelName);

      // 1. ユーザーメッセージを履歴に追加
      this.messages.push({
        role: 'user',
        content: userText
      });

      let finalText = '';

      if (!this.hasLoadedThoughts) {
        // 初回: 強制ツール呼び出し → ツール実行 → 履歴追加 → 最終回答生成
        const forcedToolChoice = {
          type: 'function',
          function: {
            name: 'all_past_thoughts'
          }
        };

        const firstResponse = await client.sendChatCompletion(this.messages, {
          tool_choice: forcedToolChoice
        });

        const choice = firstResponse.choices?.[0];
        const assistantMessage = choice?.message;

        if (!assistantMessage) {
          throw new Error('モデルから応答が取得できませんでした。');
        }

        const toolCalls = assistantMessage.tool_calls;
        if (!toolCalls || toolCalls.length === 0) {
          throw new Error('想定されたツール呼び出し（all_past_thoughts）が行われませんでした。');
        }

        const targetToolCall = toolCalls.find(tc => tc.function?.name === 'all_past_thoughts') || toolCalls[0];

        // ツール（all_past_thoughts）の実行
        const toolResult = await executeAllPastThoughts();

        // ステップUIの更新
        if (stepSummary && stepBody && stepDetails) {
          stepSummary.innerHTML = `<span>思考プロセス: <span class="tool-badge">all_past_thoughts 完了 (${toolResult.count}件の記録)</span></span>`;
          stepBody.innerHTML = `
            <div>過去の思考記録（${toolResult.count}件）の取得およびデータクレンジングが完了しました。</div>
            <div class="tool-step-details">抽出シーケンス一覧: [${toolResult.sequences.slice(0, 10).join(', ')}${toolResult.sequences.length > 10 ? ' ...' : ''}]</div>
          `;
          // 完了したらアコーディオンを閉じる（ユーザーが必要に応じて展開可能）
          stepDetails.open = false;
        }

        // ツール呼び出しとツール結果を直接 this.messages に push
        const rawEngrams = toolResult.items.map(item => item.raw_engram);
        this.messages.push(assistantMessage);
        this.messages.push({
          role: 'tool',
          tool_call_id: targetToolCall.id,
          // JSON.stringify から擬似XML変換関数に置き換え
          content: convertEngramsToPseudoXml(rawEngrams)
        });

        // 2回目の呼び出し（ツールの結果を踏まえて最終回答を生成）
        const finalResponse = await client.sendChatCompletion(this.messages, {
          tool_choice: 'auto'
        });

        const finalChoice = finalResponse.choices?.[0];
        const finalAssistantMessage = finalChoice?.message;
        finalText = finalAssistantMessage?.content || '';

        if (!finalText) {
          throw new Error('最終的な回答テキストが空でした。');
        }

        // 最終応答をテキストのみの形式で履歴に追加
        this.messages.push({
          role: 'assistant',
          content: finalText
        });

        this.hasLoadedThoughts = true;
      } else {
        // 2回目以降: ツール実行をスキップし、そのまま1回だけ呼び出し
        const response = await client.sendChatCompletion(this.messages, {
          tool_choice: 'auto'
        });

        const choice = response.choices?.[0];
        const assistantMessage = choice?.message;
        finalText = assistantMessage?.content || '';

        if (!finalText) {
          throw new Error('最終的な回答テキストが空でした。');
        }

        // 応答を履歴に追加
        this.messages.push({
          role: 'assistant',
          content: finalText
        });
      }

      // 画面に最終回答を描画
      responseBubble.innerHTML = this.renderMarkdown(finalText);
    } catch (error) {
      console.error(error);
      // 失敗したターンの履歴をロールバック
      this.messages.splice(previousHistoryLength);

      responseBubble.innerHTML = `<div class="error-notice">⚠️ <strong>エラーが発生しました:</strong><br>${escapeHtml(error.message)}</div>`;
    } finally {
      this.isProcessing = false;
      this.sendButton.disabled = false;
      this.chatTextarea.focus();
      this.scrollToBottom();
    }
  }
}

/**
 * 思考データ（engrams）の配列を擬似XML形式に変換する
 * LLMのアテンション希釈を防ぐため、JSONではなくタグ構造で出力する
 */
function convertEngramsToPseudoXml(engrams) {
  let xml = '<all_past_thoughts>\n';
  
  engrams.forEach(engram => {
    xml += '  <thought>\n';
    for (const [key, value] of Object.entries(engram)) {
      // 値がオブジェクト等の場合は stringify し、文字列化してからエスケープ処理を通す
      const strValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
      xml += `    <${key}>${escapeHtml(strValue)}</${key}>\n`;
    }
    xml += '  </thought>\n';
  });
  
  xml += '</all_past_thoughts>';
  return xml;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  new ChatApp();
});
