"""prompt_injector 插件入口。

提供基于配置规则的动态提示词注入能力，支持按群号或私聊 QQ 号精准控制作用范围。
通过订阅 on_prompt_build 事件向 SystemReminderStore 写入流隔离的提示词内容，
由 chatter 的 LLMContextManager 自动拾取并注入到最新 user 消息，
兼容所有使用 with_reminder="actor" 的 chatter（dfc / kfc / anima 等）。
"""

from __future__ import annotations

from src.app.plugin_system.base import BasePlugin, register_plugin
from src.app.plugin_system.api.log_api import get_logger

from .config import PromptInjectorConfig
from .event_handler import PromptInjectorHandler

logger = get_logger("prompt_injector")


@register_plugin
class PromptInjectorPlugin(BasePlugin):
    """提示词注入插件。

    动态向 chatter 的 SystemReminder 写入自定义内容，
    支持按群号或私聊 QQ 号精准控制生效范围（include/exclude），
    支持 per-rule 的注入策略（dynamic/fixed）和消费模式（forever/once）。
    通过 stream_id 隔离实现 per-stream 注入，互不干扰。
    """

    plugin_name = "prompt_injector"
    plugin_description = (
        "动态提示词注入插件，通过 SystemReminder 实现流隔离注入，"
        "支持 include/exclude 作用域、dynamic/fixed 注入策略、forever/once 消费模式"
    )
    plugin_version = "2.0.0"

    configs: list[type] = [PromptInjectorConfig]

    def get_components(self) -> list[type]:
        """返回当前插件包含的组件。"""
        config = self.config
        if isinstance(config, PromptInjectorConfig) and not config.plugin.enabled:
            return []
        return [PromptInjectorHandler]

    async def on_plugin_unload(self) -> None:
        """插件卸载时清理写入的 reminder，避免残留。

        由于 reminder 是流隔离的（按 stream_id 存储），卸载时无法遍历所有
        已注册的 stream_id 来逐个清理。这里清除全局命名空间下的专属 reminder
        作为兜底；流私有的 reminder 会在聊天流销毁时由框架自动清理。
        """
        from .event_handler import _REMINDER_NAME_FOREVER, _REMINDER_NAME_ONCE
        from src.core.prompt import SystemReminderBucket, get_system_reminder_store

        try:
            store = get_system_reminder_store()
            # 清除全局命名空间下的专属 reminder（stream_id=None）
            store.delete(SystemReminderBucket.ACTOR, _REMINDER_NAME_FOREVER)
            store.delete(SystemReminderBucket.ACTOR, _REMINDER_NAME_ONCE)
        except Exception as exc:
            logger.debug(f"prompt_injector: 卸载清理 reminder 时出错（忽略）: {exc}")
