/**
 * Twinage - Extract Demo UI & Logic
 * License: MIT
 */

// ==========================================
// 1. プロンプト定義 (Twinage Core Framework)
// ==========================================
const SYSTEM_PROMPT = `あなたは「認知アナリスト（Cognitive Analyst）」です。
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
`;

// 最大ファイルサイズ (256 KB)
const MAX_FILE_SIZE = 256 * 1024;

// ==========================================
// 2. ヘルパー関数
// ==========================================
function getTodayString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}${month}${day}`;
}

function parseFrontmatter(content) {
  // created: YYYY-MM-DD
  const dateMatch = content.match(/^created:\s*(\d{4}-\d{2}-\d{2})/m);
  let dateStr = getTodayString();
  if (dateMatch) {
    dateStr = dateMatch[1].replace(/-/g, '');
  }

  // source: URL
  const sourceMatch = content.match(/^source:\s*(.+)$/m);
  let sourceUrl = '';
  if (sourceMatch) {
    sourceUrl = sourceMatch[1].replace(/^["']|["']$/g, '').trim();
  }

  return { dateStr, sourceUrl };
}

function generateOpaqueId(dateStr, sessionNum, turnNum, indexNum) {
  const datePart = String(dateStr).slice(0, 8);
  const sessionPart = String(sessionNum).padStart(2, '0');
  const turnPart = String(turnNum).padStart(3, '0');
  const indexPart = String(indexNum).padStart(2, '0');
  return parseInt(`${datePart}${sessionPart}${turnPart}${indexPart}`, 10);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ==========================================
// 3. Gemini API クライアント
// ==========================================
class GeminiExtractor {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.modelName = 'gemini-flash-latest';
    this.baseUrl = `https://generativelanguage.googleapis.com/v1beta/models/${this.modelName}:generateContent`;
  }

  async extractFromTurn(turnText) {
    const url = `${this.baseUrl}?key=${encodeURIComponent(this.apiKey)}`;
    const payload = {
      systemInstruction: {
        parts: [{ text: SYSTEM_PROMPT }]
      },
      contents: [
        {
          role: 'user',
          parts: [{ text: `以下の対話ログからEngramを抽出してください:\n\n${turnText}` }]
        }
      ],
      generationConfig: {
        temperature: 0.2,
        responseMimeType: 'application/json'
      }
    };

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

    const data = await response.json();
    const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!rawText) {
      throw new Error('モデルから応答テキストを取得できませんでした。');
    }

    try {
      const parsed = JSON.parse(rawText);
      return parsed.engrams || [];
    } catch (e) {
      throw new Error(`抽出結果のJSONパースに失敗しました: ${e.message}`);
    }
  }
}

// ==========================================
// 4. アプリケーションコントローラー
// ==========================================
class ExtractDemoApp {
  constructor() {
    this.apiKey = '';
    this.selectedFile = null;
    this.fileContent = '';
    this.userTag = '**You**';
    this.assistantTag = '**Gemini**';
    this.isProcessing = false;
    this.extractedEngrams = [];

    this.initElements();
    this.bindEvents();
    this.updateExtractButtonState();
  }

  initElements() {
    this.providerSelect = document.getElementById('provider-select');
    this.apiKeyInput = document.getElementById('api-key-input');
    this.userTagInput = document.getElementById('user-tag-input');
    this.assistantTagInput = document.getElementById('assistant-tag-input');

    this.dropZone = document.getElementById('drop-zone');
    this.fileInput = document.getElementById('file-input');
    this.uploadPlaceholder = document.getElementById('upload-placeholder');
    this.fileInfoBox = document.getElementById('file-info-box');
    this.fileNameDisplay = document.getElementById('file-name-display');
    this.fileSizeDisplay = document.getElementById('file-size-display');
    this.fileClearBtn = document.getElementById('file-clear-btn');
    this.fileErrorMessage = document.getElementById('file-error-message');

    this.extractBtn = document.getElementById('extract-btn');
    this.btnSpinner = document.getElementById('btn-spinner');

    this.progressCard = document.getElementById('progress-card');
    this.logConsole = document.getElementById('log-console');

    this.resultsCard = document.getElementById('results-card');
    this.engramCountBadge = document.getElementById('engram-count-badge');
    this.engramsList = document.getElementById('engrams-list');
    this.jsonPreviewCode = document.getElementById('json-preview-code');
    this.copyJsonBtn = document.getElementById('copy-json-btn');
    this.downloadJsonBtn = document.getElementById('download-json-btn');
  }

