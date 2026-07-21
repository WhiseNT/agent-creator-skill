# Agent 细粒度工程文档导航

本目录把 Agent 参考架构继续拆成可以直接指导实现、审查和测试的工程设计。

> 本页供人类浏览；Agent 的规范路由源是 [`references/routes.json`](../routes.json)，跨文档术语和不变量以 [Agent Canonical Contract](../canonical-contract.md) 为准。默认只加载一个主文档和最多两个辅助文档。

## 当前文档

| 文档 | 解决的问题 | 何时读取 |
|---|---|---|
| [Prompt Engineering](prompt-engineering.md) | 如何编译系统指令、工具提示、模式提示和输出契约 | 设计 system prompt、tool description、plan/read-only 模式或修复指令冲突时 |
| [Context Engineering](context-engineering.md) | 如何发现、筛选、排序、压缩和持久化模型上下文 | 处理长会话、代码库规则、RAG、memory、附件和 token 预算时 |
| [Harness Engineering](harness-engineering.md) | 如何装配并监督 Agent Kernel 的完整运行环境 | 设计 runtime、权限、sandbox、session、event、plugin、subagent 和 host adapter 时 |
| [Tool Engineering](tool-engineering.md) | 如何定义、注册、调度、校验、执行和恢复工具调用 | 设计 function/tool calling、MCP、幂等、资源锁和工具结果时 |
| [State & Memory Engineering](state-memory-engineering.md) | 如何建模 session、transcript、event state、compaction 和 memory | 处理持久状态、分支、恢复、记忆写入/召回和 schema migration 时 |
| [Permission & Sandbox Engineering](permission-sandbox-engineering.md) | 如何把权限决策、审批、信任和沙箱变成可强制执行的边界 | 处理 shell、文件、网络、secret、elevated 和 prompt injection 时 |
| [Subagent Engineering](subagent-engineering.md) | 如何设计隔离的 child run、委派、并发、合并和恢复 | 需要多 Agent、后台任务、fan-out/fan-in 或成本控制时 |
| [Event & Observability Engineering](event-observability-engineering.md) | 如何统一事件、流、durability、trace、metrics、audit 和回放 | 设计事件总线、断线续传、诊断和生产监控时 |
| [Evaluation Engineering](evaluation-engineering.md) | 如何评测轨迹、状态、副作用、可靠性、安全、成本和回归 | 建立 runner、assertion、CI gates、fault injection、provider conformance 或生产反馈时 |
| [Agent Evaluation Dataset Engineering](agent-evaluation-dataset-engineering.md) | 如何构建可执行、可重放、可统计和可治理的 Agent 测评集 | 设计 golden/challenge/holdout/production 数据、taxonomy、case、ground truth、grader、污染防护和统计方法时 |
| [Coding Agent Engineering](coding-agent-engineering.md) | 如何让 Agent 在真实代码库中发现、计划、编辑、验证和恢复 | 设计 coding agent、代码修改、测试运行、review 和 workspace 状态时 |
| [Provider Runtime Engineering](provider-runtime-engineering.md) | 如何隔离 Provider/Model/Deployment、流式协议、能力、重试和计费 | 设计多模型、多云 provider adapter、fallback 或 conformance 时 |
| [Artifact Engineering](artifact-engineering.md) | 如何管理大输出、diff、日志、图片、二进制和结构化交付物 | 设计 artifact store、预览、range、脱敏、TTL、版本和跨 session 共享时 |
| [Multi-tenant Engineering](multi-tenant-engineering.md) | 如何隔离租户身份、配置、资源、配额、数据和后台任务 | 设计 SaaS、多用户、workspace、worker、数据驻留和合规边界时 |
| [Provider Routing Engineering](provider-routing-engineering.md) | 如何按能力、策略、健康、成本、延迟和数据驻留选择模型路由 | 设计多 Provider 路由、fallback、quota、canary、hedging 或 route explainability 时 |
| [Host Adapter Engineering](host-adapter-engineering.md) | 如何把 Agent Runtime 适配到 CLI、TUI、IDE、RPC、HTTP、Batch 和 Channel | 设计协议 framing、事件投影、审批、断线恢复、多客户端或交付层时 |
| [Workspace Isolation Engineering](workspace-isolation-engineering.md) | 如何隔离 workspace、repository、branch、文件、临时资源和执行边界 | 设计 Coding Agent 工作区、worktree、symlink、mount、subagent ownership 或 TOCTOU 防护时 |
| [Production Operations Engineering](production-operations-engineering.md) | 如何部署、监控、扩缩容、恢复和运营 Agent 平台 | 设计 control/data plane、SLO、worker、队列、rollout、DR、告警和 on-call 时 |
| [Provider Runtime Conformance Engineering](provider-runtime-conformance-engineering.md) | 如何验证 Provider Runtime 的跨 Provider 语义、适配器合规和发布门禁 | 设计 conformance suite、capability matrix、fixture/golden、录制回放或 Provider 发布检查时 |
| [Session Replay Engineering](session-replay-engineering.md) | 如何从 durable 事实、事件和快照重建、分支、审计和隔离重放 Session | 设计 time travel、fork/resume、crash recovery、forensics 或 deterministic replay 时 |
| [Security Operations Engineering](security-operations-engineering.md) | 如何把 Agent 安全控制、事件响应、取证和恢复做成运营系统 | 设计 SIEM、告警分级、containment、break-glass、供应链安全或安全值班时 |
| [Cost Governance Engineering](cost-governance-engineering.md) | 如何对 Token、Provider、Tool、Storage、Egress 和 Worker 成本进行预算、归因和治理 | 设计 usage ledger、price catalog、预算、chargeback、异常检测或成本门禁时 |
| [Provider Schema Evolution Engineering](provider-schema-evolution-engineering.md) | 如何演进 canonical/provider schema、迁移持久状态并控制兼容性 | 设计 schema registry、projection、dual-read/dual-write、drift、canary 或版本发布时 |
| [Durable Queue Engineering](durable-queue-engineering.md) | 如何可靠排队、租约、确认、重试、隔离和恢复 Agent 工作 | 设计 job/command/event queue、worker、DLQ、backpressure、outbox/inbox 或延迟任务时 |
| [Privacy Engineering](privacy-engineering.md) | 如何管理 Agent 数据的分类、目的、最小化、外发、保留、删除和主体控制 | 设计 PII/secret/regulated data、DSAR、DLP、驻留、删除证明或隐私指标时 |
| [Agent Product Engineering](agent-product-engineering.md) | 如何把 Kernel/Harness 能力转化为可理解、可恢复、可治理的产品体验 | 设计任务 UX、审批、流式、artifact、memory、渠道、通知、配额、反馈和发布时 |
| [Agent Memory Product Engineering](agent-memory-product-engineering.md) | 如何把 Memory 从底层存储提升为可查看、可确认、可编辑、可删除和可解释的用户产品 | 设计候选记忆、recall、scope、provenance、TTL、compaction flush、隐私和用户控制时 |
| [Workflow Orchestration Engineering](workflow-orchestration-engineering.md) | 如何把任务、工作流、步骤、队列、审批、补偿和恢复组织成 durable execution | 设计 DAG、并行、循环、checkpoint、replay、worker、partial success 或未知结果时 |
| [Provider Security Contract Engineering](provider-security-contract-engineering.md) | 如何把 Provider 的能力、信任、凭据、驻留、保留、外发和撤销约束编译为可验证契约 | 设计 provider egress、attestation、fallback safety、credential scope、安全协商或 adapter quarantine 时 |
| [Data Governance Engineering](data-governance-engineering.md) | 如何治理 Agent 全链路数据的 inventory、目的、lineage、质量、驻留、生命周期和主体控制 | 设计 data catalog、ownership、DLP、retention、删除、DSAR、数据副本或治理证明时 |
| [Agent Memory Governance Engineering](agent-memory-governance-engineering.md) | 如何把 Memory 的 purpose、scope、consent、provenance、外发、保留、删除和例外变成可执行治理 | 设计 memory policy profile、候选确认、recall/write gate、tombstone、DSAR、break-glass 或治理审计时 |
| [Agent Memory Privacy Operations Engineering](agent-memory-privacy-operations-engineering.md) | 如何把 Memory 的 inventory、分类、目的、最小化、外发、保留、删除、DSAR、驻留和隐私事件变成持续运营 | 设计 memory privacy case、DLP、provider/embedding/subagent/backup 副本、删除对账、隐私 SLO、通知或 break-glass 时 |
| [Workflow Versioning Engineering](workflow-versioning-engineering.md) | 如何让 Workflow Definition、Run Snapshot、Schema、Policy、Provider 和 Artifact 的演进可复现、可迁移、可回滚 | 设计版本 hash、兼容矩阵、long-running run、canary、migration、rollback 或版本隔离时 |
| [Provider Contract Testing Engineering](provider-contract-testing-engineering.md) | 如何用 provider-neutral contract、fixture、conformance、drift 和发布门禁验证 Provider Adapter 语义 | 设计跨 Provider 测试、stream/tool/structured output、record/replay、live smoke 或 quarantine 时 |
| [Data Quality Operations Engineering](data-quality-operations-engineering.md) | 如何把 Agent 数据质量变成有 owner、SLO、检测、隔离、修复、回填和事故恢复的运营系统 | 设计 data contract、freshness、completeness、drift、reconciliation、quarantine、backfill 或质量门禁时 |
| [Agent Memory Evaluation Engineering](agent-memory-evaluation-engineering.md) | 如何评测 memory candidate、写入、召回、编辑、删除、DSAR、隐私和用户控制的完整轨迹 | 设计 golden memory set、oracle、LLM judge、offline replay、shadow/canary、poisoning 测试或 memory release gate 时 |
| [Workflow Scheduling Engineering](workflow-scheduling-engineering.md) | 如何在 durable workflow truth、依赖、配额、容量、公平性和租约之间做可审计调度 | 设计 readiness、priority/fairness、tenant quota、backpressure、preemption、fencing、capacity planning 或 scheduler SLO 时 |
| [Workflow Capacity Engineering](workflow-capacity-engineering.md) | 如何把 workflow 的资源供给、配额、预留、突发、背压、成本、区域和恢复余量变成容量控制系统 | 设计 resource class、worker/pool/provider/model/tool/sandbox/artifact/queue capacity、Little 定律、autoscaling、shedding、DR 或容量发布门禁时 |
| [Provider Incident Response Engineering](provider-incident-response-engineering.md) | 如何检测、隔离、取证、恢复和复盘 Provider 事故，并把事故转成安全与契约门禁 | 设计 provider outage、capability drift、data exposure、traffic stop、credential revoke、egress stop 或 postmortem 时 |
| [Provider Recovery Engineering](provider-recovery-engineering.md) | 如何将 Provider 失败后的 retry、fallback、隔离、重放、区域切换、结算和恢复验证做成可审计闭环 | 设计 circuit/bulkhead、unknown outcome、queue replay、workflow checkpoint、artifact consistency、RTO/RPO、reconciliation 或 game day 时 |
| [Data Lineage Engineering](data-lineage-engineering.md) | 如何跟踪 Agent logical data object 的来源、转换、消费、影响、删除传播和驻留事实 | 设计 lineage graph、provenance、forward/backward impact、DSAR propagation、schema drift 或 lineage gate 时 |
| [Lineage Quality Engineering](lineage-quality-engineering.md) | 如何验证 lineage 的完整性、正确性、时效性、覆盖率、可信度和删除/驻留证据质量 | 设计 quality budget、edge validation、orphan/ambiguous/cyclic 检测、ground truth、backfill/rebuild、impact trust、quality incident 或 lineage SLO 时 |

