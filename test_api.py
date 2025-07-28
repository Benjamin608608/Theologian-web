#!/usr/bin/env python3
"""
FAISS神學知識庫API測試腳本
"""

import asyncio
import json
import time
from main import mock_vector_search, answer_generator, calculate_similarity

async def test_api_functions():
    """測試API核心功能"""
    print("🧪 開始測試FAISS神學知識庫API...")
    
    # 測試問題
    test_questions = [
        "什麼是三位一體？",
        "什麼是因信稱義？",
        "什麼是預定論？",
        "什麼是救恩？"
    ]
    
    print(f"\n📋 測試 {len(test_questions)} 個神學問題:")
    
    total_time = 0
    successful_tests = 0
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n{i}. 測試問題: {question}")
        
        try:
            start_time = time.time()
            
            # 執行向量搜索
            relevant_docs, search_time = await mock_vector_search(question, 3)
            
            # 生成答案
            answer, gen_time = await answer_generator.generate_answer(
                question, relevant_docs
            )
            
            end_time = time.time()
            response_time = end_time - start_time
            total_time += response_time
            
            print(f"   ✅ 搜索時間: {search_time:.3f}秒")
            print(f"   ✅ 生成時間: {gen_time:.3f}秒")
            print(f"   ✅ 總時間: {response_time:.3f}秒")
            print(f"   ✅ 找到 {len(relevant_docs)} 個相關文檔")
            print(f"   📝 答案預覽: {answer[:100]}...")
            
            successful_tests += 1
            
        except Exception as e:
            print(f"   ❌ 測試失敗: {e}")
    
    # 輸出測試總結
    print(f"\n📊 測試總結:")
    print(f"   ✅ 成功測試: {successful_tests}/{len(test_questions)}")
    print(f"   ⏱️  平均回應時間: {total_time/len(test_questions):.3f}秒")
    print(f"   🎯 成功率: {successful_tests/len(test_questions)*100:.1f}%")
    
    return successful_tests == len(test_questions)

def test_similarity_function():
    """測試相似度計算函數"""
    print("\n🔍 測試相似度計算...")
    
    test_cases = [
        ("三位一體", "三位一體是基督教的核心教義"),
        ("因信稱義", "路德強調因信稱義的重要性"),
        ("預定論", "加爾文的預定論教導"),
        ("無關問題", "這是一個完全不相關的內容")
    ]
    
    for query, doc in test_cases:
        similarity = calculate_similarity(query, doc)
        print(f"   查詢: '{query}' vs 文檔: '{doc[:30]}...'")
        print(f"   相似度: {similarity:.3f}")

async def main():
    """主測試函數"""
    print("🚀 FAISS神學知識庫API - 功能測試")
    print("=" * 50)
    
    # 測試相似度函數
    test_similarity_function()
    
    # 測試API功能
    api_success = await test_api_functions()
    
    print("\n" + "=" * 50)
    if api_success:
        print("🎉 所有測試完成！系統運行正常！")
        print("\n📋 下一步:")
        print("1. 運行 railway login 登錄Railway")
        print("2. 運行 ./deploy.sh 部署到Railway")
        print("3. 測試部署的API端點")
    else:
        print("⚠️  測試發現問題，請檢查代碼")
    
    return api_success

if __name__ == "__main__":
    result = asyncio.run(main())
