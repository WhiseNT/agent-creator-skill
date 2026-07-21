# Agent Context Engineering 设计文档

> Context Engineering 是对模型工作集的完整生命周期管理：发现、信任判定、选择、组织、预算、压缩、持久化、恢复和评估。Prompt Engineering 只负责其中最终呈现的一部分。

## 目录

1. [目标与边界](#目标与边界)
2. [Context 生命周期](#context-生命周期)
3. [Context 数据模型](#context-数据模型)
4. [来源与信任](#来源与信任)
5. [Context Compiler](#context-compiler)
6. [选择与排序](#选择与排序)
7. [Token Budget](#token-budget)
8. [对话上下文](#对话上下文)
9. [代码库上下文](#代码库上下文)
10. [RAG 与检索上下文](#rag-与检索上下文)
11. [工具结果与 Artifact](#工具结果与-artifact)
12. [Memory](#memory)
13. [Compaction](#compaction)
14. [缓存](#缓存)
15. [多 Agent 上下文](#多-agent-上下文)
16. [安全与隐私](#安全与隐私)
17. [可观测性与评估](#可观测性与评估)
18. [反模式](#反模式)
19. [实现清单](#实现清单)

## 目标与边界

好的上下文不是越多越好，而是：

```text
Relevant
Authoritative
Fresh
Non-redundant
Within budget
Recoverable
Traceable
```

Context Engineering 回答：

- 模型现在需要知道什么？
- 哪些来源可信？
- 哪些信息已经过期？
- 哪些内容应进入 prompt，哪些应留在 artifact？
- 长会话如何压缩？
- 关键状态如何避免被摘要丢失？
- 子 Agent 应得到多少父上下文？

### 与 Prompt Engineering 的区别

```text
Context Engineering: 决定选什么、丢什么、何时更新
Prompt Engineering: 决定如何表达选中的内容
```

### 与 Memory 的区别

Memory 是 Context 的一个来源，不是 Context 的全部。

## Context 生命周期

```text
Discover
  -> Classify
  -> Authorize
  -> Normalize
  -> Score
  -> Deduplicate
  -> Budget
  -> Compile
  -> Deliver
  -> Observe usage
  -> Persist/Compact
  -> Invalidate
```

### Discover

发现：

- system/product policy；
- organization/user settings；
- workspace rules；
- skills；
- session transcript；
- attachments；
- files；
- search results；
- tool outputs；
- memory；
- runtime facts；
- pending task state。

### Invalidate

上下文缓存必须定义失效条件：

- 文件 hash 变化；
- branch/commit 变化；
- toolset 变化；
- model/context window 变化；
- 权限变化；
- workspace trust 变化；
- session branch 变化；
- resource TTL 到期。

## Context 数据模型

```typescript
interface ContextResource {
  id: string;
  kind:
    | "policy"
    | "instruction"
    | "conversation"
    | "code"
    | "document"
    | "tool_result"
    | "memory"
    | "runtime_fact"
    | "artifact"
    | "summary";
  content: ContentPart[];
  source: ResourceSource;
  scope: ResourceScope;
  trust: TrustLevel;
  authority: number;
  relevance?: number;
  freshness?: number;
  estimatedTokens: number;
  version: string;
  dependencies: ResourceDependency[];
  retention: RetentionPolicy;
  sensitivity: Sensitivity;
}
```

### Scope

```text
global
organization
user
workspace
directory
session
branch
run
turn
subagent
```

### Retention

```text
always
until_session_end
until_task_end
until_file_changes
ttl
artifact_only
never_persist
```

### Trust 与 Authority 分开

- Trust：来源是否可信；
- Authority：它是否有权给模型下指令。

一个可信日志文件通常仍没有指令 authority。

## 来源与信任

### 来源矩阵

| 来源 | 默认 trust | 默认 authority | 说明 |
|---|---:|---:|---|
| Product policy | high | highest | 产品不可被 workspace 覆盖 |
| Organization policy | high | high | 企业治理 |
| User global config | medium/high | medium | 用户明确配置 |
| Trusted workspace rules | medium | scoped | 只对 workspace 生效 |
| Skill | medium | workflow | 由安装来源决定 |
| Session messages | mixed | role-based | user 有任务 authority |
| Tool result | low/mixed | data | 不能自行扩大权限 |
| Web/RAG content | low | none | 视为不可信数据 |
| Memory | mixed | data | 可能陈旧或错误 |

### Project Trust

在项目被信任前，只能发现而不能执行：

- hooks；
- plugin code；
- MCP server command；
- LSP command；
- `.envrc`；
- project-local executable configuration。

Grok Build 和 Pi 都说明项目配置加载需要独立 trust gate。

## Context Compiler

```typescript
interface ContextCompiler {
  plan(input: ContextCompileInput): Promise<ContextPlan>;
  render(plan: ContextPlan, target: ModelCapabilities): Promise<ModelContext>;
}
```

### ContextPlan

```typescript
interface ContextPlan {
  required: ContextResource[];
  selected: ContextResource[];
  summarized: SummaryPlan[];
  offloaded: ArtifactRef[];
  dropped: DroppedResource[];
  tokenBudget: TokenBudgetAllocation;
  diagnostics: ContextDiagnostic[];
}
```

先生成 plan，再 render，便于：

- 调试；
- 预览；
- 评估；
- 为不同 provider 转换格式；
- 在真正调用前发现超预算。

## 选择与排序

### 多因素评分

```text
score
  = relevance
  × authority weight
  × freshness weight
  × task-stage weight
  × source quality
  - redundancy penalty
  - token cost penalty
  - sensitivity penalty
```

不要只按向量相似度排序。

### Required 与 Optional

Required：

- system policy；
- 当前用户任务；
- 完成任务所必需的工具协议；
- 当前待处理 tool call/result；
- 关键业务状态。

Optional：

- 辅助代码；
- 历史解释；
- 相关 memory；
- 示例；
- 低分检索结果。

超预算时先处理 Optional。

### 去重

处理：

- 同一文件多个重叠片段；
- summary 与原文重复；
- tool output 重复打印；
- workspace rules 被多个路径发现；
- 相同错误日志重复出现。

保留 canonical source 和 provenance。

## Token Budget

### 预算不是 Context Window 全额

```text
context window
  - expected output
  - reasoning allowance
  - tool call/result reserve
  - safety margin
  = usable input budget
```

### 分配示例

```text
system/policy       fixed reserve
current task        fixed reserve
recent conversation 30%
project/code         30%
retrieval/memory     20%
tool results         15%
slack                 5%
```

比例应按产品和阶段调整。

### Budget Policy

```typescript
interface ContextBudgetPolicy {
  reserveOutputTokens: number;
  reserveToolTokens: number;
  safetyMarginTokens: number;
  sectionLimits: Record<ContextKind, number>;
  overflowOrder: ContextKind[];
}
```

### 降级策略

```text
remove duplicate
  -> trim low-value metadata
  -> truncate bounded outputs
  -> offload large artifacts
  -> summarize old content
  -> retrieve narrower slices
  -> compact conversation
  -> fail with diagnostic
```

不要随机截断字符串。

## 对话上下文

### Transcript 与 Model Context

Transcript 保存完整语义历史；Model Context 是某次请求的投影。

```text
Transcript
  -> select active branch
  -> apply compaction entries
  -> remove UI-only events
  -> preserve tool call/result pairs
  -> convert custom entries
  -> provider message conversion
```

### Turn 原子性

不能把以下结构拆开：

```text
assistant tool call
  + corresponding tool result
```

如果必须裁剪，整组摘要或 offload。

### Recent Window

保留最近内容时，应按完整 semantic entries 或 turn，而不是按字符尾部。

### Steering 与 Follow-up

Pi 区分：

- steering：当前 loop 中尽快插入；
- follow-up：当前任务稳定后再处理。

Context 层需要明确这些消息何时进入模型视图，避免用户新指令迟到或重复。

## 代码库上下文

### 不要全仓库注入

使用分层发现：

```text
repo map
  -> symbol/file search
  -> relevant file slices
  -> dependency neighbors
  -> tests and config
  -> targeted full file reads
```

### Code Resource

```typescript
interface CodeResourceMetadata {
  path: string;
  language?: string;
  commit?: string;
  contentHash: string;
  lineRange?: [number, number];
  symbol?: string;
  generated?: boolean;
  binary?: boolean;
}
```

### 文件读取策略

- 已知文件：直接读取；
- 未知位置：先 Glob/Grep；
- 大文件：按 symbol/range；
- 修改前：读取完整相关结构；
- 依赖关系不清：读取 imports、调用者、tests；
- generated/vendor：默认低优先级。

### Repository Map

Repo map 应是导航索引，而不是替代源码。包含：

- 目录；
- 关键 symbols；
- 模块依赖；
- 测试位置；
- 配置入口。

过期 map 必须失效。

## RAG 与检索上下文

### Retrieval Pipeline

```text
query understanding
  -> query decomposition
  -> candidate retrieval
  -> metadata filter
  -> rerank
  -> deduplicate
  -> trust annotation
  -> context budget
  -> citation mapping
```

### Query 来源

检索 query 可以来自：

- 用户问题；
- 当前计划；
- 模型提出的信息缺口；
- 失败工具结果；
- 代码 symbol；
- memory recall。

### 引用

每个片段保留：

```text
source URI
resource version
timestamp
chunk range
retrieval score
rerank score
```

模型回答中的 citation 应能映射回原资源。

### 注入防护

检索内容不能：

- 改变 system policy；
- 自动注册工具；
- 自动批准动作；
- 提供未验证凭据；
- 要求把数据发送到外部地址。

## 工具结果与 Artifact

### Tool Output 不应全部回传

工具结果分为：

```text
model-facing summary
structured result
user-facing artifact
raw diagnostic
```

示例：测试输出 50,000 行时：

- 模型：失败测试名、首个错误、摘要；
- 用户：完整日志 artifact；
- trace：命令、退出码、耗时；
- session：artifact reference。

### ArtifactRef

```typescript
interface ArtifactRef {
  id: string;
  uri: string;
  mediaType: string;
  size: number;
  hash: string;
  summary?: string;
  sensitivity: Sensitivity;
  expiresAt?: string;
}
```

### 输出截断

截断时显式标记：

```text
truncated: true
original_size
retained_range
artifact_ref
```

不要让模型误以为看到了完整输出。

## Memory

### Memory 类型

```text
Semantic memory: 稳定事实和偏好
Episodic memory: 过去任务与结果
Procedural memory: 工作流和命令
Working memory: 当前任务状态
```

### Memory 写入

不要把所有对话自动写入长期记忆。写入条件：

- 未来复用价值；
- 相对稳定；
- 来源可验证；
- 不违反隐私；
- 用户允许。

### Memory Record

```typescript
interface MemoryRecord {
  id: string;
  type: MemoryType;
  content: string;
  sourceRefs: ResourceRef[];
  confidence: number;
  createdAt: string;
  lastVerifiedAt?: string;
  expiresAt?: string;
  scope: ResourceScope;
  sensitivity: Sensitivity;
}
```

### Memory Retrieval

同时考虑：

- semantic relevance；
- scope；
- freshness；
- confidence；
- task stage；
- contradiction。

### Memory Flush

OpenClaw 在 compaction 前执行 memory flush 是有价值的模式，但应：

- 只保存允许持久化的内容；
- 结构化记录来源；
- 避免把模型猜测写成事实；
- 允许用户审查和删除。

## Compaction

### 触发条件

- 预计 token 超过阈值；
- provider 返回 context overflow；
- 模型切换到更小窗口；
- 会话阶段完成；
- 后台预压缩已准备好；
- 工具结果大量累积。

### Compaction Plan

```typescript
interface CompactionPlan {
  keepEntries: EntryId[];
  summarizeRanges: EntryRange[];
  offloadResources: ResourceId[];
  structuredState: StructuredTaskState;
  targetTokens: number;
}
```

### 必须保留的结构化状态

- 当前目标；
- 已完成工作；
- 未完成步骤；
- 修改文件；
- 测试结果；
- 失败和原因；
- 用户约束；
- pending approvals；
- 重要 artifact；
- 模型/toolset/config 变化。

不要只依赖自然语言 summary。

### 两阶段压缩

结合 Grok Build 和 Pi 的思路：

```text
background candidate summary
  -> verify source hash
  -> synchronous update for new tail
  -> write durable compaction entry
```

### 摘要验证

可检查：

- tool call/result 是否成对；
- 文件名和测试状态是否保留；
- 数值、ID 和用户约束是否保留；
- 未完成任务没有被写成已完成；
- 摘要 coverage 与 source range 匹配。

## 缓存

### 缓存层

```text
resource discovery cache
file content cache
repository map cache
retrieval cache
embedding cache
compiled context cache
provider prompt cache
compaction candidate cache
```

### Cache Key

至少包含：

```text
resource version/hash
workspace/branch
trust state
model capabilities
active toolset
compiler version
policy version
```

### 不缓存

- 未脱敏密钥；
- 短期 bearer token；
- 高度敏感工具结果；
- 不可复用的 approval；
- 来源版本未知的内容。

## 多 Agent 上下文

### 最小必要委派

子 Agent 只获取：

- objective；
- 相关资源；
- 允许工具；
- 预算；
- 结果 schema；
- 必要父状态摘要。

不要默认复制主 Agent 的全部 transcript。

### Context Isolation

```text
parent transcript
  != child transcript
```

父 Agent 保存 assignment 和 child result reference；child 保存独立 trace。

### 结果合并

子 Agent 返回：

```text
findings
confidence
source refs
artifacts
changes made
verification
open risks
```

父 Agent 不应只收到一段无来源自然语言。

## 安全与隐私

### Sensitivity

```text
public
internal
confidential
secret
regulated
```

不同等级决定：

- 是否可发送给外部 provider；
- 是否可进入日志；
- 是否可进入长期 memory；
- 是否可被 subagent 继承；
- 保留时间。

### Data Egress

Context Compiler 在调用模型前执行 egress policy：

```text
provider jurisdiction
model deployment
resource sensitivity
tenant policy
redaction rules
```

### Redaction

保留 redaction map 只在可信边界内，用占位符替换：

```text
<SECRET_1>
<EMAIL_2>
<CUSTOMER_ID_3>
```

模型结果回写时谨慎反替换，避免把占位符注入错误位置。

## 可观测性与评估

### Context Trace

记录：

```text
candidate count
selected resources
dropped resources
summary operations
token allocation
trust/authority
cache hits
resource versions
retrieval scores
compiler diagnostics
```

### 质量指标

- task success；
- relevant context recall；
- irrelevant context rate；
- stale context rate；
- duplicate token rate；
- compaction factual retention；
- context build latency；
- cache hit rate；
- 用户重复提供信息次数；
- 工具调用因缺上下文失败次数。

### Context Ablation

依次移除某类上下文，观察成功率变化：

```text
without project rules
without memory
without retrieval
without recent raw turns
summary only
```

用于判断某资源是否真正有价值。

## 反模式

1. 把整个仓库塞进 prompt。
2. Context 等同于最近 N 条聊天消息。
3. 只按向量相似度选择内容。
4. 不记录来源、版本和信任等级。
5. tool output 无限制进入上下文。
6. 把 memory 当确定事实。
7. Compaction 只生成一段摘要并删除原历史。
8. 切断 tool call/result 对。
9. 子 Agent 复制全部父上下文。
10. Cache key 不包含文件或 policy 版本。
11. 敏感数据在不同 provider 间无差别发送。
12. 超预算时从字符串尾部机械截断。
13. Repo map 过期仍继续使用。
14. 把检索内容当成高权威指令。

## 实现清单

- [ ] 定义 ContextResource、scope、trust、authority、sensitivity
- [ ] 建立 ContextCompiler 与 ContextPlan
- [ ] 明确 required/optional
- [ ] 实现多因素选择和去重
- [ ] 建立 section token budget
- [ ] Transcript 与 Model Context 分离
- [ ] 工具结果支持摘要、截断和 artifact offload
- [ ] 建立代码资源 metadata 和 repo map 失效机制
- [ ] RAG 保留 citation/provenance
- [ ] Memory 记录来源、置信度和过期时间
- [ ] Compaction 保存结构化状态和 durable entry
- [ ] Cache key 包含资源、工具、模型和 policy 版本
- [ ] 子 Agent 使用最小上下文和独立 trace
- [ ] 执行 sensitivity 与 data egress policy
- [ ] 建立 context trace、指标和 ablation 测试

## 项目启发来源

- Pi：Transcript 与 LLM message 分离、session tree、resource loader、compaction entry、steering/follow-up。
- Grok Build：ChatStateActor、token 估算、工具结果修剪、图片压缩、后台/同步两阶段 compaction。
- OpenCode：message/part、session、snapshot/patch/revert、durable event/projector。
- Claude Code：CLAUDE.md、auto memory、skills、subagent 上下文边界。
- OpenClaw：Markdown memory、混合检索、compaction 前 memory flush、多渠道 session key。
