"""
网络搜索工具

使用 httpx 发起搜索请求，支持多种搜索引擎的后备策略。
"""

from __future__ import annotations

from typing import Any

import httpx

from ...core.types import ToolResult
from ..base import BaseTool


class WebSearchTool(BaseTool):
    """网络搜索"""

    name = "web_search"
    description = "在互联网上搜索信息。返回搜索结果摘要列表。"
    permission_level = "read"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果数量，默认 10，最大 20",
                "default": 10,
            },
            "language": {
                "type": "string",
                "description": "搜索结果语言，如 zh、en，默认 zh",
                "default": "zh",
            },
        },
        "required": ["query"],
    }

    _SEARCH_TIMEOUT = 15.0
    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    async def execute(
        self,
        query: str = "",
        num_results: int = 10,
        language: str = "zh",
        **kwargs,
    ) -> ToolResult:
        """
        执行网络搜索

        先尝试 DuckDuckGo，失败后使用 Google 作为后备。

        Args:
            query: 搜索查询
            num_results: 结果数量
            language: 语言偏好

        Returns:
            ToolResult
        """
        if not query.strip():
            return ToolResult(
                success=False,
                content="",
                error="搜索关键词不能为空",
            )

        num_results = min(max(num_results, 1), 20)

        # 先尝试 DuckDuckGo HTML
        try:
            results = await self._search_duckduckgo(query, num_results)
            if results:
                formatted = self._format_results(results, "DuckDuckGo")
                return ToolResult(
                    success=True,
                    content=formatted,
                    metadata={
                        "engine": "duckduckgo",
                        "query": query,
                        "num_results": len(results),
                    },
                )
        except Exception:
            pass

        # DuckDuckGo 失败，尝试 Google 作为后备
        try:
            results = await self._search_google(query, num_results, language)
            if results:
                formatted = self._format_results(results, "Google")
                return ToolResult(
                    success=True,
                    content=formatted,
                    metadata={
                        "engine": "google",
                        "query": query,
                        "num_results": len(results),
                    },
                )
        except Exception:
            pass

        # 所有搜索引擎均失败
        return ToolResult(
            success=False,
            content="",
            error=(f"搜索 '{query}' 失败：所有搜索引擎均不可用。请检查网络连接或稍后重试。"),
        )

    async def _search_duckduckgo(self, query: str, num_results: int) -> list[dict[str, str]]:
        """通过 DuckDuckGo HTML 搜索"""
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": self._USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        data = {"q": query, "kl": "cn-zh"}

        async with httpx.AsyncClient(timeout=self._SEARCH_TIMEOUT) as client:
            response = await client.post(url, headers=headers, data=data)
            response.raise_for_status()

        # 解析 HTML 结果
        results = self._parse_duckduckgo_html(response.text, num_results)
        return results

    def _parse_duckduckgo_html(self, html: str, limit: int) -> list[dict[str, str]]:
        """解析 DuckDuckGo HTML 搜索结果"""
        import re

        results = []
        # 用正则提取每个结果块
        # DuckDuckGo HTML 结果结构: <a class="result__a" href="...">title</a>
        #                                 <a class="result__snippet">snippet</a>
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links):
            if i >= limit:
                break
            title_clean = re.sub(r"<[^>]*>", "", title).strip()
            if not title_clean:
                continue
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]*>", "", snippets[i]).strip()
            results.append(
                {
                    "title": title_clean,
                    "url": href,
                    "snippet": snippet,
                }
            )

        return results

    async def _search_google(
        self, query: str, num_results: int, language: str
    ) -> list[dict[str, str]]:
        """通过 Google 搜索 (无 API Key 的基本搜索)"""
        url = "https://www.google.com/search"
        params = {
            "q": query,
            "num": str(num_results),
            "hl": language,
        }
        headers = {
            "User-Agent": self._USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=self._SEARCH_TIMEOUT) as client:
            response = await client.get(
                url,
                params=params,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()

        return self._parse_google_html(response.text, num_results)

    def _parse_google_html(self, html: str, limit: int) -> list[dict[str, str]]:
        """解析 Google HTML 搜索结果"""
        import re

        results = []
        # Google 搜索结果通常在 <h3> 标签中包含链接
        # 结构: <a href="..."><h3>title</h3></a> ... <div class="VwiC3b">snippet</div>
        # 备用: 提取所有 /url?q= 链接
        url_pattern = re.compile(r'/url\?q=(https?://[^&\s"]+)')
        title_pattern = re.compile(r"<h3[^>]*>(.*?)</h3>", re.DOTALL)
        snippet_pattern = re.compile(
            r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
            re.DOTALL,
        )

        urls = url_pattern.findall(html)
        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i in range(min(len(urls), limit)):
            url = urls[i]
            title = ""
            snippet = ""
            if i < len(titles):
                title = re.sub(r"<[^>]*>", "", titles[i]).strip()
            if i < len(snippets):
                snippet = re.sub(r"<[^>]*>", "", snippets[i]).strip()
            if url:
                results.append(
                    {
                        "title": title or url,
                        "url": url,
                        "snippet": snippet,
                    }
                )

        return results

    def _format_results(self, results: list[dict[str, str]], engine: str) -> str:
        """格式化搜索结果为可读文本"""
        if not results:
            return f"[{engine}] 未找到相关结果"

        lines = [f"=== 搜索结果 ({engine}) ===", ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")

        return "\n".join(lines)
