# prompt_injector

动态提示词注入插件，支持按群聊 / 私聊范围向 chatter 提示词追加自定义内容。

## 功能说明

- 订阅 `on_prompt_build` 事件，在每次构建提示词前执行注入
- 支持多条注入规则并行生效，命中的规则按配置顺序拼接后追加
- 支持通过 `include` 和 `exclude` 精确控制注入范围
- 支持全局和单条规则级别的 `target_prompts` 模板控制，与 `booku_memory`、`notice_injector` 等其他注入器互不干扰

## 注入机制

注入位置由 chatter 的架构决定，与本插件无关：

| 目标模板 | 触发的提示词 | 注入位置 |
|---|---|---|
| `default_chatter_user_prompt`（dfc） | **用户提示词** | `{extra}` 占位符内（出现在用户消息里） |
| `kfc_system_prompt`（kfc） | **系统提示词** | 追加到系统提示词末尾 |
| `kfc_user_prompt`（kfc） | **用户提示词** | 附加到用户消息末尾（新消息旁边） |

- dfc 的用户提示词模板内置了 `{extra}` 占位符，专门供外部注入使用
- kfc 的系统提示词模板没有 `{extra}` 占位符，默认情况会将 `extra` 提取为独立 payload 或追加到末尾

## 配置方法

配置文件路径：`config/plugins/prompt_injector/config.toml`

```toml
[plugin]
enabled = true
debug_log = false   # 开启后以 INFO 级别输出每轮实际注入内容，便于调试
target_prompts = ["default_chatter_user_prompt"]  # 全局默认注入的目标模板

[[inject]]
content = "在所有对话中，你的语气应该亲切自然。"
include = []  # 为空时全局生效
exclude = []
enabled = true

# 第二条规则：仅对指定群聊生效
[[inject]]
content = "这是技术群，优先帮用户解决技术问题。"
include = ["group:123456789"]
exclude = []
enabled = true

# 第三条规则：独立的目标模板和排除范围
[[inject]]
content = "这条规则仅注入到 KFC 用户提示词，对 DFC 无效。并在指定私聊中排除生效。"
include = ["user:*"]
exclude = ["user:111111"]
target_prompts = ["kfc_user_prompt"]
enabled = true
```

### 范围匹配语义

`include` 和 `exclude` 使用格式化的作用域字符串：
- `"group:*"`：所有群聊
- `"group:123"`：群号为 123 的群聊
- `"user:*"`：所有私聊
- `"user:456"`：QQ 号为 456 的私聊

**匹配机制：**
- `include` / `exclude` 均为空：全局生效
- `include` 非空：仅命中列表中指定的聊天流
- `exclude` 非空：从命中集合中排除指定聊天流

### 模板控制（`target_prompts`）

- 全局控制：`[plugin]` 下的 `target_prompts` 决定默认向哪些模板注入提示词。
- 单条控制：`[[inject]]` 规则下的 `target_prompts` 如果非空，将覆盖全局配置，仅向指定模板注入此规则；如果为空，则沿用全局配置。

## 调试验证

开启 `debug_log = true` 后，发起一次对话即可在日志中看到实际注入内容：

```
[prompt_injector] 汇总注入内容 (default_chatter_user_prompt, stream_id=abcd1234...): '你需要保持简洁，每句不超过20字。'
```

也可通过 WebUI Inspector（`http://127.0.0.1:8000/_inspector/`）查看构建后的完整提示词。
