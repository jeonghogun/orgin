import pytest
import aiohttp
import time
from typing import Dict, Any, List
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestExternalAPIs:
    """외부 API 검색 기능 테스트"""
    
    @pytest.mark.asyncio
    async def test_wikipedia_search(self):
        """Wikipedia 검색 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== Wikipedia 검색 테스트 ===")
            
            # Wikipedia 검색 테스트
            query: str = "artificial intelligence"
            start_time: float = time.time()
            
            async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                assert response.status == 200
                data: Dict[str, Any] = await response.json()
                
                search_time: float = time.time() - start_time
                print(f"검색어: {query}")
                print(f"검색 시간: {search_time:.2f}초")
                print(f"총 결과 수: {data['results']['total_results']}")
                
                # Wikipedia 결과 확인
                wiki_results: List[Dict[str, Any]] = data['results']['sources'].get('wikipedia', [])
                print(f"Wikipedia 결과: {len(wiki_results)}개")
                
                for i, result in enumerate(wiki_results[:2], 1):
                    print(f"  {i}. {result['title']}")
                    print(f"     {result['snippet'][:100]}...")
                
                # 기본 검증
                assert data['results']['total_results'] >= 0
                assert search_time < 10  # 10초 이내 완료
    
    @pytest.mark.asyncio
    async def test_formatted_search_results(self):
        """포맷된 검색 결과 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 포맷된 검색 결과 테스트 ===")
            
            query: str = "machine learning"
            start_time: float = time.time()
            
            async with session.get(f'http://127.0.0.1:8000/api/search/formatted?query={query}') as response:
                assert response.status == 200
                data: Dict[str, Any] = await response.json()
                
                search_time: float = time.time() - start_time
                print(f"검색어: {query}")
                print(f"검색 시간: {search_time:.2f}초")
                
                formatted_results: str = data['formatted_results']
                print(f"포맷된 결과 길이: {len(formatted_results)} 문자")
                print("포맷된 결과 미리보기:")
                print(formatted_results[:500] + "..." if len(formatted_results) > 500 else formatted_results)
                
                # 기본 검증
                assert len(formatted_results) > 0
                assert search_time < 10  # 10초 이내 완료
    
    @pytest.mark.asyncio
    async def test_search_error_handling(self):
        """검색 에러 처리 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 검색 에러 처리 테스트 ===")
            
            # 1. 빈 검색어 테스트
            print("1. 빈 검색어 테스트...")
            async with session.get('http://127.0.0.1:8000/api/search?query=') as response:
                assert response.status == 400
                print("   ✅ 빈 검색어 400 에러 정상 처리")
            
            # 2. 너무 짧은 검색어 테스트
            print("2. 짧은 검색어 테스트...")
            async with session.get('http://127.0.0.1:8000/api/search?query=a') as response:
                assert response.status == 400
                print("   ✅ 짧은 검색어 400 에러 정상 처리")
            
            # 3. 특수 문자 포함 검색어 테스트
            print("3. 특수 문자 검색어 테스트...")
            special_query: str = "AI & ML: 2024 trends"
            async with session.get(f'http://127.0.0.1:8000/api/search?query={special_query}') as response:
                assert response.status == 200
                data: Dict[str, Any] = await response.json()
                print(f"   ✅ 특수 문자 검색어 정상 처리: {data['results']['total_results']}개 결과")
    
    @pytest.mark.asyncio
    async def test_search_performance(self):
        """검색 성능 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 검색 성능 테스트 ===")
            
            queries: List[str] = [
                "artificial intelligence",
                "machine learning",
                "deep learning",
                "neural networks",
                "computer vision"
            ]
            
            performance_results: List[float] = []
            
            for query in queries:
                start_time: float = time.time()
                async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                    assert response.status == 200
                    data: Dict[str, Any] = await response.json()
                    search_time: float = time.time() - start_time
                    performance_results.append(search_time)
                    
                    print(f"'{query}': {search_time:.2f}초, {data['results']['total_results']}개 결과")
            
            avg_time: float = sum(performance_results) / len(performance_results)
            max_time: float = max(performance_results)
            
            print(f"\n성능 요약:")
            print(f"평균 검색 시간: {avg_time:.2f}초")
            print(f"최대 검색 시간: {max_time:.2f}초")
            
            # 성능 기준 검증
            assert avg_time < 5.0, f"평균 검색 시간이 너무 김: {avg_time:.2f}초"
            assert max_time < 10.0, f"최대 검색 시간이 너무 김: {max_time:.2f}초"
    
    @pytest.mark.asyncio
    async def test_search_result_quality(self):
        """검색 결과 품질 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 검색 결과 품질 테스트 ===")
            
            query: str = "Python programming"
            async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                assert response.status == 200
                data: Dict[str, Any] = await response.json()
                
                results: List[Dict[str, Any]] = data['results'].get('items', [])
                print(f"검색어: {query}")
                print(f"총 결과 수: {len(results)}")
                
                # 결과 품질 검증
                for i, result in enumerate(results[:3], 1):
                    title: str = result.get('title', '')
                    snippet: str = result.get('snippet', '')
                    link: str = result.get('link', '')
                    
                    print(f"\n결과 {i}:")
                    print(f"  제목: {title}")
                    print(f"  요약: {snippet[:100]}...")
                    print(f"  링크: {link}")
                    
                    # 기본 품질 검증
                    assert len(title) > 0, "제목이 비어있음"
                    assert len(snippet) > 0, "요약이 비어있음"
                    assert link.startswith('http'), "유효하지 않은 링크"
                    assert 'python' in title.lower() or 'python' in snippet.lower(), "관련성 부족"
                
                # 전체 결과 검증
                assert len(results) > 0, "검색 결과가 없음"
                assert data['results']['total_results'] > 0, "총 결과 수가 0"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



