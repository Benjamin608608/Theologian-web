#!/usr/bin/env python3
"""
神學文檔數據處理腳本
用於將2GB的神學文檔轉換為FAISS向量索引

使用方法:
python data_processor.py --input_dir /path/to/documents --output_dir ./processed_data
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
import hashlib
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from tqdm import tqdm
import psutil

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TheologyDocumentProcessor:
    """神學文檔處理器"""
    
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"):
        self.model_name = model_name
        self.model = None
        self.chunk_size = 512
        self.overlap = 50
        
    def initialize_model(self):
        """初始化模型"""
        logger.info(f"載入模型: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info("模型載入完成")
    
    def load_documents_from_directory(self, input_dir: str) -> List[Dict[str, Any]]:
        """從目錄載入所有文檔"""
        logger.info(f"開始處理目錄: {input_dir}")
        
        documents = []
        input_path = Path(input_dir)
        
        if not input_path.exists():
            raise ValueError(f"輸入目錄不存在: {input_dir}")
        
        # 支援的文件格式
        supported_formats = {
            '.txt': self.load_text_file,
            '.md': self.load_text_file,
            '.json': self.load_json_file,
            '.csv': self.load_csv_file,
            '.tsv': self.load_tsv_file,
        }
        
        # 遞歸處理所有文件
        total_files = 0
        processed_files = 0
        
        for file_path in input_path.rglob('*'):
            if file_path.is_file():
                total_files += 1
                
                file_extension = file_path.suffix.lower()
                if file_extension in supported_formats:
                    try:
                        loader_func = supported_formats[file_extension]
                        file_documents = loader_func(file_path)
                        documents.extend(file_documents)
                        processed_files += 1
                        
                        if processed_files % 100 == 0:
                            logger.info(f"已處理 {processed_files}/{total_files} 個文件")
                            
                    except Exception as e:
                        logger.error(f"處理文件失敗 {file_path}: {e}")
                else:
                    logger.debug(f"跳過不支援的文件格式: {file_path}")
        
        logger.info(f"文檔載入完成: {len(documents)} 個文檔片段")
        return documents
    
    def load_text_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """載入文本文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # 嘗試其他編碼
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin1') as f:
                    content = f.read()
        
        return self.chunk_document(content, str(file_path))
    
    def load_json_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """載入JSON文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 如果是單個對象，轉換為列表
        if isinstance(data, dict):
            data = [data]
        
        documents = []
        for item in data:
            if isinstance(item, dict):
                # 提取文本內容
                content = self.extract_text_from_dict(item)
                if content:
                    docs = self.chunk_document(content, str(file_path), item)
                    documents.extend(docs)
        
        return documents
    
    def load_csv_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """載入CSV文件"""
        import pandas as pd
        
        df = pd.read_csv(file_path)
        documents = []
        
        for idx, row in df.iterrows():
            # 合併所有列的內容
            content = ' '.join([str(val) for val in row.values if pd.notna(val)])
            if content.strip():
                docs = self.chunk_document(content, f"{file_path}:row_{idx}", row.to_dict())
                documents.extend(docs)
        
        return documents
    
    def load_tsv_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """載入TSV文件"""
        import pandas as pd
        
        df = pd.read_csv(file_path, sep='\t')
        documents = []
        
        for idx, row in df.iterrows():
            content = ' '.join([str(val) for val in row.values if pd.notna(val)])
            if content.strip():
                docs = self.chunk_document(content, f"{file_path}:row_{idx}", row.to_dict())
                documents.extend(docs)
        
        return documents
    
    def extract_text_from_dict(self, data: Dict[str, Any]) -> str:
        """從字典中提取文本內容"""
        text_parts = []
        
        # 常見的文本字段名
        text_fields = ['text', 'content', 'body', 'description', 'title', 'name', 'summary']
        
        for field in text_fields:
            if field in data and isinstance(data[field], str):
                text_parts.append(data[field])
        
        # 如果沒有找到標準字段，提取所有字符串值
        if not text_parts:
            for key, value in data.items():
                if isinstance(value, str) and len(value.strip()) > 10:
                    text_parts.append(f"{key}: {value}")
        
        return ' '.join(text_parts)
    
    def chunk_document(self, content: str, source: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """將文檔分塊"""
        if not content or len(content.strip()) < 20:
            return []
        
        chunks = []
        content_length = len(content)
        
        for i in range(0, content_length, self.chunk_size - self.overlap):
            chunk_content = content[i:i + self.chunk_size].strip()
            
            # 跳過太短的片段
            if len(chunk_content) < 50:
                continue
            
            chunk_id = hashlib.md5(f"{source}_{i}".encode()).hexdigest()
            
            chunk_metadata = {
                "source": source,
                "start_pos": i,
                "end_pos": min(i + self.chunk_size, content_length),
                "chunk_index": len(chunks),
                "created_at": datetime.now().isoformat()
            }
            
            # 添加原始元數據
            if metadata:
                chunk_metadata.update(metadata)
            
            chunk = {
                "id": chunk_id,
                "content": chunk_content,
                "metadata": chunk_metadata
            }
            
            chunks.append(chunk)
        
        return chunks
    
    def vectorize_documents(self, documents: List[Dict[str, Any]], batch_size: int = 64) -> np.ndarray:
        """向量化文檔"""
        logger.info(f"開始向量化 {len(documents)} 個文檔片段...")
        
        texts = [doc['content'] for doc in documents]
        all_vectors = []
        
        # 分批處理避免內存溢出
        for i in tqdm(range(0, len(texts), batch_size), desc="向量化進度"):
            batch_texts = texts[i:i + batch_size]
            batch_vectors = self.model.encode(
                batch_texts, 
                show_progress_bar=False,
                convert_to_numpy=True
            )
            all_vectors.append(batch_vectors)
            
            # 內存監控
            memory_info = psutil.virtual_memory()
            if memory_info.percent > 85:
                logger.warning(f"內存使用率過高: {memory_info.percent}%")
        
        vectors = np.vstack(all_vectors)
        logger.info(f"向量化完成: {vectors.shape}")
        
        return vectors
    
    def build_faiss_index(self, vectors: np.ndarray, index_type: str = "IVF_PQ") -> faiss.Index:
        """構建FAISS索引"""
        logger.info(f"構建FAISS索引: {index_type}")
        
        dimension = vectors.shape[1]
        
        if index_type == "IVF_PQ":
            # 高壓縮比索引
            nlist = min(1024, vectors.shape[0] // 10)  # 動態調整聚類數量
            quantizer = faiss.IndexFlatL2(dimension)
            index = faiss.IndexIVFPQ(quantizer, dimension, nlist, 96, 8)
            
            # 訓練索引
            logger.info("訓練FAISS索引...")
            index.train(vectors)
            
        elif index_type == "FLAT":
            # 平面索引（精確搜索）
            index = faiss.IndexFlatIP(dimension)
            
        else:
            raise ValueError(f"不支援的索引類型: {index_type}")
        
        # 添加向量
        logger.info("添加向量到索引...")
        index.add(vectors)
        
        logger.info(f"索引構建完成: {index.ntotal} 個向量")
        return index
    
    def save_processed_data(self, output_dir: str, documents: List[Dict[str, Any]], 
                          vectors: np.ndarray, index: faiss.Index):
        """保存處理後的數據"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存FAISS索引
        index_path = output_path / "theology_vectors.index"
        faiss.write_index(index, str(index_path))
        logger.info(f"FAISS索引已保存: {index_path}")
        
        # 保存文檔數據
        documents_path = output_path / "documents.pkl"
        with open(documents_path, 'wb') as f:
            pickle.dump(documents, f)
        logger.info(f"文檔數據已保存: {documents_path}")
        
        # 保存向量數據（可選）
        vectors_path = output_path / "vectors.npy"
        np.save(vectors_path, vectors)
        logger.info(f"向量數據已保存: {vectors_path}")
        
        # 保存元數據
        metadata = {
            "total_documents": len(documents),
            "vector_dimension": vectors.shape[1],
            "index_type": type(index).__name__,
            "model_name": self.model_name,
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "created_at": datetime.now().isoformat(),
            "total_vectors": index.ntotal
        }
        
        metadata_path = output_path / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"元數據已保存: {metadata_path}")
        
        # 輸出統計信息
        total_size = sum(f.stat().st_size for f in output_path.iterdir())
        logger.info(f"總輸出大小: {total_size / (1024**2):.2f} MB")
    
    def process_documents(self, input_dir: str, output_dir: str, 
                         index_type: str = "IVF_PQ", batch_size: int = 64):
        """完整的文檔處理流程"""
        logger.info("🚀 開始神學文檔處理流程...")
        
        # 初始化模型
        self.initialize_model()
        
        # 載入文檔
        documents = self.load_documents_from_directory(input_dir)
        
        if not documents:
            raise ValueError("未找到任何有效文檔")
        
        # 向量化
        vectors = self.vectorize_documents(documents, batch_size)
        
        # 構建索引
        index = self.build_faiss_index(vectors, index_type)
        
        # 保存數據
        self.save_processed_data(output_dir, documents, vectors, index)
        
        logger.info("✅ 文檔處理完成!")
        
        # 輸出最終統計
        memory_info = psutil.virtual_memory()
        logger.info(f"📊 處理統計:")
        logger.info(f"   - 文檔片段: {len(documents)}")
        logger.info(f"   - 向量維度: {vectors.shape[1]}")
        logger.info(f"   - 索引類型: {index_type}")
        logger.info(f"   - 內存使用: {memory_info.percent}%")

def main():
    parser = argparse.ArgumentParser(description="神學文檔數據處理器")
    parser.add_argument("--input_dir", required=True, help="輸入文檔目錄")
    parser.add_argument("--output_dir", default="./processed_data", help="輸出目錄")
    parser.add_argument("--model_name", 
                       default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                       help="使用的模型名稱")
    parser.add_argument("--index_type", choices=["IVF_PQ", "FLAT"], 
                       default="IVF_PQ", help="FAISS索引類型")
    parser.add_argument("--batch_size", type=int, default=64, help="向量化批次大小")
    parser.add_argument("--chunk_size", type=int, default=512, help="文檔分塊大小")
    parser.add_argument("--overlap", type=int, default=50, help="分塊重疊大小")
    
    args = parser.parse_args()
    
    # 創建處理器
    processor = TheologyDocumentProcessor(args.model_name)
    processor.chunk_size = args.chunk_size
    processor.overlap = args.overlap
    
    try:
        # 執行處理
        processor.process_documents(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            index_type=args.index_type,
            batch_size=args.batch_size
        )
        
    except Exception as e:
        logger.error(f"處理失敗: {e}")
        raise

if __name__ == "__main__":
    main()