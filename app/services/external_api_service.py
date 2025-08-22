"""
External API Service - Google Search and Wikipedia integration
"""
from __future__ import annotations
import logging
import httpx
import urllib.parse
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from app.config.settings import settings

logger = logging.getLogger(__name__)

# KST timezone
KST = timezone(timedelta(hours=9))


class ExternalSearchService:
    """External search service for Google CSE and Wikipedia"""
    
    def __init__(self, timeout: int = 20) -> None:
        super().__init__()  # object 부모 클래스 호출로 경고 제거
        self.key: Optional[str] = settings.GOOGLE_API_KEY
        self.cse: Optional[str] = settings.GOOGLE_CSE_ID
        self.timeout: int = timeout
        
        # Log configuration status
        if not (self.key and self.cse):
            logger.warning("Google API keys not configured - search functionality disabled")
        else:
            logger.info("External search service initialized with Google CSE")

    def _safe_get(self, data: Dict[str, Any], key: str, default: Optional[Any] = None) -> Any:
        """Safely get value from dictionary"""
        return data.get(key, default)

    def now_kst(self) -> str:
        """Get current KST time as formatted string"""
        kst_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        return f"현재 시간은 {kst_time} KST 입니다."

    def weather(self, location: str) -> str:
        """Get weather information (placeholder)"""
        return f"'{location}' 날씨 기능은 준비 중입니다. 위치 기반 API 연동 예정이에요. 🙂"

    async def web_search(self, query: str, num: int = 5) -> List[Dict[str, str]]:
        """Perform web search using Google Custom Search API"""
        if not (self.key and self.cse):
            logger.warning("Web search requested but API keys not configured")
            return []
        
        try:
            q = urllib.parse.quote(query)
            url = f"https://www.googleapis.com/customsearch/v1?q={q}&key={self.key}&cx={self.cse}&num={num}"
            
            logger.info(f"Performing web search: {query}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url)
                r.raise_for_status()
                data: Dict[str, Any] = r.json()
                items: List[Dict[str, Any]] = self._safe_get(data, "items", []) or []
                
                results: List[Dict[str, str]] = [
                    {
                        "title": str(self._safe_get(it, "title", "")),
                        "link": str(self._safe_get(it, "link", "")),
                        "snippet": str(self._safe_get(it, "snippet", "")),
                        "displayLink": str(self._safe_get(it, "displayLink", "")),
                    } for it in items
                ]
                
                logger.info(f"Web search completed: {len(results)} results")
                return results
                
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []

    async def search(self, q: str, n: int = 3) -> List[Dict[str, str]]:
        """Alias for web_search with default n=3"""
        return await self.web_search(q, n)

    async def wiki_summary(self, topic: str, sentences: int = 3) -> Optional[str]:
        """Get Wikipedia summary using REST API"""
        try:
            logger.info(f"Fetching Wikipedia summary for: {topic}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Try Korean first, then English
                for lang in ("ko", "en"):
                    t = urllib.parse.quote(topic.replace(" ", "_"))
                    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{t}"
                    
                    try:
                        r = await client.get(url)
                        if r.status_code == 200:
                            data: Dict[str, Any] = r.json() or {}
                            extract: Optional[str] = self._safe_get(data, "extract")
                            if extract:
                                logger.info(f"Wikipedia summary found in {lang}")
                                return extract
                    except Exception as e:
                        logger.warning(f"Wikipedia {lang} request failed: {e}")
                        continue
                
                logger.warning(f"No Wikipedia summary found for: {topic}")
                return None
                
        except Exception as e:
            logger.error(f"Wikipedia summary failed: {e}")
            return None

    async def wiki(self, topic: str) -> str:
        """Get Wikipedia summary with fallback"""
        summary = await self.wiki_summary(topic)
        if summary:
            return f"**{topic}**에 대한 위키피디아 요약:\n\n{summary}"
        else:
            return f"'{topic}'에 대한 위키피디아 정보를 찾을 수 없습니다."

    async def get_current_time(self) -> str:
        """Get current system time in Korean format"""
        return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    async def get_weather(self, location: str = "서울") -> str:
        """Get weather information (placeholder for future implementation)"""
        # For now, return a placeholder message
        # TODO: Implement actual weather API when keys are available
        return f"날씨 정보는 현재 준비 중입니다. 위치: {location}"


# Global instance
search_service = ExternalSearchService()
