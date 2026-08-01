"""prompt_injector 插件配置。

配置文件默认路径：config/plugins/prompt_injector/config.toml

本插件通过 SystemReminder 机制向 chatter 注入自定义提示词。
利用 ``stream_id`` 维度实现 per-stream 隔离，不同聊天流互不干扰。
注入内容由 LLMContextManager 自动拾取并注入到最新 user 消息，
通过 DYNAMIC 模式的去重机制避免历史消息累积。
"""

from __future__ import annotations

from typing import ClassVar, Literal

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class InjectionEntry(SectionBase):
    """单条提示词注入规则。

    **作用域匹配（聊天流隔离）：**
    - include/exclude 均为空 → 全局生效（所有聊天）
    - include 非空 → 仅匹配列表中指定的聊天流
    - exclude 非空 → 从命中集合中排除指定聊天流

    **include/exclude 格式：**
    - ``"group:*"``   — 所有群聊
    - ``"group:123"`` — 群号为 123 的群聊
    - ``"user:*"``    — 所有私聊
    - ``"user:456"``  — QQ 号为 456 的私聊

    **注入策略（insert_type）：**
    - ``"dynamic"``（默认）— 注入到最新 user 消息开头，并自动从历史 user
      消息中剥离上一轮的旧注入文本，避免累积。适合"持续提醒模型注意行为"
      的场景（如人设锚定、格式规则）。
    - ``"fixed"`` — 注入到第一条 user 消息（对话历史最早位置），不会被
      自动剥离。适合需要固定出现在对话开头、且内容不变的背景信息。

    **消费模式（consume）：**
    - ``"forever"``（默认）— 每次 LLM 请求都会注入该提醒，持续生效。
      适合需要反复强调的长期规则。
    - ``"once"`` — 仅在单次 LLM 请求中消费一次，之后不再出现。
      必须配合 ``insert_type="dynamic"`` 使用。适合一次性指令，
      如"本轮回复请使用简体中文"。

    **常见组合建议：**
    - 持续行为约束（人设、格式）→ ``dynamic`` + ``forever``
    - 一次性指令（特定要求）  → ``dynamic`` + ``once``
    - 固定背景信息            → ``fixed``  + ``forever``
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

    # ── 注入策略 ──
    insert_type: Literal["dynamic", "fixed"] = Field(
        default="dynamic",
        description=(
            "注入位置类型。\n"
            "dynamic（默认）：注入到最新 user 消息开头，自动剥离历史旧注入，避免累积。\n"
            "fixed：注入到第一条 user 消息开头，不会被自动剥离。"
        ),
    )
    consume: Literal["forever", "once"] = Field(
        default="forever",
        description=(
            "消费模式。\n"
            "forever（默认）：每次 LLM 请求都注入，持续生效。\n"
            "once：仅单次请求消费一次，之后消失。必须配合 insert_type=dynamic 使用。"
        ),
    )


class PromptInjectorConfig(BaseConfig):
    """prompt_injector 插件配置模型。"""

    name: ClassVar[str] = "config"
    description: ClassVar[str] = "提示词注入插件配置"

    @config_section("plugin")
    class PluginSection(SectionBase):
        """插件基础配置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用插件",
        )
        debug_log: bool = Field(
            default=False,
            description=(
                "是否在日志中输出每轮实际注入的内容（INFO 级别），便于调试"
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
                content="这条规则排除指定群，对其余群聊生效。",
                include=["group:*"],
                exclude=["group:111111111"],
                enabled=False,
            ),
        ],
        description="提示词注入规则列表（TOML 数组表，格式为 [[inject]]）。",
    )
