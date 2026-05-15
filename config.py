"""prompt_injector 插件配置。

配置文件默认路径：config/plugins/prompt_injector/config.toml
"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class InjectionEntry(SectionBase):
    """单条提示词注入规则。

    **作用域匹配：**
    - include/exclude 均为空 → 全局生效（所有聊天）
    - include 非空 → 仅匹配列表中指定的聊天流
    - exclude 非空 → 从命中集合中排除指定聊天流

    **include/exclude 格式：**
    - ``"group:*"``   — 所有群聊
    - ``"group:123"`` — 群号为 123 的群聊
    - ``"user:*"``    — 所有私聊
    - ``"user:456"``  — QQ 号为 456 的私聊

    **per-rule 模板控制：**
    - target_prompts 非空 → 覆盖全局 plugin.target_prompts，仅注入到指定模板
    - target_prompts 为空 → 沿用全局配置
    """

    content: str = Field(default="", description="要注入的提示词内容")
    enabled: bool = Field(default=True, description="是否启用此规则")

    # ── 作用域：聊天流匹配 ──
    include: list[str] = Field(
        default_factory=list,
        description=(
            "命中范围。为空时全局生效。\n"
            '格式："group:*" "group:群号" "user:*" "user:QQ号"'
        ),
    )
    exclude: list[str] = Field(
        default_factory=list,
        description=(
            "从命中范围中排除。格式同 include。\n"
            '示例：exclude = ["group:123456"] 表示排除该群。'
        ),
    )

    # ── 作用域：模板控制 ──
    target_prompts: list[str] = Field(
        default_factory=list,
        description=(
            "此规则注入的模板名称列表，覆盖全局 plugin.target_prompts。\n"
            "为空时沿用全局配置。\n"
            "可选值：default_chatter_user_prompt / kfc_system_prompt / kfc_user_prompt"
        ),
    )


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
                "kfc_system_prompt：kfc 系统提示词末尾\n"
                "kfc_user_prompt：kfc 用户消息末尾（新消息旁边）\n"
                '示例：target_prompts = ["default_chatter_user_prompt", "kfc_user_prompt"]'
            ),
        )

    plugin: PluginSection = Field(default_factory=PluginSection)

    inject: list[InjectionEntry] = Field(
        default_factory=lambda: [
            InjectionEntry(
                content="在所有对话中，你的语气应该亲切自然。",
                enabled=False,
            ),
            InjectionEntry(
                content="这是技术群，优先帮用户解决技术问题。",
                include=["group:123456789"],
                enabled=False,
            ),
            InjectionEntry(
                content="和这位朋友说话可以随意一点。",
                include=["user:987654321"],
                enabled=False,
            ),
            InjectionEntry(
                content="这条规则仅注入到 KFC 用户提示词，对 DFC 无效。",
                include=["user:*"],
                target_prompts=["kfc_user_prompt"],
                enabled=False,
            ),
            InjectionEntry(
                content="这条规则注入所有群聊，但排除指定群。",
                include=["group:*"],
                exclude=["group:111111111"],
                enabled=False,
            ),
        ],
        description="提示词注入规则列表（TOML 数组表，格式为 [[inject]]）。",
    )
