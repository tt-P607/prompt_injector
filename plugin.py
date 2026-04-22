"""prompt_injector 插件入口。

提供基于配置规则的动态提示词注入能力，支持按群号或私聊 QQ 号精准控制作用范围。
通过订阅 on_prompt_build 事件向目标 chatter 提示词追加内容，
兼容所有触发该事件的 chatter（dfc / kfc 等）。
"""

from __future__ import annotations

from src.app.plugin_system.base import BasePlugin, register_plugin

from .config import PromptInjectorConfig
from .event_handler import PromptInjectorHandler


@register_plugin
class PromptInjectorPlugin(BasePlugin):
    """提示词注入插件。

    动态向 chatter 的提示词注入自定义内容，
    支持按群号（group_targets）或私聊 QQ 号（user_targets）精准控制生效范围。
    通过 target_prompts 配置兼容 dfc / kfc 等多种 chatter。
    """

    plugin_name = "prompt_injector"
    plugin_description = "动态提示词注入插件，支持按群聊 / 私聊范围控制注入内容，兼容 dfc / kfc 等多种 chatter"
    plugin_version = "1.0.0"

    configs: list[type] = [PromptInjectorConfig]

    def get_components(self) -> list[type]:
        """返回当前插件包含的组件。"""
        config = self.config
        if isinstance(config, PromptInjectorConfig) and not config.plugin.enabled:
            return []
        return [PromptInjectorHandler]