## 阅读方式

不要按固定线性顺序加载全部文档。先通过 [`routes.json`](../routes.json) 选择当前任务的主文档，再按路由补充最多两篇资料；跨模块设计时才扩大范围。

实际实现通常从 Harness 开始装配，但设计时应先确定 Context、Prompt、Tool、State、Policy、Provider 和 Artifact 的契约，否则 Harness 容易退化成散乱的依赖容器。

## 工程边界

```text
Prompt      解释策略和任务
Context     选择模型工作集
Tool        暴露和执行外部能力
State       持久化运行事实
Policy      决定动作是否允许
Sandbox     强制限制实际副作用
Subagent    管理隔离的 child run
Event       传播、记录和回放事实
Artifact    管理大内容、版本、传输和交付
Provider    隔离模型 API、能力、流和计费
Routing     选择满足能力、策略和预算的 Provider/Deployment
Coding      面向代码库的发现、编辑和验证
Tenant      隔离身份、资源、配额和数据生命周期
Workspace   隔离代码、文件、分支和执行资源
Host        适配协议、事件交付和用户控制
Operations  运营部署、容量、SLO、恢复和事故响应
Conformance 验证 Provider Runtime 的跨 Provider 语义和发布合规
Replay      重建、分支、审计和隔离重放 Session
Security    运营安全控制、告警、取证和事故响应
Cost        预算、计量、归因、预测和成本治理
Schema      演进 canonical/provider schema 和持久状态兼容性
Queue       持久化排队、租约、确认、重试和恢复
Privacy     管理数据目的、最小化、外发、保留和主体控制
Product     将 Kernel/Harness 能力转化为产品任务和交付体验
Memory      管理用户可见的记忆候选、确认、召回、修订、删除和生命周期
Workflow    编排可版本化的任务、步骤、队列、审批、补偿和 durable execution
ProviderSec 将 Provider 安全声明、凭据、驻留、外发、fallback 和撤销编译为契约
DataGov     管理数据 inventory、目的、lineage、质量、驻留、生命周期和治理证明
MemoryGov   管理 memory purpose、scope、consent、provenance、外发、删除和治理例外
MemoryPrivacy 运营 memory inventory、分类、最小化、DLP、外发、保留、删除、DSAR、驻留和隐私事件
Versioning  管理 workflow definition、snapshot、兼容、迁移、发布和回滚
ContractTest 验证 Provider contract、adapter 语义、drift 和发布证据
DataQuality 运营数据质量 SLO、检测、隔离、修复、回填和事故恢复
MemoryEval  评测 memory 语义、治理、隐私、状态、用户控制和发布质量
Scheduling  调度 workflow readiness、依赖、公平、配额、容量、租约和恢复
Capacity    管理 workflow resource supply、reservation、burst、backlog、headroom、成本、区域和恢复容量
ProviderIR  响应 Provider outage、drift、暴露、隔离、取证、恢复和事故回归
Recovery    管理 Provider failure 后的隔离、重试、fallback、重放、failover、结算和恢复验证
Lineage     追踪数据对象来源、转换、消费、影响、驻留和删除传播
LineageQuality 验证 lineage completeness、correctness、freshness、coverage、confidence、删除证明和质量 SLO
Evaluation  验证结果、轨迹和副作用
EvalDataset 管理任务分布、case、真值、grader、统计、污染、split 和生命周期
Harness     装配并监督以上组件
```

这些边界不是绝对的模块拆分要求，但每个系统都应能回答：某条规则由谁解释、由谁强制、由谁记录、由谁评测。
