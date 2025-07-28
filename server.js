const express = require('express');
const cors = require('cors');
const path = require('path');
const OpenAI = require('openai');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// 初始化 OpenAI 客戶端
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

// 你的向量資料庫 ID
const VECTOR_STORE_ID = process.env.VECTOR_STORE_ID || 'vs_6886f711eda0819189b6c017d6b96d23';

// 中間件設置
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// 獲取文件名稱的函數
async function getFileName(fileId) {
  try {
    const file = await openai.files.retrieve(fileId);
    let fileName = file.filename || `檔案-${fileId.substring(0, 8)}`;
    fileName = fileName.replace(/\.(txt|pdf|docx?|rtf|md)$/i, '');
    return fileName;
  } catch (error) {
    console.warn(`無法獲取檔案名稱 ${fileId}:`, error.message);
    return `檔案-${fileId.substring(0, 8)}`;
  }
}

// 處理引用標記並轉換為網頁格式的函數
async function processAnnotationsInText(text, annotations) {
  let processedText = text;
  const sourceMap = new Map();
  const usedSources = new Map();
  let citationCounter = 1;
  
  if (annotations && annotations.length > 0) {
    for (const annotation of annotations) {
      if (annotation.type === 'file_citation' && annotation.file_citation) {
        const fileId = annotation.file_citation.file_id;
        const fileName = await getFileName(fileId);
        const quote = annotation.file_citation.quote || '';
        
        let citationIndex;
        if (usedSources.has(fileId)) {
          citationIndex = usedSources.get(fileId);
        } else {
          citationIndex = citationCounter++;
          usedSources.set(fileId, citationIndex);
          sourceMap.set(citationIndex, {
            fileName,
            quote,
            fileId
          });
        }
        
        const originalText = annotation.text;
        if (originalText) {
          const replacement = `${originalText}[${citationIndex}]`;
          processedText = processedText.replace(originalText, replacement);
        }
      }
    }
    
    // 清理格式問題並改善排版
    processedText = processedText
      .replace(/【[^】]*】/g, '')
      .replace(/†[^†\s]*†?/g, '')
      .replace(/,\s*\n/g, '\n')
      .replace(/,\s*$/, '')
      .replace(/\n\s*,/g, '\n')
      .replace(/(\[\d+\])(\[\d+\])*\1+/g, '$1$2')
      .replace(/(\[\d+\])+/g, (match) => {
        const citations = match.match(/\[\d+\]/g);
        const uniqueCitations = [...new Set(citations)];
        return uniqueCitations.join('');
      })
      .replace(/(\d+)\.\s*([^：。！？\n]+[：])/g, '\n\n**$1. $2**\n')
      .replace(/([。！？])\s+(\d+\.)/g, '$1\n\n**$2')
      .replace(/([。！？])\s*([A-Za-z][^。！？]*：)/g, '$1\n\n**$2**\n')
      .replace(/\*\s*([^*\n]+)\s*：\s*\*/g, '**$1：**')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\s+|\s+$/g, '')
      .replace(/([。！？])(?=\s*(?!\*\*\d+\.)[^\n])/g, '$1\n\n')
      .trim();
  }
  
  return { processedText, sourceMap };
}

// 創建來源列表的函數
function createSourceList(sourceMap) {
  if (sourceMap.size === 0) return [];
  
  const sortedSources = Array.from(sourceMap.entries()).sort((a, b) => a[0] - b[0]);
  
  return sortedSources.map(([index, source]) => ({
    index,
    fileName: source.fileName,
    quote: source.quote && source.quote.length > 120 
      ? source.quote.substring(0, 120) + '...' 
      : source.quote,
    fileId: source.fileId
  }));
}

