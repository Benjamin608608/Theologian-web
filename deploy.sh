#!/bin/bash

# 🚀 Railway自動化部署腳本

set -e

echo "🚀 開始部署FAISS神學知識庫API到Railway..."

# 檢查.env文件
if [ ! -f ".env" ]; then
    echo "❌ 未找到 .env 文件"
    echo "正在創建 .env 文件..."
    cat > .env << 'ENVEOF'
# OpenAI API密鑰 (請替換為您的實際密鑰)
OPENAI_API_KEY=your_openai_api_key_here

# 服務端口
PORT=8000

# Python配置
PYTHONPATH=/app
PYTHONUNBUFFERED=1
ENVEOF
    echo "⚠️  請編輯 .env 文件，設置您的 OPENAI_API_KEY"
    echo "然後重新運行此腳本"
    exit 1
fi

if grep -q "your_openai_api_key_here" .env; then
    echo "❌ 請先在 .env 文件中設置您的 OPENAI_API_KEY"
    echo "編輯 .env 文件，將 'your_openai_api_key_here' 替換為您的實際API密鑰"
    exit 1
fi

# 檢查Railway CLI
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI 未安裝"
    echo "正在安裝Railway CLI..."
    npm install -g @railway/cli
fi

echo "✅ Railway CLI 已就緒"

# 檢查Railway登錄狀態
echo "🔐 檢查Railway登錄狀態..."
if ! railway whoami &> /dev/null; then
    echo "請先登錄Railway:"
    echo "運行以下命令進行登錄："
    echo "railway login"
    echo ""
    echo "登錄後，重新運行此腳本"
    exit 1
fi

echo "✅ Railway 已登錄"

# 創建或連接項目
echo "📦 設置Railway項目..."
if [ ! -f ".railway/project.json" ]; then
    echo "創建新的Railway項目..."
    railway new --name "faiss-theology-api"
else
    echo "使用現有Railway項目..."
fi

# 設置環境變量
echo "⚙️  設置環境變數..."
OPENAI_KEY=$(grep OPENAI_API_KEY .env | cut -d'=' -f2)
railway variables set OPENAI_API_KEY="$OPENAI_KEY"
railway variables set PORT=8000
railway variables set PYTHONPATH=/app
railway variables set PYTHONUNBUFFERED=1

echo "✅ 環境變數設置完成"

# 部署
echo "🚀 開始部署..."
railway up --detach

echo "⏳ 等待部署完成..."
sleep 30

# 獲取部署URL
echo "🌐 獲取部署URL..."
DEPLOY_URL=$(railway domain)

if [ -n "$DEPLOY_URL" ]; then
    echo "✅ 部署完成!"
    echo "🔗 您的API地址: https://$DEPLOY_URL"
    echo ""
    
    # 測試部署
    echo "🧪 測試部署..."
    sleep 15
    
    if curl -f "https://$DEPLOY_URL/api/health" > /dev/null 2>&1; then
        echo "✅ 健康檢查通過"
        echo "🎉 FAISS API部署成功!"
        echo ""
        echo "📋 接下來的步驟:"
        echo "1. 測試搜索API:"
        echo "   curl -X POST https://$DEPLOY_URL/api/search \\"
        echo "        -H 'Content-Type: application/json' \\"
        echo "        -d '{\"question\": \"什麼是三位一體？\"}'"
        echo ""
        echo "2. 在前端中設置:"
        echo "   window.FAISS_CONFIG.API_URL = 'https://$DEPLOY_URL'"
        echo ""
        echo "3. 監控服務:"
        echo "   railway logs --follow"
        echo ""
        echo "4. API文檔:"
        echo "   https://$DEPLOY_URL/docs"
    else
        echo "⚠️  健康檢查失敗，服務可能還在啟動中"
        echo "請稍後檢查: https://$DEPLOY_URL/api/health"
        echo "查看日誌: railway logs"
    fi
else
    echo "⚠️  無法獲取部署URL，請檢查Railway控制台"
    echo "查看日誌: railway logs"
fi

echo ""
echo "🎯 部署摘要:"
echo "- 項目: FAISS神學知識庫API"
echo "- 版本: 2.0.0 (簡化版)"
echo "- 功能: 模擬向量搜索 + OpenAI問答"
echo "- 快取: 智能問題快取系統"
echo "- 文檔: 8個核心神學主題"
echo ""
echo "感謝使用！🚀✨"
