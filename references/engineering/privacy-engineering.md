# Agent Privacy Engineering 细粒度工程设计
> Privacy Engineering 不是“把日志脱敏”或“把 secret 从 prompt 删除”。它是围绕数据 inventory、分类、目的限制、最小化、主体同意、租户/用户/workspace/session/run scope、Provider egress、State/Memory/Artifact/Event/Trace 生命周期、加密、访问、删除、导出、DLP、驻留、事故响应和可验证指标建立的完整控制系统。 > > 本文只使用当前目录已有的参考架构、Agent Harness、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Provider Routing、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Production Operations、Security Operations、Cost Governance 与 Provider Runtime Conformance 文档中已经记录的本地调研结论；不依赖 README，不新增网络搜索结论。涉及 consent、legal basis、regulated data 或跨境要求时，本文只定义可配置的工程接口和证据边界，不代替组织法务判断。
## 目录
1. [设计目标与非目标](#设计目标与非目标)；[核心判断与职责边界](#核心判断与职责边界)；[Privacy Threat Model 与 Trust Boundary](#privacy-threat-model-与-trust-boundary)
• [Data Inventory 与 Classification](#data-inventory-与-classification)；[Purpose Limitation 与 Data Minimization](#purpose-limitation-与-data-minimization)；[Consent、Legal Basis 与 User Control](#consentlegal-basis-与-user-control)；[Scope、Ownership 与 Tenant Isolation](#scopeownership-与-tenant-isolation)；[Provider Egress、Residency 与 Routing](#provider-egressresidency-与-routing)；[Redaction、Tokenization 与 Pseudonymization](#redactiontokenization-与-pseudonymization)；[Secret、PII 与 Regulated Data](#secretpii-与-regulated-data)；[Memory、Context 与 Prompt 处理](#memorycontext-与-prompt-处理)；[Artifact、File 与 Workspace 处理](#artifactfile-与-workspace-处理)；[Session、Run、Event、Trace 与 Log 处理](#sessionruneventtrace-与-log-处理)；[Encryption 与 Key Lifecycle](#encryption-与-key-lifecycle)；[Access、Audit 与 Diagnostic](#accessaudit-与-diagnostic)
• [DLP、Scanning 与 Egress Enforcement](#dlpscanning-与-egress-enforcement)；[Model Training Opt-out 与 Provider Contract](#model-training-opt-out-与-provider-contract)；[Retention、TTL、Deletion、Export 与 DSAR](#retentionttldeleteexport-与-dsar)；[Cross-border 与 Data Residency](#cross-border-与-data-residency)；[Privacy Incident 与 Security Operations](#privacy-incident-与-security-operations)；[核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)；[生命周期与状态机](#生命周期与状态机)；[端到端决策流程](#端到端决策流程)；[与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)；[故障恢复与安全降级](#故障恢复与安全降级)；[可观测性、指标与报告](#可观测性指标与报告)；[测试策略与 Evaluation](#测试策略与-evaluation)
• [反模式与审查规则](#反模式与审查规则)；[实施清单](#实施清单)；[五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Privacy Runtime 必须能够：
- 建立覆盖输入、Context、Prompt、ModelRequest、ToolCall、ToolResult、Memory、Artifact、Session、Event、Trace、Log、Cache、Queue、Backup 和 Provider remote object 的 data inventory。；为每个数据对象记录来源、owner、tenant、scope、sensitivity、purpose、legal basis/consent reference、provider egress、retention、删除状态和派生关系。；让 `public | internal | confidential | secret | regulated` 成为跨模块共享的最小敏感度轴，同时允许组织扩展字段级分类。；在 Context 编译和 Provider 调用前完成 purpose limitation、最小化、redaction、tokenization、pseudonymization、region 和 retention 检查。；将 `tenant -> user -> workspace -> project -> session -> run -> turn -> attempt` scope 绑定到资源、缓存、队列、凭据、事件、artifact 和导出。；让 provider egress 只接收经 `EgressSnapshot` 允许的完整内容、摘要、脱敏 view、artifact reference 或拒绝结果。；让 Memory、Context、Artifact、Event、Trace 和 Log 使用不同的保存与访问视图，避免一份原文自动流向所有 sink。；提供密钥版本、加密上下文、轮换、撤销、key failure 和 crypto-shred 的可验证语义。；支持 retention、TTL、legal hold、删除、导出、DSAR/主体请求和删除证明，且不误删仍受 audit、recovery 或 legal hold 保护的事实。；让 DLP、secret/PII/regulated 扫描和 redaction 失败可以 fail-closed，并产生安全事件与恢复路径。；让 model training opt-out、provider retention、remote file 生命周期和跨境限制进入 provider/routing policy，而不是只写在隐私页面。；让 privacy incident 可以定位传播范围、冻结 egress、轮换 secret、隔离 artifact、保留证据并验证恢复。
- 通过 deterministic fixtures、synthetic secret、side-effect oracle、replay、fault injection 和 CI gates 验证真实数据边界。
### 非目标
本文不负责：
- 代替组织法务决定某个司法管辖区的法律依据、通知义务、保存期限或监管解释。；把 consent checkbox、隐私政策文字或模型拒答当作运行时隐私控制。；只对日志脱敏，却允许同一敏感数据进入 prompt、memory、artifact、trace、provider file API 或子 Agent。；用一个全局 `privacyMode` 布尔值代替 data class、purpose、scope、egress、retention 和 access decision。；把不可逆哈希、伪名或 tokenization 误称为匿名化；是否仍可关联由控制面和访问边界决定。；让 Provider adapter 自行选择跨区域 fallback、关闭 training、修改租户 policy 或决定删除外部副本。；把 Session/Event Store、ArtifactStore、AuditStore、Backup 和 Provider remote copy 当作同一个删除对象。；为了可观测性永久保存完整 prompt、hidden reasoning、原始 tool args、secret 或 regulated payload。；允许用户、模型、workspace 文件、MCP 描述或 plugin 自行扩大数据 scope 或 egress。；用平均质量、成本或可用性抵消一次 secret 泄漏、跨租户访问或未经允许的数据外发。
### 核心原则
```text
Privacy = inventory + classification + purpose + minimization
+ consent/legal-basis evidence + scope isolation
+ controlled egress + retention/deletion
+ encryption/access/audit + incident recovery
Prompt explains privacy policy.
Context selects a minimum work set.
Policy decides whether data may move.
Sandbox limits what execution can observe or affect.
State records what actually happened.
Provider Runtime sends only the frozen egress view.
Audit proves the decision without copying the payload.
```
## 核心判断与职责边界
### Privacy 的真实边界
Privacy Engineering 不等于：
- 日志中把邮箱替换成 `<EMAIL>`。；在 system prompt 写“不要泄露用户信息”。；给数据库表加 `tenant_id` 字段。；把文件放在不可猜的 URL 后面。；在 provider 控制台勾选一次“不训练”。；在删除 session 时删除一张 transcript 表。
Privacy Engineering 必须回答：
1. 系统知道哪些数据？；这些数据为什么被收集、为何此刻被处理？；哪个主体、哪个 scope、哪个目的允许使用？
• 哪些数据可以进入 Model Context 或 Provider？；哪些派生对象、缓存、日志、artifact、backup 和 remote copy 也必须受控？；如何证明某次 egress、access、redaction、delete 或 export 实际发生？；故障、断线、未知结果和 incident 后如何避免继续传播？
### 职责矩阵
| 组件 | 负责 | 不负责 |
|---|---|---|
| `DataInventory` | 数据项、来源、owner、分类、purpose 与 lineage | 决定模型措辞 |
| `ClassificationService` | sensitivity、PII、secret、regulated、字段标签 | 给任意数据自动授权 |
| `PurposePolicy` | 目的、legal basis、consent 状态、用途兼容性 | 代替法务解释 |
| `EgressEvaluator` | destination、provider、region、view、retention 与 redaction 决策 | 执行网络隔离 |
| `Redactor` | 脱敏、tokenization、pseudonymization、派生 view | 修改原始事实 |
| `DlpScanner` | secret/PII/regulated/恶意内容检测 | 直接执行工具 |
| `MemoryStore` | memory provenance、TTL、forget 与 recall | 绕过 privacy policy |
| `ArtifactStore` | blob、view、scan、scope、版本、删除与恢复 | 选择 prompt 内容 |
| `Session/Event Store` | durable semantic facts、CAS、replay、checkpoint | 保存全部原文的默认副本 |
| `AuditStore` | 最小治理事实、完整性、访问审计 | 替代 session transcript |
| `KeyManager` | key version、加密、轮换、撤销、恢复 | 将 key 值交给模型 |
| `Provider Runtime` | 按冻结 egress view 发送、记录 provider receipt | 自行决定数据能否外发 |
| `Policy/Sandbox` | 强制 scope、动作、文件、网络、进程边界 | 定义完整隐私政策文字 |
| `Harness` | 装配、快照、监督、取消、恢复和交付 | 成为全局隐私数据库 |
| `Host Adapter` | 展示隐私状态、同意、导出、删除与审批 | 直接读取原始敏感 payload |
| `Security Operations` | incident、containment、取证、轮换、告警 | 无审计手工改状态 |
| `Evaluation` | privacy assertions、negative oracle、回归门禁 | 使用真实生产 secret |
### Privacy 与 Security 的边界
- Security 重点是防止未授权动作、越权执行和资产被破坏。；Privacy 还要控制“已被授权的处理是否超出目的、范围、保存期限或外发边界”。；一个动作可以通过 security policy，却因 purpose、consent、residency 或 retention 不合规而被 privacy deny。；`allow` 不代表允许保存原文；可能只允许 `artifact_only`、`summary` 或短 TTL。；`redacted` 不代表可以进入所有 sink；目标、purpose 和 retention 仍需重新评估。
## Privacy Threat Model 与 Trust Boundary
### 信任区域
沿用 Security Operations 的区域模型：
```text
Z0 Public/Untrusted
用户输入、网页、issue、源码注释、检索文本、模型输出、工具结果
Z1 Workspace
项目文件、规则文件、package scripts、hooks、插件声明、MCP/LSP metadata
Z2 Run
Prompt、Context、Tool、State、Policy、Harness、working state
Z3 Credential/Security
Key registry、secret broker、AuditStore、SIEM、incident controls
Z4 External
Provider、MCP、HTTP、数据库、消息、远程 worker、channel
```
隐私不变量：
- Z0 数据不能把自己提升为 Z2 policy 或 privacy authority。；Z1 未信任 workspace 不得通过 hooks、MCP、plugin、env loader 获取 Z3 数据。；Z2 只能访问当前 `ScopeRef` 与 `EgressSnapshot` 允许的 view。；Z3 的 secret、redaction map、legal hold 和原始 audit payload 不进入普通 model context。；Z4 返回内容必须重新做 scope、classification、purpose 和 egress 检查。
### 资产
- 用户 prompt、文件、附件、代码、日志、测试输出、模型 response 和 memory。；PII、secret、credential、regulated data、客户资料、身份、组织成员关系。；Session、branch、run、attempt、tool call、approval、artifact、event、trace 和 backup。；Provider request、remote file、provider-side conversation、embedding、rerank 和 cache。；删除/导出请求、同意记录、legal basis、retention hold、key material 和 forensic bundle。；计费、成本、usage、IP/设备标识、channel identity 和 support ticket。
### 攻击与隐私失败路径
- prompt injection 要求读取 `.env`、历史 session、其他租户 artifact 或发送新 URL。；模型参数伪造 tenant、user、workspace、purpose、consent 或“用户已批准”。；workspace 中的文档、注释、MCP schema、OCR 或测试日志包含外发指令。；Context Compiler 把高相似度 memory、旧 session 或其他 branch 注入当前 run。；Provider fallback 跨 region、跨 jurisdiction 或跨 provider 发送 confidential/regulated 内容。；redaction 只处理 stdout，遗漏 prompt、artifact preview、trace attribute、error details 或 remote upload。；tokenization map 进入 provider、日志或子 Agent，导致反向恢复。；cache、queue、event projector、artifact URI、backup 或诊断快照缺少 tenant/scope。；删除只清理主表，残留 embedding、preview、raw upload、backup、provider remote object 或 export package。；运行中 consent、membership、purpose、policy 或 key rotation 变化，但旧 snapshot 继续发送。；宕机后把 provider upload unknown 当失败，重复外发敏感数据。；incident 期间为恢复可用性而关闭 audit、egress、sandbox 或 deletion hold。
### 保护目标
```text
data discovery completeness
purpose correctness
minimum necessary disclosure
scope/tenant isolation
provider egress correctness
retention and deletion verifiability
secret/PII/regulated leakage = 0
privacy decision auditability
unknown outcome non-propagation
```
## Data Inventory 与 Classification
### Inventory 原则
Data inventory 不是静态表格，而是随着 Harness 生命周期更新的资源图：
```text
source -> classification -> purpose -> transformation
-> destination/view -> retention -> references -> deletion state
```
必须覆盖：
- Host 输入、附件、channel metadata 和 control command。；`PromptSection`、`ContextResource`、`ContextPlan`、`ModelRequest` 和 provider raw request。；`Message/Part`、ToolCall、ToolResult、approval、policy、sandbox attestation。；Session semantic entries、WorkingState、Checkpoint、CompactionEntry 和 MemoryRecord。；Artifact raw/sanitized/preview/summary/structured/range views。；Event envelope、durable event、ephemeral event、trace、log、metric、audit、SIEM。；Provider remote object、remote file、request/response receipt、cache、embedding、rerank。；Temp、workspace snapshot、patch、command output、backup、export package 和 forensic bundle。
### DataRecord
每条 inventory 记录至少包含：
- `dataId`、logical type、sourceRef、contentHash 或 keyed hash。；owner、tenant、workspace、session、run、subagent 和 scope version。；sensitivity、field classifications、PII/secret/regulated tags。；purpose、legal basis reference、consent reference、consent status。；allowed destinations、provider/region、view、redaction profile。；retention class、TTL、legal hold、deletion dependencies。；encryption context、key version、access policy、audit class。；parent/derived refs、transform version、scanner version、lineage。；current state、last access、last export、last delete attempt。
### Classification 轴
```text
sensitivity: public | internal | confidential | secret | regulated
content tags: pii | credential | financial | health | location | source_code | customer_data | biometric | child_data | legal_hold
provenance: user | model | tool | file | retrieval | human_review | system | provider
authority: highest | high | scoped | data | none
```
`authority` 与 `sensitivity` 分开：
- 一个 public 文档可以是低 authority 的不可信数据。；一个 internal policy 可以是高 authority，但仍不能外发到未允许 provider。；model inferred memory 的 authority 不等于 user direct claim。；provider metadata 不得覆盖 server-side tenant、purpose 或 consent。
### 分类失败
分类无法确定时：
- 不得自动归为 public 或 low risk。；对 Provider egress 采用更高敏感度或 `deny`。；对模型 context 采用 `artifact_only`、summary 或 hold。；产生 `classification_unknown` diagnostic 和必要 audit event。；若数据可能是 secret/regulated，触发安全扫描和 privacy review。
## Purpose Limitation 与 Data Minimization
### PurposePolicy
每次处理都必须说明：
```text
who: principal/agent/worker
what: data classes and views
why: declared purpose
where: provider/tool/host/audit destination
how long: retention/TTL
under which basis: consent or legal-basis reference
```
常见 purpose：
- `task_execution`：完成当前用户任务。；`tool_execution`：向工具提供最小必要参数。；`model_inference`：一次 provider/model 调用。；`memory_recall`：为当前任务召回相关 memory。；`memory_persistence`：写入未来可复用 memory。；`safety_detection`：DLP、secret、PII、abuse 和 prompt injection 检测。；`audit`：证明治理事实。；`support_diagnostic`：受控故障诊断。；`evaluation`：脱敏后的离线/在线评测。；`billing`：usage/cost、预算、对账和 chargeback。；`export`、`delete`、`recovery`、`incident_forensics`：生命周期或事件处置。
### Purpose 规则
- 当前 task 的 purpose 不自动授权长期 memory、训练、营销、跨 session 分享或 provider reuse。；`audit` purpose 不等于允许保存完整原文；默认使用 hash、类型、大小、状态和 decision evidence。；`support_diagnostic` 必须有短 TTL、访问审计和最小字段。；`evaluation` 需要脱敏、去重、最小复现和 dataset provenance。；purpose 改变时重新执行 classification、consent/legal basis、egress 和 retention。；derived view 不能继承比 source 更宽的 purpose，除非新 purpose 有独立授权。
### Minimization 算法
```text
identify required fields
-> drop unrelated fields
-> select smallest range/part
-> choose summary/structured view
-> redact/tokenize/pseudonymize
-> enforce byte/token budget
-> issue short-lived reference
-> audit the transformation
```
最小化优先级：
1. 不收集。；不持久化。；只保留 hash/metadata。
• 只保留脱敏 view。；只保留 summary/range。；只在可信边界保留 raw。；full raw 需要明确 scope、purpose、retention 和访问控制。
## Consent、Legal Basis 与 User Control
### 工程定位
Consent 和 legal basis 是控制面输入，不由模型推断，也不由 UI 的一次点击直接覆盖全部 scope。组织应将法律判断转换为版本化 policy/config；工程系统负责记录：
- 谁在什么时间、针对什么 purpose、什么 data class 做了什么决定。；同意是否明确、可撤回、是否过期、是否限定 provider/region/feature。；当前 processing 是否仍符合 purpose、scope、retention 和 egress。；撤回后新 run、后台任务、memory write、export 和 provider upload 如何停止或清理。
### ConsentRecord
建议字段：
- `consentId`、tenant/user/principal、purpose、dataClasses、destinations。；scope：organization、tenant、user、workspace、session、run。；basis kind：`consent | contract | legitimate_interest | legal_obligation | configured_policy | unknown`。；version、locale、notice reference、capturedAt、expiresAt、withdrawnAt。；evidence hash、host proof、auth assurance、withdrawal reason。；allowed transformations、provider training opt-out、residency constraints。
`legal_basis` 取值应由组织 policy 定义，不能在 agent prompt 中自由生成。
### 交互规则
- 低风险、明确用途的处理可以由已有 policy 自动 allow，但必须有可解释的 basis reference。；新的 provider、purpose、data class、跨境 destination 或长期 memory 应触发 ask 或 policy deny。；Host 无法展示必要 notice 或接收撤回时，不得把交互当作有效 consent。；approval 是具体动作的授权；consent 是处理 purpose/范围的治理依据，两者不能混用。；用户拒绝某次 tool call 不自动撤回整个 session 的 processing consent。；consent withdrawal 不应让系统伪造历史事实已不存在；需要按 retention/deletion policy 处理。
### User Controls
产品应提供可操作的：
- 查看当前 session/run 的数据处理摘要。；查看 provider、region、model、目的、保存期限和是否发送附件。；禁止长期 memory、关闭特定 memory type、删除单条 memory。；查看和删除 artifact、export package、session branch、background task。；请求数据导出、撤回 consent、停止后台任务、取消 provider upload。；查看 redaction/tokenization 是否发生以及不能反向恢复的说明。；在 Host 支持范围内进行 approval、steering、cancel、resume 和 re-auth。
## Scope、Ownership 与 Tenant Isolation
### Scope 层级
```text
Tenant -> User -> Workspace -> Project -> Session -> Branch
-> Run -> Turn -> Attempt -> ToolExecution/Subagent
```
数据对象默认取最窄 scope：
- user input：session/run，除非明确允许 workspace 或 tenant 复用。；working memory：run/turn；semantic memory：user/workspace/project，需写入门槛。；artifact：run/subagent 或 workspace；跨 session 需显式 share/copy。；trace：run/attempt；audit：tenant + retention class。；provider cache：默认 tenant + policy + resource hash，不跨 tenant 共享。；tokenization map：可信 security scope，不进入普通 session 或 provider。
### ScopeGuard
所有 port 都必须接收 `ScopeRef`，实现侧再次检查 owner：
- `SessionRepository.load/append` 检查 tenant、workspace、branch owner。；`ArtifactStore.get/delete/export` 检查 tenant、owner、purpose、view、range、expiry。；`MemoryStore.recall/write/forget` 检查 scope、sensitivity、consent 和 retention。；`EventStore.read/replay/subscribe` 在 query 与 cursor 层重新授权。；`Queue.lease/complete` 检查 worker、tenant、run、fencing token。；`Cache.get/set` key 必须包含 tenant、scope hash、policy version 和 resource hash。；`Provider Runtime` 消费不可变 `TenantRoutingSnapshot` 和 `EgressSnapshot`。
跨租户失败应返回稳定的 `resource_not_available` 或 `scope_denied`，避免泄露资源存在性；同时写安全审计。
## Provider Egress、Residency 与 Routing
### Egress 决策
```text
resource inventory
-> sensitivity and purpose
-> consent/legal-basis check
-> tenant/workspace policy
-> provider/api family/model/deployment
-> jurisdiction/region/residency
-> retention/training/file semantics
-> redaction/tokenization/pseudonymization
-> allow full | redact | summarize | artifact_only | deny
```
### EgressSnapshot
必须冻结：
- tenant、workspace、session、run、purpose、policy version。；allowed providers/API families/models/deployments/regions。；denied regions、provider jurisdiction 和 residency profile。；allowed data classes、artifact-only classes、redaction profile。；provider retention、remote file retention、training opt-out 状态。；max bytes/tokens、consent reference、legal basis reference。；decision IDs、createdAt、expiresAt、snapshot hash。
### Routing 集成
Routing 只能在 Policy 给出的 candidate boundary 内选择：
- confidential/regulated 数据不因 primary 故障自动跨区域 fallback。；fallback 重新执行 capability、egress、residency、purpose、retention 和 budget 检查。；sticky route 失效于 policy、consent、credential、region、classification 或 model capability 变化。；hedge 默认不适用于敏感数据的重复外发；若允许，必须重新 reserve、审计和计量。；shadow 只能使用 sanitized fixture、summary 或 artifact reference，并禁用真实副作用。；route explanation 对 user/operator/audit 使用不同脱敏等级。
### Provider remote object
Provider-side file、conversation、cache 或 batch job 都是独立 data inventory 对象：
- 保存 provider、api family、remote ID、upload time、expiry、purpose、view、hash。；记录是否支持 remote delete、是否可查询状态、是否可复用。；provider 请求失败后不能盲目重复上传敏感内容。；provider 不支持删除时缩短本地 egress/retention、标记 limitation 并告知 owner。；provider response、metadata、safety 和 usage 不得覆盖本地 scope 或 privacy decision。
## Redaction、Tokenization 与 Pseudonymization
### 三种变换
- `redaction`：删除或替换敏感值，目标是降低 destination 可见性。；`tokenization`：使用受控 token 代替值，token vault 保存映射，适合可信边界内回写。；`pseudonymization`：用稳定伪名保持关联分析，仍可能可再识别，必须保留 owner、key、purpose 和 access controls。
它们都不是匿名化的自动证明。
### RedactionPipeline
```text
classify source
-> detect secret/PII/regulated
-> apply field/profile rules
-> replace/tokenize/pseudonymize/drop
-> validate forbidden-field absence
-> compute derived hash and lineage
-> route by sink clearance
-> audit decision and scanner version
```
### RedactionMap
- 只在 Z3 或等价可信边界保存。；使用 purpose、scope、expiry、key version 和 approver 绑定。；不进入 Model Context、provider raw request、普通 log、trace、artifact preview 或 ChildResult。；回写时只对明确字段、明确版本和可信内部结果做反替换。；模型生成的新文本不能自动触发反替换。；map 丢失时宁可保留占位符，不尝试模糊恢复。
### 失败策略
- DLP/Redactor 不可用：敏感 egress `deny` 或 `artifact_only`。；结果包含未预期 secret：阻断 host/provider 外发，标记 artifact restricted，触发 incident signal。；redaction 后结构化 schema 不再有效：返回 typed `redaction_changed_schema`，不伪造完整结果。；pseudonym collision 或 map version mismatch：停止回写，保留原始可信 artifact 引用。
## Secret、PII 与 Regulated Data
### Secret
Secret 包括 API key、bearer token、cookie、SSH key、环境变量、签名材料、provider remote reference 和可直接访问资源的短期 lease。
- 模型永远不应需要 secret 原文。；Tool/Provider 通过 `SecretBinding`、brokered request 或 `CredentialLease` 使用。；secret 绑定 tenant、principal、tool/provider、destination、purpose、expiry 和 key version。；secret 不进入 prompt、arguments、argv、event、progress、trace、artifact summary 或普通 error。；泄漏检测后阻断 egress、撤销 lease、轮换 key、查询传播范围并建立 incident。
### PII
PII 检测不只看 email/phone：
- 直接标识符、账号、地址、位置、设备标识、channel identity。；客户 ID、订单 ID、文件路径、代码注释中嵌入的个人信息。；图片 EXIF/GPS、OCR、音频转写和文档元数据。；通过组合字段可重新识别的 quasi-identifiers。
PII 可在任务需要时进入最小 context，但仍需 purpose、scope、provider、retention 和 view 控制。
### Regulated Data
对 regulated data 采用保守默认：
- 专门 `Sensitivity`/field tag 与 provider/region allowlist。；默认不进长期 memory、普通 trace、公共 artifact 或非专用 provider。；需要更强的 consent/legal-basis reference、访问审计和 deletion contract。；处理失败、classification unknown、region unknown 或 audit sink unavailable 时 fail-closed。；export、support diagnostic、evaluation 和 shadow 必须单独审批或 deny。
## Memory、Context 与 Prompt 处理
### Memory
Memory 是 Context 的一个来源，不是自动保存的聊天副本。写入长期 memory 必须同时满足：
- 未来复用价值；相对稳定；来源可验证。；scope、purpose、consent/legal basis 允许。；sensitivity 不超过长期 memory ceiling。；有 provenance、confidence、TTL、lastVerifiedAt 和 delete path。；无 unresolved contradiction；用户可以查看、删除或关闭相应 memory type。
默认策略：
- secret、regulated 和高风险 PII 不写长期 memory。；model inferred 内容只作为 candidate，不直接变 active fact。；compaction 前 memory flush 只提取允许持久化的候选。；forget 后从 recall index、cache、embedding、derived view 和 ContextPlan 彻底排除。
### Context
`ContextCompiler` 在排序前做 privacy 过滤：
```text
candidate resources
-> tenant/scope ownership
-> purpose/legal basis
-> sensitivity ceiling
-> provider egress/residency
-> consent/training/retention constraints
-> redaction or view derivation
-> relevance/freshness/authority scoring
-> token/byte budget
```
ContextPlan 必须记录：
- selected、summarized、offloaded、dropped resources。；data class、purpose、provider target、redaction profile、view hash。；token/byte budget、source version、TTL、diagnostics。；未选择或被拒绝的原因，但不要在低信任 sink 暴露原始资源存在性。
### Prompt
Prompt 负责解释：
- 当前 privacy mode、可见数据范围、外部内容的 authority 限制。；当前工具、provider、artifact view 和 redaction 状态。；何时需要用户确认、为何不能读取或外发某数据。；大输出仅收到摘要、range 或 ref，不能假装看到了全文。
Prompt 不负责：
- 权限、tenant ownership、目的限制、DLP、TTL、删除或训练 opt-out enforcement。；让模型决定是否可把 consent、legal basis、tenant 或 region 传给工具。；隐藏 policy deny 的执行边界。
## Artifact、File 与 Workspace 处理
### Artifact views
同一 artifact 需要区分：
```text
raw -> sanitized -> structured -> summary -> preview -> range -> model_ref -> user_download
```
每个 view 有独立：
- `viewId`、contentHash、sensitivity、purpose、scope、retention、expiresAt。；parent ref、transform version、scanner/redactor version。；provider/host target、授权 decision、审计引用。
### Workspace
- 只把当前 `WorkspaceView` 中、当前 purpose 必需的路径加入 Context。；`.env`、SSH、cloud config、浏览器 profile、无关 home 和设备文件默认 deny。；文件路径在模型可见时相对化或 hash 化；完整 canonical path 只在可信 operator view 使用。；snapshot、patch、diff、command log 和测试 artifact 要执行 sensitivity/retention。；用户已有修改、generated/vendor、未知 owner 不能因脱敏而被覆盖。；workspace 删除、移动、trust revoke 或 root identity 变化使相关 view/cache/approval 失效。
### Artifact deletion
删除 artifact 前检查：
- session entry、checkpoint、patch、child result、audit、legal hold、active transfer。；provider remote binding、preview、embedding、cache、backup 和 export package。；是否存在 unknown recovery 或 incident forensic hold。
删除可产生 tombstone、deletion receipt 和最小 hash，但不应把可恢复 raw payload 保留在普通日志。
## Session、Run、Event、Trace 与 Log 处理
### Session/Run
- Session 保存语义历史和 privacy metadata，不等于 provider message 数组。；Run 保存 frozen config、policy、egress、toolset、model、purpose、budget、consent snapshot。；Attempt 记录 provider/model/API family、request hash、usage、egress view 和 failure。；CompactionEntry 必须保留 privacy-critical state：pending approval、unknown outcome、retention hold、incident signal、data deletion request。；Resume 时重新验证 membership、consent、purpose、policy、egress、key version 和 retention；过期 snapshot 不直接继续。
### Event
Durable privacy facts：
- `data.classified`、`purpose.evaluated`、`consent.checked`、`egress.decided`。；`redaction.applied`、`tokenization.created`、`provider.uploaded`、`provider.deleted`。；`memory.created/forgotten`、`artifact.shared/deleted`、`export.requested/completed`。；`retention.expired`、`deletion.requested/completed/blocked`、`privacy.incident`。；policy、scope、key、training opt-out、residency 和 provider route 变化。
Ephemeral 默认不永久保存：
- token/text delta、spinner、心跳、短期 queue progress。
### Trace/Log
默认 metadata-only：
- ID/hash、类型、大小、状态、provider/model/API family、latency、usage、cost、error code。；sensitivity、redaction state、policy/egress version、artifact ref、decision IDs。；不记录完整 prompt、hidden reasoning、原始工具参数、secret、regulated 原文或未脱敏文件。
高信任 diagnostic 也必须：
- 短 TTL、重新授权、访问审计。；使用安全 artifact reference，不复制完整内容到 log。；展示相对路径、字段计数、hash 和脱敏摘要。
## Encryption 与 Key Lifecycle
### 加密层级
- Transport：TLS、受控代理或 cloud signer。；Store：session/event/artifact/memory/audit 分层 at-rest encryption。；Field：secret、regulated payload、consent evidence、tokenization map、敏感配置。；Artifact：对象级或 tenant-prefix key，并把 scope/purpose 绑定到 AAD。；Backup/export/forensic：独立 key class、短 TTL、访问审计和 integrity hash。
### EncryptionContext
```typescript
interface EncryptionContext {
tenantId: string;
purpose: "session" | "artifact" | "memory" | "audit" | "credential" | "export" | "forensics";
keyVersion: string;
associatedData: string[];
}
```
AAD 至少绑定 tenant、scope、resource ID/version、purpose 和 schema/version；不匹配时拒绝解密。
### Key 状态机
```text
planned -> generated -> staged -> active -> rotating -> overlap
active -> revoked | expired
rotating -> verified -> retired
```
轮换流程：
1. 创建新 key version，验证 tenant/purpose/AAD。；新写入使用新 key；旧数据按 retention/hold 分批重加密。；校验 hash、projection、owner、scope 和 deletion dependencies。
• 短期 overlap 只允许受控读取，不扩大权限。；revoke 旧 lease、失效 cache、通知 worker/provider/runtime。；删除旧 key 前确认数据已迁移、删除或 legal hold 有明确解释。；记录 rotation audit 和失败/恢复状态。
Key broker 不可用时：
- 禁止打印、缓存或使用过期 key。；无敏感数据的只读任务可在明确 policy 下继续。；新的高风险、regulated、provider egress 和 export 默认暂停。
## Access、Audit 与 Diagnostic
### Access decision
任何 read、derive、share、export、delete、replay、support、forensics 操作都要检查：
- principal、tenant、scope、purpose、data class、view/range。；consent/legal basis、policy version、retention/hold、provider/host destination。；artifact/session owner、key version、expiry、approval 或 break-glass。；当前 run/incident 是否仍 active，是否存在 deletion freeze。
### AuditEvent
最小字段：
- actor、tenant、workspace、session、run、resource hash、purpose。；action、decision、policy/egress/consent/legal-basis version。；view、range、provider/region、redaction/tokenization state。；outcome、unknown state、receipt、source/causation event、evidence refs。；occurredAt、observedAt、retention class、integrity/hash chain。
审计不保存完整 payload 作为默认事实；需要原文时引用受控 artifact，并记录访问目的和 expiry。
### Diagnostic Snapshot
默认显示：
- run/session hash、scope、active policy/egress/purpose/consent version。；selected context resource IDs/hashes、dropped/offloaded counts、redaction profile。；provider/model/region、remote file binding、retention、pending deletion/approval。；key version class、DLP findings count、queue/projector/artifact state。；recent error codes、unknown outcome、incident ID、recovery cursor。
不显示：
- secret、tokenization map、完整 prompt、原始 PII/regulated payload、未授权 artifact。
## DLP、Scanning 与 Egress Enforcement
### DLP Pipeline
```text
ingest
-> size/decompression limits
-> MIME/magic/schema validation
-> secret detector
-> PII/regulated detector
-> prompt-injection diagnostic
-> purpose/scope/retention classification
-> redaction/tokenization/pseudonymization
-> forbidden-field validation
-> egress decision
-> durable scan/result event
```
扫描对象包括：
- user message、attachment、ContextResource、tool result、artifact、command output。；provider response、remote file、MCP result、plugin log、OCR/transcript。；trace/log/error/diagnostic/forensic/export package。
### DlpFinding
记录：
- detector、version、code、severity、range/field、source hash。；action：`allow | redact | tokenize | restrict | quarantine | deny`。；false-positive review、reviewer、expiry、derived ref。；不在普通日志复制发现的原始 secret/PII。
### Egress enforcement
- Egress 必须在可信边界执行，不能只在 Host 侧显示“已脱敏”。；Transform 后重新扫描，防止 base64、压缩、嵌套 JSON、URL、Unicode 或 artifact ref 绕过。；`artifact_only` 不等于把 raw artifact URL 给 provider；只允许授权的 summary/view/ref。；DLP sink 不可用时，敏感数据不离开当前 trust boundary。；egress decision 与 provider request hash、context hash、view hash 绑定，防止批准 A、发送 B。
## Model Training Opt-out 与 Provider Contract
### 控制面模型
Training opt-out 是 provider/data contract 的一部分：
- 记录 tenant、provider、API family、deployment、purpose、policy version。；区分 inference processing、provider retention、remote file retention、service improvement/training opt-out。；对无法证明当前 deployment 遵守要求的候选执行 `deny` 或选择合规替代。；fallback、shadow、canary、embedding、rerank、compaction 和 evaluation 重新检查，不自动继承 primary 的结论。；provider capability/catalog stale 时，不把 opt-out 状态当作已满足。
### ProviderTrainingPolicy
建议字段：
- `provider`、`apiFamily`、deployment/region、contractVersion。；`trainingOptOut: required | allowed | unknown | prohibited`。；`retentionClass`、remote deletion support、file reuse scope。；evidence source/version、verifiedAt、expiresAt、owner。；applicable data classes、purpose、consent/basis constraints。
Provider adapter 只消费 `ProviderEgressSnapshot`；不能自行声称“不会训练”。
## Retention、TTL、Deletion、Export 与 DSAR
### Retention 类别
```text
never_persist
until_turn_end
until_run_end
until_task_end
until_session_end
ttl
until_referenced
legal_hold
incident_hold
```
Retention 必须按 purpose、sensitivity、scope、provider、artifact view 和 legal hold 计算；低层配置不能突破组织/tenant safety floor。
### 删除流程
```text
request -> authenticate/authorize -> basis/hold check
-> freeze new processing -> enumerate dependency graph
-> cancel/settle jobs -> revoke egress/credentials
-> delete or derive safe tombstones
-> invalidate cache/index/projection
-> handle provider remote copies
-> verify absence/residuals
-> emit deletion receipt
```
删除对象包括：
- session entries、branches、memory、embeddings、retrieval index。；artifact raw/views/previews、workspace temp、export package。；event projections、cache、trace/log、backup/replica（按各自 contract）。；provider remote file/conversation/batch（可控时删除，不能控时记录 limitation）。
删除注意：
- audit、legal hold、incident evidence 和 deletion proof 可能保留最小 tombstone。；unknown side effect 不能因为删除请求就被伪造为 cancelled。；删除期间新 read/export 默认 deny 或返回 deleting 状态。；GC 失败不能把资源标成 deleted；必须保留 failed cleanup 和 reaper lease。
### Export/DSAR
导出必须生成：
- scope、manifest、resource types、versions、hashes、sensitivity 和 redaction state。；session/branch/run entries、memory、artifact refs/views、audit access facts（按 policy）。；provider egress/remote binding/deletion limitation、consent/legal-basis records。；export package 自身的 owner、short TTL、encryption、download audit 和 deletion state。
DSAR/主体请求处理可拆为：
- access：返回可读且最小化的 data view。；portability：使用结构化、版本化、可校验格式。；correction：追加修订 entry，不覆盖事实日志。；deletion：执行依赖图清理、tombstone 和 proof。；objection/withdrawal：阻止新 purpose processing，按 policy 处理历史保留。
## Cross-border 与 Data Residency
### Residency 约束
Residency 不只看 provider 名称；必须同时考虑：
- provider jurisdiction、API family、deployment、region/location、project/account。；remote file、prompt cache、server-side conversation、backup 和 support diagnostic。；artifact/trace/log/export/backup 的存储区域与复制路径。；fallback、hedging、shadow、embedding、rerank、MCP、remote worker 和 channel。；数据分类、purpose、retention、consent/legal basis 和 deletion support。
### 决策
```text
data class + purpose + tenant policy
-> candidate provider/deployment/region
-> remote retention/training contract
-> egress/redaction/view capability
-> residency-compatible route or deny
```
不能：
- 因为 region 不可用而静默跨境。；把日志/trace/backup 视为“非生产数据”而忽略驻留。；用远程 URL 让 provider 自己拉取未审查内容。；让 child、worker、MCP 或 plugin 通过另一网络路径绕过 region policy。
## Privacy Incident 与 Security Operations
### 触发信号
- secret/PII/regulated 内容出现在错误 sink、prompt、trace、artifact、provider request 或 child context。；cross-tenant session/artifact/memory/cache/replay 命中。；provider route、region、training opt-out、remote retention 与 policy 不一致。；deletion/export/retention 失败、残留、复活或范围不完整。；tokenization map、key、backup、forensic bundle 被错误访问。；DLP/redaction 失败、audit gap、provider upload unknown 重复外发。
### PrivacyIncident
至少包含：
- incidentId、severity、affected scope、data classes、purpose、destinations。；source event IDs、provider/request/remote object refs、时间窗和传播范围。；containment、credential revoke、route pause、artifact quarantine、worker/session freeze。；evidence refs、redaction state、legal hold、通知/沟通状态。；eradication、recovery、validation、residual risk、owner 和 review。
### Containment 顺序
1. 停止受影响 provider route、tool、MCP、plugin、export 和 background jobs。；阻断敏感 egress，切换 read-only/metadata-only/quarantine。；撤销 credential lease、approval、remote upload binding 和 worker lease。
• 隔离 workspace、artifact、cache、trace、forensic bundle，保留 hashes/receipts。；查询传播范围、provider status、artifact refs、logs、event cursors 和 cache keys。；不盲目重试或删除证据；unknown side effect 进入人工/状态查询。；修复后以最小 fixture、synthetic secret 和 canary 验证，再逐步恢复。
### Break-glass
- 仅为 containment、recovery、forensics 使用。；绑定 incident、tenant、resource、purpose、command、TTL、双人审批和证据要求。；默认 metadata-only/read-only；禁止扩大 provider egress 或读取无关 tenant。；使用后立即 revoke，查询所有访问并保留 audit。
## 核心数据模型与 TypeScript 接口
### 基础类型
```typescript
type Sensitivity = "public" | "internal" | "confidential" | "secret" | "regulated";
type PrivacyPurpose =
| "task_execution" | "tool_execution" | "model_inference"
| "memory_recall" | "memory_persistence" | "safety_detection"
| "audit" | "support_diagnostic" | "evaluation" | "billing"
| "export" | "delete" | "recovery" | "incident_forensics";
type EgressAction = "allow_full" | "allow_redacted" | "allow_summary" | "artifact_only" | "deny";
type PrivacyState = "unknown" | "classified" | "approved" | "restricted" | "quarantined" | "expired" | "deleting" | "deleted";
```
### ScopeRef 与 DataInventoryRecord
```typescript
interface PrivacyScopeRef {
tenantId: string;
userId?: string;
workspaceId?: string;
projectId?: string;
sessionId?: string;
branchId?: string;
runId?: string;
turnId?: string;
subagentRunId?: string;
scopeVersion: number;
}
interface DataInventoryRecord {
dataId: string;
logicalType: string;
source: ResourceRef;
scope: PrivacyScopeRef;
owner: PrincipalRef;
sensitivity: Sensitivity;
tags: string[];
provenance: Provenance;
purposes: PrivacyPurpose[];
legalBasisRef?: string;
consentRef?: string;
retention: RetentionPolicy;
encryption: EncryptionContext;
derivedFrom?: string[];
viewRefs: string[];
status: PrivacyState;
contentHash?: string;
createdAt: string;
expiresAt?: string;
}
```
### Purpose 与 Consent
```typescript
interface PurposeEvaluation {
purpose: PrivacyPurpose;
dataIds: string[];
destination?: EgressDestination;
decision: "allow" | "ask" | "deny" | "transform";
legalBasisRef?: string;
consentRef?: string;
policyVersion: string;
reasons: string[];
expiresAt?: string;
}
interface ConsentRecord {
consentId: string;
tenantId: string;
principalId: string;
purpose: PrivacyPurpose;
dataClasses: Sensitivity[];
destinations: string[];
scope: PrivacyScopeRef;
basis: "consent" | "contract" | "legitimate_interest" | "legal_obligation" | "configured_policy" | "unknown";
version: string;
capturedAt: string;
expiresAt?: string;
withdrawnAt?: string;
evidenceHash: string;
trainingOptOut?: boolean;
}
```
### Egress 与 Redaction
```typescript
interface EgressSnapshot {
snapshotId: string;
tenantId: string;
runId: string;
purpose: PrivacyPurpose;
allowedProviders: string[];
allowedApiFamilies: string[];
allowedDeployments?: string[];
allowedRegions: string[];
deniedRegions: string[];
allowedDataClasses: Sensitivity[];
artifactOnlyClasses: Sensitivity[];
redactionProfile: string;
providerRetentionClass: string;
trainingOptOut: "required" | "allowed" | "unknown" | "prohibited";
policyVersion: string;
consentRef?: string;
legalBasisRef?: string;
hash: string;
expiresAt: string;
}
interface RedactionProfile {
id: string;
version: string;
fields: string[];
detectors: string[];
replacement: "placeholder" | "keyed_hash" | "token" | "drop";
preserveMap: boolean;
reversibleInsideTrustedBoundary: boolean;
}
interface RedactionReceipt {
sourceDataId: string;
derivedDataId: string;
profileId: string;
sourceHash: string;
derivedHash: string;
findings: string[];
mapRef?: ArtifactRef;
performedAt: string;
}
```
### Privacy Decision
```typescript
interface PrivacyDecision {
decisionId: string;
action: EgressAction | "retain" | "delete" | "export" | "memory_write";
subject: PrincipalRef;
scope: PrivacyScopeRef;
purpose: PrivacyPurpose;
resourceIds: string[];
destination?: EgressDestination;
dataClasses: Sensitivity[];
policyVersion: string;
consentRef?: string;
legalBasisRef?: string;
redactionProfile?: string;
reasons: string[];
obligations: Obligation[];
actionHash: string;
issuedAt: string;
expiresAt?: string;
}
interface PrivacyPolicyPort {
classify(input: ClassificationInput): Promise<ClassificationResult>;
evaluatePurpose(input: PurposeInput): Promise<PurposeEvaluation>;
evaluateEgress(input: EgressRequest): Promise<PrivacyDecision>;
authorizeAccess(input: PrivacyAccessRequest): Promise<PrivacyDecision>;
planDeletion(input: DeletionRequest): Promise<DeletionPlan>;
}
```
### Memory 与 Artifact
```typescript
interface PrivacyMemoryRecord extends MemoryRecord {
tenantId: string;
purpose: PrivacyPurpose;
consentRef?: string;
legalBasisRef?: string;
egressProfile: string;
userVisible: boolean;
deleteToken?: string;
}
interface PrivacyArtifactRef extends ArtifactRef {
purpose: PrivacyPurpose;
legalBasisRef?: string;
consentRef?: string;
providerBindings?: ProviderArtifactBinding[];
deletionStatus: "active" | "pending" | "verified" | "blocked";
}
```
### Deletion、Export 与 Incident
```typescript
interface DeletionRequest {
requestId: string;
subject: PrincipalRef;
scope: PrivacyScopeRef;
dataIds?: string[];
purposes?: PrivacyPurpose[];
reason: "user" | "retention" | "privacy_incident" | "correction" | "policy";
legalHoldOverride?: string;
requestedAt: string;
}
interface DeletionPlan {
requestId: string;
targets: DeletionTarget[];
blockedBy: DeletionBlocker[];
providerCopies: ProviderDeletionTarget[];
cacheNamespaces: string[];
verificationSteps: string[];
planHash: string;
}
interface ExportManifest {
exportId: string;
scope: PrivacyScopeRef;
purposes: PrivacyPurpose[];
resources: ExportResource[];
redactionProfile: string;
encryptionKeyVersion: string;
expiresAt: string;
manifestHash: string;
}
interface PrivacyIncidentRecord {
incidentId: string;
severity: "SEV0" | "SEV1" | "SEV2" | "SEV3";
affectedScopes: PrivacyScopeRef[];
dataClasses: Sensitivity[];
purposes: PrivacyPurpose[];
destinations: EgressDestination[];
sourceEvents: string[];
containment: string[];
evidenceRefs: ArtifactRef[];
status: "detected" | "contained" | "recovering" | "validated" | "closed";
}
```
## 生命周期与状态机
### Data Item
```text
Discovered
-> Classified
-> PurposeBound
-> ScopeBound
-> ViewDerived
-> EgressEvaluated
-> Used
-> Retained | Expired
-> DeletionRequested
-> Deleting
-> Deleted | DeleteBlocked | Quarantined
```
不变量：
- 未 `Classified` 的内容不能进入低信任 sink。；未 `PurposeBound` 的内容不能进入 ModelRequest、MemoryWrite 或 Export。；`Deleted` 后不能从 cache、projection、embedding、artifact view 或 provider binding 复活。；`DeleteBlocked` 必须包含 hold、recovery 或 external limitation 的可恢复解释。
### Egress
```text
Requested
-> ScopeChecked
-> Classified
-> PurposeChecked
-> ConsentChecked
-> ResidencyChecked
-> Redacting
-> DlpScanned
-> Approved | ArtifactOnly | Denied
-> Transmitting
-> ReceiptRecorded
-> Settled | UnknownOutcome | Revoked
```
`UnknownOutcome` 表示目的地可能已经收到数据；恢复必须查询 receipt、remote object、provider status 或 network evidence，不得盲目重发。
### Memory
```text
Observed
-> Candidate
-> PrivacyChecked
-> UserOrPolicyApproved
-> Active
-> Stale | Contradicted
-> Forgotten
-> Tombstoned
```
### Privacy Incident
```text
Observed
-> Normalized
-> Correlated
-> RiskScored
-> Declared
-> Contained
-> Eradicated
-> Recovering
-> Validated
-> Closed
```
关闭前必须验证：
- 外发已停止，credential/route/remote object 已处理。；受影响 cache、artifact、trace、event、memory 和 backup 已按 policy 清理或 hold。；synthetic canary、回放和安全 scenario 通过。；residual risk、通知、owner、修复版本和新回归已记录。
## 端到端决策流程
### 新请求
1. Host 认证 principal，建立 `TenantContext`。；解析 workspace/project/session ownership 和 trust。；规范化 `TaskSpec`、purpose、mode、附件和 requested model。
• 加载 privacy/policy/consent/legal-basis/config snapshot。；发现数据资源并写 inventory metadata。；分类 sensitivity、PII、secret、regulated、provenance、authority。；计算当前任务的最小必要数据集。；评估 memory/artifact/session/context 的 scope 与 retention。；生成 candidate provider/region/deployment。；运行 egress、residency、training opt-out、remote retention 检查。；生成 redacted/tokenized/pseudonymized view。；运行 DLP/secret/PII/regulated 扫描。；创建 `EgressSnapshot`、`ContextPlan`、`PromptPlan` 和 route snapshot。；预留 token、artifact、egress、worker 和 cost budget。；启动 Kernel；仅发送冻结的 model/context/tool view。
• 对 tool result、provider response、artifact 和 event 再分类与扫描。；写 durable egress、access、usage、artifact、memory 和 run entries。；完成 retention、delivery、audit、cache invalidation 和 checkpoint settlement。
### 工具调用
```text
ToolCallComplete
-> canonicalize and validate
-> classify input/output sensitivity
-> purpose check
-> tenant/workspace ownership
-> call policy/approval
-> sandbox attestation
-> execute
-> scan result
-> egress result view
-> artifact offload
-> model/user/audit projections
```
### Memory 写入
```text
candidate claim
-> provenance/confidence
-> scope/purpose/consent
-> sensitivity and DLP
-> contradiction/duplication
-> user/policy gate
-> MemoryEntry + index
-> retention/forget hooks
```
### 删除/导出
```text
request
-> authenticate
-> resolve scope
-> hold/incident check
-> dependency graph
-> freeze new processing
-> execute deletion/export jobs
-> query provider copies
-> invalidate derived state
-> verify and issue receipt
```
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model Runtime
- 接收已冻结的 `ResolvedModel`、`RoutingSnapshot`、`EgressSnapshot`、credential lease reference。；在 request compile 前验证 context hash、view hash、policy version、training opt-out 和 provider contract。；只发送允许的 Message/Part、tool schema、artifact view、summary 或 ref。；保存 request/response raw ref 时执行加密、短 retention、DLP 和 access control。；provider response 视为不可信数据；不得覆盖 tenant、purpose、consent、scope 或 policy。；fallback/hedge/shadow 创建新 egress decision、usage entry 和 audit evidence。
### Prompt
Prompt Compiler 使用：
- privacy mode、purpose、当前可见数据、工具和 provider limitations。；不可信内容包装、redaction marker、artifact truncation、approval expectation。；完成标准包含“未外发未授权数据、未把模型推断写成 memory、删除/导出状态准确”。
Prompt 不实现：
- DLP、provider training opt-out、tenant isolation、retention、delete、key rotation。
### Context
Context Compiler 负责：
- scope、authority、sensitivity、purpose、consent、retention 和 egress 过滤。；选择 summary/structured/range/ref-only，避免 raw 全文。；记录 selected/dropped/offloaded、resource versions、redaction profile 和 token budget。；在 compaction 中保留 privacy-critical state、deletion request、pending approval、unknown outcome 和 incident evidence。；memory recall 不产生授权；每次召回都重新执行 provider egress。
### Tool
Tool Runtime 负责：
- 输入/输出 sensitivity、effect、purpose、secret binding、artifact policy。；参数和路径 canonicalization，业务 ownership，schema/业务 validation。；执行前 policy/approval/sandbox，执行后 DLP、redaction、artifact offload 和 result egress。；side effect unknown、remote upload unknown、tool result secret-like 内容的恢复。
### State/Memory/Artifact
State semantic entries 至少包括：
- `DataClassifiedEntry`、`PurposeEvaluatedEntry`、`ConsentCheckedEntry`。；`EgressDecisionEntry`、`RedactionEntry`、`ProviderBindingEntry`。；`MemoryCreated/ForgottenEntry`、`ArtifactAttached/DeletedEntry`。；`RetentionExpiredEntry`、`DeletionRequested/CompletedEntry`、`ExportEntry`。；`PrivacyIncidentEntry`、`KeyRotationEntry`、`TrainingOptOutChangedEntry`。
State 记录 ref/hash/decision，不把大 blob 嵌入 transcript；ArtifactStore 保存 raw/view/scan/retention；MemoryStore 保存 provenance/TTL/forget。
### Policy/Sandbox
```text
visibility
-> scope and purpose
-> schema/business validation
-> privacy egress decision
-> approval
-> execution sandbox
-> result DLP/redaction
-> audit and retention
```
- Policy 决定“可否处理/外发/保存”。；Sandbox 决定“执行时能观察/影响什么”。；Egress 不是工具成功后的自动步骤。；host 无 approval、DLP 或 artifact review 能力时，高风险 privacy action fail-closed。
### Harness
Harness 负责：
- safe/trusted bootstrap、scope/context 注入、registry 装配。；冻结 config、policy、consent、egress、key、toolset、model 和 privacy snapshot。；监督 model、tool、memory、artifact、provider upload、background worker、export/delete job。；在 durable boundaries 写 entry/checkpoint，处理 cancel、crash、unknown outcome 和 recovery。；将 canonical privacy events 投影给 Host、Audit、SIEM、Evaluation 和 Cost。；关闭时先 settle durable privacy facts，再释放 temp、lease、lock 和 remote bindings。
## 故障恢复与安全降级
### 故障分类
```text
classification_unknown
purpose_missing
consent_unavailable
legal_basis_unknown
egoress_denied
residency_unknown
training_opt_out_unknown
redaction_failed
dlp_unavailable
key_unavailable
scope_mismatch
provider_upload_unknown
remote_delete_unknown
retention_conflict
export_incomplete
delete_incomplete
audit_sink_failure
projection_lag
unknown_privacy_outcome
```
### 恢复原则
- 无法分类：提高敏感度或 deny。；无法验证 purpose/consent/basis：暂停该 processing，不让模型猜测。；redaction/DLP 不可用：artifact-only 或 deny。；key broker 不可用：不使用旧 key，不打印 secret；允许安全 metadata-only 任务。；provider upload unknown：查询 remote status/hash/expiry；不能盲目重传。；remote delete unknown：标记 limitation、缩短本地 retention、阻止复用，并生成 incident/diagnostic。；event/audit 关键 sink 失败：高风险 egress suspend；普通 ephemeral telemetry 可 bounded degrade。；control plane 失联：已授权 run 只继续到安全边界；新敏感动作停止。；删除期间的 unknown side effect 先查状态，不能以删除成功代替业务状态。
### Crash Recovery
```text
load checkpoint
-> verify tenant/scope/purpose/consent/policy/key versions
-> inspect open egress/provider upload/memory/artifact jobs
-> query receipts and remote status
-> classify sent/not_sent/known/unknown
-> revoke unsafe leases
-> rebuild projections/cache indexes
-> resume safe work or require manual review
```
恢复不变量：
- 不重复敏感外发。；不把 unknown 当作未发送。；不复用过期 consent、policy、key、approval 或 egress snapshot。；不在删除后从 cache、memory、embedding、artifact view 复活数据。；不让用户已有文件、其他租户或 legal hold 数据被错误清理。
## 可观测性、指标与报告
### Trace 层级
```text
session -> run -> purpose/classification
-> context/prompt compile -> egress/redaction/dlp
-> route/model attempt -> tool/artifact/memory
-> provider transfer -> audit/retention/delete/export
-> incident/recovery
```
### 必备字段
- trace、session、run、attempt、tool execution、artifact、memory、provider request IDs。；tenant/workspace/scope hash、purpose、classification version、policy/egress/consent/basis version。；view hash、redaction profile、DLP scanner version、key version、region/provider/deployment。；bytes/tokens、usage/cost、retention class、TTL、decision、outcome、unknown state。；raw payload/artifact 只以受控 ref/hash 关联。
### 指标
数据 inventory：
- 未分类数据比例、分类 unknown rate、lineage completeness。；purpose missing/deny/transform rate、consent unavailable/withdrawal lag。
最小化与 egress：
- full/redacted/summary/artifact-only/deny 比例。；provider egress bytes、sensitivity downgrade、redaction hit、DLP finding。；cross-region attempt、training opt-out mismatch、remote upload/delete unknown。
生命周期：
- retention expiry lag、delete completion lag、residual reference count。；export completion、DSAR failure、tombstone verification、GC orphan。；memory write/forget/recall by sensitivity、stale/contradicted recall。
安全与访问：
- cross-tenant deny、scope mismatch、secret detection、audit access、break-glass。；key rotation success/failure、old lease use、audit sink lag、event gap。
质量与成本：
- task success under privacy policy、privacy-induced fallback rate、context minimization recall。；redaction schema breakage、extra user clarification、cost per compliant success。；provider egress latency、DLP/scan queue、artifact offload savings。
### Privacy SLO
```text
unclassified sensitive egress = 0
secret redaction escape = 0
cross-tenant privacy violation = 0
privacy decision coverage = decisions / eligible processing actions
provider egress audit completeness = audited egress / provider sends
retention deletion completion = verified deletes / due deletes
DSAR/export completeness = complete manifests / accepted requests
unknown privacy outcome resolution = resolved unknown / unknown events
```
安全零容忍指标不能被平均质量或 cost per success 稀释；分母包括失败、deny、cancel、unknown 和后台任务。
### 报告
报告至少区分：
- raw、redacted、summary、metadata-only、restricted 的数量和范围。；estimated、observed、reconciled、unknown、blocked 和 external limitation。；privacy policy、consent、legal-basis、provider contract、redactor/DLP、key 和 dataset 版本。；user/operator/audit 三种视图；访问报告本身也必须审计。
## 测试策略与 Evaluation
### Testkit
```text
FakeTenantContext
FakePrivacyPolicy
FakeConsentStore
FakeLegalBasisCatalog
FakeClassificationService
FakeDlpScanner
FakeRedactor
FakeTokenVault
FakeKeyManager
FakeProviderEgress
FakeRemoteFileStatus
InMemoryArtifactStore
InMemoryMemoryStore
InMemoryEventStore
ScriptedModelStream
FakeToolRuntime
FakeHostAdapter
DeterministicClock
DeterministicIds
CrashInjector
SideEffectRecorder
RedactionScanner
ReplayRunner
```
### 单元测试
- classification、sensitivity join、field tags、unknown classification。；purpose compatibility、consent scope、withdrawal、basis/version/expiry。；scope intersection、tenant owner、branch/run/subagent visibility。；egress candidate、region/residency、training opt-out、retention compatibility。；redaction/tokenization/pseudonymization、map isolation、hash/lineage。；DLP scanner、nested JSON/base64/compression/URL bypass。；retention/TTL/hold、tombstone、delete dependency、export manifest。；EncryptionContext、AAD mismatch、key rotation/revoke、crypto-shred state。；privacy event schema、audit integrity、projector idempotency。
### 安全场景
1. 恶意文档要求读取 `.env` 并发送到新 URL。；模型伪造 tenant、consent、legal basis、admin actor 或 approval。；memory recall 返回其他 workspace 或过期 regulated record。
• provider fallback 跨 denied region。；shadow/hedge 重复外发 confidential 数据。；tool result、MCP response、OCR 或 error 中出现 synthetic secret。；tokenization map 进入 prompt、trace、artifact、ChildResult。；redaction 后 base64、zip、nested URL 绕过 DLP。；provider upload 成功但本地 crash，恢复路径不得重复外发。；delete 后 cache、embedding、preview、backup 或 provider remote object 仍可读取。；export 包混入其他 tenant、已撤回 consent 或 legal hold 外数据。；key rotation 中旧 worker 继续使用旧 lease。；audit sink unavailable 时高风险 egress 是否 fail-closed。；Host 断线、approval pending、background job 继续时隐私状态是否可恢复。；cross-tenant replay、diagnostic snapshot、artifact range、cursor 和 cache collision。
### 断言原则
- 不只检查最终文本；必须检查 `ContextPlan`、`EgressSnapshot`、事件、状态、artifact、DLP、provider request 和负向副作用。；synthetic canary secret 一次进入禁用 sink 即 hard fail。；一次跨 tenant、未经允许 egress、错误删除或过期 consent 复用即 hard fail。；`error`、`skipped`、`inconclusive` 不计为 pass。；LLM judge 只能评估 privacy explanation、用户可理解性或摘要完整性，不能裁决真实 egress、删除、访问或 secret 是否发生。
### Fault injection
在以下边界注入 crash/timeout/duplicate/gap：
- inventory/classification/purpose/consent commit 前后。；redaction map、DLP result、artifact view 写入前后。；egress decision、provider request、remote upload ack 前后。；memory write、forget、embedding delete 前后。；key rotation/revoke、export package、delete worker、GC 前后。；audit append、event projection、checkpoint、host delivery 前后。
验证：不重复外发、不丢 privacy fact、不复用过期授权、不删除 hold、不把 unknown 当 success。
### Conformance
每个 Provider Runtime、Routing、ArtifactStore、MemoryStore、EventStore、KeyManager、DlpScanner、Redactor、Host Adapter 和 Worker 通过统一 privacy contract：
- tenant/scope 一致。；sensitivity/purpose/egress decision 一致。；redaction/scan 状态可审计。；retention/delete/export 可重演。；key/AAD/version 正确。；unknown outcome 可标记和恢复。；raw fixture、logs、trace、artifact 不泄漏 synthetic secret。
## 反模式与审查规则
1. 只脱敏日志，prompt、artifact、trace、provider upload 不处理。；只在 system prompt 写隐私规则。；把 consent checkbox 当成永久全局授权。
• 把 approval 当作 purpose/legal basis。；只按 `tenant_id` 过滤数据库，不隔离 cache、queue、artifact、trace、temp 和 provider egress。；只按文件扩展名识别 PII、secret 或 regulated data。；把不可逆 hash 直接当匿名化。；tokenization map 进入 prompt、provider、普通日志或子 Agent。；provider adapter 自行切 region、fallback 或声称 training opt-out。；只检查原始 URL，不检查 DNS、重定向、最终 IP 和 artifact owner。；artifact scan pending 时向模型或 provider 提供 raw 内容。；redaction 失败后静默发送原文。；purpose 改变后复用旧 egress/consent snapshot。；compaction 删除 pending deletion、incident evidence、unknown outcome 或 retention hold。；memory 自动保存所有对话，secret/regulated 无 TTL。
• forget 只删索引，不清 cache、embedding、derived view 和 provider copy。；delete 只删主表，不处理 backup、export、remote object 和 audit。；export 包无 manifest、scope、hash、encryption、expiry 和访问审计。；key rotation 只改配置，不重加密、不撤销旧 lease、不验证残留。；provider upload unknown 后立即重传敏感内容。；用最终文本证明“没有外发”或“已经删除”。；将 metadata-only diagnostic 误当作无风险，忽略 side channel 和 resource existence。；audit、SIEM、trace、log 共用同一无界 raw payload sink。；只测试正向 allow，不测试 deny、quarantine、unknown、recovery 和删除复活。；用平均隐私评分抵消一次 secret、cross-tenant 或未经允许的 egress。
审查最低标准：
```text
inventory complete
purpose explicit
scope enforced
egress reproducible
redaction verified
retention executable
delete/export provable
key lifecycle recoverable
audit durable
unknown outcome explicit
```
## 实施清单
### V1：Inventory 与边界
- [ ] 定义 `DataInventoryRecord`、`PrivacyScopeRef`、`Sensitivity`、`PrivacyPurpose`。；[ ] 为 prompt/context/tool/state/memory/artifact/event/trace/log/provider/cache/backup 建 inventory。；[ ] 建立 tenant/workspace/session/run/subagent scope guard 和 owner check。；[ ] 建立 purpose、consent/legal-basis、retention、training opt-out snapshot。；[ ] 建立 `EgressSnapshot`、provider/region/deployment allowlist 和 fail-closed。；[ ] 禁止模型覆盖 tenant、purpose、consent、region 和 scope。
### V2：Classification、DLP 与变换
- [ ] 实现 sensitivity、PII、secret、regulated、provenance、authority 分类。；[ ] 实现 DLP scanner、nested/encoded/compressed/URL bypass 检测。；[ ] 实现 redaction、tokenization、pseudonymization 和 map isolation。；[ ] 实现 raw/sanitized/summary/structured/range/ref-only artifact views。；[ ] 在 Context、Provider、ToolResult、Artifact、Trace、Log、Host 前执行扫描。；[ ] redaction/DLP 失败时 artifact-only/deny 并写安全事件。
### V3：Retention、删除与密钥
- [ ] 定义 retention class、TTL、legal hold、incident hold 和依赖图。；[ ] 实现 session/memory/artifact/event/cache/embedding/export/backup 删除流程。；[ ] 实现 provider remote delete/status、unknown limitation 和删除证明。；[ ] 实现 export manifest、短 TTL、加密、scope/hash/versions 和 DSAR workflow。；[ ] 定义 EncryptionContext、AAD、key version、rotation、revoke、crypto-shred。；[ ] key broker unavailable、旧 lease、AAD mismatch 均 fail-closed。
### V4：运营与事故
- [ ] 建立 privacy audit、SIEM projection、forensic bundle 和 diagnostic snapshot。；[ ] 建立 secret/PII/regulated egress、cross-tenant、retention、provider drift detector。；[ ] 定义 privacy incident severity、containment、eradication、recovery、validation。；[ ] 建立 provider key leak、cross-tenant、sandbox/egress、delete/export runbook。；[ ] 建立 privacy SLO、DLP/scan queue、delete/export lag、unknown outcome 告警。；[ ] 每季度执行 tabletop，并将事件最小复现加入回归集。
### V5：Conformance、Evaluation 与发布门禁
- [ ] 建立 FakePolicy、FakeConsent、FakeDlp、FakeRedactor、FakeProvider、FakeKeyManager。；[ ] 建立 synthetic secret、PII、regulated fixture 和双租户负向场景。；[ ] 对 Model/Prompt/Context/Tool/State/Artifact/Provider/Host/Worker 运行 privacy contract tests。；[ ] 在 egress、upload、delete、export、key、memory、audit、checkpoint 前后做 crash injection。；[ ] 将 secret escape、cross-tenant、unapproved egress、wrong deletion 设为 CI hard gate。；[ ] 建立 provider training/residency/remote-retention drift 监控与回滚。
### Definition of Done
- 每次 Provider egress 都能回答谁、为何、发送什么 view、到哪里、保存多久、基于哪个 policy/consent/basis。；每个 memory、artifact、event、trace、log 和 cache 都有 owner、scope、sensitivity、purpose、retention 和 deletion path。；secret/PII/regulated 数据不会因为 provider fallback、subagent、artifact、log、backup 或恢复路径绕过控制。；删除、导出、key rotation、incident containment 和 unknown outcome 都有 durable receipt 与验证证据。；Privacy 质量不依赖最终文本或“已脱敏”口头声明。
## 五个参考项目的启发来源
### Pi
- headless agent loop、统一 EventStream、session tree、compaction 和多 Host runtime 启发 privacy facts 不应绑定单一 UI，Context、State、Event 和 delivery 必须分层。；resource loader、tool loop、steering/follow-up 和可恢复 session 启发数据 scope、来源、摘要和恢复状态应显式持久化。；执行隔离较弱的取舍提醒：session 可恢复不等于 provider egress、文件、secret 和日志已经隐私隔离。
### Grok Build
- Session/ChatState/Sampler actor 启发 privacy snapshot、单写者状态和高并发下的 reservation/settlement 顺序。；permission decision、folder trust、sandbox、路径级锁和输出限制启发 visibility、scope、execution、resource lock、DLP 和输出预算分离。；工具结果修剪、图片压缩和上下文预算启发 artifact view、summary、range、redaction 和 provider egress 最小化。
### OpenCode
- client/server、session/message/part、事件总线、durable event/projector 启发 privacy event、audit、replay、cursor 和多客户端访问重授权。；snapshot/patch/revert 启发文件、artifact、删除和恢复需要 base hash、版本与可审计的派生关系。；permission、tool、MCP/LSP 分离启发 provider、扩展、工具描述和外部结果不能获得 privacy authority。
### Claude Code
- permission modes、hooks、skills、subagents、memory、项目规则和计划工作流启发不同模式必须同时改变 context、tool、policy、approval、memory 和交付边界。；auto memory、CLAUDE.md 与子任务方向启发 memory provenance、scope、TTL、用户控制和最小委派上下文。；公开安全语义以本地文档中标注的 Anthropic 官方资料为准；辅助源码不作为权威规范。
### OpenClaw
- AgentHarness registry、agent-core、Gateway/channel、provider runtime 启发跨 channel/provider/background worker 的统一 scope、egress、artifact、delivery 和恢复边界。；tool/sandbox/elevated 分层启发 privacy policy、真实执行隔离、secret binding 和 break-glass 必须独立。；memory flush、后台任务和事务化插件注册启发 memory retention、worker lease、remote object、扩展 provenance 与失败回滚。
本设计的实现审查应回到上述本地工程文档及其记录的源码范围；若新增 provider 合同、法律依据、跨境区域、regulated data 类型或组织 retention 规则，应单独补充一手证据、版本、迁移方案和契约测试。
