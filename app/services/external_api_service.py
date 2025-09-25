"""External API Service - Google Search, Wikipedia, Weather integration."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# KST timezone
KST = timezone(timedelta(hours=9))

_WEATHER_CODE_KO: Dict[int, str] = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 낀 안개",
    51: "가벼운 이슬비",
    53: "보통 이슬비",
    55: "강한 이슬비",
    56: "가벼운 언 이슬비",
    57: "강한 언 이슬비",
    61: "약한 비",
    63: "보통 비",
    65: "강한 비",
    66: "약한 언 비",
    67: "강한 언 비",
    71: "약한 눈",
    73: "보통 눈",
    75: "강한 눈",
    77: "진눈깨비",
    80: "약한 소나기",
    81: "보통 소나기",
    82: "강한 소나기",
    85: "약한 소나기 눈",
    86: "강한 소나기 눈",
    95: "천둥번개",
    96: "천둥을 동반한 우박",
    99: "강한 천둥과 우박",
}


class ExternalSearchService:
    """External search service for Google CSE, Wikipedia, and weather data."""

    def __init__(self, timeout: int = 20) -> None:
        super().__init__()  # object 부모 클래스 호출로 경고 제거
        self.key: Optional[str] = settings.GOOGLE_API_KEY
        self.cse: Optional[str] = settings.GOOGLE_CSE_ID
        self.timeout: int = timeout

        # Log configuration status
        if not (self.key and self.cse):
            logger.warning(
                "Google API keys not configured - search functionality disabled"
            )
        else:
            logger.info("External search service initialized with Google CSE")

    def _safe_get(
        self, data: Dict[str, Any], key: str, default: Optional[Any] = None
    ) -> Any:
        """Safely get value from dictionary"""
        return data.get(key, default)

    def now_kst(self) -> str:
        """Get current KST time as formatted string"""
        kst_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        return f"현재 시간은 {kst_time} KST 입니다."

    async def weather(self, location: str) -> Optional[Dict[str, Any]]:
        """Fetch real-time weather data for a given location using Open-Meteo."""

        location = location.strip()
        if not location:
            return None

        try:
            geo = await self._geocode_location(location)
            if not geo:
                logger.info("Weather lookup failed to geocode location: %s", location)
                return None

            weather = await self._fetch_weather_data(geo["latitude"], geo["longitude"], geo["timezone"])
            if not weather:
                return None

            current = weather.get("current", {})
            hourly = weather.get("hourly", {})
            hourly_time = hourly.get("time") or []
            precipitation_probability = None
            observation_time = current.get("time")
            if observation_time and hourly_time:
                try:
                    index = hourly_time.index(observation_time)
                    precipitation_probability = (
                        hourly.get("precipitation_probability", [None])[index]
                        if index < len(hourly.get("precipitation_probability", []))
                        else None
                    )
                except ValueError:
                    precipitation_probability = None

            code = current.get("weather_code")
            description = _WEATHER_CODE_KO.get(code, "상세 날씨 정보를 확인할 수 없어요")

            display_location = geo.get("display_name") or location

            report = {
                "location": display_location,
                "queried_location": location,
                "observation_time": observation_time,
                "temperature": current.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "relative_humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "weather_code": code,
                "weather_description": description,
                "precipitation_probability": precipitation_probability,
                "units": weather.get("current_units", {}),
                "source": "Open-Meteo (https://open-meteo.com/)",
            }

            return report
        except Exception as exc:
            logger.error("Weather API error for %s: %s", location, exc, exc_info=True)
            return None

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
                    }
                    for it in items
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
        """Convenience helper returning a formatted weather summary."""

        report = await self.weather(location)
        if not report:
            return f"'{location}' 날씨 정보를 가져올 수 없습니다."

        return self._format_weather_summary(report)

    async def _geocode_location(self, location: str) -> Optional[Dict[str, Any]]:
        params = {
            "name": location,
            "count": 1,
            "language": settings.WEATHER_DEFAULT_LANGUAGE,
            "format": "json",
        }
        url = settings.WEATHER_GEOCODING_URL
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json() or {}
        except Exception as exc:
            logger.error("Geocoding request failed for %s: %s", location, exc)
            return None

        results = data.get("results") or []
        if not results:
            return None

        result = results[0]
        admin_parts = [
            part
            for part in [
                result.get("name"),
                result.get("admin1"),
                result.get("country"),
            ]
            if part
        ]
        display_name = ", ".join(dict.fromkeys(admin_parts))

        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if latitude is None or longitude is None:
            return None

        return {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": result.get("timezone", "Asia/Seoul"),
            "display_name": display_name,
        }

    async def _fetch_weather_data(
        self, latitude: float, longitude: float, timezone_name: str
    ) -> Optional[Dict[str, Any]]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "hourly": "precipitation_probability",
            "forecast_days": 1,
            "timezone": timezone_name,
            "language": settings.WEATHER_DEFAULT_LANGUAGE,
        }
        url = settings.WEATHER_API_BASE_URL
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json() or {}
        except Exception as exc:
            logger.error("Weather data request failed (%s, %s): %s", latitude, longitude, exc)
            return None

    def _format_weather_summary(self, report: Dict[str, Any]) -> str:
        units = report.get("units", {}) or {}
        temp_unit = units.get("temperature_2m", "°C")
        wind_unit = units.get("wind_speed_10m", "m/s")

        temperature = report.get("temperature")
        apparent = report.get("apparent_temperature")
        humidity = report.get("relative_humidity")
        wind = report.get("wind_speed")
        precipitation = report.get("precipitation_probability")
        description = report.get("weather_description") or "날씨 정보를 확인할 수 없어요"
        location = report.get("location") or report.get("queried_location")
        observed = report.get("observation_time")

        details: List[str] = [description]
        if temperature is not None:
            details.append(f"기온 {temperature}{temp_unit}")
        if apparent is not None:
            details.append(f"체감 {apparent}{temp_unit}")
        if humidity is not None:
            details.append(f"습도 {humidity}%")
        if wind is not None:
            details.append(f"바람 {wind}{wind_unit}")
        if precipitation is not None:
            details.append(f"강수확률 {precipitation}%")

        observed_text = f" ({observed})" if observed else ""
        details_text = ", ".join(details)
        return f"{location}의 현재 날씨{observed_text}: {details_text}."


