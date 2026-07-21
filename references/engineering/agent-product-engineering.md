# Agent Product Engineering 细粒度工程设计
> Agent Product Engineering 关注如何把 Agent Kernel 与 Harness 的能力边界转化为可靠、可理解、可恢复、可治理的产品体验。产品不是“把模型文本显示出来”，而是围绕用户任务、引导与信任、会话、流式事件、进度、审批、转向、取消、artifact/diff、memory、skills/plugins/MCP、多客户端、后台任务、通知、配额、成本、错误恢复、反馈评测、功能发布和隐私分析建立完整的交付系统。 > > 本文只使用当前目录已有的参考架构、Agent Harness、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Provider Routing、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Production Operations、Security Operations、Cost Governance 与 Provider Runtime Conformance 文档中已经记录的本地调研结论；不依赖 README，不新增网络搜索结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)；[Kernel、Harness 与产品边界](#kernelharness-与产品边界)；[用户任务模型与产品状态](#用户任务模型与产品状态)
• [用户角色、信任与引导](#用户角色信任与引导)；[核心产品数据模型](#核心产品数据模型)；[TypeScript 接口](#typescript-接口)；[能力发现与产品模式](#能力发现与产品模式)；[Task Intake 与任务规范化](#task-intake-与任务规范化)；[会话 UX 与 Transcript 投影](#会话-ux-与-transcript-投影)；[流式、进度与 Backpressure](#流式进度与-backpressure)；[审批、转向、取消与恢复控制](#审批转向取消与恢复控制)；[Tool、Artifact、Diff 与交付](#toolartifactdiff-与交付)；[Memory 控制](#memory-控制)；[Skills、Plugins 与 MCP 产品化](#skillsplugins-与-mcp-产品化)；[多客户端、渠道与身份路由](#多客户端渠道与身份路由)
• [后台任务、通知与结果回收](#后台任务通知与结果回收)；[配额、成本与用户透明度](#配额成本与用户透明度)；[错误恢复 UX](#错误恢复-ux)；[反馈、评测与质量闭环](#反馈评测与质量闭环)；[功能发布、实验与回滚](#功能发布实验与回滚)；[产品分析、隐私与数据治理](#产品分析隐私与数据治理)；[生命周期与状态机](#生命周期与状态机)；[端到端产品决策流程](#端到端产品决策流程)；[与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)；[可观测性、运营与 SLO](#可观测性运营与-slo)；[测试策略与 Evaluation](#测试策略与-evaluation)；[反模式与审查规则](#反模式与审查规则)
• [实施清单](#实施清单)；[五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Agent Product Runtime 必须能够：
- 明确区分 Agent Kernel 的模型—工具循环、Harness 的执行监督和产品层的任务/用户/交付语义。；让用户知道 Agent 当前目标、阶段、可见工具、预计等待、预算、风险和完成标准。；通过引导、项目 trust、模式、审批、diff、artifact 和错误文案建立可解释的信任，而不是依靠人格化文本。；将一次用户意图规范化为 `TaskSpec`、acceptance criteria、mode、scope、priority、delivery preference 和 privacy choice。；使用 `Session -> Branch -> Run -> Attempt -> Turn -> Message/Part` 结构呈现可恢复的对话，而不是只维护字符串数组。；将文本、推理摘要、工具调用、审批、工具进度、artifact、usage、错误、compaction、通知和终态作为结构化事件交付。；让用户可以在安全边界内 steering 当前 run、暂停、取消、恢复、重试、切换计划、查看 diff 和选择下一步。；把审批呈现为具体 action、material parameters、risk、sandbox、scope、expiry 和结果，不把按钮点击直接映射为执行。；将大输出、日志、diff、图片、测试报告和二进制转成带权限、hash、TTL 的 ArtifactRef。；提供清晰的 memory 查看、写入、关闭、修订、删除和 scope 控制，避免“自动记住一切”。；将 skills、plugins、MCP、hooks 和 providers 作为带 provenance、trust、capability、版本和失败回滚的产品能力。；在 CLI、TUI、IDE、RPC、HTTP、Batch 和 Channel 中保持事实一致，同时允许交付密度不同。
- 支持 foreground/background run、队列、lease、heartbeat、通知、断线恢复和结果回收。；让配额、成本、估算、预留、实际和对账对用户可理解且不可被模型伪造。；让错误恢复 UX 区分可重试、需用户决策、等待外部状态、unknown outcome、partial success 和 terminal failure。；通过反馈、轨迹评测、side-effect oracle、在线信号、canary 和回滚形成产品质量闭环。；将产品分析设计为最小化、脱敏、目的限定、租户隔离和可删除的事件系统。
### 非目标
本文不负责：
- 重新实现 Agent Kernel 的 provider loop、tool parser 或底层 sandbox。；仅通过 prompt 文字实现权限、审批、取消、配额、成本或隐私。；把所有内部事件都显示给用户，或默认显示 hidden reasoning、完整 prompt 和原始工具输出。；把 UI 的 spinner、按钮状态或 socket 关闭当作 durable execution truth。；把“Agent 自动完成”定义为没有人工控制、无限后台运行或默认自动提交/发布。；把所有产品模式压缩为一个聊天窗口和一个 `isRunning` 布尔值。；用单一满意度分数覆盖安全失败、未授权副作用、成本超限、事件丢失或恢复失败。；把 plugin/MCP/skill 的安装等同于它们已经获得执行、网络、secret 或跨租户权限。；让产品分析采集完整 prompt、secret、原始文件、hidden reasoning、完整 tool args 或未脱敏 artifact。；为了提升转化或 retention，隐式延长 session、memory、artifact、trace 或 provider remote object 的保存期限。
### 产品质量公式
```text
Agent Product Quality
= Task Success
× Trust Calibration
× Control Quality
× Feedback Clarity
× Recovery Quality
× Delivery Integrity
× Privacy Safety
× Cost Predictability
```
任一项接近零，产品即使能生成漂亮文本，也不应被视为可靠。
## Kernel、Harness 与产品边界
### Agent Kernel
Kernel 是 headless 最小闭环：
- 发送 provider-neutral messages、tool definitions 和 output contract。；接收 canonical model events。；提交完整 assistant item。；收集、校验并执行 tool calls。；回传 tool results，继续或终止 loop。；处理 stop reason、max turns、abort 和核心 lifecycle events。
Kernel 不知道：
- 用户是否在 CLI、IDE、Channel 或后台通知中。；何时展示 approval card、diff、预算和升级提示。；session 如何分支、如何删除、memory 是否开启。；provider、tool、artifact、queue、notification 的具体产品体验。
### Agent Harness
Harness 回答：
- 模型看见什么、工具能做什么、在哪个 workspace 执行。；哪些动作需要 policy、approval、sandbox、egress 和预算。；session、checkpoint、compaction、artifact、subagent、retry、fallback 和恢复如何工作。；事件如何 durable、ephemeral、replay、trace、audit 和交付。
Harness 对产品提供稳定能力：
```text
start / resume / inspect / cancel / steer / approve
subscribe events / read snapshot / resolve artifact
spawn background / report usage / request deletion
```
### Agent Product Layer
产品层负责：
- 用户任务模型、onboarding、trust education、模式选择和完成标准。；会话列表、消息/part 投影、进度、审批、diff、artifact 和通知。；用户控制语义：steering、cancel、pause、retry、branch、memory、settings。；结果交付、反馈、错误解释、帮助、升级、功能发布和分析。；将多端 Host 能力映射为一致的产品语义，不把 host 特性泄漏到 Kernel。
### 边界判断
```text
Kernel: 下一步模型—工具循环如何推进？
Harness: 允许看到什么、做什么、在哪里做、如何恢复？
Product: 用户现在需要知道什么、决定什么、审查什么、接收什么？
Host: 通过什么协议和交互设备交付？
```
### 产品不能绕过执行事实
- UI 显示“完成”必须引用 canonical terminal event 和必要 settlement。；UI 显示“已取消”必须区分 cancel requested、cancelled、unknown outcome。；UI 显示“已发送”必须有 delivery receipt；不能用模型文本替代。；UI 显示“已记住”必须有 MemoryEntry、scope、TTL 和 consent/policy evidence。；UI 显示“已删除”必须有 deletion receipt；不能只隐藏列表项。
## 用户任务模型与产品状态
### 用户任务不是聊天消息
产品需要同时管理三种 truth：
```text
User Truth
目标、约束、偏好、批准、反馈、取消、交付选择
Task Truth
acceptance criteria、计划、完成项、未完成项、风险、依赖
Run Truth
model/tool/policy、事件、预算、artifact、错误、checkpoint、side effects
```
它们分别来源于用户输入、Harness/State 和执行事实，不能混为一张消息表。
### TaskSpec
```typescript
interface ProductTaskSpec {
taskId: string;
objective: string;
constraints: string[];
acceptanceCriteria: AcceptanceCriterion[];
requestedMode: ProductMode;
workspaceTarget?: WorkspaceTarget;
inputArtifacts: ArtifactRef[];
privacyChoices: PrivacyChoice[];
deliveryPreference: DeliveryPreference;
priority: "interactive" | "standard" | "background";
assumptions: string[];
unresolvedQuestions: string[];
}
```
### AcceptanceCriterion
验收标准必须可观察：
- 文件、diff、test、command、artifact、finding、state、review。；required 与 optional 分开。；verifier 指定 harness、parent、user 或 automated test。；“尽力完成”可以是说明，但不能作为唯一 hard criterion。
### 任务阶段
```text
Intake
-> Understanding
-> Planning
-> Executing
-> Verifying
-> Reviewing
-> Delivering
-> Settled
```
阶段用于决定：
- 当前显示哪些工具和事件。；上下文和 prompt 如何编译。；是否需要 plan approval、action approval 或结果 review。；当前 completion criteria、预算、通知和自动化程度。
### 任务视图
产品可提供：
- Chat view：消息、工具卡片、审批和结果。；Work view：计划、步骤、状态、依赖、日志、diff。；Review view：变更、证据、测试、风险、批准。；Run view：尝试、provider、usage、cost、错误、恢复。；Privacy view：数据范围、provider、retention、memory 和删除。；Admin view：租户配额、路由、feature rollout、分析和审计。
这些是 projector，不是独立事实源。
## 用户角色、信任与引导
### Trust Calibration
信任体验的目标不是让用户“相信 Agent”，而是让用户知道：
- Agent 当前知道什么、尚未验证什么。；它可以调用哪些工具、哪些工具被隐藏或拒绝。；哪些动作会改变文件、发送消息、产生费用或外发数据。；哪些结果来自模型推断，哪些来自工具 receipt、测试、diff 或 artifact。；发生失败、fallback、compaction、取消或 unknown outcome 时应该做什么。
### 首次引导
引导应分阶段：
1. 说明产品边界：Kernel、Harness、workspace、工具和 approval 的关系。；让用户选择 workspace/project，并展示 project trust 的含义。；展示模式矩阵：read-only、plan、implementation、review、offline。
• 展示数据处理：哪些内容可能发送到 provider，如何选择 provider/region/privacy profile。；让用户设置 memory、background task、通知、预算和成本上限。；运行安全的 dry-run 或只读任务，展示 event、tool card、artifact、diff 和恢复按钮。；在首次高风险动作前再进行上下文相关的解释，不在 onboarding 一次塞完全部规则。
### 信任层级
- `Untrusted workspace`：只读元数据、源码、静态搜索，不执行 hooks/MCP/plugins。；`Trusted read-only`：读取项目规则和指定资源，但仍不开放写入或任意 shell。；`Trusted implementation`：按 policy 开放 scoped write、sandbox、审批和 diff。；`Elevated`：独立通道、短 TTL、强认证、逐动作审计，不由普通模式隐式升级。
### 解释原则
- 展示 action 的具体目标，而不是笼统的“允许 Agent 操作”。；展示 material parameters、影响范围、可逆性、sandbox、网络和费用。；拒绝时给出安全替代方案，但不泄露敏感 policy 细节或其他资源存在性。；不把复杂内部错误原样转成用户文案；保留 diagnostic reference。；对 uncertain/unknown 状态使用准确语言，不用“可能完成”掩盖事实缺口。
## 核心产品数据模型
### ProductSession
```typescript
interface ProductSession {
sessionId: string;
tenantId: string;
ownerId?: string;
workspaceId?: string;
projectId?: string;
title?: string;
activeBranchId: string;
mode: ProductMode;
status: "active" | "idle" | "background" | "waiting" | "archived" | "deleting";
lastRunId?: string;
unreadCount: number;
pendingApprovalCount: number;
memoryPolicy: MemoryProductPolicy;
privacySummary: PrivacySummary;
retention: RetentionPolicy;
createdAt: string;
updatedAt: string;
}
```
### ProductRunView
```typescript
interface ProductRunView {
runId: string;
sessionId: string;
branchId: string;
taskId: string;
status: ProductRunStatus;
phase: ProductPhase;
progress?: ProgressModel;
currentAttempt?: AttemptView;
activeTools: ToolCardView[];
pendingApprovals: ApprovalCardView[];
artifacts: ArtifactRef[];
diffs: PatchRef[];
usage: UsageView;
cost: CostView;
recovery?: RecoveryView;
delivery: DeliveryView;
lastDurableCursor?: EventCursor;
configSummary: ConfigSummaryView;
}
```
### MessagePartView
```typescript
interface MessagePartView {
id: string;
kind: "text" | "reasoning_summary" | "tool_call" | "tool_result"
| "artifact" | "citation" | "warning" | "error" | "status";
state: "streaming" | "complete" | "failed" | "hidden" | "redacted";
content?: ContentPart[];
sourceEventIds: string[];
sensitivity: Sensitivity;
presentation: "inline" | "collapsed" | "card" | "link" | "metadata_only";
}
```
### ProgressModel
```typescript
interface ProgressModel {
phase: ProductPhase;
label: string;
completedSteps: number;
totalSteps?: number;
currentStep?: string;
blockers: ProgressBlocker[];
confidence: "known" | "estimated" | "unknown";
updatedAt: string;
}
```
进度不能伪造精确百分比：如果 Harness 没有可计算的步骤或 total，不显示 73% 之类的虚假数字，改显示阶段、当前动作和等待原因。
### UsageView 与 CostView
```typescript
interface UsageView {
inputTokens?: number;
outputTokens?: number;
reasoningTokens?: number;
toolCalls: number;
artifactsBytes: number;
source: "provider" | "estimated" | "reconciled";
includesRetries: boolean;
updatedAt: string;
}
interface CostView {
currency: string;
estimated?: Money;
reserved?: Money;
settled?: Money;
reconciled?: Money;
capState: "within" | "warning" | "paused" | "exhausted" | "unknown";
byOperation: Record<string, Money>;
pricingVersion?: string;
}
```
## TypeScript 接口
### ProductPort
```typescript
interface AgentProductPort {
createSession(input: CreateSessionInput): Promise<ProductSession>;
submitTask(input: ProductTaskInput): Promise<TaskAcceptanceReceipt>;
inspectSession(input: InspectSessionInput): Promise<ProductSessionView>;
subscribe(input: ProductSubscription): AsyncIterable<ProductEvent>;
sendControl(input: ProductControlCommand): Promise<ControlReceipt>;
resolveArtifact(input: ArtifactRequest): Promise<ArtifactDeliveryPlan>;
requestExport(input: ExportRequest): Promise<ExportReceipt>;
requestDeletion(input: DeletionRequest): Promise<DeletionReceipt>;
}
```
### ProductEvent
```typescript
type ProductEvent =
| { type: "session.opened"; session: ProductSession }
| { type: "task.accepted"; taskId: string; runId: string }
| { type: "phase.changed"; runId: string; phase: ProductPhase }
| { type: "message.delta"; runId: string; partId: string; delta: string }
| { type: "message.completed"; runId: string; part: MessagePartView }
| { type: "tool.card"; runId: string; card: ToolCardView }
| { type: "tool.progress"; runId: string; progress: ToolProgressView }
| { type: "approval.requested"; runId: string; card: ApprovalCardView }
| { type: "approval.resolved"; runId: string; approvalId: string; outcome: string }
| { type: "artifact.available"; runId: string; ref: ArtifactRef }
| { type: "diff.available"; runId: string; patch: PatchRef }
| { type: "usage.updated"; runId: string; usage: UsageView; cost: CostView }
| { type: "recovery.required"; runId: string; recovery: RecoveryView }
| { type: "run.completed"; runId: string; result: ProductResult }
| { type: "run.failed"; runId: string; error: ProductErrorView }
| { type: "run.cancelled"; runId: string; outcome: CancelOutcome };
```
### ProductControlCommand
```typescript
interface ProductControlCommand {
commandId: string;
tenantId: string;
sessionId: string;
runId?: string;
kind: "approve" | "deny" | "steer" | "cancel" | "pause"
| "resume" | "retry" | "branch" | "change_mode" | "forget_memory";
payload: unknown;
expectedVersion?: number;
idempotencyKey: string;
}
```
### HostCapabilities
产品在 Host capability 之上定义 product capability：
```typescript
interface ProductCapabilities {
supportsStreaming: boolean;
supportsApproval: boolean;
supportsSteering: boolean;
supportsCancellation: boolean;
supportsPauseResume: boolean;
supportsDiffPreview: boolean;
supportsArtifactDownload: boolean;
supportsBackgroundJobs: boolean;
supportsSessionBrowsing: boolean;
supportsMemoryControls: boolean;
supportsRichProgress: boolean;
supportsNotifications: boolean;
maxMessageBytes?: number;
}
```
Host capability 只能影响交付和控制可用性；不能放宽 Policy、Sandbox、Egress 或 tenant safety floor。
## 能力发现与产品模式
### 能力分层
```text
catalog capability
∩ deployment capability
∩ tenant policy
∩ workspace trust
∩ active toolset
∩ sandbox capability
∩ host/product capability
∩ budget/egress state
= effective product capability
```
产品启动时应显示 capability summary：
- 可用模型/Provider/API family 的用户可见摘要。；当前模式可见工具和副作用等级。；是否支持 streaming、approval、resume、artifact、diff、background。；当前 workspace trust、sandbox、network、memory 和 provider egress 限制。；不可用能力的安全解释和替代路径。
### ProductMode
```typescript
type ProductMode =
| "offline"
| "read_only"
| "plan"
| "implementation"
| "review"
| "background";
```
模式必须同时改变：
- active toolset。；Policy/Approval。；Sandbox/Network。；Prompt/Context。；completion criteria。；delivery、notification、cost 和 privacy choices。
### 模式矩阵
| 模式 | 写工具 | 外部网络 | 审批 | 默认交付 |
|---|---:|---:|---:|---|
| `offline` | 否 | 否 | 不适用 | 本地结果/diagnostic |
| `read_only` | 否 | policy | 不应需要 | 解释/证据 |
| `plan` | 仅 plan artifact | policy | plan 可选 | 计划/风险 |
| `implementation` | policy | policy | 高风险需要 | diff/test/artifact |
| `review` | 否 | policy | 不执行高风险 | findings/diff |
| `background` | policy | policy | durable approval | notification/artifact |
### 能力不一致
如果 prompt、toolset、policy、sandbox、host 或 provider 宣称不一致：
- bootstrap 产生 diagnostic。；隐藏或拒绝不一致能力。；不让用户看到“可用”但点击后才失败的虚假工具。；记录 config/toolset/policy/sandbox hash。
## Task Intake 与任务规范化
### Intake 目标
Intake 不应立即让模型开始长回答，而应先解析：
- objective、scope、workspace、输入附件、模式、优先级。；constraints、acceptance criteria、不可接受动作、交付格式。；是否需要计划、审批、后台、memory、provider choice、privacy profile。；未解决问题、假设和当前用户已有修改。
### Intake UX
- 用户明确路径/仓库时先验证 ownership、trust 和 workspace。；目标不清时优先生成可编辑的 assumptions/questions，不要立即扩大 scope。；低风险明确任务可直接进入 execution；高风险/大范围任务先 plan。；附件先显示类型、大小、敏感度、发送目标和 retention，再进入 Context。；任务目标变化时将旧 plan 标记 `superseded`，创建新 plan hash，不覆盖历史。
### Plan approval
Plan approval 不是 tool approval：
- plan approval 允许执行某组已说明的工作步骤。；具体高风险 tool action 仍可能逐项需要 approval。；plan 变化、目标路径变化、预算变化或 policy 变化会使 approval 失效。；用户可批准 plan 的某个步骤、全部低风险步骤或只读阶段。
### Completion contract
产品应在任务开始时显示简短完成标准：
```text
目标已处理
必要文件/资源已修改或明确未修改
相关测试/验证有真实证据
diff/artifact 可审查
未授权副作用未发生
剩余风险和配置明确
```
## 会话 UX 与 Transcript 投影
### Session 与 Run 的呈现
- Session 是用户可回访、分支、搜索、导出、删除的长期容器。；Run 是一次可取消、可恢复、可比较的执行。；Attempt 是一次 provider/model 路径；失败尝试不能被 UI 隐藏。；Turn 是一次模型采样与工具批次；工具 call/result 必须成对显示。
### Transcript 投影
Transcript projector 应把：
- user/assistant message 投影为消息卡片。；tool call 投影为工具卡片或折叠细节。；tool result 投影为摘要、结构化结果和 artifact link。；approval 投影为待处理控制卡片。；compaction 投影为可展开的“上下文已压缩”事实和摘要范围。；model change/fallback 投影为可解释的 route notice。；error/recovery 投影为下一步操作而非堆栈。
### 消息状态
```text
draft -> accepted -> streaming -> complete
accepted -> blocked | waiting_for_approval | cancelled
streaming -> failed | interrupted | complete
complete -> superseded | archived
```
UI 不应在事件缺失时自行补全状态；重连后从 snapshot + tail 重建。
### Branch 与历史
- Branch 允许用户尝试不同方案，但不自动合并有副作用的状态。；branch/fork 应显示共同 ancestor、差异、artifact、model/toolset/policy 变化。；revert 是新事实，不删除历史。；当前活跃 branch、切换原因和未交付变更必须明显显示。
### 会话搜索与浏览
- 支持按状态、workspace、时间、标签、artifact、错误、任务类型搜索。；搜索结果只显示调用者有权看到的摘要、status、cursor 和 refs。；不用全文 prompt、secret 或原始 tool args 作为公共索引。；attach session 前重新授权 tenant/workspace/policy/capability。
## 流式、进度与 Backpressure
### 流式事件
产品消费 canonical/product events，而不是 provider raw chunks：
```text
RunStarted
PhaseChanged
ContextCompiled
ModelAttemptStarted
TextDelta
ReasoningSummaryDelta
ToolCard
ToolProgress
ApprovalRequested
ArtifactCreated
UsageUpdated
AttemptFailed
FallbackSelected
CompactionStarted
CompactionCompleted
RunCompleted/Failed/Cancelled
```
### 展示策略
- text delta 可 coalesce，但不跨控制事件、redaction 边界或消息 part。；reasoning 默认显示摘要或 metadata，不默认显示 hidden reasoning。；tool arguments 可显示安全摘要和 material parameters，原始 secret/path 受 redaction。；progress 显示 phase、current action、queue/lock/approval wait，不伪造未知百分比。；completion/error/approval/safety 事件不可被 delta 淹没。
### Backpressure
- Host delivery、projection、trace 和 durable writer 使用独立队列。；慢 UI 不得阻塞 provider stream、tool stdout 读取或 durable commit。；高价值事件优先；低价值 delta 可合并、降采样或转 artifact。；队列满时显示 `delivery.slow_consumer`、提供 resume cursor，不静默宣称完成。；多客户端各有 cursor、redaction profile、delivery status；一个客户端慢不影响其他客户端事实。
### 断线
断线是 transport fact，不等于 run cancel：
- 前台短任务可按 policy 继续到 checkpoint。；background run 不依赖前台连接。；approval UI 消失不自动 allow。；重连重新认证、协商 capability、校验 cursor 和 projection profile。；cursor 过期时 snapshot + tail，不从内存 buffer 猜测。
## 审批、转向、取消与恢复控制
### Approval Card
审批卡片必须显示：
- tool/action 名称和版本。；canonical target、material parameters、environment、effect、risk。；sandbox filesystem/network/process profile。；data egress、provider/region、敏感度和费用估算。；是否可逆、snapshot/diff、TTL、scope 和重复调用语义。；approve once、exact action、scoped grant、deny、cancel 等选项。
不能只显示“是否允许 shell”。
### Approval control flow
```text
ApprovalRequested
-> host presents material action
-> user/authenticated approver chooses decision
-> ControlCommand with idempotency + expectedVersion
-> Policy revalidates action hash
-> ApprovalStore commits decision
-> Harness consumes grant once or scoped
-> Tool executes or remains denied
```
重复审批、过期审批、参数变化、tool version 变化、policy/trust 变化必须返回 conflict/expired，而不是重复执行。
### Steering
Steering 是用户改变当前任务方向的结构化控制：
- `interrupt`：在安全边界尽快注入当前 loop。；`normal`：下一 turn 使用。；`after_current_task`：当前稳定完成后作为 follow-up。
Steering 不能：
- 越过 pending approval、lock、durable commit 或 sandbox boundary。；伪造 system prompt、policy、tenant、user consent 或 tool result。；修改已执行的历史；只能创建新 entry、supersede plan 或 branch。
UI 应显示 steering 已接受、排队、延迟、应用、拒绝或因 run 已终止而无效。
### Cancel
取消必须区分：
```text
cancel_requested
-> stopping_new_work
-> abort_propagated
-> tools_settling
-> side_effect_reconciled
-> cancelled | unknown_outcome | completed_race
```
用户文案：
- “已请求取消”：尚未确认停止。；“正在停止工具”：模型流已停止，但工具/进程仍在清理。；“已取消”：没有未结算的未知副作用，或结果已明确。；“结果未知”：可能已发生副作用，提供查询/人工处理。
### Pause/Resume
Pause 只在 Harness 支持 checkpoint 和安全边界时提供：
- 停止新 model/tool work。；保存 working state、pending approval、in-flight state、budget、context hash。；不释放仍影响状态的 lease，除非有安全的 lease transfer。；Resume 重新验证 policy、workspace、model/toolset、budget、consent、sandbox 和 unknown outcome。
## Tool、Artifact、Diff 与交付
### Tool card
Tool card 显示：
- 工具名称、用途、effect、状态、开始/完成时间。；安全摘要、输入范围、输出摘要、退出码/业务状态。；policy/approval/sandbox 状态、artifact refs、truncation。；可重试、可查询、可撤销或需人工处理的下一步。
不显示完整内部异常、secret、host 绝对路径、无授权 raw output。
### Artifact
大结果优先交付 `ArtifactRef`：
- 内容类型、大小、hash、敏感度、owner、expiry、scan status。；model-facing summary、user-facing preview、raw diagnostic 分离。；支持 range、分页、下载、短 TTL share、断点续传和 checksum。；artifact unavailable、quarantined、expired、deleted 和 provider remote limitation 都要有明确状态。
### Diff
Coding Agent 交付至少包括：
- unified diff、文件统计、symbol 影响、base/target hash。；user/agent/generated/vendor 变更标记。；测试、命令、退出码、artifact evidence。；conflict、base mismatch、revert 和可恢复动作。；预览不等于 apply；apply 不等于 commit；commit 不等于 push/deploy。
### 交付状态
```text
Prepared -> Authorized -> Generated -> Scanned
-> Available -> Presented -> Acknowledged
Presented -> Failed | Expired | Revoked
```
Host ack 只表示收到交付，不表示用户阅读或业务副作用完成。
### 多渠道消息
- 长文本拆分、摘要或 artifact ref，保持 correlation 和顺序。；渠道限制不能删除审批、安全、错误和终态事实；可转为 link/card/manifest。；channel edit/delete 能力只影响展示，不覆盖 canonical transcript。；外部消息发送需要独立 delivery status、幂等和 unknown outcome。
## Memory 控制
### Product memory taxonomy
```text
Working memory
当前任务、步骤、pending work
Semantic memory
稳定偏好、项目事实、用户明确保存的规则
Episodic memory
过去任务与结果
Procedural memory
被允许复用的工作流和命令
```
### Memory UX
用户必须能：
- 查看某条 memory 的内容、来源、confidence、scope、created/verified/expiry。；看到它为何被召回、当前任务是否使用。；批准、拒绝、编辑、supersede、forget 单条 memory。；关闭某个 memory type、workspace memory 或自动写入。；清理 session、workspace、user scope 的 memory。；看到敏感内容为何不能保存或只能短期使用。
### Memory write product flow
```text
candidate detected
-> preview claim and source
-> classify sensitivity/purpose
-> show approval if required
-> save active/candidate/stale
-> notify scope and expiry
```
不能把“模型在回答里提到过”显示成“系统已记住”。
### Memory recall
- 召回卡片显示来源、freshness、confidence、scope 和是否 stale/contradicted。；过期 memory 可以作为低优先级 evidence，但不能伪装为当前事实。；memory recall 不扩大工具权限、不替代 approval、不改变 tenant。；用户删除后，产品立即从当前 UI 和 recall index 排除，并显示清理进度/限制。
## Skills、Plugins 与 MCP 产品化
### Skill
Skill 主要是 workflow knowledge/resource navigation：
- 显示名称、版本、来源、scope、适用模式、所需工具和隐私影响。；Skill 不能直接扩大 tool visibility、approval、sandbox、retention 或 provider egress。；读取 skill 内容与执行 skill workflow 分开；未信任 workspace 的 skill 不自动执行。；skill 更新产生版本、diff、compatibility、rollback 和 toolset hash 变化。
### Plugin
Plugin 产品安装流程：
```text
discover metadata
-> verify provenance/digest/signature
-> show capabilities and data access
-> trust/approval
-> sandbox/profile selection
-> transactional registration
-> health check
-> publish active contribution
```
插件失败时逆序 dispose 并恢复旧 registry/toolset snapshot。 产品必须明确：
- plugin 是否进程内可信代码、是否独立进程/容器。；可访问的文件、网络、secret、tenant、artifact 和事件。；可注册的 tools/hosts/providers/hooks。；更新、卸载、撤销、隔离和残留清理。
### MCP
MCP server 产品化需要显示：
- server provenance、启动命令/transport、auth、workspace trust。；tools/resources 列表、schema snapshot、effect/risk、network、output budget。；server 运行状态、重连、schema drift、版本、scope 和 owner。；server crash 或连接失败时的重试/禁用/替代路径。
MCP 描述和结果不能自动获得 policy authority；本地 wrapper 负责 effect、risk、budget、redaction、egress 和审计。
## 多客户端、渠道与身份路由
### Canonical session
多客户端共享：
- Session/Branch/Run/Turn/Attempt 事实。；canonical event sequence、durable entries、artifact refs、approval state。
每客户端独立：
- projection profile、redaction profile、cursor、ack、delivery status。；UI 展开/折叠、滚动、typing、通知已读状态。
### 身份路由
渠道消息不能仅凭文本中的 user ID 建立身份：
- 由认证 token、channel signature、service identity 或已验证映射解析 principal。；tenant/workspace/session key 由 Harness/Host policy 决定。；thread、channel、IDE document、CLI cwd 只是输入 hint，必须重新授权。；跨渠道 attach 需要明确 ownership、privacy、retention 和 delivery capability。
### Host capability intersection
```text
effective product delivery
= canonical events
∩ host capabilities
∩ tenant policy
∩ redaction profile
∩ artifact availability
```
Host 不支持 approval 时，高风险动作 fail-closed；Host 不支持 diff 时交付 patch artifact 或只读预览；Host 不支持 background notification 时提供 polling/resume。
## 后台任务、通知与结果回收
### BackgroundRun
后台任务必须：
- 有 durable queue、job ID、owner、tenant、session/run、priority、deadline。；有 worker lease、heartbeat、checkpoint、idempotency key 和 recovery lease。；与前台连接解耦；客户端断线不自动取消。；有 notification policy、quiet hours、channel、摘要、artifact ref 和 unread state。；结果回收时重新授权 session/artifact/tenant，不能广播到全局频道。
### 状态
```text
Queued -> Leased -> Running -> WaitingForApproval
Running -> Checkpointed -> Completed
Running -> WorkerLost -> Recovering
任何活动状态 -> Cancelled | Expired | Failed | UnknownOutcome
```
### 通知
通知等级：
- informational：阶段完成、低风险 artifact ready。；action required：approval、credential、workspace trust、conflict。；warning：预算、provider degradation、partial result、stale memory。；critical：unknown side effect、privacy/security incident、删除失败。
通知内容必须最小化：
- 不在 push/channel 中放 secret、完整 prompt、regulated 原文或未授权 artifact。；notification delivery 与 run outcome 分开；发送失败不改写业务事实。；重复通知按 event/cursor/idempotency 去重；无法确认送达时提供 inbox/poll。
### 结果回收
- 用户重新打开产品先看到未读 run、pending approval、recovery required 和 artifact。；结果页面显示 completed/partial/failed/cancelled/unknown，不把 partial 当 success。；background run 的 child transcript 默认不混入主对话，只展示 assignment、summary、evidence、artifact 和 cost。
## 配额、成本与用户透明度
### 用户可见预算
显示：
- 当前 run/session/tenant 的 token、tool、artifact、worker、egress、时间和费用预算。；estimated、reserved、settled、reconciled、pending/unknown 状态。；cost per operation：model、retry、fallback、compaction、subagent、tool、storage、egress。；soft cap、hard cap、暂停原因和替代方案。；provider/model/region、pricing version 和可能变化的估算假设。
不显示或不暴露：
- secret、完整 prompt、内部价格合同、其他租户 cost。；用模型自然语言估算的“节省金额”。
### Cost decision UX
```text
within budget -> proceed
soft cap -> explain + ask/downgrade/queue
hard cap -> stop new reservation + recovery/query
unknown price -> interval/ask/deny
provider failure -> bounded retry/fallback with new cost entry
```
### 配额控制
- reservation 先于并发 model/tool/subagent/egress。；child budget 是 parent remaining 的子集。；retry/fallback/compaction/denied attempt 仍计量或释放 reservation。；队列等待、后台任务、artifact storage、下载和通知成本可单独显示。；quota unavailable 时显示可执行的 read-only 或低成本替代，不自动超卖。
## 错误恢复 UX
### 错误分类
产品文案由稳定 error code 映射，不展示内部堆栈：
```text
invalid_input
workspace_unresolved
project_untrusted
policy_denied
approval_required
approval_expired
sandbox_unavailable
provider_rate_limit
provider_capability
context_overflow
tool_validation
tool_execution
artifact_unavailable
session_conflict
host_delivery
budget_exhausted
cancel_pending
unknown_outcome
privacy_restricted
internal_error
```
### 恢复动作模型
```typescript
interface RecoveryView {
reasonCode: string;
state: "retryable" | "waiting" | "requires_user" | "requires_manual"
| "partial" | "terminal" | "unknown";
summary: string;
nextActions: RecoveryAction[];
evidenceRefs: ArtifactRef[];
safeToRetry: boolean;
affectsSideEffects: boolean;
}
```
### 文案规则
- 说明发生了什么、当前事实、用户可做什么、系统不会做什么。；`safeToRetry=false` 时不提供“一键重试原动作”，而提供 query/status、inspect、branch 或人工处理。；provider 429 显示等待/队列/换兼容模型，记录费用和新 attempt。；context overflow 显示“正在压缩/需要缩小范围”，不显示“模型笨”。；approval expired 显示参数、policy 或时间变化，不把它当系统故障。；partial success 显示已完成与未完成项，给出 artifact/diff/evidence。；unknown outcome 明确可能副作用、查询状态和人工入口。
### Resume UX
- 展示 last durable checkpoint、pending approvals、in-flight tools、unknown outcomes。；允许 resume safe step、rebuild context、change model/toolset、discard branch 或 request manual review。；恢复前显示 policy/trust/workspace/budget 变化；不静默使用旧 snapshot。
## 反馈、评测与质量闭环
### 反馈类型
- explicit：thumbs up/down、评分、文本反馈、接受/拒绝 diff、memory edit。；corrective：用户重复说明、手工修改、撤销 patch、重新运行、人工接管。；operational：timeout、retry、fallback、approval deny、cancel、disconnect。；business：任务完成、测试通过、artifact 下载、外部 receipt、rollback。；safety/privacy：policy deny、redaction hit、egress block、unknown outcome、cross-scope attempt。
### Feedback contract
```typescript
interface ProductFeedbackRecord {
feedbackId: string;
tenantId: string;
sessionIdHash?: string;
runIdHash?: string;
type: "rating" | "correction" | "acceptance" | "rollback"
| "approval" | "support" | "business_outcome";
value?: number | string;
targetEventIds: string[];
taskClass?: string;
redactionState: string;
consentScope?: string;
createdAt: string;
}
```
### Evaluation
产品评测必须同时检查：
- task completion、acceptance criteria、最终解释。；event sequence、tool choice、approval、steering、cancel、resume。；state/projection、artifact/diff、side effect、tenant/privacy。；usage/cost、latency、backpressure、notification、multi-client resume。；unknown outcome、partial result、failure recovery 和 user control。
LLM judge 只负责开放式语义质量，不能判定真实副作用、权限、schema、成本或删除。
### Feedback to regression
```text
observe signal
-> redact/minimize
-> triage and reproduce
-> create deterministic fixture
-> add trajectory/state/side-effect oracle
-> fix
-> CI gate
-> canary
-> monitor
```
生产 transcript 不直接作为 golden；必须删除无关数据、合并相似 case、记录 provenance、敏感度、版本和 consent。
## 功能发布、实验与回滚
### 发布单位
- Kernel/Harness、model/provider adapter、tool、skill/plugin/MCP。；prompt/context compiler、memory、artifact、host projection。；product mode、approval UX、background queue、notification。；policy、privacy/egress、cost、analytics、schema/projector。
每个发布记录：
- version、config hash、schema compatibility、owner、scope、rollout group。；required capabilities、known gaps、privacy impact、cost impact。；migration/upcaster、rollback plan、canary criteria、expiry。
### Rollout 流程
```text
draft
-> static/type/security/evaluation
-> offline replay
-> shadow/dry-run
-> small canary
-> observe SLO/cost/privacy/trajectory
-> expand cohorts
-> complete or pause
```
### 实验原则
- 实验不能放宽 safety floor、tenant isolation、approval、egress、retention 或 hard cap。；shadow 禁止真实外部副作用；使用 fake/dry-run tools。；A/B 记录 mode、prompt/context/tool/policy/model/host 版本。；不把不同实验因素混在一起后宣称单一功能提升。；用户可见的能力变化需有说明、关闭或回退路径；后台实验不应隐式改变 memory/retention。
### 回滚
回滚应用不等于回滚 session/event/artifact/schema：
- 先确认旧版本能读取新 checkpoint、event、toolset、policy、artifact view。；保留 upcaster、dual-read 或 migration rollback window。；若出现 privacy/security、sandbox fail-open、重复副作用或 audit loss，立即暂停高风险动作并保留证据。；rollback 后重新验证 provider conformance、Host projection、成本、隐私和恢复。
## 产品分析、隐私与数据治理
### Analytics 原则
Product analytics 是独立目的：
- 不因为用户使用 Agent 就自动允许收集完整 prompt、代码、tool args、hidden reasoning 或 artifact。；每个分析事件声明 purpose、data class、retention、tenant scope、consent/legal basis。；默认只收集 event kind、阶段、状态、延迟、计数、版本、hash、reason code 和聚合标签。；高敏感事件使用 metadata-only、短 TTL、restricted sink 或不采集。；用户、租户和管理员可查看、导出、删除或关闭可选分析。
### AnalyticsEvent
```typescript
interface AnalyticsEvent {
eventId: string;
name: string;
schemaVersion: string;
tenantIdHash: string;
workspaceIdHash?: string;
sessionIdHash?: string;
runIdHash?: string;
productMode?: ProductMode;
taskClass?: string;
outcome?: string;
latencyMs?: number;
counts?: Record<string, number>;
reasonCodes?: string[];
featureVersions: Record<string, string>;
purpose: "product_analytics" | "reliability" | "cost" | "evaluation";
sensitivity: Sensitivity;
retentionClass: string;
redactionState: "metadata_only" | "redacted" | "tokenized";
createdAt: string;
}
```
### 不采集清单
默认不进入普通 analytics：
- 完整 user/assistant text、prompt、tool arguments、源代码、文件名、路径。；hidden reasoning、secret、token、PII、regulated payload。；artifact raw content、provider headers、remote URL、approval material parameters。
如为了安全/诊断需要受控保存：
- 使用 ArtifactRef、加密、短 TTL、purpose-specific access、legal hold 和 audit。；对生产数据执行最小化、脱敏、去重、review 和 deletion。
### 指标
产品指标分层： 任务与交付：
- task acceptance、completion、partial、failed、unknown、manual handoff。；acceptance criteria coverage、diff accepted、artifact opened/downloaded、notification acknowledged。
控制与信任：
- approval shown/approved/rejected/expired、cancel requested/settled、steering applied。；user correction、rollback、re-run、branch、memory edit、privacy settings change。
可靠性：
- TTFE、TTFT、phase latency、queue/lock/approval wait、resume success、delivery gap。；provider retry/fallback、context overflow、tool failure、artifact scan/quarantine。
成本：
- cost/run、cost/success、retry waste、compaction/subagent/tool/storage/egress。
安全隐私：
- privacy decision coverage、egress deny/transform、redaction、cross-tenant deny、unknown outcome。
所有高基数字段在 metrics 中使用分类、hash 或受控 query，不用完整 text/path/ID 作为 label。
### 删除与访问
- Analytics store、feature flag exposure、experiment assignment、support export 和 dashboards 都纳入 retention/deletion graph。；删除用户/session/run 数据时，聚合指标是否可回溯要有明确 policy；不可逆聚合只能保留不含个人可识别信息的结果。；analytics access、query、export、debug replay 都写 audit。
## 生命周期与状态机
### Product Run
```text
Created
-> Intake
-> Ready
-> Planning
-> AwaitingPlanApproval
-> Executing
-> WaitingForApproval | WaitingForInput | WaitingForDependency
-> Verifying
-> Reviewing
-> Delivering
-> Settling
-> Completed
```
任意活动状态可进入：
```text
Cancelling -> Cancelled | UnknownOutcome
Failed -> Recovering -> Ready | WaitingForApproval | TerminalFailed
Paused -> Resuming -> Ready
```
### UI Delivery
```text
Disconnected
-> Authenticated
-> Subscribed
-> Streaming
-> Backpressured
-> ResyncRequired
-> Resumed
-> Delivered
-> Closed
```
Delivery terminal 不能覆盖 Harness terminal；两者分别显示。
### Approval
```text
Requested
-> Presented
-> Approved | Rejected | Expired | Cancelled | Conflict
-> Revalidated
-> Consumed
-> Executed | Invalidated
```
### Background Job
```text
Created -> Queued -> Leased -> Running
Running -> Checkpointed -> Completed
Running -> WorkerLost -> Recovering
Running -> WaitingForApproval | Cancelled | Expired | Failed | UnknownOutcome
```
### Feature Rollout
```text
Draft -> Validating -> Shadowing -> Canarying -> Expanding -> Active
Canarying/Expanding -> Paused -> RollingBack -> RolledBack | Failed
```
## 端到端产品决策流程
### 前台任务
1. Host 认证并解析 tenant/workspace/session。；展示当前 trust、mode、privacy、provider、budget 和 capabilities。；接收并规范化任务，生成 TaskSpec 和 acceptance criteria。
• 判断 direct execution、plan-first、read-only 或 background。；装配 Harness：Context、Prompt、Model、Tool、Policy、Sandbox、State、Artifact、Event、Host。；创建 session/run、配置快照、budget reservation 和 initial checkpoint。；发布 phase/context/model events，开始模型 stream。；将 assistant message、tool card、progress、approval、artifact 和 usage 投影到 UI。；在每个高风险边界等待 approval、policy、lock、sandbox attestation。；处理用户 steering、cancel、pause、follow-up 和 host disconnect。；验证 diff、测试、artifact、acceptance criteria 和 side-effect receipt。；交付 final result、remaining risks、cost、privacy summary 和 recovery path。；等待 durable event、usage、artifact、audit、delivery 和 cleanup settle。
### 后台任务
```text
user requests background
-> estimate/capability/privacy check
-> create durable job
-> enqueue with lease/budget
-> notify accepted
-> worker runs Harness
-> checkpoint/progress/approval
-> result/artifact/notification
-> user resumes and reviews
```
### 变更任务
```text
baseline capture
-> plan
-> plan approval
-> snapshot
-> edit/command under policy+lock+sandbox
-> read-back/diff
-> test/lint/build
-> review
-> commit request separately
```
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model/Provider
- 产品显示 provider/model/route 的必要摘要，隐藏 credential/raw headers。；fallback、retry、hedge、compaction、subagent 都显示为可解释的 attempt/usage 事实。；provider safety/refusal 与本地 policy deny 分开呈现。；capability mismatch 在任务开始前尽量发现，避免工具显示与实际不一致。
### Prompt
- Prompt 说明目标、模式、可见工具、完成标准、审批、错误和隐私边界。；不把 UX 文案当作执行控制；按钮、approval、cancel、budget 和 privacy 由 Harness 强制。；prompt compiler version、section hash、mode、toolset hash 进入 run snapshot，帮助解释体验回归。
### Context
- 产品选择“显示多少历史”和“展示哪些 artifact”，Context 负责语义选择与预算。；session transcript、UI projection、model context 分离。；compaction 通过事件和摘要可解释；用户可查看覆盖范围与结构化状态。；context overflow UX 提供缩小范围、分支、上传 artifact 或切换模型的操作。
### Tool
- 产品只呈现 active toolset 中的工具；隐藏工具直接调用也被 Harness 拒绝。；tool card、approval、progress、result、artifact、unknown outcome 都来自 canonical events。；tool retry、resource lock、parallel execution、result order 不由 UI 猜测。
### State/Memory/Artifact
- Product projector 从 semantic entries、durable events、checkpoint、artifact refs 和 memory records 构建视图。；memory controls 产生 durable command/entry，不是前端本地删除。；artifact/diff 交付使用授权 ref、range、hash、TTL，不把路径当权限。；branch/revert/merge 保留事实历史并展示冲突。
### Policy/Sandbox
- mode 切换改变 visibility、call、approval、execution、egress、budget、delivery 和 completion criteria。；UI 只能请求 approval/steering/cancel；不能直接执行 tool。；host 无审批、diff、artifact 或 background 能力时使用安全替代或 fail-closed。
### Harness
Harness 是 ProductPort 的执行后端：
- `start/resume/inspect/cancel/steer/submitApproval` 通过稳定端口提供。；event stream 与 final result 同时存在。；structured concurrency、checkpoint、retry、fallback、compaction、background、cleanup 由 Harness 监督。；UI 生命周期结束不等于 run 生命周期结束。
## 可观测性、运营与 SLO
### 产品 Trace
```text
host request
-> intake/task normalization
-> capability/trust/privacy
-> session/run admission
-> context/prompt compile
-> model attempt/tool/approval
-> artifact/diff/verification
-> delivery/notification
-> feedback/evaluation
```
### 必备字段
- tenant/session/run/task/attempt/turn、host/client/correlation/cursor。；product mode、phase、feature versions、prompt/context/toolset/policy/sandbox hashes。；tool/approval/artifact/diff/notification IDs，usage/cost、queue/lock、retry/fallback。；recovery state、unknown outcome、feedback type、experiment cohort。；仅使用脱敏摘要/hash，避免 raw text/path/secret。
### 用户路径 SLO
- request acceptance latency。；time to first meaningful event、time to first text、time to first tool card。；approval presentation/resume latency。；phase progress freshness。；terminal result availability、durable settlement latency。；resume completeness、artifact/diff availability、notification delivery。；cancel acknowledgement 与 side-effect reconciliation time。
### 正确性指标
- tool call/result pairing、approval binding、event sequence、terminal uniqueness。；completed task with verified evidence，而非 final text success。；duplicate side effects、unknown outcome、cross-tenant、privacy egress violations = hard zero targets。
### 运营视图
- 用户视图：任务状态、下一步、成本、隐私、证据、风险。；Operator：run snapshot、queue、provider、tool、policy、sandbox、artifact、worker、recovery。；Product：funnel、task success、correction、latency、cost、feature adoption。；Security/Privacy：egress、DLP、approval、scope、retention、incident、key 和 audit。
## 测试策略与 Evaluation
### Testkit
```text
FakeModelProvider
ScriptedModelStream
FakeToolRuntime
FakePolicyEngine
FakeApprovalStore
FakeSandboxBackend
InMemorySessionRepository
InMemoryArtifactStore
FakeMemoryStore
FakeHostAdapter
FakeNotificationProvider
FakeQueueWorker
DeterministicClock
DeterministicIds
EventRecorder
SlowConsumer
CrashInjector
SideEffectRecorder
ReplayRunner
```
### 单元测试
- TaskSpec、acceptance criteria、mode、phase、recovery action 文案映射。；Product projector、message/part 状态、tool card、approval card、usage/cost view。；event coalescing、cursor、resume、backpressure、multi-client dedupe。；control command idempotency、expectedVersion、approval conflict、steering queue、cancel semantics。；artifact/diff preview、truncation、scan/quarantine、short TTL delivery。；memory write/forget/recall UI state、scope、consent、expiry。；feature flag、cohort、rollback、analytics redaction 和 deletion。
### 场景测试
1. 无工具的普通回答显示正确 phase 和终态。；单工具调用显示 card、progress、result、artifact 和 usage。；并行工具 UI 按完成时间展示，但模型 feedback 按 call order。
• 审批 allow/deny/expire/duplicate/parameter change。；steering 在 current turn、next turn、after task 三种窗口。；cancel requested、tool process still running、unknown outcome、completed race。；host 断开、重连、cursor gap、snapshot + tail、多客户端。；大日志/diff/artifact 超 frame/上下文预算。；session branch、revert、user changes conflict、review mode。；memory candidate、user approval、forget、stale/contradiction。；plugin/MCP install、trust、schema drift、server crash、rollback。；background queue、lease expiry、worker recovery、notification duplicate。；budget soft/hard cap、cost unknown、provider fallback、compaction cost。；partial success、provider refusal、context overflow、tool validation error。；privacy egress deny、DLP redaction、cross-tenant、retention/delete/export。
• feature canary rollback、analytics redaction、experiment opt-out。
### Event/State/Side-effect 断言
每个工具型 scenario 至少包含：
- trajectory/event assertion。；final state/projection assertion。；side-effect oracle 或 negative oracle。；budget/termination assertion。；privacy/tenant/approval assertion（若适用）。
不能只比较最终文本；不能把 UI 显示成功当作真实状态。
### Fault injection
在以下边界注入：
- intake/session append、plan approval、context compile、model stream。；tool call ready、approval consume、sandbox attest、side effect、result commit。；artifact upload/scan/delivery、checkpoint、compaction、notification。；worker lease、queue、host disconnect、cursor replay、projector。；feature flag、config migration、analytics sink、privacy audit。
验证不重复副作用、不丢 durable state、不让 UI 伪造 success、能恢复或明确要求用户处理。
### Evaluation gates
- presubmit：protocol/projector、mode visibility、deterministic scripted runs、privacy/security core。；merge：完整任务回归、fault injection、replay、multi-client、cost/latency、artifact/memory。；scheduled：多 seed、load/soak、provider smoke、judge calibration、feedback regression。；release：关键任务、安全/隐私、migration、rollback、production config snapshot。
Hard gate：
- unauthorized side effect、secret/cross-tenant、approval bypass、event/state invariant、duplicate execution、unknown replay、budget bypass。
Soft gate：
- open-ended quality、judge score、live provider latency、文案偏好和小幅转化波动。
## 反模式与审查规则
1. 一个巨型 `AgentUI` 同时负责 provider、tool、state、policy、UI 和数据库。；只显示最终文本，不显示正在执行的工具、审批、失败、成本或证据。；用 spinner 代表真实进度，或显示没有来源的百分比。
• socket 关闭就把 run 标为 cancelled。；UI 按钮直接调用 tool，不经过 ControlCommand、Policy 和 durable approval。；approval 卡片只写“允许 shell”，不展示目标、参数、环境和风险。；允许用户批准一次后所有重试、fallback、child 和参数变化复用授权。；把 provider raw event 直接交给 UI，导致 Host 绑定某家 SDK。；把 UI 本地 transcript 当 session truth，断线后无法 resume。；把完整 tool output、hidden reasoning、secret 或 raw prompt 默认显示给用户/分析系统。；大日志直接塞进消息 frame 或 prompt，不使用 artifact/range/summary。；显示“已删除/已发送/已取消/已记住”但没有 receipt 或 durable event。；模式只改 prompt 文案，不改变 toolset、policy、sandbox、budget 和 completion criteria。；plan approval 隐式覆盖 commit/push/deploy 或外部发送 approval。；background run 依赖前台连接，客户端断线导致任务丢失或重复。
• 多客户端通过本地缓存互相同步，不从 canonical event/snapshot 重建。；产品分析采集完整用户内容，把 retention/analytics 当成产品默认。；memory 自动保存全部会话，没有 scope、TTL、consent、provenance 和 forget。；只按最终评分选择功能发布，忽略未授权副作用、成本、恢复和隐私。；shadow/canary 执行真实外部工具或放宽安全 policy。；错误文案把 retryable、manual、unknown、partial 和 terminal 混为“失败”。；通过无限 retry、fallback、subagent 或 compaction 隐藏成本。；Host capability 被当作授权，导致无审批 Host 自动执行高风险动作。；rollback 只回滚服务代码，不验证 event/schema/checkpoint/artifact/policy 兼容。；只测试 happy path，不测试 cancel、approval、replay、lease、privacy、delete 和恢复。
审查最低标准：
```text
用户知道目标和状态
用户能控制高风险动作
事实来自 durable event/state
大结果引用化
错误提供可操作恢复
成本与隐私可解释
多端事实一致
安全失败不可被 UI 掩盖
```
## 实施清单
### V1：Kernel-to-Product 基础
- [ ] 定义 ProductPort、ProductEvent、ProductControlCommand、ProductSession、ProductRunView。；[ ] 建立 Session/Branch/Run/Attempt/Turn/Message/Part 投影。；[ ] 实现 intake、TaskSpec、acceptance criteria、mode、phase 和 completion contract。；[ ] 实现 CLI/TUI/IDE/RPC/HTTP/Channel 的 Host capability intersection。；[ ] 实现 streaming、final result、cursor、resume、backpressure 和 multi-client consistency。；[ ] 实现基本 tool card、artifact ref、error view、usage/cost view。
### V2：信任、控制与交付
- [ ] 实现 onboarding、workspace trust、privacy/provider/region 选择和预算设置。；[ ] 实现 plan approval、tool approval、material parameters、scope、expiry、conflict。；[ ] 实现 steering、cancel、pause/resume、retry、branch、follow-up。；[ ] 实现 diff/snapshot/patch/revert、test evidence 和 review view。；[ ] 实现 artifact preview/range/download/short TTL/scan 状态。；[ ] 实现准确的 partial/unknown/recovery UX。
### V3：Memory、扩展与后台
- [ ] 实现 memory candidate/approval/edit/forget/scope/TTL/contradiction UI。；[ ] 实现 skill/plugin/MCP provenance、trust、capability、schema drift、transaction rollback。；[ ] 实现 background job、queue、lease、checkpoint、heartbeat、worker recovery。；[ ] 实现 notification policy、inbox、dedupe、quiet hours、result recovery。；[ ] 实现多渠道 identity/session routing 和跨客户端 attach。
### V4：成本、隐私与质量闭环
- [ ] 实现 estimated/reserved/settled/reconciled cost、soft/hard cap 和用户解释。；[ ] 实现 privacy summary、egress view、retention、memory、export/delete controls。；[ ] 实现 feedback schema、correction/rollback/acceptance/business outcome 信号。；[ ] 建立 trajectory/state/side-effect/privacy/cost evaluation suite。；[ ] 建立 production feedback 脱敏、最小复现、regression 和 CI gate。
### V5：发布、分析与运营
- [ ] 定义 feature/version/config/schema compatibility 和 rollback plan。；[ ] 实现 offline replay、shadow/dry-run、canary、cohort、自动暂停/回滚。；[ ] 实现 analytics purpose、retention、redaction、tenant isolation、delete/export。；[ ] 建立产品/可靠性/成本/隐私/安全 dashboard 与 SLO。；[ ] 建立 incident、unknown outcome、provider outage、queue backlog、sandbox 和 delivery runbook。；[ ] 进行长任务、慢消费者、多客户端、后台恢复、迁移和 chaos 演练。
### Definition of Done
- 用户能看到当前任务阶段、可用能力、工具/审批、进度、成本、隐私和完成证据。；每个控制动作都经过 Harness/Policy 并可恢复；UI 不会把连接状态当执行事实。；每个大结果可通过 ArtifactRef/diff/hash/TTL 审查；每个错误有正确恢复路径。；前台、后台、多客户端、多渠道和断线恢复共享同一 canonical state/event truth。；质量评估覆盖轨迹、状态、副作用、成本、隐私、恢复和最终结果，而非只评文本。
## 五个参考项目的启发来源
### Pi
- 极小 headless agent loop、统一 provider event、EventStream 与最终结果并存，启发 ProductPort 与 Kernel/Harness 分离，以及 live stream 与 final result 并存。；session tree、branch、steering/follow-up、compaction 和 AgentSession 启发可恢复会话、用户 steering、分支、长任务与上下文压缩 UX。；CLI/TUI/RPC 共用 runtime 启发多 Host 只改变 projection/delivery，不改变 canonical facts。
### Grok Build
- Session/ChatState/Sampler actor 启发任务状态所有权、并发工具、执行顺序与 UI feedback 顺序分离。；permission decision、folder trust、sandbox、路径级锁和输出限制启发审批卡片、workspace trust、风险说明、并行工具进度和 artifact offload。；分层 sampler、上下文修剪和独立 trace 启发 attempt/fallback/compaction/usage 的产品可解释性。
### OpenCode
- client/server、session/message/part、event bus、durable event/projector 启发多客户端 session UX、cursor/resume、消息 part、事件驱动 UI 和可重建投影。；snapshot/patch/revert 启发 diff、review、冲突、变更所有权和可审计恢复。；permission、MCP/LSP、server/client 分离启发扩展安装、审批、工具状态和 Host 交付的边界。
### Claude Code
- permission modes、hooks、skills、subagents、memory、项目规则、计划和任务工作流启发 coding mode、onboarding、计划审批、memory controls、子任务和用户信任体验。；通过完整产品 harness 组合工具、权限、记忆和扩展，说明产品价值不只来自模型文本。；公开能力和安全语义以本地文档中标注的 Anthropic 官方资料为准；辅助源码不作为权威规范。
### OpenClaw
- AgentHarness registry、agent-core、Gateway/channel、provider runtime 启发 capability registry、多渠道身份路由、后台任务和交付分层。；tool/sandbox/elevated 分离启发产品中“可见、可批准、可执行、可升级”四类不同控制。；memory flush、后台运行和事务化插件注册启发长期任务、通知、扩展安装、失败回滚和结果治理。
本设计的实现审查应回到上述本地工程文档及其记录的源码范围；若新增渠道、provider、产品模式、定价、合规、实验或通知平台，应单独补充一手证据、版本、迁移方案和契约测试。
