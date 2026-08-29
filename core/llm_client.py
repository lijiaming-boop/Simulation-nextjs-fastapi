"""直连 Anthropic Messages API 的 LLM 客户端

绕过 claude-agent-sdk（SDK 的认证机制与自定义 ANTHROPIC_BASE_URL 代理
不兼容），用 httpx 直连代理端点 /v1/messages。

用法：
    >>> from core.llm_client import DirectLLMClient
    >>> client = DirectLLMClient()
    >>> text = client.create_message("用一句话介绍惠州")
    >>> print(text)

环境变量：
    ANTHROPIC_BASE_URL  默认 https://api.anthropic.com
    ANTHROPIC_API_KEY   必填
    ANTHROPIC_MODEL     默认 claude-sonnet-4-20250514
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Iterator, Optional


class LLMError(Exception):
    """LLM 调用错误"""


class DirectLLMClient:
    """直连 Anthropic Messages API 的轻量客户端（同步 + 流式）

    不依赖 anthropic SDK，仅用 httpx 实现。
    """

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        import httpx  # 延迟 import，避免无 httpx 时整个模块无法加载

        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY 环境变量未设置")
        self.model = model or os.getenv("ANTHROPIC_MODEL") or self.DEFAULT_MODEL
        self.timeout = timeout
        self._httpx = httpx
        self._repair_ssl_cert_env()

    @staticmethod
    def _repair_ssl_cert_env() -> None:
        """修复失效的 SSL_CERT_FILE 环境变量

        httpx 创建 SSL 上下文时会读取 SSL_CERT_FILE；部分机器（如 Miniconda
        激活脚本）会注入指向不存在文件的路径，导致所有请求直接 FileNotFoundError。
        检测到坏路径时回退到 certifi 证书包（httpx 的必然依赖）。
        """
        bad = os.getenv("SSL_CERT_FILE")
        if bad and not os.path.isfile(bad):
            try:
                import certifi
                os.environ["SSL_CERT_FILE"] = certifi.where()
            except ImportError:
                os.environ.pop("SSL_CERT_FILE", None)

    # ==================== 公共接口 ====================

    def create_message(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> str:
        """同步调用，返回 LLM 响应文本"""
        text, _ = self.create_message_with_usage(
            prompt, system=system, max_tokens=max_tokens, temperature=temperature
        )
        return text

    def create_message_with_usage(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> tuple[str, dict[str, int]]:
        """同步调用，返回 (响应文本, token 用量)

        用量字典: {"input_tokens": int, "output_tokens": int}，
        代理未返回 usage 字段时对应项为 0。
        """
        payload = self._build_payload(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        with self._httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
        if resp.status_code != 200:
            raise LLMError(
                f"LLM 返回 {resp.status_code}: {resp.text[:500]}"
            )
        body = resp.json()
        usage_raw = body.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0) or 0,
            "output_tokens": usage_raw.get("output_tokens", 0) or 0,
        }
        return self._extract_text(body), usage

    def stream_message(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> Iterator[str]:
        """流式调用，逐块产出增量文本（event: content_block_delta）

        如果代理的流式接口报错（比如 litellm 常见 bug），自动降级为同步调用。
        """
        payload = self._build_payload(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        try:
            yield from self._do_stream(payload)
        except LLMError as e:
            # 检测到代理流式失败，降级为同步
            if "stream" in str(e).lower() or "list index" in str(e).lower() or "error" in str(e).lower():
                fallback_payload = self._build_payload(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                )
                with self._httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/v1/messages",
                        headers=self._headers(),
                        json=fallback_payload,
                    )
                if resp.status_code != 200:
                    raise
                yield self._extract_text(resp.json())
            else:
                raise

    def _do_stream(self, payload: dict[str, Any]) -> Iterator[str]:
        """真正的 SSE 流式读取"""
        with self._httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    raise LLMError(
                        f"LLM 流式响应失败 {resp.status_code}: "
                        f"{resp.read().decode('utf-8', errors='replace')[:500]}"
                    )
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        evt = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    # 代理可能在流式里嵌入 error event
                    if "error" in evt:
                        err_msg = evt["error"].get("message", "") if isinstance(evt["error"], dict) else str(evt["error"])
                        raise LLMError(f"代理流式错误: {err_msg[:300]}")
                    if evt.get("type") != "content_block_delta":
                        continue
                    delta = evt.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield text

    def call_with_callback(
        self,
        prompt: str,
        callback: Callable[[str], None],
        *,
        system: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> str:
        """流式调用，每收到一个 delta 就通过 callback 传出增量文本，最终返回完整文本"""
        chunks: list[str] = []
        for chunk in self.stream_message(
            prompt, system=system, max_tokens=max_tokens
        ):
            chunks.append(chunk)
            try:
                callback(chunk)
            except Exception:
                # 回调失败不影响主流程
                pass
        return "".join(chunks)

    # ==================== 内部方法 ====================

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def _build_payload(
        self,
        prompt: str,
        *,
        system: Optional[str],
        max_tokens: int,
        temperature: Optional[float],
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    @staticmethod
    def _extract_text(body: dict) -> str:
        """从 Messages API 响应中提取文本"""
        content = body.get("content") or []
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        if not parts:
            raise LLMError(f"LLM 响应无文本内容: {json.dumps(body)[:300]}")
        return "".join(parts)


# ==================== 模块级便捷函数 ====================

def quick_call(prompt: str, **kwargs: Any) -> str:
    """一行调用：DirectLLMClient().create_message(prompt)"""
    return DirectLLMClient().create_message(prompt, **kwargs)
