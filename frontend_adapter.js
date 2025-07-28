/**
 * 前端適配器 - 讓現有前端無縫使用新的FAISS向量搜索API
 * 
 * 使用方法：
 * 1. 將此文件添加到現有項目
 * 2. 修改現有的 callSearchAPI 函數
 * 3. 設置 FAISS_API_URL 環境變量
 */

// FAISS API配置
const FAISS_CONFIG = {
    // Railway部署的FAISS服務URL
    API_URL: process.env.FAISS_API_URL || 'https://your-faiss-service.railway.app',
    
    // 備用API（原OpenAI Assistant）
    FALLBACK_URL: '/api/search',
    
    // 配置選項
    USE_FAISS: true,  // 是否使用FAISS
    FALLBACK_ON_ERROR: true,  // 錯誤時是否回退到原API
    TIMEOUT: 30000,  // 請求超時時間（毫秒）
    
    // A/B測試配置
    AB_TEST_ENABLED: false,
    AB_TEST_RATIO: 0.5  // 50%用戶使用FAISS
};

/**
 * FAISS API客戶端
 */
class FAISSAPIClient {
    constructor(config = FAISS_CONFIG) {
        this.config = config;
        this.requestId = 0;
    }

    /**
     * 調用FAISS搜索API
     */
    async callFAISSSearch(question, conversationHistory = []) {
        const requestId = ++this.requestId;
        console.log(`🚀 [${requestId}] 調用FAISS API: ${question.substring(0, 50)}...`);
        
        const startTime = performance.now();
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.config.TIMEOUT);
            
            const response = await fetch(`${this.config.API_URL}/api/search`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify({
                    question: question,
                    top_k: 5,
                    temperature: 0.7,
                    use_cache: true
                }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            const totalTime = performance.now() - startTime;
            
            console.log(`✅ [${requestId}] FAISS API成功 (${totalTime.toFixed(0)}ms, 快取: ${data.cache_hit ? '命中' : '未命中'})`);
            
            // 轉換為原API格式
            return this.transformFAISSResponse(data);
            
        } catch (error) {
            const totalTime = performance.now() - startTime;
            console.error(`❌ [${requestId}] FAISS API失敗 (${totalTime.toFixed(0)}ms):`, error.message);
            
            if (this.config.FALLBACK_ON_ERROR) {
                console.log(`🔄 [${requestId}] 回退到原API...`);
                return this.callFallbackAPI(question, conversationHistory);
            } else {
                throw error;
            }
        }
    }

