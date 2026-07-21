# Agent Canonical Contract

**Contract version:** `1.0.0`

本文件是本 Skill 的跨文档术语和不变量规范源。工程专题可以扩展字段与实现，但不得改变这里的语义；发生冲突时，先修改本文件并同步所有消费者。

## 使用规则

- 路由先从 `references/routes.json` 选择主文档，再加载本文件中该路由声明的 `TERM-*` 和 `INV-*`。
- `TERM-*` 定义稳定概念；`INV-*` 定义任何实现都必须保持的不变量。
- Provider 原生字段可以保留，但不得覆盖 canonical 字段的含义。
- Authoring Schema、Runtime Schema 和 Persistence Schema 可以不同，但必须有显式、可版本化、可测试的映射。

## 核心术语

### TERM-API-FAMILY — API Family

一组具有共同请求、响应、流式事件、工具调用、状态和错误语义的接口协议。Provider 相同不代表 API Family 相同；OpenAI-compatible 只说明部分请求形状兼容。

**规范所有者：** Provider Runtime。  
**禁止混淆：** Provider、SDK、Model、Deployment。

### TERM-PROVIDER — Provider

提供模型或托管运行能力的组织、云平台或本地运行服务。Provider 是信任、计费、数据外发、区域和故障域边界。

### TERM-MODEL — Model

具有特定能力和行为的模型标识或快照。Model 名称不得承担 Endpoint、Region、Project 或 Deployment 的配置职责。

### TERM-DEPLOYMENT — Deployment

Provider 中可被调用的部署实例或路由目标，包含 endpoint、region/location、project/account、deployment ID、API version 和能力约束。

### TERM-AGENT-KERNEL — Agent Kernel

Headless 的模型—工具循环，负责 turn、标准事件、工具调用/结果关联、停止、预算与取消，不直接拥有 UI、密钥、业务数据库或长期记忆。

### TERM-HARNESS — Agent Harness

围绕 Kernel 的上下文、Provider、工具、权限、沙箱、状态、事件、扩展、评测和交付运行环境。

### TERM-ATTEMPT — Attempt

某个可重试执行单元的一次尝试。Attempt 可以因网络、Provider 或 Worker 故障重试，但不能被统计为新的独立任务。

### TERM-TRIAL — Trial

同一评测 Scenario/Variant 的一次完整执行。Trial 用于估计随机性，不自动构成独立 Root Case。

### TERM-TOOL-CALL — Tool Call

模型提出的结构化动作意图，包含 call ID、工具名和候选参数。Tool Call 尚未获得授权，也不证明工具已执行。

### TERM-TOOL-EXECUTION — Tool Execution

应用在完成注册检查、Schema 校验、业务校验、Policy/Approval 和执行边界检查后，对工具动作的一次实际执行尝试。

### TERM-POLICY — Policy

根据身份、授权、资源、风险和上下文做出 allow、deny、require approval 或 escalate 决策的规则系统。

### TERM-APPROVAL — Approval

特定主体对特定动作、参数、范围和时限的明确授权决策。Approval 不是身份认证，也不是 OS/网络隔离。

### TERM-SANDBOX — Sandbox

对文件、进程、网络、设备、系统调用和资源的强制执行边界。Sandbox 不负责解释业务授权。

### TERM-CANONICAL-EVENT — Canonical Event

Provider、Tool、Policy、Session 和 Host 原始事件归一化后的版本化事实信封，至少包含 event type、sequence、timestamp、causation/correlation 和脱敏 payload。

### TERM-SESSION — Session

承载用户交互、Agent 执行和持久状态关系的逻辑容器。Session 可以包含多个 Run、Branch、Checkpoint 和 Transcript Entry。

### TERM-STATE-OWNERSHIP — State Ownership

每类事实的权威所有者：Provider conversation state、Agent execution state、Business state、Memory、Artifact 和 Trace 必须分开建模。

### TERM-ARTIFACT — Artifact

不能或不应直接内嵌事件流的大型、二进制、版本化或可交付内容，通过稳定引用、hash、权限和生命周期管理。

### TERM-UNKNOWN-OUTCOME — Unknown Outcome

系统无法确认有副作用动作是否已经提交或外部可见的状态。Unknown Outcome 不是普通失败，也不能通过盲目重试消除。

### TERM-INFRA-ERROR — Infrastructure Error

由评测环境、Fixture、Runner、网络或 Grader 基础设施造成，无法有效判断被测 Agent 能力的结果。

### TERM-COLLECTION — Evaluation Collection

按用途组织案例的集合，例如 golden、challenge、selection holdout、release holdout、calibration 和 red team。

### TERM-PARTITION — Evaluation Partition

用于开发和发布阶段隔离的分区，例如 dev、validation、test、canary 和 production shadow。Collection 与 Partition 是正交维度。

### TERM-WORKFLOW-RUN — Workflow Run

