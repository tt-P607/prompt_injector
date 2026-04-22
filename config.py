"""prompt_injector 插件配置。

配置文件默认路径：config/plugins/prompt_injector/config.toml
"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class InjectionEntry(SectionBase):
    """单条提示词注入规则。

    targets 均为空时对所有聊天流全局生效；
    group_targets 非空则仅限列表中的群聊；
    user_targets 非空则仅限列表中的私聊；
    两者均非空则对其并集生效。
    """

    content: str = Field(default="")
    group_targets: list[str] = Field(default_factory=list)
    user_targets: list[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class PromptInjectorConfig(BaseConfig):
    """prompt_injector 插件配置模型。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "提示词注入插件配置"

    @config_section("plugin")
    class PluginSection(SectionBase):
        """插件基础配置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用插件",
        )
        debug_log: bool = Field(
            default=False,
            description="是否在日志中输出每轮实际注入的内容（INFO 级别），便于调试",
        )
        target_prompts: list[str] = Field(
            default_factory=lambda: ["default_chatter_user_prompt"],
            description=(
                "要注入的提示词模板名称，对应 on_prompt_build 事件的 name 字段。\n"
                "default_chatter_user_prompt：dfc 用户提示词 {extra} 占位符（默认）\n"
                "kfc_system_prompt：kfc 系统提示词末尾（手动添加）\n"
                '两者同时支持示例：target_prompts = ["default_chatter_user_prompt", "kfc_system_prompt"]'
            ),
        )

    plugin: PluginSection = Field(default_factory=PluginSection)

    inject: list[InjectionEntry] = Field(
        default_factory=lambda: [
            InjectionEntry(
                content="在所有对话中，你的语气应该亲切自然。",
                group_targets=[],
                user_targets=[],
                enabled=False,
            ),
            InjectionEntry(
                content="这是技术群，优先帮用户解决技术问题。",
                group_targets=["123456789"],
                user_targets=[],
                enabled=False,
            ),
            InjectionEntry(
                content="和这位朋友说话可以随意一点。",
                group_targets=[],
                user_targets=["987654321"],
                enabled=False,
            ),
        ],
        description="提示词注入规则列表（TOML 数组表，格式为 [[inject]]）。",
    )