  bindEvents() {
    // API Key & Tags
    this.apiKeyInput.addEventListener('input', (e) => {
      this.apiKey = e.target.value.trim();
      this.updateExtractButtonState();
    });

    this.userTagInput.addEventListener('input', (e) => {
      this.userTag = e.target.value.trim() || '**You**';
    });

    this.assistantTagInput.addEventListener('input', (e) => {
      this.assistantTag = e.target.value.trim() || '**Gemini**';
    });

    // File Drag & Drop
    this.dropZone.addEventListener('click', () => {
      if (!this.selectedFile) {
        this.fileInput.click();
      }
    });

    this.dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.dropZone.classList.add('dragover');
    });

    this.dropZone.addEventListener('dragleave', () => {
      this.dropZone.classList.remove('dragover');
    });

    this.dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      this.dropZone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        this.handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    this.fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        this.handleFileSelected(e.target.files[0]);
      }
    });

    this.fileClearBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.clearFile();
    });

    // Extract Execution
    this.extractBtn.addEventListener('click', () => {
      this.handleExtract();
    });

    // Results Actions
    this.copyJsonBtn.addEventListener('click', () => {
      this.handleCopyJson();
    });

    this.downloadJsonBtn.addEventListener('click', () => {
      this.handleDownloadJson();
    });
  }

  handleFileSelected(file) {
    this.hideFileError();

    // Check size limit: 256KB
    if (file.size > MAX_FILE_SIZE) {
      this.showFileError(`ファイルサイズが制限（256KB）を超えています（現在: ${formatBytes(file.size)}）。処理できません。`);
      this.clearFile();
      return;
    }

    this.selectedFile = file;
    this.fileNameDisplay.textContent = file.name;
    this.fileSizeDisplay.textContent = formatBytes(file.size);

    this.uploadPlaceholder.style.display = 'none';
    this.fileInfoBox.style.display = 'flex';

    // Read content
    const reader = new FileReader();
    reader.onload = (e) => {
      this.fileContent = e.target.result;
      this.updateExtractButtonState();
    };
    reader.onerror = () => {
      this.showFileError('ファイルの読み込みに失敗しました。');
      this.clearFile();
    };
    reader.readAsText(file, 'utf-8');
  }

  clearFile() {
    this.selectedFile = null;
    this.fileContent = '';
    this.fileInput.value = '';
    this.uploadPlaceholder.style.display = 'flex';
    this.fileInfoBox.style.display = 'none';
    this.updateExtractButtonState();
  }

  showFileError(msg) {
    this.fileErrorMessage.textContent = msg;
    this.fileErrorMessage.style.display = 'block';
  }

  hideFileError() {
    this.fileErrorMessage.textContent = '';
    this.fileErrorMessage.style.display = 'none';
  }

  updateExtractButtonState() {
    const canRun = Boolean(this.apiKey && this.fileContent && !this.isProcessing);
    this.extractBtn.disabled = !canRun;
  }

  appendLog(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const timestamp = new Date().toLocaleTimeString();
    entry.textContent = `[${timestamp}] ${message}`;
    this.logConsole.appendChild(entry);
    this.logConsole.scrollTop = this.logConsole.scrollHeight;
  }

  clearLogs() {
    this.logConsole.innerHTML = '';
  }

  async handleExtract() {
    if (!this.apiKey) {
      alert('APIキーを入力してください。');
      this.apiKeyInput.focus();
      return;
    }

    if (!this.fileContent) {
      alert('Markdownファイルを選択してください。');
      return;
    }

    this.isProcessing = true;
    this.updateExtractButtonState();
    this.btnSpinner.style.display = 'inline-block';
    this.progressCard.style.display = 'block';
    this.resultsCard.style.display = 'none';
    this.clearLogs();

    this.appendLog('【処理開始】Markdownファイルの解析を開始します...', 'info');

    try {
      // 1. Frontmatter parse
      const { dateStr, sourceUrl } = parseFrontmatter(this.fileContent);
      this.appendLog(`日付抽出: ${dateStr} (createdフィールドまたは本日日付)`, 'info');
      if (sourceUrl) {
        this.appendLog(`ソースURL: ${sourceUrl}`, 'info');
      }

      // 2. Split body
      const parts = this.fileContent.split(/^---\s*$/m);
      const bodyText = parts.length >= 3 ? parts.slice(2).join('---') : this.fileContent;

      // 3. Extract turns based on User/Assistant tags
      const userTag = this.userTag;
      const assistantTag = this.assistantTag;
      const rawTurns = bodyText.split(userTag);

      const validTurns = [];
      for (const rawTurn of rawTurns) {
        const trimmed = rawTurn.trim();
        if (!trimmed || !trimmed.includes(assistantTag)) {
          continue;
        }
        validTurns.append ? validTurns.append(`${userTag}\n${trimmed}`) : validTurns.push(`${userTag}\n${trimmed}`);
      }

      const totalTurns = validTurns.length;
      this.appendLog(`セッション番号: 01 (デモ版固定仕様)`, 'info');
      this.appendLog(`検出された有効ターン数: ${totalTurns} 件 (User: "${userTag}", Assistant: "${assistantTag}")`, 'info');

      if (totalTurns === 0) {
        throw new Error(`発話タグ（User: ${userTag} / Assistant: ${assistantTag}）に一致する対話ターンが見つかりませんでした。タグ設定やファイル内容をご確認ください。`);
      }

      const client = new GeminiExtractor(this.apiKey);
      const sessionNum = 1;
      const allFinalEngrams = [];

      for (let turnIdx = 0; turnIdx < validTurns.length; turnIdx++) {
        const turnNum = turnIdx + 1;
        const turnText = validTurns[turnIdx];
        const turnPad = String(turnNum).padStart(3, '0');
        const totalPad = String(totalTurns).padStart(3, '0');

        this.appendLog(`-> Turn ${turnPad}/${totalPad} を成分分離中 (Gemini呼び出し)...`, 'info');
        const startTime = Date.now();

        const extractedItems = await client.extractFromTurn(turnText);
        const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);

        this.appendLog(`   Turn ${turnPad} 完了 (${elapsedSec}秒, ${extractedItems.length} 件抽出)`, 'success');

        for (let idx = 0; idx < extractedItems.length; idx++) {
          const item = extractedItems[idx];
          const indexNum = idx + 1;
          const sequenceId = generateOpaqueId(dateStr, sessionNum, turnNum, indexNum);

          const engram = {
            sequence: sequenceId,
            category: item.category || 'undecided',
            content: item.content || '',
            description: item.description || '',
            feel: item.feel || '',
            origin_point: item.origin_point || '',
            story_path: item.story_path || ''
          };

          const questions = item.questions || [];
          for (let qIdx = 0; qIdx < Math.min(questions.length, 6); qIdx++) {
            engram[`q_${qIdx + 1}`] = questions[qIdx];
          }

          allFinalEngrams.push(engram);
        }
      }

      this.extractedEngrams = allFinalEngrams;
      this.appendLog(`【全行程完了】計 ${allFinalEngrams.length} 件の Engram を生成しました。`, 'success');

      // Render Results
      this.renderResults(allFinalEngrams);
      this.resultsCard.style.display = 'block';
      this.resultsCard.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
      console.error(error);
      this.appendLog(`【エラー】${error.message}`, 'error');
    } finally {
      this.isProcessing = false;
      this.btnSpinner.style.display = 'none';
      this.updateExtractButtonState();
    }
  }

  renderResults(engrams) {
    this.engramCountBadge.textContent = `${engrams.length} 件の Engram を抽出`;
    this.engramsList.innerHTML = '';

    engrams.forEach((engram, i) => {
      const itemEl = document.createElement('div');
      itemEl.className = 'engram-item';

      const catClass = `category-${(engram.category || 'undecided').toLowerCase()}`;

      // Extract questions array
      const questions = [];
      for (let q = 1; q <= 6; q++) {
        if (engram[`q_${q}`]) {
          questions.push(engram[`q_${q}`]);
        }
      }

      itemEl.innerHTML = `
        <div class="engram-item-header" onclick="this.parentElement.querySelector('.engram-item-body').classList.toggle('hidden')">
          <div class="engram-item-header-main">
            <span class="engram-category-badge ${catClass}">${escapeHtml(engram.category)}</span>
            <span class="engram-title">${escapeHtml(engram.content || '(無題)')}</span>
          </div>
          <span class="engram-seq">#${engram.sequence}</span>
        </div>
        <div class="engram-item-body">
          <div class="engram-field">
            <span class="engram-field-label">Origin Point (起点)</span>
            <div class="engram-field-value">${escapeHtml(engram.origin_point || '-')}</div>
          </div>
          <div class="engram-field">
            <span class="engram-field-label">Description (説明)</span>
            <div class="engram-field-value">${escapeHtml(engram.description || '-')}</div>
          </div>
          <div class="engram-field">
            <span class="engram-field-label">Feel (主観的感情・思想)</span>
            <div class="engram-field-value">${escapeHtml(engram.feel || '-')}</div>
          </div>
          <div class="engram-field">
            <span class="engram-field-label">Story Path (推移)</span>
            <div class="engram-field-value">${escapeHtml(engram.story_path || '-')}</div>
          </div>
          ${questions.length > 0 ? `
            <div class="engram-field">
              <span class="engram-field-label">Questions (想定疑問文)</span>
              <ul class="engram-questions-list">
                ${questions.map(q => `<li>${escapeHtml(q)}</li>`).join('')}
              </ul>
            </div>
          ` : ''}
        </div>
      `;

      this.engramsList.appendChild(itemEl);
    });

    // Raw JSON highlight
    const jsonStr = JSON.stringify(engrams, null, 2);
    this.jsonPreviewCode.textContent = jsonStr;
    if (typeof hljs !== 'undefined') {
      hljs.highlightElement(this.jsonPreviewCode);
    }
  }

  handleCopyJson() {
    if (!this.extractedEngrams || this.extractedEngrams.length === 0) return;
    const jsonStr = JSON.stringify(this.extractedEngrams, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
      const originalText = this.copyJsonBtn.textContent;
      this.copyJsonBtn.textContent = 'コピーしました！';
      setTimeout(() => {
        this.copyJsonBtn.textContent = originalText;
      }, 2000);
    }).catch((err) => {
      alert(`クリップボードへのコピーに失敗しました: ${err}`);
    });
  }

  handleDownloadJson() {
    if (!this.extractedEngrams || this.extractedEngrams.length === 0) return;
    const jsonStr = JSON.stringify(this.extractedEngrams, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const baseName = this.selectedFile ? this.selectedFile.name.replace(/\.[^/.]+$/, '') : 'engrams';
    const filename = `${baseName}_engrams.json`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  new ExtractDemoApp();
});
