import pytest
import asyncio
import aiohttp
import json
import time
from typing import Dict, Any
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
            query = "artificial intelligence"
            start_time = time.time()
            
            async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                assert response.status == 200
                data = await response.json()
                
                search_time = time.time() - start_time
                print(f"검색어: {query}")
                print(f"검색 시간: {search_time:.2f}초")
                print(f"총 결과 수: {data['results']['total_results']}")
                
                # Wikipedia 결과 확인
                wiki_results = data['results']['sources'].get('wikipedia', [])
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
            
            query = "machine learning"
            start_time = time.time()
            
            async with session.get(f'http://127.0.0.1:8000/api/search/formatted?query={query}') as response:
                assert response.status == 200
                data = await response.json()
                
                search_time = time.time() - start_time
                print(f"검색어: {query}")
                print(f"검색 시간: {search_time:.2f}초")
                
                formatted_results = data['formatted_results']
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
            special_query = "AI & ML: 2024 trends"
            async with session.get(f'http://127.0.0.1:8000/api/search?query={special_query}') as response:
                assert response.status == 200
                data = await response.json()
                print(f"   ✅ 특수 문자 검색어 정상 처리: {data['results']['total_results']}개 결과")
    
    @pytest.mark.asyncio
    async def test_search_performance(self):
        """검색 성능 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 검색 성능 테스트 ===")
            
            queries = [
                "artificial intelligence",
                "machine learning",
                "deep learning",
                "natural language processing"
            ]
            
            total_time = 0
            total_results = 0
            
            for i, query in enumerate(queries, 1):
                print(f"{i}. '{query}' 검색 중...")
                start_time = time.time()
                
                async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                    assert response.status == 200
                    data = await response.json()
                    
                    search_time = time.time() - start_time
                    total_time += search_time
                    total_results += data['results']['total_results']
                    
                    print(f"   완료: {search_time:.2f}초, {data['results']['total_results']}개 결과")
            
            avg_time = total_time / len(queries)
            avg_results = total_results / len(queries)
            
            print(f"\n성능 요약:")
            print(f"평균 검색 시간: {avg_time:.2f}초")
            print(f"평균 결과 수: {avg_results:.1f}개")
            print(f"총 검색 시간: {total_time:.2f}초")
            
            # 성능 기준 검증
            assert avg_time < 5, f"평균 검색 시간이 너무 김: {avg_time:.2f}초"
            assert total_time < 20, f"총 검색 시간이 너무 김: {total_time:.2f}초"
    
    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """동시 검색 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 동시 검색 테스트 ===")
            
            queries = [
                "python programming",
                "javascript development",
                "data science",
                "web development",
                "mobile apps"
            ]
            
            async def search_query(query: str):
                start_time = time.time()
                async with session.get(f'http://127.0.0.1:8000/api/search?query={query}') as response:
                    search_time = time.time() - start_time
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'query': query,
                            'success': True,
                            'time': search_time,
                            'results': data['results']['total_results']
                        }
                    else:
                        return {
                            'query': query,
                            'success': False,
                            'time': search_time,
                            'error': response.status
                        }
            
            # 동시 검색 실행
            start_time = time.time()
            tasks = [search_query(query) for query in queries]
            results = await asyncio.gather(*tasks)
            total_time = time.time() - start_time
            
            # 결과 분석
            success_count = sum(1 for r in results if r['success'])
            total_results = sum(r['results'] for r in results if r['success'])
            avg_time = sum(r['time'] for r in results) / len(results)
            
            print(f"동시 검색 결과:")
            print(f"성공: {success_count}/{len(queries)}")
            print(f"총 결과 수: {total_results}")
            print(f"평균 검색 시간: {avg_time:.2f}초")
            print(f"총 실행 시간: {total_time:.2f}초")
            
            for result in results:
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {result['query']}: {result['time']:.2f}초")
            
            # 성능 기준 검증
            assert success_count >= len(queries) * 0.8, f"성공률이 낮음: {success_count}/{len(queries)}"
            assert total_time < 15, f"동시 검색 시간이 너무 김: {total_time:.2f}초"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