// 處理搜索請求的核心函數
async function processSearchRequest(question, user = null) {
  console.log(`處理搜索請求: ${question}${user ? ` (用戶: ${user.email})` : ''}`);
  
  const assistant = await openai.beta.assistants.create({
    model: 'gpt-4o-mini',
    name: 'Theology RAG Assistant',
    instructions: `你是一個專業的神學助手，只能根據提供的知識庫資料來回答問題。

重要規則：
1. 只使用檢索到的資料來回答問題
2. 如果資料庫中沒有相關資訊，請明確說明「很抱歉，我在資料庫中找不到相關資訊來回答這個問題，因為資料庫都為英文，建議將專有名詞替換成英文或許會有幫助」
3. 回答要準確、簡潔且有幫助
4. 使用繁體中文回答
5. 專注於提供基於資料庫內容的準確資訊
6. 盡可能引用具體的資料片段

格式要求：
- 直接回答問題內容
- 引用相關的資料片段（如果有的話）
- 不需要在回答中手動添加資料來源，系統會自動處理`,
    tools: [{ type: 'file_search' }],
    tool_resources: {
      file_search: {
        vector_store_ids: [VECTOR_STORE_ID]
      }
    }
  });

  const thread = await openai.beta.threads.create();

  await openai.beta.threads.messages.create(thread.id, {
    role: 'user',
    content: question
  });

  const run = await openai.beta.threads.runs.create(thread.id, {
    assistant_id: assistant.id
  });

  // 等待完成
  let runStatus = await openai.beta.threads.runs.retrieve(thread.id, run.id);
  let attempts = 0;
  const maxAttempts = 60;

  while (runStatus.status !== 'completed' && runStatus.status !== 'failed' && attempts < maxAttempts) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    runStatus = await openai.beta.threads.runs.retrieve(thread.id, run.id);
    attempts++;
  }

  if (runStatus.status === 'failed') {
    throw new Error(`Assistant run failed: ${runStatus.last_error?.message || 'Unknown error'}`);
  }

  if (attempts >= maxAttempts) {
    throw new Error('查詢時間過長，請嘗試簡化您的問題或稍後再試');
  }

  // 獲取回答
  const threadMessages = await openai.beta.threads.messages.list(thread.id);
  const responseMessage = threadMessages.data[0];
  
  let botAnswer = '';
  let sources = [];
  
  if (responseMessage.content && responseMessage.content.length > 0) {
    const textContent = responseMessage.content.find(content => content.type === 'text');
    if (textContent) {
      const { processedText, sourceMap } = await processAnnotationsInText(
        textContent.text.value, 
        textContent.text.annotations
      );
      
      botAnswer = processedText;
      sources = createSourceList(sourceMap);
    }
  }

  if (!botAnswer) {
    botAnswer = '很抱歉，我在資料庫中找不到相關資訊來回答這個問題。\n\n📚 **資料來源：** 神學知識庫';
  }

  // 清理資源
  try {
    await openai.beta.assistants.del(assistant.id);
  } catch (cleanupError) {
    console.warn('Failed to cleanup assistant:', cleanupError.message);
  }

  return {
    question: question,
    answer: botAnswer,
    sources: sources,
    timestamp: new Date().toISOString(),
    user: user ? { email: user.email, name: user.name } : null
  };
}

// 主要搜索 API 端點
app.post('/api/search', async (req, res) => {
  try {
    const { question, user } = req.body;

    if (!question || !question.trim()) {
      return res.status(400).json({
        success: false,
        error: '請提供有效的問題'
      });
    }

    const trimmedQuestion = question.trim();
    console.log(`收到搜索請求: ${trimmedQuestion}${user ? ` (用戶: ${user.email})` : ''}`);

    // 處理搜索請求
    const result = await processSearchRequest(trimmedQuestion, user);

    res.json({
      success: true,
      data: result
    });

  } catch (error) {
    console.error('搜索錯誤:', error);
    
    let errorMessage = '很抱歉，處理您的問題時發生錯誤，請稍後再試。';
    
    if (error.message.includes('查詢時間過長') || error.message.includes('timeout')) {
      errorMessage = '查詢時間過長，請嘗試簡化您的問題或稍後再試。';
    } else if (error.message.includes('rate limit')) {
      errorMessage = '目前請求過多，請稍後再試。';
    } else if (error.message.includes('Assistant run failed')) {
      errorMessage = '系統處理問題，請稍後再試或聯繫管理員。';
    }
    
    res.status(500).json({
      success: false,
      error: errorMessage,
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// 健康檢查端點
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

// 獲取系統資訊端點
app.get('/api/info', (req, res) => {
  res.json({
    name: '神學知識庫 API',
    version: '1.0.0',
    description: '基於 OpenAI 向量搜索的神學問答系統',
    vectorStoreId: VECTOR_STORE_ID ? 'configured' : 'not configured'
  });
});

// 服務靜態文件（前端）
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 錯誤處理中間件
app.use((error, req, res, next) => {
  console.error('未處理的錯誤:', error);
  res.status(500).json({
    success: false,
    error: '服務器內部錯誤',
    details: process.env.NODE_ENV === 'development' ? error.message : undefined
  });
});

// 404 處理
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: '找不到請求的資源'
  });
});

// 全局錯誤處理
process.on('unhandledRejection', (error) => {
  console.error('Unhandled promise rejection:', error);
});

process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error);
  process.exit(1);
});

// 啟動服務器
app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 神學知識庫服務器已啟動`);
  console.log(`📍 端口: ${PORT}`);
  console.log(`🔍 API 健康檢查: /api/health`);
  console.log(`📊 系統狀態: /api/info`);
  console.log(`💡 向量資料庫 ID: ${VECTOR_STORE_ID ? '已設定' : '未設定'}`);
});