    /**
     * 調用備用API（原OpenAI Assistant）
     */
    async callFallbackAPI(question, conversationHistory = []) {
        const requestId = ++this.requestId;
        console.log(`🔄 [${requestId}] 調用備用API: ${question.substring(0, 50)}...`);
        
        const startTime = performance.now();
        
        try {
            const response = await fetch(this.config.FALLBACK_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question: question,
                    conversationHistory: conversationHistory
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const totalTime = performance.now() - startTime;
            
            console.log(`✅ [${requestId}] 備用API成功 (${totalTime.toFixed(0)}ms)`);
            
            if (!data.success) {
                throw new Error(data.error || '查詢失敗');
            }

            return data.data;
            
        } catch (error) {
            const totalTime = performance.now() - startTime;
            console.error(`❌ [${requestId}] 備用API失敗 (${totalTime.toFixed(0)}ms):`, error.message);
            throw error;
        }
    }

    /**
     * 轉換FAISS API響應為原API格式
     */
    transformFAISSResponse(faissData) {
        return {
            question: faissData.question || '',
            answer: faissData.answer,
            sources: faissData.sources.map((source, index) => ({
                index: index + 1,
                fileName: this.extractFileName(source.source),
                quote: source.content.substring(0, 200) + (source.content.length > 200 ? '...' : ''),
                fileId: source.metadata?.id || `faiss_${index}`,
                score: source.score,
                metadata: source.metadata
            })),
            timestamp: new Date().toISOString(),
            user: null,
            // FAISS特有的額外信息
            faiss_meta: {
                search_time: faissData.search_time,
                total_time: faissData.total_time,
                cache_hit: faissData.cache_hit,
                confidence_score: faissData.confidence_score,
                api_version: '2.0.0'
            }
        };
    }

    /**
     * 從文件路徑提取文件名
     */
    extractFileName(filePath) {
        if (!filePath) return 'Unknown Source';
        
        // 處理不同的路徑格式
        const fileName = filePath.split(/[/\\]/).pop() || filePath;
        
        // 移除文件擴展名
        return fileName.replace(/\.(txt|md|json|csv|tsv)$/i, '');
    }

    /**
     * 檢查是否應該使用FAISS（A/B測試）
     */
    shouldUseFAISS(userId = null) {
        if (!this.config.USE_FAISS) return false;
        
        if (this.config.AB_TEST_ENABLED) {
            // 基於用戶ID或隨機數進行A/B測試
            const hash = userId ? this.simpleHash(userId) : Math.random();
            return hash < this.config.AB_TEST_RATIO;
        }
        
        return true;
    }

    /**
     * 簡單哈希函數（用於A/B測試）
     */
    simpleHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // 轉換為32位整數
        }
        return Math.abs(hash) / 2147483647; // 標準化到[0,1]
    }

    /**
     * 獲取API健康狀態
     */
    async getHealthStatus() {
        try {
            const response = await fetch(`${this.config.API_URL}/api/health`, {
                method: 'GET',
                timeout: 5000
            });
            
            if (response.ok) {
                return await response.json();
            } else {
                return { status: 'unhealthy', error: `HTTP ${response.status}` };
            }
        } catch (error) {
            return { status: 'error', error: error.message };
        }
    }

    /**
     * 獲取API統計信息
     */
    async getStats() {
        try {
            const response = await fetch(`${this.config.API_URL}/api/stats`);
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('無法獲取FAISS API統計信息:', error.message);
        }
        return null;
    }
}

/**
 * 全局FAISS客戶端實例
 */
const faissClient = new FAISSAPIClient();

/**
 * 智能搜索API - 自動選擇最佳API
 * 這個函數可以直接替換現有的 callSearchAPI
 */
async function callSearchAPI(question, conversationHistory = []) {
    // 記錄請求開始時間
    const requestStart = performance.now();
    
    try {
        // 決定使用哪個API
        const useFAISS = faissClient.shouldUseFAISS();
        
        let result;
        if (useFAISS) {
            // 使用FAISS API
            result = await faissClient.callFAISSSearch(question, conversationHistory);
        } else {
            // 使用原API
            result = await faissClient.callFallbackAPI(question, conversationHistory);
        }
        
        // 添加性能指標
        const totalRequestTime = performance.now() - requestStart;
        result.performance_meta = {
            total_request_time: totalRequestTime,
            api_used: useFAISS ? 'FAISS' : 'OpenAI Assistant',
            timestamp: new Date().toISOString()
        };
        
        return result;
        
    } catch (error) {
        // 統一錯誤處理
        console.error('搜索API調用失敗:', error);
        
        // 檢查是否是認證錯誤
        if (error.message.includes('401') || error.message.includes('需要登入')) {
            const authError = new Error('需要登入才能使用此功能');
            authError.requiresAuth = true;
            throw authError;
        }
        
        // 其他錯誤
        throw new Error(`搜索失敗: ${error.message}`);
    }
}

/**
 * 增強的搜索API - 包含重試邏輯
 */