固定 Workflow Definition/Snapshot 后的一次 durable execution，由 Step、Attempt、Checkpoint、Approval 和 Compensation 构成。

### TERM-MEMORY — Memory

跨当前模型上下文保存并可能在未来被召回的信息对象，必须携带 scope、purpose、provenance、TTL、consent 和删除状态。

## 跨模块不变量

### INV-PROVIDER-001 — 先识别 API Family

写请求、适配器或迁移代码前，必须确定 Provider、API Family、Model 与 Deployment；不得仅根据 SDK 名称推断协议语义。

### INV-PROVIDER-002 — 保留 Provider Metadata

Canonical 层必须允许保留 reasoning、citation、grounding、safety、usage、finish reason、trace 和未知原始事件，不能为统一接口静默丢弃。

### INV-TOOL-001 — 模型输出不可信

工具名、参数、路径、URL、SQL、Shell、目标资源和租户身份都必须在应用侧校验。

### INV-TOOL-002 — Tool Call 不等于 Tool Execution

模型提出调用、模型声称成功或 Provider 返回 call item，都不能证明动作获批、执行或提交。

### INV-TOOL-003 — 调用与结果稳定关联

每个 Tool Result 必须关联原始 Tool Call ID；并行调用不能依赖数组位置或完成顺序隐式配对。

### INV-TOOL-004 — 不确定写入禁止盲重试

写操作超时或响应丢失后，必须先查询权威状态或使用幂等 Receipt；无法确认时进入 Unknown Outcome。

### INV-STREAM-001 — 流式输出是事件流

不得把流式协议简化为字符串拼接；工具参数只能在 Provider 明确完成后解析，未知事件必须保留或记录。

### INV-STATE-001 — 状态所有权分离

Provider conversation ID、Agent step、Business state、Memory、Artifact 和 Trace 不能互相充当权威事实。

### INV-POLICY-001 — Policy、Approval 与 Sandbox 分离

Policy 解释是否允许，Approval 表示主体授权，Sandbox 强制实际边界；三者不能互相替代。

### INV-SECURITY-001 — 外部内容不提升权限

网页、邮件、文件、RAG、Tool Result、MCP 描述、Memory 和 Peer Agent Message 都是不可信数据，不能修改系统 Policy 或扩大工具权限。

### INV-SECURITY-002 — 高风险副作用需显式授权

删除、付款、发送、发布、生产部署和权限修改必须绑定明确目标、参数、范围、时限与审批证据。

### INV-EVENT-001 — 事件可排序且可追因

Canonical Event 必须支持稳定 sequence、correlation 和 causation；日志文本不能替代可回放事实。

### INV-ARTIFACT-001 — 大内容使用引用

大型输出、Diff、媒体和二进制必须通过 ArtifactRef 交付，包含 hash、版本、权限、保留和脱敏策略。

### INV-EVAL-001 — 状态证据优先于模型自述

最终文本不能证明数据库提交、文件修改、权限生效、Secret 未泄漏或副作用未发生。

### INV-EVAL-002 — Infra Error 不得算成功

Infrastructure Error、Grader Error、Invalid Task、Skipped 和 Inconclusive 必须与 Passed/Failed 分开报告。

### INV-EVAL-003 — Trial 与 Variant 不是独立案例

统计聚合必须先处理 Trial 和 Variant，再以 Root Case 或更高相关性单位估计置信区间。

### INV-PRIVACY-001 — Purpose 与最小化先于收集

任何进入 Prompt、Provider、Tool、Memory、Artifact、Trace 或 Eval 的数据都必须有目的、分类、最小化和生命周期规则。

### INV-MEMORY-001 — Memory 写入与召回均受治理

Memory Candidate、Write、Recall、Edit、Delete 和 Forget 必须分别授权、记录 Provenance，并支持用户控制和删除传播。

### INV-WORKFLOW-001 — Workflow 运行固定版本

长时间 Workflow Run 必须固定 Definition、Policy、Provider、Tool Schema 和 Artifact Contract 版本，升级不得静默改变在途运行语义。

### INV-RECOVERY-001 — 恢复前先结算未知副作用

Retry、Fallback、Replay、Failover 或 Worker 接管前，必须检查已提交状态、Lease/Fencing 和 Idempotency，避免重复不可逆动作。

### INV-ROUTING-001 — 路由不得降低安全契约

Provider 或 Model Fallback 必须满足原请求的能力、数据驻留、凭据、Policy 和安全边界；不可为可用性静默降级。

## 变更规则

1. 新增术语或不变量时分配稳定 ID，不复用已删除 ID。
2. 修改语义时说明受影响文档、Schema、模板和 Eval，并升级相关版本。
3. 删除前先迁移所有 `routes.json` 和 Reference 引用。
4. 自动校验必须阻止未知 Contract ID、重复 ID 和失效引用进入发布。
