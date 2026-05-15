"""prompt_injector 事件处理器。

订阅 on_prompt_build 事件，在 chatter prompt 构建时
根据配置规则向指定模板注入自定义提示词内容。
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


def _scope_matches(spec: str, chat_type: str, chat_id: str, platform: str = "") -> bool:
    """判断单条作用域字符串是否命中当前聊天流。

    Args:
        spec: 格式为 "group:*" / "group:123" / "user:*" / "user:456"
        chat_type: 聊天类型，"group" 或 "private"
        chat_id: 群号（group）或原始 person_id 哈希（private）
        platform: 平台标识，用于计算私聊用户哈希

    Returns:
        bool: 是否命中
    """
    if ":" not in spec:
        return False
    kind, value = spec.split(":", 1)
    kind = kind.strip().lower()
    value = value.strip()

    if kind == "group":
        if chat_type != "group":
            return False
        return value == "*" or value == chat_id
    if kind == "user":
        if chat_type != "private":
            return False
        if value == "*":
            return True
        # value 是原始 QQ 号，需要与哈希后的 person_id 比较
        if platform:
            expected = hashlib.sha256(f"{platform}_{value}".encode()).hexdigest()
            return expected == chat_id
        # 没有 platform 时退而求其次直接比较（兼容）
        return value == chat_id
    return False


def _entry_matches(entry: "InjectionEntry", stream_info: dict[str, Any]) -> bool:
    """判断单条注入规则的聊天流作用域是否命中当前流。

    **规则：**
    - include/exclude 均为空 → 全局生效
    - include 非空 → 至少命中一条 include 规则才算命中
    - exclude 非空 → 命中任意一条 exclude 则排除

    **include/exclude 格式：**
    - ``"group:*"``   — 所有群聊
    - ``"group:123"`` — 指定群
    - ``"user:*"``    — 所有私聊
    - ``"user:456"``  — 指定私聊用户

    Args:
        entry: 单条注入规则配置
        stream_info: 由 stream_api.get_stream_info 返回的聊天流元数据

    Returns:
        bool: 当前规则是否对该聊天流生效
    """
    chat_type = str(stream_info.get("chat_type", ""))
    platform = str(stream_info.get("platform", ""))
    # 群聊用 group_id，私聊用 person_id（哈希格式）
    if chat_type == "group":
        chat_id = str(stream_info.get("group_id") or "")
    else:
        chat_id = str(stream_info.get("person_id") or "")

    # include 为空 → 全局生效，否则至少命中一条
    if entry.include:
        if not any(_scope_matches(spec, chat_type, chat_id, platform) for spec in entry.include):
            return False

    # exclude：命中任意一条则排除
    if entry.exclude:
        if any(_scope_matches(spec, chat_type, chat_id, platform) for spec in entry.exclude):
            return False

    return True


class PromptInjectorHandler(BaseEventHandler):
    """自定义提示词注入器。

    订阅 ``on_prompt_build`` 事件，根据配置规则和当前提示词模板名称
    向目标模板注入自定义提示词内容。

    支持：
    - 全局 target_prompts 控制注入哪个模板
    - 每条规则独立的 target_prompts 字段（覆盖全局）
    - include/exclude 作用域控制（格式："group:*" "user:123" 等）

    多条规则均命中时，按配置顺序拼接后一次性注入，与其他注入器互不干扰。
    """

    handler_name: str = "prompt_injector_handler"
    handler_description: str = "在目标 prompt 中注入自定义提示词（支持 dfc/kfc 多模板、include/exclude 作用域）"
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
        - kfc_system_prompt / kfc_user_prompt 等 → 追加到 params["template"] 末尾

        每条规则可通过 target_prompts 字段独立控制注入目标；
        为空时沿用全局 plugin.target_prompts 配置。

        Args:
            event_name: 事件名称
            params: 事件参数，包含模板名称、values 等

        Returns:
            tuple[EventDecision, dict]: 决策 + 更新后的参数
        """
        config = self._get_config()
        if not config.plugin.enabled:
            return EventDecision.SUCCESS, params

        prompt_name: str = params.get("name", "")
        global_target_prompts: list[str] = config.plugin.target_prompts

        # 全局过滤：如果当前模板不在任何规则的目标列表（包括全局和 per-rule）中，直接跳过
        is_relevant = prompt_name in global_target_prompts or any(
            prompt_name in (entry.target_prompts or []) for entry in config.inject if entry.enabled
        )
        if not is_relevant:
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
        # 每条规则先检查 per-rule target_prompts，再检查聊天流匹配
        collected: list[str] = []
        for entry in config.inject:
            if not entry.enabled:
                continue
            content = entry.content.strip()
            if not content:
                continue
            # per-rule 模板过滤：非空时覆盖全局，为空时沿用全局
            rule_targets = entry.target_prompts if entry.target_prompts else global_target_prompts
            if prompt_name not in rule_targets:
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

        # 所有 chatter 均通过 values["extra"] 注入额外内容；
        # builder 负责将 extra 提取为独立 payload（kfc）或占位符替换（dfc）
        existing = str(values.get("extra", ""))
        values["extra"] = (existing + "\n" + injected) if existing else injected

        return EventDecision.SUCCESS, params