async function callSearchAPIWithRetry(question, conversationHistory = [], maxRetries = 2) {
    let lastError;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            console.log(`🔄 搜索嘗試 ${attempt}/${maxRetries}: ${question.substring(0, 30)}...`);
            
            const result = await callSearchAPI(question, conversationHistory);
            
            // 成功則返回結果
            if (attempt > 1) {
                console.log(`✅ 第 ${attempt} 次嘗試成功`);
            }
            
            return result;
            
        } catch (error) {
            lastError = error;
            
            // 如果是認證錯誤，不重試
            if (error.requiresAuth) {
                throw error;
            }
            
            // 如果不是最後一次嘗試，等待後重試
            if (attempt < maxRetries) {
                const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000); // 指數退避，最大5秒
                console.log(`⏳ 第 ${attempt} 次嘗試失敗，${delay}ms 後重試...`);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
    
    // 所有重試都失敗
    console.error(`❌ 所有 ${maxRetries} 次嘗試都失敗`);
    throw lastError;
}

/**
 * 批量搜索API - 支持多個問題並行搜索
 */
async function batchSearchAPI(questions, conversationHistory = []) {
    console.log(`🔄 批量搜索 ${questions.length} 個問題...`);
    
    const promises = questions.map((question, index) => 
        callSearchAPI(question, conversationHistory)
            .then(result => ({ index, question, result, success: true }))
            .catch(error => ({ index, question, error, success: false }))
    );
    
    const results = await Promise.all(promises);
    
    const successful = results.filter(r => r.success);
    const failed = results.filter(r => !r.success);
    
    console.log(`✅ 批量搜索完成: ${successful.length} 成功, ${failed.length} 失敗`);
    
    return {
        successful: successful.map(r => ({ question: r.question, result: r.result })),
        failed: failed.map(r => ({ question: r.question, error: r.error.message })),
        total: questions.length,
        success_rate: successful.length / questions.length
    };
}

/**
 * 搜索建議API - 基於輸入提供搜索建議
 */
async function getSearchSuggestions(partialQuery, limit = 5) {
    // 這裡可以實現基於歷史搜索或預定義問題的建議邏輯
    const commonQuestions = [
        "什麼是三位一體？",
        "什麼是原罪？",
        "什麼是因信稱義？",
        "什麼是預定論？",
        "什麼是聖靈？",
        "什麼是救恩？",
        "什麼是聖經的權威？",
        "什麼是教會？",
        "什麼是洗禮？",
        "什麼是聖餐？"
    ];
    
    const query = partialQuery.toLowerCase();
    const suggestions = commonQuestions
        .filter(q => q.toLowerCase().includes(query))
        .slice(0, limit);
    
    return suggestions;
}

/**
 * 導出供現有代碼使用的函數
 */
if (typeof module !== 'undefined' && module.exports) {
    // Node.js環境
    module.exports = {
        callSearchAPI,
        callSearchAPIWithRetry,
        batchSearchAPI,
        getSearchSuggestions,
        faissClient,
        FAISS_CONFIG
    };
} else {
    // 瀏覽器環境 - 將函數添加到全局作用域
    window.callSearchAPI = callSearchAPI;
    window.callSearchAPIWithRetry = callSearchAPIWithRetry;
    window.batchSearchAPI = batchSearchAPI;
    window.getSearchSuggestions = getSearchSuggestions;
    window.faissClient = faissClient;
    window.FAISS_CONFIG = FAISS_CONFIG;
}

/**
 * 初始化函數 - 檢查FAISS API狀態
 */
async function initializeFAISSAPI() {
    console.log('🚀 初始化FAISS API客戶端...');
    
    try {
        const health = await faissClient.getHealthStatus();
        const stats = await faissClient.getStats();
        
        console.log('📊 FAISS API狀態:', health);
        if (stats) {
            console.log('📈 FAISS API統計:', stats);
        }
        
        if (health.status === 'healthy') {
            console.log('✅ FAISS API就緒');
            return true;
        } else {
            console.warn('⚠️ FAISS API不健康，將使用備用API');
            return false;
        }
        
    } catch (error) {
        console.error('❌ FAISS API初始化失敗:', error.message);
        console.log('🔄 將使用備用API');
        return false;
    }
}

// 自動初始化（如果在瀏覽器環境中）
if (typeof window !== 'undefined') {
    // 等待DOM加載完成後初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeFAISSAPI);
    } else {
        initializeFAISSAPI();
    }
}