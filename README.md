# 神學知識庫網頁版

一個基於 OpenAI 向量搜索的神學問答系統，支援 Google OAuth 登入功能。

## 功能特色

- 🔐 **Google 登入**: 使用 Google OAuth 2.0 進行安全認證
- 🔍 **智能搜索**: 使用 OpenAI 的向量搜索技術，從神學家著作中尋找答案
- 📚 **詳細引用**: 顯示具體的資料來源和引用片段
- 🎨 **現代界面**: 響應式設計，支持桌面和手機瀏覽
- ⚡ **實時反饋**: 搜索過程中顯示進度狀態
- 💡 **範例問題**: 提供常見神學問題作為查詢起點

## 系統架構

- **前端**: HTML + CSS + JavaScript (純前端，無需框架)
- **後端**: Node.js + Express + OpenAI API
- **認證**: Passport.js + Google OAuth 2.0
- **AI**: OpenAI GPT-4o-mini + 向量搜索
- **資料庫**: OpenAI 向量資料庫 (Vector Store)

## 快速開始

### 1. 環境要求

- Node.js >= 16.0.0
- NPM 或 Yarn
- OpenAI API Key
- Google OAuth 憑證

### 2. 安裝依賴

```bash
# 克隆項目
git clone <your-repo-url>
cd theology-knowledge-base

# 安裝依賴
npm install
```

### 3. 設置 Google OAuth

#### 3.1 創建 Google Cloud 項目

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 創建新項目或選擇現有項目
3. 啟用 Google+ API

#### 3.2 創建 OAuth 2.0 憑證

1. 在 Google Cloud Console 中，前往「憑證」頁面
2. 點擊「建立憑證」→「OAuth 2.0 用戶端 ID」
3. 選擇「網頁應用程式」
4. 設置授權重新導向 URI：
   - 開發環境：`http://localhost:3000/auth/google/callback`
   - 生產環境：`https://your-domain.com/auth/google/callback`
5. 記錄下 Client ID 和 Client Secret

### 4. 配置環境變數

```bash
# 複製環境變數模板
cp env.example .env

# 編輯 .env 文件，填入你的配置
nano .env
```

在 `.env` 文件中設置：

```env
# OpenAI API 配置
OPENAI_API_KEY=your_openai_api_key_here

# 向量資料庫 ID
VECTOR_STORE_ID=vs_6886f711eda0819189b6c017d6b96d23

# Google OAuth 配置
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_CALLBACK_URL=http://localhost:3000/auth/google/callback

# Session 配置
SESSION_SECRET=your_session_secret_here

# 環境配置
NODE_ENV=development
PORT=3000
```

### 5. 啟動服務

```bash
# 開發模式
npm run dev

# 生產模式
npm start
```

### 6. 訪問應用

打開瀏覽器訪問 `http://localhost:3000`

## 項目結構

```
theology-knowledge-base/
├── server.js              # 後端服務器
├── package.json           # 項目配置
├── .env                   # 環境變數 (需要創建)
├── env.example           # 環境變數模板
├── public/               # 靜態文件目錄
│   └── index.html        # 前端界面
└── README.md            # 說明文件
```

## API 端點

### 認證相關

#### GET /auth/google
啟動 Google OAuth 登入流程

#### GET /auth/google/callback
Google OAuth 回調處理

#### GET /auth/logout
登出用戶

#### GET /api/user
獲取當前用戶資訊

**回應:**
```json
{
  "success": true,
  "user": {
    "id": "google_user_id",
    "email": "user@example.com",
    "name": "用戶姓名",
    "picture": "https://profile_picture_url"
  }
}
```

### 搜索相關

#### POST /api/search
搜索神學知識庫（需要登入）

**請求體:**
```json
{
  "question": "什麼是三位一體？"
}
```

**回應:**
```json
{
  "success": true,
  "data": {
    "question": "什麼是三位一體？",
    "answer": "詳細的回答內容...",
    "sources": [
      {
        "index": 1,
        "fileName": "系統神學 - 路易斯·貝科夫",
        "quote": "引用的文字片段...",
        "fileId": "file_123456"
      }
    ],
    "timestamp": "2025-07-28T10:30:00.000Z",
    "user": {
      "email": "user@example.com",
      "name": "用戶姓名"
    }
  }
}
```

