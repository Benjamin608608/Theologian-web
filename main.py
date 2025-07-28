import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import openai
from dotenv import load_dotenv
import psutil
from tqdm import tqdm
import pickle

# 載入環境變數
load_dotenv()

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI應用
app = FastAPI(
    title="🚀 神學知識庫 FAISS 向量搜索API",
    description="高性能本地向量搜索 + OpenAI智能問答",
    version="2.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI設定
openai.api_key = os.getenv("OPENAI_API_KEY")

# 全局變數
vector_model = None
faiss_index = None
document_chunks = None
metadata = None
question_cache = {}

# 配置參數
class Config:
    MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"  # 多語言模型
    VECTOR_DIM = 768
    INDEX_TYPE = "IVF_PQ"  # 高壓縮比索引
    NLIST = 1024  # 聚類中心數量
    M = 96  # PQ子向量數量
    NBITS = 8  # 位數
    CHUNK_SIZE = 512  # 文檔分塊大小
    OVERLAP = 50  # 重疊字符數
    TOP_K = 10  # 檢索文檔數量
    CACHE_SIZE = 2000  # 問題快取大小
    CACHE_DURATION = 24 * 3600  # 24小時快取

# 數據模型
class SearchRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    temperature: Optional[float] = 0.7
    use_cache: Optional[bool] = True

class SearchResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    search_time: float
    total_time: float
    cache_hit: bool
    confidence_score: float

class DocumentChunk(BaseModel):
    id: str
    content: str
    source: str
    metadata: Dict[str, Any]

# 文檔處理工具
class DocumentProcessor:
    def __init__(self):
        self.chunk_size = Config.CHUNK_SIZE
        self.overlap = Config.OVERLAP
    
    def load_documents_from_directory(self, directory_path: str) -> List[DocumentChunk]:
        """從目錄載入文檔"""
        chunks = []
        directory = Path(directory_path)
        
        if not directory.exists():
            logger.error(f"目錄不存在: {directory_path}")
            return chunks
        
        # 支援的文件格式
        supported_formats = ['.txt', '.md', '.json']
        
        for file_path in directory.rglob('*'):
            if file_path.suffix.lower() in supported_formats:
                try:
                    content = self.load_file(file_path)
                    file_chunks = self.chunk_document(content, str(file_path))
                    chunks.extend(file_chunks)
                    logger.info(f"處理文件: {file_path}, 生成 {len(file_chunks)} 個片段")
                except Exception as e:
                    logger.error(f"處理文件失敗 {file_path}: {e}")
        
        return chunks
    
    def load_file(self, file_path: Path) -> str:
        """載入單個文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def chunk_document(self, content: str, source: str) -> List[DocumentChunk]:
        """將文檔分塊"""
        chunks = []
        content_length = len(content)
        
        for i in range(0, content_length, self.chunk_size - self.overlap):
            chunk_content = content[i:i + self.chunk_size]
            
            # 跳過太短的片段
            if len(chunk_content.strip()) < 50:
                continue
            
            chunk_id = hashlib.md5(f"{source}_{i}".encode()).hexdigest()
            
            chunk = DocumentChunk(
                id=chunk_id,
                content=chunk_content.strip(),
                source=source,
                metadata={
                    "start_pos": i,
                    "end_pos": min(i + self.chunk_size, content_length),
                    "chunk_index": len(chunks)
                }
            )
            chunks.append(chunk)
        
        return chunks

# FAISS索引管理器
class FAISSIndexManager:
    def __init__(self):
        self.index = None
        self.is_trained = False
    
    def create_index(self, dimension: int) -> faiss.Index:
        """創建FAISS索引"""
        if Config.INDEX_TYPE == "IVF_PQ":
            # 高壓縮比索引
            quantizer = faiss.IndexFlatL2(dimension)
            index = faiss.IndexIVFPQ(
                quantizer, 
                dimension, 
                Config.NLIST, 
                Config.M, 
                Config.NBITS
            )
            logger.info(f"創建 IVF_PQ 索引: nlist={Config.NLIST}, m={Config.M}, nbits={Config.NBITS}")
        else:
            # 簡單平面索引
            index = faiss.IndexFlatIP(dimension)
            logger.info("創建 Flat 索引")
        
        return index
    
    def train_and_add_vectors(self, vectors: np.ndarray):
        """訓練並添加向量"""
        dimension = vectors.shape[1]
        self.index = self.create_index(dimension)
        
        # 訓練索引（如果需要）
        if hasattr(self.index, 'train'):
            logger.info("開始訓練FAISS索引...")
            self.index.train(vectors)
            self.is_trained = True
        
        # 添加向量
        logger.info(f"添加 {len(vectors)} 個向量到索引...")
        self.index.add(vectors)
        
        logger.info(f"索引構建完成，總向量數: {self.index.ntotal}")
    
    def search(self, query_vector: np.ndarray, k: int = 10):
        """搜索相似向量"""
        if self.index is None:
            raise ValueError("索引未初始化")
        
        scores, indices = self.index.search(query_vector, k)
        return scores[0], indices[0]
    
    def save_index(self, filepath: str):
        """保存索引"""
        if self.index is not None:
            faiss.write_index(self.index, filepath)
            logger.info(f"索引已保存到: {filepath}")
    
    def load_index(self, filepath: str):
        """載入索引"""
        if os.path.exists(filepath):
            self.index = faiss.read_index(filepath)
            self.is_trained = True
            logger.info(f"索引已載入: {filepath}")
            return True
        return False

# 向量搜索引擎
class VectorSearchEngine:
    def __init__(self):
        self.model = None
        self.faiss_manager = FAISSIndexManager()
        self.documents = []
        self.cache = {}
    
    async def initialize(self, documents_path: str = None):
        """初始化搜索引擎"""
        logger.info("🚀 初始化向量搜索引擎...")
        
        # 載入模型
        logger.info(f"載入模型: {Config.MODEL_NAME}")
        self.model = SentenceTransformer(Config.MODEL_NAME)
        
        # 檢查是否有預建索引
        index_path = "theology_vectors.index"
        documents_path_pkl = "documents.pkl"
        
        if os.path.exists(index_path) and os.path.exists(documents_path_pkl):
            # 載入預建索引和文檔
            logger.info("載入預建的FAISS索引...")
            self.faiss_manager.load_index(index_path)
            
            with open(documents_path_pkl, 'rb') as f:
                self.documents = pickle.load(f)
            
            logger.info(f"載入完成: {len(self.documents)} 個文檔片段")
        
        elif documents_path and os.path.exists(documents_path):
            # 構建新索引
            await self.build_index_from_documents(documents_path)
        
        else:
            # 使用示例數據
            await self.build_sample_index()
        
        logger.info("✅ 向量搜索引擎初始化完成")
    
    async def build_index_from_documents(self, documents_path: str):
        """從文檔構建索引"""
        logger.info(f"從文檔構建索引: {documents_path}")
        
        # 處理文檔
        processor = DocumentProcessor()
        chunks = processor.load_documents_from_directory(documents_path)
        
        if not chunks:
            logger.warning("未找到文檔，使用示例數據")
            await self.build_sample_index()
            return
        
        # 向量化
        logger.info("開始向量化文檔...")
        texts = [chunk.content for chunk in chunks]
        
        # 分批處理避免內存溢出
        batch_size = 100
        all_vectors = []
        
        for i in tqdm(range(0, len(texts), batch_size), desc="向量化進度"):
            batch_texts = texts[i:i + batch_size]
            batch_vectors = self.model.encode(batch_texts, show_progress_bar=False)
            all_vectors.append(batch_vectors)
        
        vectors = np.vstack(all_vectors)
        
        # 構建索引
        self.faiss_manager.train_and_add_vectors(vectors)
        self.documents = chunks
        
        # 保存索引和文檔
        self.faiss_manager.save_index("theology_vectors.index")
        with open("documents.pkl", 'wb') as f:
            pickle.dump(self.documents, f)
        
        logger.info(f"索引構建完成: {len(chunks)} 個文檔片段")
    
    async def build_sample_index(self):
        """構建示例索引（用於演示）"""
        logger.info("構建示例神學知識索引...")
        
        sample_documents = [
            "三位一體是基督教的核心教義，指聖父、聖子、聖靈三個位格在一個神聖本質中的統一。這個教義在尼西亞信經中得到了明確的表述。",
            "原罪是指人類因亞當和夏娃在伊甸園中的墮落而承受的罪性。奧古斯丁認為原罪是人類本性的腐敗，影響了人的意志和理性。",
            "因信稱義是新教改革的核心教義，由馬丁·路德提出。它強調人不是因行為稱義，而是單純因信心而在上帝面前被宣告為義。",
            "預定論是加爾文神學的重要概念，認為上帝在創世之前就預定了誰將得救。這個教義在改革宗傳統中佔有重要地位。",
            "聖靈是三位一體的第三個位格，在五旬節降臨到使徒身上。聖靈的工作包括光照、重生、成聖和賜予屬靈恩賜。",
            "救恩是上帝拯救人類脫離罪惡的計劃，通過耶穌基督的十字架工作得以實現。救恩包括稱義、成聖和得榮耀三個階段。",
            "聖經是基督教信仰的最高權威，被認為是上帝默示的話語。聖經包括舊約和新約兩部分，共66卷書。",
            "教會是所有信徒的群體，被稱為基督的身體。教會的使命包括敬拜、團契、教導和宣教。",
            "洗禮是基督教的重要聖禮，象徵信徒與基督同死同復活。不同教派對洗禮的方式和意義有不同的理解。",
            "聖餐是耶穌設立的聖禮，記念他的死和復活。餅和杯象徵基督的身體和血，信徒通過聖餐與主聯合。"
        ]
        
        # 創建文檔片段
        chunks = []
        for i, text in enumerate(sample_documents):
            chunk = DocumentChunk(
                id=f"sample_{i}",
                content=text,
                source=f"sample_document_{i}.txt",
                metadata={"type": "sample", "index": i}
            )
            chunks.append(chunk)
        
        # 向量化
        vectors = self.model.encode([chunk.content for chunk in chunks])
        
        # 構建索引
        self.faiss_manager.train_and_add_vectors(vectors)
        self.documents = chunks
        
        logger.info(f"示例索引構建完成: {len(chunks)} 個文檔片段")
    
    async def search(self, query: str, top_k: int = 5) -> tuple:
        """執行向量搜索"""
        start_time = datetime.now()
        
        # 向量化查詢
        query_vector = self.model.encode([query])
        
        # FAISS搜索
        scores, indices = self.faiss_manager.search(query_vector, top_k * 2)  # 多檢索一些備選
        
        # 獲取相關文檔
        relevant_docs = []
        for score, idx in zip(scores, indices):
            if idx < len(self.documents) and score > 0.3:  # 相關性閾值
                doc = self.documents[idx]
                relevant_docs.append({
                    "content": doc.content,
                    "source": doc.source,
                    "score": float(score),
                    "metadata": doc.metadata
                })
        
        search_time = (datetime.now() - start_time).total_seconds()
        
        return relevant_docs[:top_k], search_time

# 問答生成器
class AnswerGenerator:
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_answer(self, query: str, relevant_docs: List[Dict], temperature: float = 0.7) -> tuple:
        """生成答案"""
        start_time = datetime.now()
        
        # 構建上下文
        context = "\n\n".join([
            f"【文獻 {i+1}】{doc['content']}"
            for i, doc in enumerate(relevant_docs)
        ])
        
        # 構建提示詞
        prompt = f"""你是一位專業的神學助手。請基於以下神學文獻回答用戶的問題。

神學文獻：
{context}

用戶問題：{query}

請遵循以下要求：
1. 使用繁體中文回答
2. 基於提供的文獻內容回答，不要編造信息
3. 如果文獻中沒有相關信息，請誠實說明
4. 回答要準確、簡潔且有幫助
5. 可以適當引用文獻內容
6. 保持客觀和學術性的語調

回答："""

        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=1500
            )
            
            answer = response.choices[0].message.content
            generation_time = (datetime.now() - start_time).total_seconds()
            
            return answer, generation_time
            
        except Exception as e:
            logger.error(f"生成答案失敗: {e}")
            return f"抱歉，生成答案時發生錯誤：{str(e)}", 0

# 快取管理器
class CacheManager:
    def __init__(self):
        self.cache = {}
        self.max_size = Config.CACHE_SIZE
        self.duration = Config.CACHE_DURATION
    
    def _get_cache_key(self, query: str) -> str:
        """生成快取鍵"""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()
    
    def get(self, query: str) -> Optional[Dict]:
        """獲取快取"""
        key = self._get_cache_key(query)
        
        if key in self.cache:
            cached_data = self.cache[key]
            
            # 檢查是否過期
            if datetime.now().timestamp() - cached_data['timestamp'] < self.duration:
                logger.info(f"🎯 快取命中: {query[:50]}...")
                return cached_data['data']
            else:
                # 清理過期快取
                del self.cache[key]
        
        return None
    
    def set(self, query: str, data: Dict):
        """設置快取"""
        key = self._get_cache_key(query)
        
        # 清理舊快取
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        self.cache[key] = {
            'data': data,
            'timestamp': datetime.now().timestamp()
        }
        
        logger.info(f"💾 快取已保存: {query[:50]}... (快取大小: {len(self.cache)})")

# 全局實例
search_engine = VectorSearchEngine()
answer_generator = AnswerGenerator()
cache_manager = CacheManager()

# API端點
@app.on_event("startup")
async def startup_event():
    """應用啟動事件"""
    logger.info("🚀 啟動神學知識庫 FAISS 向量搜索服務...")
    
    # 檢查環境變量
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("❌ 未設置 OPENAI_API_KEY 環境變量")
        raise ValueError("OPENAI_API_KEY is required")
    
    # 初始化搜索引擎
    documents_path = os.getenv("DOCUMENTS_PATH", "./documents")
    await search_engine.initialize(documents_path)
    
    # 輸出系統信息
    memory_info = psutil.virtual_memory()
    logger.info(f"💾 系統內存: {memory_info.total // (1024**3)}GB (可用: {memory_info.available // (1024**3)}GB)")
    logger.info("✅ 服務啟動完成")

@app.get("/")
async def root():
    """根端點"""
    return {
        "service": "神學知識庫 FAISS 向量搜索API",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "🚀 高性能FAISS向量搜索",
            "🧠 多語言語義理解",
            "💾 智能問題快取",
            "🎯 精確文檔檢索",
            "✨ OpenAI智能問答"
        ]
    }

@app.get("/api/health")
async def health_check():
    """健康檢查"""
    memory_info = psutil.virtual_memory()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "memory_usage": f"{memory_info.percent}%",
        "available_memory": f"{memory_info.available // (1024**2)}MB",
        "index_loaded": search_engine.faiss_manager.index is not None,
        "documents_count": len(search_engine.documents),
        "cache_size": len(cache_manager.cache)
    }

@app.post("/api/search", response_model=SearchResponse)
async def vector_search(request: SearchRequest):
    """向量搜索API"""
    start_time = datetime.now()
    
    try:
        # 檢查快取
        cache_hit = False
        if request.use_cache:
            cached_result = cache_manager.get(request.question)
            if cached_result:
                cached_result['cache_hit'] = True
                return SearchResponse(**cached_result)
        
        # 執行向量搜索
        relevant_docs, search_time = await search_engine.search(
            request.question, 
            request.top_k
        )
        
        if not relevant_docs:
            return SearchResponse(
                answer="抱歉，我在知識庫中找不到相關資訊來回答這個問題。請嘗試使用不同的關鍵詞或更具體的問題。",
                sources=[],
                search_time=search_time,
                total_time=(datetime.now() - start_time).total_seconds(),
                cache_hit=False,
                confidence_score=0.0
            )
        
        # 生成答案
        answer, generation_time = await answer_generator.generate_answer(
            request.question,
            relevant_docs,
            request.temperature
        )
        
        # 計算信心分數
        avg_score = sum(doc['score'] for doc in relevant_docs) / len(relevant_docs)
        confidence_score = min(avg_score * 1.2, 1.0)  # 調整信心分數
        
        total_time = (datetime.now() - start_time).total_seconds()
        
        result = {
            "answer": answer,
            "sources": relevant_docs,
            "search_time": search_time,
            "total_time": total_time,
            "cache_hit": cache_hit,
            "confidence_score": confidence_score
        }
        
        # 保存到快取
        if request.use_cache and confidence_score > 0.5:
            cache_manager.set(request.question, result)
        
        return SearchResponse(**result)
        
    except Exception as e:
        logger.error(f"搜索失敗: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失敗: {str(e)}")

@app.get("/api/stats")
async def get_stats():
    """獲取統計信息"""
    return {
        "documents_count": len(search_engine.documents),
        "index_size": search_engine.faiss_manager.index.ntotal if search_engine.faiss_manager.index else 0,
        "cache_size": len(cache_manager.cache),
        "model_name": Config.MODEL_NAME,
        "vector_dimension": Config.VECTOR_DIM,
        "index_type": Config.INDEX_TYPE
    }

@app.post("/api/clear_cache")
async def clear_cache():
    """清理快取"""
    cache_manager.cache.clear()
    return {"message": "快取已清理", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "faiss_main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1,
        log_level="info"
    )