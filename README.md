# prompt_injector

动态提示词注入插件，支持按群聊 / 私聊范围向 chatter 提示词追加自定义内容。

## 功能说明

- 订阅 `on_prompt_build` 事件，在每次构建提示词前执行注入
- 支持多条注入规则并行生效，命中的规则按配置顺序拼接后追加
- 通过 `target_prompts` 配置兼容所有 chatter，与 `booku_memory`、`notice_injector` 等其他注入器互不干扰

## 注入机制

注入位置由 chatter 的架构决定，与本插件无关：

| 目标模板 | 触发的提示词 | 注入位置 |
|---|---|---|
| `default_chatter_user_prompt`（dfc） | **用户提示词** | `{extra}` 占位符内（出现在用户消息里） |
| `kfc_system_prompt`（kfc） | **系统提示词** | 追加到系统提示词末尾 |

- dfc 的用户提示词模板内置了 `{extra}` 占位符，专门供外部注入使用
- kfc 的系统提示词模板没有 `{extra}` 占位符，只能追加到末尾

## 配置方法

配置文件路径：`config/plugins/prompt_injector/config.toml`

```toml
[plugin]
enabled = true
debug_log = false   # 开启后以 INFO 级别输出每轮实际注入内容，便于调试
target_prompts = ["default_chatter_user_prompt", "kfc_system_prompt"]  # 默认同时支持 dfc 和 kfc

[[inject]]
content = "你需要保持简洁，每句不超过20字。"
group_targets = []      # 非空时仅对列表中的群聊生效
user_targets = []       # 非空时仅对列表中的私聊生效
enabled = true

# 第二条规则：仅对指定群聊生效
[[inject]]
content = "当前对话为游戏频道，请优先讨论游戏相关内容。"
group_targets = ["123456789"]
user_targets = []
enabled = true
```

### 范围匹配语义

| `group_targets` | `user_targets` | 生效范围 |
|---|---|---|
| 空 | 空 | 所有聊天流 |
| 非空 | 空 | 仅列出的群聊 |
| 空 | 非空 | 仅列出的私聊 |
| 非空 | 非空 | 列出的群聊 + 列出的私聊 |

## 调试验证

开启 `debug_log = true` 后，发起一次对话即可在日志中看到实际注入内容：

```
[prompt_injector] 汇总注入内容 (default_chatter_user_prompt, stream_id=abcd1234...): '你需要保持简洁，每句不超过20字。'
```

也可通过 WebUI Inspector（`http://127.0.0.1:8000/_inspector/`）查看构建后的完整提示词。
