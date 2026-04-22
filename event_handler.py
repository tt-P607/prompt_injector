"""prompt_injector 事件处理器。

订阅 on_prompt_build 事件，在 default_chatter user prompt 构建前
根据配置规则向 extra 占位符追加自定义提示词内容。
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from src.app.plugin_system.api.event_api import EventDecision
from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.stream_api import get_stream_info
from src.app.plugin_system.base import BaseEventHandler

if TYPE_CHECKING:
    from .config import InjectionEntry, PromptInjectorConfig

logger = get_logger("prompt_injector")

_DFC_PROMPT = "default_chatter_user_prompt"


def _build_private_stream_id(platform: str, user_id: str) -> str:
    """构造私聊聊天流 ID（与框架 ChatStream.generate_stream_id 逻辑保持一致）。

    Args:
        platform: 平台标识
        user_id: 用户 QQ 号

    Returns:
        str: SHA-256 哈希的 stream_id
    """
    key = f"{platform}_{user_id}_private"
    return hashlib.sha256(key.encode()).hexdigest()


def _entry_matches(entry: "InjectionEntry", stream_info: dict[str, Any]) -> bool:
    """判断单条注入规则是否对当前聊天流生效。

    匹配语义：
    - group_targets 与 user_targets 均为空 → 对所有聊天流生效
    - 仅 group_targets 非空 → 只匹配其中指定的群聊，私聊不生效
    - 仅 user_targets 非空 → 只匹配其中指定的私聊，群聊不生效
    - 两者均非空 → 匹配指定群聊 + 指定私聊的并集

    Args:
        entry: 单条注入规则配置
        stream_info: 由 stream_api.get_stream_info 返回的聊天流元数据

    Returns:
        bool: 当前规则是否对该聊天流生效
    """
    has_group_filter = bool(entry.group_targets)
    has_user_filter = bool(entry.user_targets)

    # 两个列表均为空，全局生效
    if not has_group_filter and not has_user_filter:
        return True

    chat_type = stream_info.get("chat_type", "")
    actual_stream_id = stream_info.get("stream_id", "")
    platform = str(stream_info.get("platform", ""))

    if chat_type == "group" and has_group_filter:
        group_id = str(stream_info.get("group_id") or "")
        return group_id in entry.group_targets

    if chat_type == "private" and has_user_filter:
        for uid in entry.user_targets:
            if platform and uid:
                expected = _build_private_stream_id(platform, uid)
                if expected == actual_stream_id:
                    return True
        return False

    # chat_type 不属于已配置的过滤类型，不匹配
    return False


class PromptInjectorHandler(BaseEventHandler):
    """自定义提示词注入器。

    订阅 ``on_prompt_build`` 事件，当 ``default_chatter_user_prompt``
    模板即将构建时，根据配置规则向 ``values["extra"]`` 追加提示词内容。

    多条规则均命中时，按配置顺序拼接后一次性追加，与其他注入器
    （booku_memory、notice_injector）通过换行累加、互不干扰。
    """

    handler_name: str = "prompt_injector_handler"
    handler_description: str = "在 default_chatter user prompt extra 板块注入自定义提示词"
    weight: int = 15
    intercept_message: bool = False
    init_subscribe: list[str] = ["on_prompt_build"]

    def _get_config(self) -> "PromptInjectorConfig":
        """获取插件配置实例。"""
        from .config import PromptInjectorConfig

        config = self.plugin.config
        assert isinstance(config, PromptInjectorConfig), (
            f"prompt_injector: 预期 PromptInjectorConfig，实际为 {type(config)}"
        )
        return config

    async def execute(
        self,
        event_name: str,
        params: dict[str, Any],
    ) -> tuple[EventDecision, dict[str, Any]]:
        """处理 on_prompt_build 事件，向目标 chatter 注入自定义提示词。

        支持所有触发 on_prompt_build 事件的 chatter：
        - default_chatter_user_prompt → 注入到 values["extra"] 占位符
        - kfc_system_prompt 等 → 追加到 params["template"] 末尾

        Args:
            event_name: 事件名称
            params: 事件参数，包含模板名称、values 等

        Returns:
            tuple[EventDecision, dict]: 决策 + 更新后的参数
        """
        config = self._get_config()
        if not config.plugin.enabled:
            return EventDecision.SUCCESS, params

        # 仅处理已配置的目标模板
        prompt_name: str = params.get("name", "")
        if prompt_name not in config.plugin.target_prompts:
            return EventDecision.SUCCESS, params

        values = params.get("values", {})
        stream_id = str(values.get("stream_id", ""))
        if not stream_id:
            return EventDecision.SUCCESS, params

        try:
            stream_meta = await get_stream_info(stream_id)
        except Exception as exc:
            logger.error(
                f"prompt_injector: 查询 stream_info 时发生异常，"
                f"stream_id={stream_id!r}, error={exc}"
            )
            return EventDecision.SUCCESS, params

        if stream_meta is None:
            logger.error(
                f"prompt_injector: 无法获取 stream_info，跳过本轮注入 "
                f"(stream_id={stream_id!r})"
            )
            return EventDecision.SUCCESS, params

        # 收集所有命中规则的内容
        collected: list[str] = []
        for entry in config.inject:
            if not entry.enabled:
                continue
            content = entry.content.strip()
            if not content:
                continue
            if _entry_matches(entry, stream_meta):
                collected.append(content)

        if not collected:
            return EventDecision.SUCCESS, params

        injected = "\n".join(collected)

        if config.plugin.debug_log:
            logger.info(
                f"[prompt_injector] 汇总注入内容 ({prompt_name}, "
                f"stream_id={stream_id[:8]}...): {injected!r}"
            )

        # dfc 通过 values["extra"] 注入到用户提示词占位符；
        # kfc 等其他 chatter 无 {extra} 占位符，追加到系统提示词模板末尾
        if prompt_name == _DFC_PROMPT:
            existing = str(values.get("extra", ""))
            values["extra"] = (existing + "\n" + injected) if existing else injected
        else:
            template: str = str(params.get("template", ""))
            params["template"] = template + "\n\n" + injected

        return EventDecision.SUCCESS, params
