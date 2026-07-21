# Agent Creator 核心工程导航

本目录只保留直接服务于完善 Agent 实现的工程资料。Agent 的规范路由源是 [`references/routes.json`](../routes.json)，跨文档术语和不变量以 [Canonical Contract](../canonical-contract.md) 为准。默认只加载一个主文档和最多两个辅助文档。

## 核心文档

| 文档 | 解决的问题 | 何时读取 |
|---|---|---|
| [Prompt Engineering](prompt-engineering.md) | 编译 system prompt、tool description、模式提示和输出契约 | 设计提示、工具描述、计划/只读模式或修复指令冲突时 |
| [Context Engineering](context-engineering.md) | 发现、筛选、排序、压缩和持久化模型上下文 | 处理长会话、RAG、附件、memory 和 token 预算时 |
| [Harness Engineering](harness-engineering.md) | 装配并监督 Agent Kernel 的运行环境 | 设计 runtime、session、event、plugin 或 host 边界时 |
| [Tool Engineering](tool-engineering.md) | 定义、注册、调度、校验、执行和恢复工具调用 | 设计 function/tool calling、MCP、幂等和工具结果时 |
| [State & Memory Engineering](state-memory-engineering.md) | 建模 session、transcript、checkpoint、event state 和基础 memory | 处理持久状态、恢复、分支和状态迁移时 |
| [Permission & Sandbox Engineering](permission-sandbox-engineering.md) | 把权限、审批、信任和沙箱变成可执行边界 | 处理 shell、文件、网络、secret 和 prompt injection 时 |
| [Event & Observability Engineering](event-observability-engineering.md) | 统一事件、流、trace、metrics、audit 和诊断 | 设计流式输出、日志、追踪和回放事实时 |
| [Provider Runtime Engineering](provider-runtime-engineering.md) | 隔离 Provider/Model/Deployment、能力、流式、重试和计费 | 设计 Provider adapter、迁移或多模型运行时适配时 |
| [Evaluation Engineering](evaluation-engineering.md) | 评测轨迹、状态、副作用、可靠性、安全和回归 | 建立测试、评测 runner、CI gate 或 fault injection 时 |

## 阅读边界

核心 Skill 适合：

- 单 Agent 或有限规模的多工具 Agent；
- Provider/API family 选型与迁移；
- 工具循环、流式输出和结构化输出；
- 基础 Session、Checkpoint、Memory 和恢复；
- 权限、审批、沙箱、可观测性和测试。

如果需求涉及多租户平台、生产运维、长期 Workflow、容量与成本、复杂 Memory 治理、隐私/数据治理、Provider 事故响应、Coding Agent 工作区隔离或高级合规，切换到同级 `agent-platform-engineering-skill`，不要在这里加载平台级文档。

## 基础边界

```text
Prompt      解释策略和任务
Context     选择模型工作集
Tool        暴露、校验和执行外部能力
State       持久化运行事实
Policy      决定动作是否允许
Sandbox     强制限制实际副作用
Event       传播、记录和诊断事实
Provider    隔离模型 API、能力、流和计费
Evaluation  验证结果、轨迹和副作用
Harness     装配并监督以上组件
```

这些边界不是必须的一类一个，但每个实现都应能回答：某条规则由谁解释、由谁强制、由谁记录、由谁评测。
