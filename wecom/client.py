from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

import httpx

class WeComAPIError(Exception):
    """Raised when WeCom API returns an error."""


class WeComClient:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._base_url = self._get_base_url()

    def _get_base_url(self) -> str:
        proxy_domain = self.config.get("proxy_domain", "").strip()
        if proxy_domain:
            return proxy_domain.rstrip("/")
        return "https://qyapi.weixin.qq.com"

    def _get_cache_file_path(self) -> str:
        cache_dir = os.path.join("config", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        corp_id = self.config.get("corp_id", "default")
        return os.path.join(cache_dir, f"wecom_token_{corp_id}.json")

    def _load_cached_token(self) -> Optional[Dict[str, Any]]:
        cache_file = self._get_cache_file_path()
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("expires_at", 0) > time.time() + 60:
                        return data
        except Exception:
            pass
        return None

    def _save_cached_token(self, token: str, expires_at: float) -> None:
        cache_file = self._get_cache_file_path()
        try:
            cache_data = {
                "access_token": token,
                "expires_at": expires_at,
                "cached_at": time.time()
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass

    async def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            data = response.json()
        if data.get("errcode") not in (0, None):
            raise WeComAPIError(data.get("errmsg", "Unknown WeCom API error"))
        return data

    async def _get_access_token(self) -> str:
        if not self._is_configured():
            raise WeComAPIError("WeCom credentials are not configured")

        async with self._lock:
            now = time.time()

            # Check memory cache first
            if self._access_token and now < self._expires_at - 60:
                return self._access_token

            # Check persistent cache
            cached_data = self._load_cached_token()
            if cached_data:
                self._access_token = cached_data.get("access_token")
                self._expires_at = cached_data.get("expires_at")
                return self._access_token

            # Fetch new token from API
            params = {
                "corpid": self.config.get("corp_id"),
                "corpsecret": self.config.get("app_secret"),
            }
            data = await self._request(
                "GET",
                f"{self._base_url}/cgi-bin/gettoken",
                params=params,
            )
            self._access_token = data.get("access_token")
            expires_in = data.get("expires_in", 7200)
            self._expires_at = now + expires_in

            # Save to persistent cache
            self._save_cached_token(self._access_token, self._expires_at)

            return self._access_token

    async def send_news(
        self,
        title: str,
        description: str,
        picurl: Optional[str] = None,
        url: Optional[str] = None,
        touser: Optional[str] = None,
        toparty: Optional[str] = None,
        totag: Optional[str] = None,
        chatid: Optional[str] = None,
    ) -> None:
        token = await self._get_access_token()

        article = {
            "title": title,
            "description": description,
        }

        if picurl:
            article["picurl"] = picurl
        if url:
            article["url"] = url

        if chatid:
            api_url = f"{self._base_url}/cgi-bin/appchat/send"
            payload = {
                "chatid": chatid,
                "msgtype": "news",
                "news": {
                    "articles": [article]
                },
                "safe": 0,
            }
        else:
            api_url = f"{self._base_url}/cgi-bin/message/send"
            payload = {
                "msgtype": "news",
                "agentid": self.config.get("agent_id"),
                "news": {
                    "articles": [article]
                },
                "safe": 0,
            }
            if touser:
                payload["touser"] = touser
            if toparty:
                payload["toparty"] = toparty
            if totag:
                payload["totag"] = totag

        await self._request(
            "POST",
            api_url,
            params={"access_token": token},
            json=payload,
        )


    async def send_text(
        self,
        content: str,
        touser: Optional[str] = None,
        toparty: Optional[str] = None,
        totag: Optional[str] = None,
        chatid: Optional[str] = None,
    ) -> None:
        token = await self._get_access_token()

        if chatid:
            url = f"{self._base_url}/cgi-bin/appchat/send"
            payload = {
                "chatid": chatid,
                "msgtype": "text",
                "text": {"content": content},
                "safe": 0,
            }
        else:
            url = f"{self._base_url}/cgi-bin/message/send"
            payload = {
                "msgtype": "text",
                "agentid": self.config.get("agent_id"),
                "text": {"content": content},
                "safe": 0,
            }
            if touser:
                payload["touser"] = touser
            if toparty:
                payload["toparty"] = toparty
            if totag:
                payload["totag"] = totag

        await self._request(
            "POST",
            url,
            params={"access_token": token},
            json=payload,
        )

    def _is_configured(self) -> bool:
        return all(
            [
                self.config.get("corp_id"),
                self.config.get("agent_id") is not None,
                self.config.get("app_secret"),
            ]
        )
