"""LLM 网关（M2）

所有 LLM 调用的统一入口，提供：
- **计量**：每次调用落 llm_calls 表（谁、什么用途、哪个模型、多少 token）
- **预算**：按用户的日 token 预算，超额抛 LLMBudgetError（可被上层降级处理）
- **熔断**：连续失败 N 次后短暂熔断，避免雪崩式重试烧钱
- **重试**：瞬时错误指数退避重试（预算错误不重试）
- **路由**：按用途选模型（决策用便宜模型，重活用默认模型）

对外暴露 create_message_with_usage 兼容签名，可直接作为 LLMBrain 的 client。
claude-agent-sdk 的多轮技能会话（空压提取/冷站仿真）暂不收编——它们是
agent 会话而非单次调用，M3 后按"LLM 型工具"方式纳入统一计量。
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any, Optional

from core.llm_client import DirectLLMClient, LLMError

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0
BREAKER_THRESHOLD = 5          # 连续失败次数阈值
BREAKER_COOLDOWN_SECONDS = 60  # 熔断冷却时长


class LLMBudgetError(LLMError):
    """用户当日 LLM token 预算已用尽"""


class LLMGatewayError(LLMError):
    """网关熔断或上游不可用"""


class LLMGateway:
    """带治理能力的 LLM 客户端（计量/预算/熔断/重试/路由）"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        purpose_default: str = "misc",
        daily_token_budget: Optional[int] = None,
        client: Optional[DirectLLMClient] = None,
        store=None,
    ) -> None:
        import os
        self.client = client or DirectLLMClient()
        self.user_id = user_id
        self.purpose_default = purpose_default
        import os as _os
        self.daily_token_budget = daily_token_budget or int(
            _os.getenv("LLM_DAILY_TOKEN_BUDGET", "500000"))
        self.heavy_model = _os.getenv("LLM_MODEL_HEAVY") or self.client.model
        self.fast_model = _os.getenv("LLM_MODEL_FAST") or self.client.model
        self._store = store  # PersistentSessionStore，延迟注入避免循环依赖
        self._consecutive_failures = 0
        self._breaker_open_until = 0.0

    # ---------- 兼容 LLMBrain 的调用签名 ----------

    def create_message_with_usage(self, prompt: str, *, system: Optional[str] = None,
                                  max_tokens: int = 4096,
                                  temperature: Optional[float] = None,
                                  purpose: Optional[str] = None,
                                  model_tier: str = "fast") -> tuple[str, dict[str, int]]:
        text, usage, _ = self.chat_with_meta(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, purpose=purpose or self.purpose_default,
            model_tier=model_tier,
        )
        return text, usage

    def create_message(self, prompt: str, *, system: Optional[str] = None,
                       max_tokens: int = 4096, temperature: Optional[float] = None,
                       purpose: Optional[str] = None,
                       model_tier: str = "fast") -> str:
        text, _, _ = self.chat_with_meta(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, purpose=purpose or self.purpose_default,
            model_tier=model_tier,
        )
        return text

    # ---------- 核心 ----------

    def chat_with_meta(self, prompt: str, *, system: Optional[str] = None,
                       max_tokens: int = 4096, temperature: Optional[float] = None,
                       purpose: str = "misc", model_tier: str = "fast",
                       ) -> tuple[str, dict[str, int], str]:
        """执行一次受治理的 LLM 调用，返回 (文本, 用量, 模型)"""
        self._check_breaker()
        self._check_budget()

        model = self.heavy_model if model_tier == "heavy" else self.fast_model
        last_err: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            started = time.monotonic()
            try:
                original_model = self.client.model
                self.client.model = model
                try:
                    text, usage = self.client.create_message_with_usage(
                        prompt, system=system, max_tokens=max_tokens,
                        temperature=temperature,
                    )
                finally:
                    self.client.model = original_model
                self._on_success(usage, purpose, model, started)
                return text, usage, model
            except LLMBudgetError:
                raise
            except LLMError as e:
                last_err = e
                self._on_failure()
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

        raise LLMGatewayError(f"LLM 调用在重试后仍失败: {last_err}")

    # ---------- 治理组件 ----------

    def _check_breaker(self) -> None:
        if time.monotonic() < self._breaker_open_until:
            raise LLMGatewayError("LLM 网关熔断中（连续失败过多），稍后重试")

    def _check_budget(self) -> None:
        if self.daily_token_budget <= 0 or not self._store:
            return
        used = self._store.llm_tokens_used_today(self.user_id)
        if used >= self.daily_token_budget:
            raise LLMBudgetError(
                f"用户 {self.user_id or 'anonymous'} 当日 LLM token 预算已用尽"
                f"（已用 {used}，预算 {self.daily_token_budget}）。"
                "可改用 mode=deterministic 或由管理员调整预算。"
            )

    def _on_success(self, usage: dict, purpose: str, model: str,
                    started: float) -> None:
        self._consecutive_failures = 0
        self._record_call(usage, purpose, model, started, ok=True)

    def _on_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= BREAKER_THRESHOLD:
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_SECONDS
            self._consecutive_failures = 0

    def _record_call(self, usage: dict, purpose: str, model: str,
                     started: float, ok: bool) -> None:
        if not self._store:
            return
        try:
            self._store.record_llm_call(
                user_id=self.user_id, purpose=purpose, model=model,
                input_tokens=usage.get("input_tokens") or 0,
                output_tokens=usage.get("output_tokens") or 0,
                duration_ms=int((time.monotonic() - started) * 1000),
                ok=ok,
            )
        except Exception:
            # 计量失败不影响调用本身
            pass