### 系統相關

#### GET /api/health
健康檢查

#### GET /api/info
系統資訊

## 部署

### 本地部署

適合個人使用或小團隊：

```bash
# 設置環境變數
export OPENAI_API_KEY="your_key"
export VECTOR_STORE_ID="your_vector_store_id"
export GOOGLE_CLIENT_ID="your_google_client_id"
export GOOGLE_CLIENT_SECRET="your_google_client_secret"
export SESSION_SECRET="your_session_secret"

# 啟動服務
npm start
```

### Docker 部署

創建 `Dockerfile`：

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["npm", "start"]
```

建立和運行容器：

```bash
# 建立映像
docker build -t theology-kb .

# 運行容器
docker run -p 3000:3000 \
  -e OPENAI_API_KEY="your_key" \
  -e VECTOR_STORE_ID="your_vector_store_id" \
  -e GOOGLE_CLIENT_ID="your_google_client_id" \
  -e GOOGLE_CLIENT_SECRET="your_google_client_secret" \
  -e SESSION_SECRET="your_session_secret" \
  theology-kb
```

### 雲端部署

支持部署到以下平台：

- **Heroku**: 添加 `Procfile` 和環境變數
- **Vercel**: 配置 `vercel.json`
- **Railway**: 直接連接 GitHub 倉庫
- **Render**: 自動部署設置

**重要提醒**: 在生產環境中，請確保：
1. 設置 `NODE_ENV=production`
2. 使用 HTTPS
3. 更新 Google OAuth 的回調 URL
4. 設置安全的 `SESSION_SECRET`

## 自定義配置

### 修改向量資料庫

如果你有自己的神學文件資料庫：

1. 上傳文件到 OpenAI
2. 創建向量資料庫
3. 更新 `.env` 中的 `VECTOR_STORE_ID`

### 調整 AI 模型

在 `server.js` 中修改：

```javascript
const assistant = await openai.beta.assistants.create({
  model: 'gpt-4o-mini', // 可改為 gpt-4o 獲得更好效果
  // ... 其他配置
});
```

### 自定義前端樣式

修改 `public/index.html` 中的 CSS 部分來調整外觀。

### 自定義認證策略

可以修改 `server.js` 中的 Passport 配置來添加其他認證方式：

```javascript
// 添加其他 OAuth 提供商
passport.use(new FacebookStrategy({
  // Facebook 配置
}));
```

## 故障排除

### 常見問題

1. **Google OAuth 錯誤**
   - 檢查 `GOOGLE_CLIENT_ID` 和 `GOOGLE_CLIENT_SECRET` 是否正確
   - 確認回調 URL 設置正確
   - 檢查 Google Cloud Console 中的 API 是否已啟用

2. **Session 錯誤**
   - 確保 `SESSION_SECRET` 已設置
   - 在生產環境中使用 HTTPS

3. **API Key 錯誤**
   - 檢查 `.env` 文件中的 `OPENAI_API_KEY`
   - 確認 API Key 有效且有足夠額度

4. **向量資料庫錯誤**
   - 驗證 `VECTOR_STORE_ID` 是否正確
   - 確認資料庫包含相關文件

5. **查詢超時**
   - 簡化問題描述
   - 檢查網路連接
   - 增加後端超時時間

6. **端口被占用**
   - 修改 `.env` 中的 `PORT` 設置
   - 或終止占用端口的程序

### 日誌檢查

```bash
# 查看服務器日誌
npm run dev

# 檢查 API 健康狀態
curl http://localhost:3000/api/health

# 檢查用戶認證狀態
curl http://localhost:3000/api/user
```

## 安全性考量

1. **環境變數**: 確保所有敏感資訊都存儲在環境變數中
2. **HTTPS**: 生產環境必須使用 HTTPS
3. **Session 安全**: 使用強密碼作為 `SESSION_SECRET`
4. **CORS**: 根據需要配置 CORS 設置
5. **輸入驗證**: 所有用戶輸入都經過驗證

## 貢獻

歡迎提交 Issues 和 Pull Requests 來改進這個項目。

## 許可證

MIT License

## 聯絡

如有問題或建議，請透過 GitHub Issues 聯繫。
