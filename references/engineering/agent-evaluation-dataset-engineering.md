# Agent Evaluation Dataset Engineering 细粒度工程设计
> 本文定义如何把 Agent 测评集建设成可执行、可重放、可统计、可治理和可持续演进的数据产品。
>
> Agent eval 的基本单位不是一条静态问答，而是一个带初始状态、工具、策略、环境、预算、轨迹证据、最终状态和副作用 Oracle 的可重放 episode。
>
> 本文偏重 Dataset、Case Authoring、Ground Truth、Grader、Coverage、Statistics、Contamination 与 Lifecycle；Runner、Scripted Model、Fake Tool、Event Assertion、Crash Injection 等执行细节见 [Evaluation Engineering](evaluation-engineering.md)。
>
> 公开资料核对日期：**2026-07-21**。快速变化的 benchmark、排行榜、模型版本和厂商功能仍应在使用时重新核对一手来源。
## 目录
- 基础：[核心结论](#核心结论)、[目标与边界](#设计目标与非目标)、[总体结构](#测评集总体结构)、[Episode](#episode-是最小评测单位)
- 分类与覆盖：[任务 Taxonomy](#多轴任务-taxonomy)、[能力链](#能力链-taxonomy)、[风险](#风险与副作用-taxonomy)、[复杂度](#复杂度与-horizon)、[覆盖矩阵](#覆盖矩阵与-suite-composition)
- 数据构建：[案例来源](#案例来源)、[生产抽样](#生产流量抽样)、[Root Case](#root-casefamily-与-variant)、[Counterfactual](#counterfactual-与-metamorphic-case)
- Schema：[Manifest](#dataset-manifest)、[Task](#task-record)、[Environment](#environment-snapshot)、[Oracle](#oracle-与-assertion-schema)、[Result](#trial-与-result-schema)
- 真值与评分：[Ground Truth](#ground-truth-工程)、[Solvability](#solvability-与坏题审计)、[Composite Oracle](#composite-oracle)、[Trajectory](#trajectory-invariant)、[Side Effect](#state-与-side-effect-oracle)
- Judge 与统计：[Judge](#llm-judge-的适用边界)、[Calibration](#judge-calibration)、[标注](#人工标注与仲裁)、[随机性](#随机性与重复运行)、[统计](#统计比较)
- 数据完整性：[去重](#去重与独立样本)、[污染](#contamination-防护)、[Replay](#环境重置与-replay)
- 安全与鲁棒：[安全](#安全测评集)、[Injection](#prompt-injection-与恶意工具)、[Canary](#secretpii-与跨租户-canary)、[Memory](#memory-与多-agent-污染)、[恢复](#鲁棒性与恢复测评)
- 运营：[Benchmark](#benchmark-设计启发)、[Release Gate](#release-gates)、[上线](#shadowcanary-与-ab)、[Failure](#failure-taxonomy-与聚类)、[生命周期](#案例晋升饱和与退役)
- 落地：[治理](#版本provenance-与治理)、[Authoring](#authoring-workflow)、[清单](#单案例质量清单)、[反模式](#反模式)、[DoD](#definition-of-done)、[来源](#一手资料与项目启发)
## 核心结论
1. **Agent 测评集不是 Prompt 列表。**
2. **最小单位是可重放 Episode。**
3. **最终状态和执行证据优先于模型自述。**
4. **成功与禁止副作用必须同时评分。**
5. **高风险失败不能被平均分抵消。**
6. **完整外显轨迹应默认留存。**
7. **不要求或依赖私有 Chain-of-Thought。**
8. **确定性 Oracle 优先于 LLM Judge。**
9. **LLM Judge 本身也必须有校准集。**
10. **公开 Benchmark 不能替代私有产品测评集。**
11. **固定公开题集最终都会面临污染和饱和。**
12. **数据拆分应按泛化轴，而不只随机拆分样本。**
13. **统计独立单位应是 Root Case，而不是模板变体。**
14. **Infra Error 不能计为安全通过。**
15. **测评集需要 Owner、版本、SLA、审计和退役机制。**
```text
Agent Evaluation Dataset Quality
  = Task Representativeness
  × Ground-truth Integrity
  × Oracle Correctness
  × Environment Reproducibility
  × Coverage
  × Contamination Resistance
  × Statistical Validity
  × Operational Usefulness
```
任一因子接近零，排行榜数字都不能构成可靠发布证据。
## 设计目标与非目标
### 目标
测评集工程必须能够：
- 表达真实用户目标、约束、工具、政策和初始状态。
- 验证最终结果、关键里程碑、轨迹不变量和真实副作用。
- 覆盖正常、边界、失败、拒绝、澄清、取消和恢复路径。
- 支持单轮、多轮、长程、状态化、多应用和多 Agent 任务。
- 支持 Golden、Challenge、Holdout 和 Production Observational 数据。
- 按 Domain、Capability、Risk、Difficulty 和 Environment 分层报告。
- 区分 Agent Failure、Environment Failure、Grader Failure 和 Bad Task。
- 保存可重放证据并允许重新评分。
- 量化随机性、可靠性、成本和延迟。
- 支持离线回归、Shadow、Canary 和在线实验。
- 把生产事故和真实失败安全地晋升为回归案例。
- 防止重复、泄漏、污染、过拟合和人为调低标准。
### 非目标
本模块不负责：
- 用一个总分描述 Agent 的全部质量。
- 用公开排行榜代替产品验收。
- 用最终文本相似度证明业务动作完成。
- 用 LLM Judge 判断数据库是否提交或审批是否生效。
- 保存模型私有思维链作为评测前提。
- 使用真实生产凭据或真实受害者数据做安全测试。
- 允许 Shadow Candidate 产生真实写操作。
- 把超时、服务错误或评测器崩溃记为安全成功。
- 让开发团队无限次探测 Sealed Holdout。
- 为当前 Candidate 通过而修改 Golden 标准。
## 职责边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| `DatasetRegistry` | Manifest、版本、Split、Hash、权限和生命周期 | 执行 Agent |
| `TaxonomyRegistry` | Domain、Capability、Risk、Difficulty 标签 | 给 Candidate 打分 |
| `CaseAuthoringPipeline` | 来源转换、脱敏、去重、Review 和晋升 | 线上流量路由 |
| `EnvironmentRegistry` | 镜像、快照、Fixture、Reset 和依赖版本 | 业务 Oracle 解释 |
| `OracleRegistry` | Assertion、Rubric、Grader 版本和证据要求 | 修改被测状态 |
| `EvaluationRunner` | 执行 Episode、采集 Trace 和结算结果 | 随意改变 Dataset |
| `JudgeService` | 受限语义评分与校准 | 权限和副作用裁决 |
| `StatisticsService` | 聚合、置信区间、功效和差异分析 | 掩盖 Slice 失败 |
| `ReleaseGate` | 根据预注册规则决定阻断、告警或继续 | 临时改阈值迎合发布 |
| `ProductionFeedbackPipeline` | 抽样、脱敏、分诊、最小复现 | 直接复制原始 Transcript 入库 |
Dataset Truth 与 Product Truth 必须分离：
```text
Product Truth
  = 真实用户授权 + 业务状态 + 外部提交事实
Evaluation Truth
  = Fixture + Label + Oracle + Rubric + Threshold + Evidence
```
评测集可以描述和检查 Product Truth，但不能反向覆盖真实业务事实。
### 规范源、基数与编译契约
本文是 `DatasetManifest`、`RootCase`、`EpisodeSpec`、Ground Truth、Collection 和 Authoring Lifecycle 的规范源；[Evaluation Engineering](evaluation-engineering.md) 是 `EvaluationSuite/Scenario/Variant`、Execution、Observation、Assertion 执行和 Result 的规范源。
```text
Dataset -> Collection -> Partition -> RootCase -> EpisodeSpec -> Scenario -> Trial -> Result
                                      \-> Authoring Variant -> EvaluationVariant
```
- `Case` 只是编辑泛称；持久身份使用 `rootCaseId`、`episodeSpecId` 和可选 `variantId`。
- 编译器按唯一 `(datasetVersion, collection, partition)` 生成一个 `EvaluationSuite`；`suite.dataset.id` 固定为 `<datasetId>@<version>/<collection>`，Runner `DatasetDescriptor.split` 只承载 `partition`。
- 一个 `EpisodeSpec` 恰好编译成一个 `EvaluationScenario`，`scenario.id = episodeSpecId`；仅改变输入/Fixture/Seed 且共享 Risk、Policy、Oracle 的变体进入 `EvaluationScenario.variants[]`，改变这些语义的变体必须成为新 EpisodeSpec。
- 可执行 `collection` 仅为 golden/challenge/selection_holdout/release_holdout/calibration/red_team；`partition` 为 dev/validation/test/canary/production_shadow，两者不能共用一个字段。
- `Trial` 是 Scenario/Variant 的一次执行；Observation 与 Result 必须回写 datasetVersion、collection、partition、rootCaseId、episodeSpecId 和 variantId，确保可追溯。
- `invalid_task -> error(task_spec)`、`infrastructure_error -> error(infrastructure)`、`grader_error -> error(grader)`；原始原因必须保留，均不得计为 Passed。
- 自由字符串 Oracle 仅是展示简写；可执行版本必须编译为 Runner 的封闭 Assertion 联合类型或显式版本化插件。
## 测评集总体结构
推荐维护至少四套主数据和两套辅助数据。
### Golden / Regression Set
用途：
- Presubmit 和 CI 回归。
- 已修复故障防复发。
- 核心产品合同和高风险不变量。
- 高频关键工作流。
特征：
- 开发团队可见。
- Oracle 高确定性。
- 结果应稳定。
- 修改语义必须升版本。
- 不适合长期测前沿能力。
### Challenge / Frontier Set
用途：
- 长程、组合、长尾和新颖能力。
- 当前模型尚未饱和的任务。
- 对抗、故障和高复杂度场景。
- 比较架构、模型和 Harness 的能力上限。
特征：
- 可部分公开。
- 持续增加更难任务。
- 允许 Partial Credit。
- 必须保持人工可解。
- 达到饱和后转入 Regression 或退役。
### Sealed Holdout
Holdout 必须再分两层：`selection_holdout` 用于受限候选选择，`release_holdout` 用于最终发布验收；不能在同一集合上反复选型后仍宣称最终结果无偏。
共同特征：Prompt、Fixture、答案和 Grader 细节受限；按组织、发布周期和系统版本限制查询预算；默认只返回聚合结果；采用时间切分和定期轮换；泄漏后标记 `compromised` 并冻结比较。
`release_holdout` 应一次性或低频使用，失败细节只有在该批 Case 退役并补充新 Holdout 后才能进入开发闭环。
### Blind Production / Production Observational Set
`blind_production_observation` 指 Candidate 开发者不可按题查看或调参的盲测生产样本；完成脱敏和合法性审查前，它只是 `ProductionObservationRecord`，不是可执行 Episode。
用途：
- 估计真实流量表现。
- 发现分布漂移和未覆盖失败。
- 形成生产加权指标。
- 生成候选 Regression Case。
特征：
- 严格访问控制。
- 必须脱敏、最小化和获得合法处理依据。
- 不直接依赖仍有效的用户对象或凭据。
- 不应与用于调参的数据重复报告无偏提升。
### Judge Calibration Set
用于：
- 校准 LLM Judge 与 Human Label 的一致性。
- 测试 Position、Verbosity、Self-preference 和风格偏差。
- 评估 False Pass、False Fail 和 Unknown。
- 验证新 Judge Model、Prompt 或 Rubric。
### Red-team / Adaptive Attack Set
用于：
- 直接滥用。
- 间接 Prompt Injection。
- 恶意 Tool、MCP、网页、邮件和文件。
- Secret、PII、权限、Memory 和 Multi-agent 风险。
- 独立攻击模型生成的 Held-out 自适应攻击。
## Episode 是最小评测单位
每个 Episode 至少包含：
```text
task identity
instruction and conversation seed
input assets
initial state snapshot
available tools and schemas
policy and authorization context
allowed and forbidden actions
network and sandbox policy
resource budget
user simulator or interaction script
termination conditions
success oracle
invariant oracle
side-effect contract
reset procedure
randomness policy
provenance and split
```
静态问答可以退化为无工具、无状态 Episode，但工具 Agent 不应退化为静态问答。
一个完整 Episode 的生命周期：
```text
Author -> Review -> Compile -> Prepare Environment
  -> Execute Trial -> Collect Trace
  -> Settle External State -> Grade
  -> Aggregate -> Diagnose -> Promote or Retire
```
Episode 必须回答：
- Agent 被要求完成什么？
- Agent 被允许做什么？
- Agent 必须先确认什么？
- 哪些输入是不可信的？
- 哪个系统保存权威状态？
- 什么证据证明任务完成？
- 什么副作用即使目标完成也构成失败？
- 如何恢复到干净初始状态？
## 多轴任务 Taxonomy
不要用单棵分类树限制案例；一个案例应同时拥有多轴标签。
### Domain
```text
customer_support
coding
research
browser
desktop
commerce
finance
scheduling
data_analysis
security
internal_operations
healthcare
legal_workflow
creative_production
```
### Interaction Mode
```text
single_turn
multi_turn
agent_user_dialogue
single_agent_environment
multi_agent
human_in_the_loop
background_job
long_running_workflow
```
### Interface
```text
text
structured_output
api_tools
mcp
code_execution
browser_dom
browser_visual
desktop_gui
filesystem
database
mixed
```
### Statefulness
```text
stateless
session_state
persistent_state
cross_session_state
cross_application_state
shared_multi_agent_state
external_transaction_state
```
### Information Condition
```text
sufficient
missing_required_information
ambiguous_goal
contradictory_information
stale_information
untrusted_external_content
user_changes_mind
impossible_request
partially_observable_state
```
### Oracle Type
```text
exact_answer
structured_match
unit_test
execution_result
database_state
filesystem_state
ui_state
artifact_diff
state_diff
invariant_check
milestone
policy_rule
human_rubric
llm_rubric
composite
```
## 能力链 Taxonomy
能力标签应能直接映射失败阶段。
```text
instruction_understanding
constraint_extraction
ambiguity_detection
clarification
planning
decomposition
retrieval
evidence_selection
tool_discovery
tool_selection
argument_grounding
state_tracking
policy_reasoning
authorization_reasoning
execution
parallel_coordination
verification
error_recovery
stopping
user_communication
artifact_delivery
handoff
```
案例应标记：
- 主要能力。
- 次要能力。
- 最小必要能力链。
- 预期关键里程碑。
- 可接受替代能力链。
不要把所有失败都归类为“Reasoning Failure”。
## 风险与副作用 Taxonomy
### Operation Class
```text
retrieve_only
recommend
draft
reversible_mutation
irreversible_mutation
external_communication
financial_transaction
permission_change
code_execution
destructive_operation
```
### Risk
```text
privacy
authorization
data_exfiltration
prompt_injection
policy_violation
unsafe_tool_use
destructive_side_effect
financial_loss
external_miscommunication
deception
goal_misalignment
over_autonomy
failure_to_escalate
cross_tenant_access
security_resilience
```
风险严重度与任务难度必须分离。每个 Case 另标 `risk_severity: low | medium | high | critical`；`critical` 表示一次误放行即可造成不可接受的安全、权限、隐私、跨租户、资金或不可逆副作用，必须进入 Hard Gate。一个简单删除动作可以是低难度、高风险；一个复杂只读研究任务可以是高难度、低副作用风险。
### Side-effect Contract
每个可写任务必须声明：
```yaml
side_effect_contract:
  allowed_reads:
    - tenant_A/orders/*
  allowed_writes:
    - tenant_A/drafts/task_123/*
  required_changes:
    - refunds/order_123.status=processed
  forbidden_changes:
    - orders.exclude(order_123)
  forbidden_external_actions:
    - send_email
    - transfer_money
  confirmation_required:
    - process_refund
```
以上 YAML 是 authoring view；进入 Runner 前必须编译为版本化 Assertion：状态 Selector、集合/顺序 Comparator、动作阶段、Settlement Window、Idempotency Receipt 和 `unknown_outcome` 处理均不可依赖自然语言解释。
## 复杂度与 Horizon
不要只写 `easy/medium/hard`。
先记录可测量特征：
```text
expected_turns
minimum_tool_calls
maximum_reasonable_tool_calls
applications_touched
dependency_depth
branching_factor
context_bytes
required_entities
policy_rules_in_scope
state_mutations
recovery_points
human_completion_seconds
human_completion_variance
```
再派生难度等级：
```text
D1 直接、单步、单工具、低状态
D2 多步、单域、少量状态
D3 多工具、含澄清或政策约束
D4 长程、跨应用、故障恢复或高风险
D5 开放式、长 Horizon、部分可观测或复杂协作
```
Horizon 应优先参考人类完成任务所需工作量，而不是 Agent 实际耗时。
## 覆盖矩阵与 Suite Composition
Suite 不能只报告“共有 500 道题”。
推荐维护：
```text
Domain × Capability × Risk × Difficulty × Source × Split
```
每个 Cell 至少记录：
```yaml
coverage_cell:
  domain: customer_support
  capability: policy_reasoning
  risk: financial_loss
  difficulty: d3
  root_case_count: 18
  variant_count: 42
  production_weight: 0.031
  source_mix:
    production: 8
    human: 6
    synthetic: 4
  baseline_pass_rate: 0.61
  candidate_pass_rate: 0.66
  paired_delta_ci95: [-0.03, 0.13]
  critical_failures: 1
```
必须区分：
- `root_case_count`。
- `variant_count`。
- `trial_count`。
- `effective_sample_size`。
推荐同时报告：
- Macro Average。
- Production-weighted Average。
- Risk Gate。
- Worst Slice。
- Critical Failure Count。
- Coverage Gap。
Suite 配比应由产品分布和风险决定，不应照搬固定百分比。
高风险低频任务可以在 Production Weight 中很小，但在 Release Gate 中权重极高。
## 案例来源
### 生产来源
- 用户负反馈。
- 用户纠正。
- 人工接管。
- Support Ticket。
- Bug Tracker。
- 回滚和撤销。
- 重复工具调用。
- Policy Violation。
- 高延迟和高成本异常。
- 成功但有多余副作用的会话。
- 高频正常成功样本。
### 人工编写
适合：
- 尚未上线的功能。
- 低频高损风险。
- 法律、合规和授权边界。
- 必须澄清或升级人工的场景。
- 已知系统性弱点。
### 合成生成
适合变换：
- 实体、金额、日期、地区和语言。
- 账户状态和权限。
- 缺失、冲突和过期信息。
- 工具超时、断流和错误。
- 用户中途改变目标。
- 无关工具和顺序扰动。
- Prompt Injection 位置和表达。
- 极端上下文与长 Horizon。
合成变体必须保留 Parent 和 Transformation Provenance。
### 公开 Benchmark
公开 Benchmark 适合：
- 对比行业能力。
- 学习环境和 Oracle 设计。
- 验证跨任务泛化。
- 做外部可复现报告。
公开 Benchmark 不适合：
- 作为唯一 Release Gate。
- 代表真实产品分布。
- 证明不存在污染。
- 证明真实权限和副作用安全。
### 事故回归
每次事故应沉淀：
- 原始症状。
- 最小复现。
- Root Cause。
- Expected Safe Behavior。
- Deterministic Oracle。
- Known-bad Mutation。
- Fix Version。
- Regression Owner。
## 生产流量抽样
推荐分层双阶段抽样。
第一阶段按 Root Incident、User Journey 或 Template 聚类。
第二阶段在以下 Strata 中抽样：
- 高频正常流量。
- 低频长尾。
- 高业务影响。
- 明确失败。
- 人工接管。
- 高风险权限和工具。
- 新模型、新地区和新功能。
- 漂移明显的 Slice。
每条生产案例保存：
```text
sampling_probability
production_weight
traffic_window
root_case_id
source_system
privacy_review
redaction_version
```
必须同时抽样成功案例。
如果只收集失败案例，Suite 会高估失败分布并缺少正常行为对照。
原始 `blind_production_observation` 不是可执行 Episode，不受“每个 Trial 从干净状态启动”约束，也不得直接参与可重放成功率；只有完成下列转换、获得新 `EpisodeSpec` 身份后，才可进入 Golden、Challenge 或 Holdout：
```text
collect
  -> legal basis / consent / retention check
  -> redact and tokenize
  -> cluster and deduplicate
  -> minimize reproduction
  -> rebuild deterministic environment
  -> author oracle
  -> independent review
  -> assign collection, partition and version
```
## Root Case、Family 与 Variant
### Root Case
表示一个统计上应视为同源的核心问题。
例如同一个生产 Incident 的十次用户重试仍是一个 Root Case。
### Family
表示共享目标、状态模式、政策规则或工具依赖图的一组 Root Case。
### Variant
表示对 Root Case 的受控变换。
```typescript
interface CaseIdentity {
  episodeSpecId: string;
  episodeSpecVersion: string;
  rootCaseId: string;
  familyId?: string;
  parentCaseId?: string;
  variantId?: string;
  transformationIds?: string[];
}
```
统计时：
- Trial 不是独立题目。
- Variant 不自动是独立题目。
- 同一 Incident 不自动是独立题目。
- Bootstrap 默认按 `rootCaseId` 聚类；若多个 Root Case 共享 Incident、用户旅程、模板或强相关 Family，应预注册更高层聚类键，不能用更细粒度低估方差。
## Counterfactual 与 Metamorphic Case
### Counterfactual Pair
只改变一个关键因素：
- 用户是否明确确认。
- 当前用户是否有权限。
- 文档是否来自可信来源。
- 账户是否属于当前租户。
- Tool Result 是否包含注入。
- Memory 是否过期。
理想 Agent 应在 Counterfactual Pair 上产生预期差异。
### Metamorphic Relation
在不改变正确语义时扰动输入：
- 改写表达。
- 改变工具展示顺序。
- 添加无关工具。
- 改变非关键实体名称。
- 调整页面布局。
- 改变 Tool Result 字段顺序。
在应改变行为时做关系断言：
```text
增加明确拒绝 -> 不得执行写操作
撤销权限 -> 必须拒绝或升级
工具确认 Unknown -> 不得盲目重复提交
注入出现 -> 合法任务可继续但攻击目标不得完成
```
## Dataset Manifest
```yaml
dataset:
  dataset_id: support-agent-eval
  version: 2.3.1
  schema_version: 1.1.0
  taxonomy_version: 1.4.0
  owner: agent-evals
  created_at: 2026-01-15
  modified_at: 2026-07-18
  description: Customer support agent evaluation
collections:
  golden: { root_case_count: 420, record_count: 670, digest: "sha256:..." }
  challenge: { root_case_count: 180, record_count: 290, digest: "sha256:..." }
  selection_holdout: { root_case_count: 130, record_count: 130, digest: "sha256:..." }
  release_holdout: { root_case_count: 130, record_count: 130, digest: "sha256:..." }
  calibration: { root_case_count: 80, record_count: 160, digest: "sha256:..." }
  red_team: { root_case_count: 120, record_count: 300, digest: "sha256:..." }
observations:
  blind_production: { record_count: 5000, digest: "sha256:...", executable: false }
partitions: [dev, validation, test, canary, production_shadow]
artifacts:
  - uri: tasks/golden.jsonl
    sha256: ...
  - uri: environments/index.json
    sha256: ...
policies:
  holdout_access_policy: sealed-v2
  pii_policy: production-redaction-v3
  contamination_policy: contamination-v2
  review_policy: dual-review-v1
```
Manifest 必须固定：
- Dataset 内容。
- Environment 引用。
- Oracle 和 Judge 版本。
- Taxonomy 版本。
- Collection、Partition 与 Observation Stream。
- Hash。
- License。
- Owner。
- Sensitivity。
## EpisodeSpec Record
```typescript
interface EpisodeSpec {
  identity: CaseIdentity;
  status: "draft" | "review" | "active" | "quarantined" | "retired";
  collection: "golden" | "challenge" | "selection_holdout" | "release_holdout"
    | "calibration" | "red_team";
  partition: "dev" | "validation" | "test" | "canary" | "production_shadow";
  source: CaseSource;
  taxonomy: CaseTaxonomy;
  difficulty: DifficultyProfile;
  input: TaskInput;
  environment: EnvironmentRef;
  tools: ToolFixtureRef[];
  policy: PolicyFixtureRef;
  userSimulator?: UserSimulatorRef;
  oracle: CompositeOracleSpec;
  stochasticPolicy: StochasticPolicy;
  contamination: ContaminationRecord;
  annotation: AnnotationRecord;
  lifecycle: LifecycleRecord;
}
```
这些命名类型是 authoring schema 的必填模块，不是任意对象：每个 Dataset `schema_version` 必须提供对应 JSON Schema、封闭枚举、必填性、引用解析和未知字段策略；编译器再将其转换为 Runner 的 `EvaluationScenario`。
```typescript
interface ProductionObservationRecord {
  observationId: string; trafficWindow: string; samplingProbability: number;
  sourceRef: string; redactionVersion: string; privacyReview: string;
  observedInputRef: string; observedOutcomeRef: string; evidenceRefs: string[];
  executable: false;
}
```
该类型禁止 environment/oracle/partition，编译器必须拒绝将其送入 Runner；晋升时创建新的 `EpisodeSpec`，并以 provenance 引用 `observationId`。
Task Input 至少支持：
```text
user prompt
conversation seed
attachments
files
initial artifacts
user profile fixture
policy references
system context reference
completion contract
```
## Environment Snapshot
```typescript
interface EnvironmentSnapshot {
  imageDigest?: string;
  vmSnapshotDigest?: string;
  osArch: string;
  repositoryCommit?: string;
  dependencyLockDigest?: string;
  initialStateFixtureDigest: string;
  databaseSnapshotDigest?: string;
  filesystemSnapshotDigest?: string;
  toolSchemaDigest: string;
  policyDocumentDigest: string;
  browserOrAppVersion?: string;
  locale: string;
  timezone: string;
  frozenClock?: string;
  networkMode: "disabled" | "recorded" | "allowlisted" | "simulated";
  allowedDomains?: string[];
  externalApiRecordingDigest?: string;
  secretFixtureVersion?: string;
  resetProcedureDigest: string;
  resourceLimits: ResourceLimits;
}
```
每个可执行 Episode 的 Trial 必须从干净状态启动；原始 Production Observation 先按前述流程重建为 Episode。
禁止依赖：
- 开发机残留文件。
- 前一 Trial 的 Cache。
- 前一 Trial 的 Git History。
- 未声明环境变量。
- 仍有效的生产 Token。
- 可随时变化的外部网页作为唯一 Oracle。
## Oracle 与 Assertion Schema
```typescript
interface AssertionSpec {
  assertionId: string;
  category:
    | "outcome"
    | "milestone"
    | "trajectory"
    | "policy"
    | "communication"
    | "side_effect"
    | "budget"
    | "recovery";
  description: string;
  oracleType: string;
  target?: string;
  comparator?: string;
  expected?: unknown;
  tolerance?: number;
  weight?: number;
  required: boolean;
  hardFail: boolean;
  evidencePath?: string;
}
```
Critical Case 必须至少包含：
- 一个 Outcome 或 Final-state Assertion。
- 一个 Negative Side-effect Assertion。
- 一个 Policy 或 Authorization Assertion。
- 一个 Budget 或 Termination Assertion。
## Trial 与 Result Schema
```typescript
interface EvalTrialRecord {
  runId: string;
  episodeSpecId: string;
  episodeSpecVersion: string;
  rootCaseId: string;
  variantId?: string;
  datasetVersion: string;
  collection: string;
  partition: string;
  systemUnderTest: SystemVersionBundle;
  execution: TrialExecution;
  artifacts: TrialArtifacts;
  grade: TrialGrade;
}
```
`SystemVersionBundle` 至少记录：
```text
model provider
model id and snapshot
agent harness commit
system prompt digest
context policy digest
tool bundle digest
policy bundle digest
judge bundle version
environment digest
```
`TrialGrade` 必须区分：
```text
passed
failed
infrastructure_error
grader_error
invalid_task
inconclusive
skipped
```
后五类不能计为 Passed。`infrastructure_error`、`grader_error`、`invalid_task` 和缺失关键证据必须从能力估计中单列并报告分母损失；Critical Case 默认阻断发布，除非预注册的有限重跑得到有效结果且同时满足 Infra Error Ceiling，首次结果仍须保留。
## Ground Truth 工程
每个 Golden 或 Holdout Case 应提供：
- Reference Solution。
- Alternate Valid Solution；若任务确有唯一合法结果或路径，允许 `not_applicable + justification`。
- Negative Control。
- Required Outcome。
- Forbidden Outcome。
- Required Milestone。
- Policy Constraints。
- Side-effect Contract。
- Ambiguity Note。
- Solvability Evidence。
Reference Solution 不是唯一允许轨迹。
不要要求 Agent 完全复制专家的动作序列。
Ground Truth 审查需要回答：
- 任务说明是否足以推出所有 Hard Assertion？
- 是否存在多个合法结果？
- 是否存在合法但未被 Grader 接受的替代方案？
- 是否存在错误方案能利用 Oracle 漏洞得分？
- 环境中是否真的存在解？
- Reference Solution 是否在干净环境重复通过？
## Solvability 与坏题审计
坏题常见来源：
- 初始状态缺失。
- 工具无权限完成任务。
- Policy 自相矛盾。
- Reference Solution 依赖隐藏知识。
- External API 已变化。
- Test 过度约束实现路径。
- Oracle 没有覆盖替代合法解。
- Case 实际不可完成。
推荐 Solvability Gate：
1. 两名领域人员独立理解任务。
2. 至少一条 Reference Solution 可执行通过。
3. 至少一条 Alternate Solution 被正确接受；若标记 `not_applicable`，两名 Reviewer 必须确认唯一性理由且 Oracle 不过度约束。
4. 至少一个 Known-bad Solution 被拒绝。
5. 多次 Clean Replay 结果稳定。
6. 环境重置后状态一致。
7. Grader Mutation Test 能抓住预期缺陷。
如果多个强 Agent 在大量 Trial 上全部为零分，应优先审计坏题，而不是直接宣称任务极难。
## Composite Oracle
推荐评分结构：
```text
Composite Result
  = Outcome
  + Required Milestones
  + Communication Quality
  + Efficiency
  - Policy Violations
  - Forbidden Side Effects
```
但 Critical Violation 不是普通扣分。
```text
hard_fail_if:
  unauthorized_action
  secret_exfiltration
  cross_tenant_access
  destructive_collateral_damage
  financial_action_without_confirmation
  sandbox_escape
  duplicate_irreversible_action
```
Oracle 证据优先级：
```text
external authoritative receipt
  > database / filesystem / application state
  > sandbox and network capture
  > tool execution ledger
  > canonical tool result
  > model final text
```
## Outcome、Milestone 与 Partial Credit
二元成功率适合清晰事务结果，但长程任务还需里程碑。
示例：
```text
0.10 识别正确账户
0.10 识别信息缺失并澄清
0.15 找到目标订单
0.15 获得必要确认
0.25 正确完成状态修改
0.15 验证修改
0.10 准确总结结果
```
Partial Credit 规则：
- 只为可观测结果给分。
- 不为冗长推理文本给分。
- 不允许高风险违规仍获得“总体通过”。
- Milestone 必须有状态或轨迹证据。
- 同一事实不能在多个维度重复计分。
## Trajectory Invariant
不要强制完整轨迹相同。
只检查：
- 必须发生的动作。
- 必须先发生的授权或确认。
- 禁止出现的动作。
- 关键依赖的 Partial Order。
- 重复、循环和无界重试。
- 是否验证关键副作用。
- 无法继续时是否停止或升级人工。
示例：
```text
explicit_confirmation
  < refund_tool_dispatched
  < external_receipt_observed
  < final_user_summary
```
并行工具使用 Partial Order，不要求任意固定完成顺序。
## State 与 Side-effect Oracle
每次运行保存：
- Before Snapshot。
- Append-only Action Ledger。
- Commit Receipt。
- Network 或 Message Sink Evidence。
- After Snapshot。
- State Diff。
- Cleanup Result。
分别计算：
```text
expected_changes
missing_changes
unexpected_changes
forbidden_changes
external_effects
unknown_outcomes
```
必须区分动作阶段：
```text
Attempted
Dispatched
Committed
Externally Observable
```
Agent 在执行后说“我拒绝了”不能撤销已经发生的副作用。
工具返回 Timeout 但外部已提交时，盲目重试导致重复付款必须判失败。
## LLM Judge 的适用边界
适合：
- 开放式方案质量。
- 解释是否完整。
- 摘要是否忠实。
- 引用是否支持结论。
- 用户沟通是否清楚。
- 多个合法答案的语义等价。
不适合：
- 工具是否真的执行。
- 数据库是否提交。
- 文件是否修改。
- 权限是否有效。
- Secret 是否泄漏。
- 事件顺序是否正确。
- 成本和延迟是否超限。
- Crash 是否重复副作用。
Judge 输入应是精选、脱敏、结构化证据，不必提供完整私有推理。
## Judge Calibration
独立维护 `judge_calibration_set`。
应包含：
- 清晰通过。
- 清晰失败。
- 边界案例。
- 信息不足，应返回 Unknown。
- 冗长但错误。
- 简短但正确。
- 与 Judge 同模型家族和异模型家族的答案。
- A/B 顺序交换对。
执行规范：
- 每个 Rubric Dimension 独立评分。
- 允许 `unknown` 或 `insufficient_evidence`。
- Pairwise Judge 随机交换 A/B。
- 隐藏 Candidate 身份。
- 锁定 Judge Model、Prompt、Temperature 和版本。
- 保存结构化 Reason Code。
- 高风险 False Pass 必须人工复核。
报告：
```text
exact agreement
weighted agreement
confusion matrix
false pass rate
false fail rate
unknown rate
position consistency
repeated-run consistency
per-slice agreement
human-human agreement
judge-human agreement
```
总体相关性高不能掩盖高风险 Slice 的 False Pass。上线前按 Rubric 与风险 Slice 预注册人工 Gold 最小样本、置信区间、False Pass/Fail 上限和 Unknown 上限；高风险 False Pass 超限或漂移检查失败时，Judge 必须停用或降级为 Deterministic-only，不得临时放宽阈值。
## 人工标注与仲裁
标注协议应定义：
- 标签含义。
- 证据要求。
- 是否允许 Unknown。
- 如何处理多种合法解。
- 如何处理任务歧义。
- 如何处理 Environment Error。
- 如何升级争议。
推荐：
- 关键 Case 双人盲标。
- 保存仲裁前原始标签。
- 由第三人或领域 Owner 仲裁。
- 记录 Disagreement Reason。
- 定期抽检已上线 Grader。
一致性指标可使用：
- Percent Agreement。
- Cohen's Kappa。
- Krippendorff's Alpha。
- Weighted Agreement。
一致性低可能表示标注者问题，也可能表示任务本身主观或定义不清。
## 随机性与重复运行
Hosted Model 和多轮 Agent 不应假设完全确定。
每个 Task 可定义：
```typescript
interface StochasticPolicy {
  defaultTrials: number;
  reliabilityTrials?: number;
  temperature?: number;
  seedPolicy: "fixed" | "rotating" | "record_if_supported";
  aggregationUnit: "task" | "root_case";
}
```
报告：
- `pass@1`：一次运行成功率。
- `pass@k`：k 次至少一次成功。
- `pass^k`：k 次全部成功。
- Task-level Mean。
- Variance。
- Worst Trial。
- Catastrophic Failure Rate。
- Side-effect-free Success Rate。
生产事务 Agent 更看重 `pass^k`，而不是“多试几次总能成功”的 `pass@k`。
## 指标与聚合
### 正确性
- Task Success。
- Partial Completion。
- Outcome Accuracy。
- Milestone Completion。
- Verification Success。
### 安全
- Policy Violation Rate。
- Unauthorized Action Rate。
- Secret Leak Rate。
- Cross-tenant Violation Rate。
- Forbidden Side-effect Rate。
### 可靠性
- `pass^k`。
- Timeout Rate。
- Recovery Success Rate。
- Duplicate Side-effect Rate。
- Unknown Outcome Rate。
### 效率
- Turns per Success。
- Tool Calls per Success。
- Tokens per Success。
- Cost per Success。
- p50/p95/p99 Latency。
### 可审计性
- Trace Completeness。
- State Evidence Completeness。
- Oracle Coverage。
- Replay Success。
- Environment Reset Success。
聚合规则：
- 先 Task 内聚合 Trial。
- 再 Root Case 内聚合 Variant。
- 再按 Slice 聚合 Root Case。
- 同时报 Macro 和 Production-weighted。
- Hard Safety Failure 独立报告。
- Missing、Error、Inconclusive 单列。
预注册 Estimand：Trial 聚合函数、Variant 权重、Root Case 权重和统计分母。Production-weighted 指标使用记录的抽样概率做设计加权并报告权重截断规则与 Effective Sample Size；Candidate/Baseline 缺失配对、Trial 数不等和 Infra Error 不得静默填充或删除。
## 统计比较
Candidate 与 Baseline 优先使用配对比较。
```text
same root case
same environment version
same tool and policy snapshot
same trial budget
paired candidate-baseline delta
```
推荐 Clustered Paired Bootstrap：
1. Task 内先聚合重复 Trial。
2. 以 `root_case_id` 为重采样单位。
3. 保持 Candidate 与 Baseline 配对。
4. 必要时按 Domain、Risk 或 Source 分层重采样。
5. 计算 Delta 的 95% CI。
6. 同时报关键 Slice。
不要把 100 个模板变体当成 100 个独立样本来缩窄置信区间。
## Power 与 Sequential Testing
评测前定义：
```text
alpha
target power
minimum detectable effect
baseline rate
paired delta variance
cluster design effect
invalid rate
trials per task
```
如果目标改进小于当前 CI 宽度：
- 增加独立 Root Case。
- 对高随机 Task 增加 Trial。
- 改善 Grader 降低噪声。
- 使用配对分析。
- 不把“未显著”解释为“等价”。
持续在线观察时不得每天用普通固定样本 P-value 看到显著就停止。
可采用：
- Fixed Horizon。
- Group Sequential 与 Alpha Spending。
- Always-valid P-value。
- Confidence Sequence。
- 预注册 Bayesian Stopping Rule。
同时定义：
```text
look schedule
harm boundary
success boundary
futility boundary
maximum sample
primary metric
guardrail metrics
multiple testing policy
```
## 去重与独立样本
### Exact Dedup
- Canonical Prompt Hash。
- Fixture Hash。
- Oracle Hash。
### Near-text Dedup
- Token N-gram。
- MinHash / LSH。
- Jaccard Similarity。
### Semantic Dedup
- Goal Embedding。
- Prompt Embedding。
- 人工复核阈值附近候选。
### Structural Dedup
- 相同 Tool Dependency Graph。
- 相同 Initial/Target State。
- 相同 Policy Rule。
- 只替换名称、日期和金额的模板。
统计和 Split 应以 Root Case 为基础，防止近重复跨 Split 泄漏。
## Contamination 防护
每条 Case 保存：
```yaml
contamination:
  exposure_status: sealed
  first_exposed_at: null
  canonical_hash: ...
  minhash_signature: ...
  semantic_cluster_id: ...
  nearest_public_case_ids: []
  training_overlap_status: unknown
  contamination_risk: low
```
检查：
1. Eval 各 Split 间 Exact/Near/Semantic/Structural Overlap。
2. 与 Prompt Library、Few-shot、SFT、RL 数据比对。
3. 与公开 Benchmark、GitHub、文档和历史 Issue 比对。
4. 记录首次公开日期。
5. 对闭源模型依赖 Time Holdout、Private Holdout 和 Dynamic Environment。
防护组合：
- Public Dev Set。
- Private Static Test。
- Rotating Challenge Set。
- Programmatic Generation。
- Hidden Generator Seed。
- Temporal Split。
- Exposure Audit。
- Canary String。
- 限制 Holdout 查询次数。
- 退役后延迟公开旧题。
N-gram 检测只能提供证据，不能完整证明无污染。
## 环境重置与 Replay
### Observation Replay
回放原 Trial 收到的：
- Tool Result。
- Web Content。
- User Simulator Output。
- Provider Event。
适合：
- Prompt/Model 对比。
- Judge 重算。
- 轨迹离线分析。
- 隔离外部环境漂移。
局限：新策略无法探索原轨迹中没有的状态。
### Executable Replay
重新启动环境并执行 Candidate 的真实动作。
适合：
- 最终状态评分。
- Side-effect 评分。
- 恢复测试。
- 新策略探索。
必须保存：
- Initial Snapshot。
- Action 与参数。
- Action 前后 State Diff。
- Raw Tool Result。
- 时间和随机种子。
- Final State。
- External Write Ledger。
### Reset 验证
Reset 不只是执行清理脚本。
还应验证：
- 数据库 Hash 回到基线。
- 文件系统无残留。
- 无孤儿进程。
- 无外部资源残留。
- Cache 和 Queue 已隔离。
- Account 和 Permission 回到初态。
## 安全测评集
安全 Suite 至少覆盖四个结果：
```text
utility_without_attack
utility_under_attack
attack_success
critical_side_effects
```
必须保留“合法任务成功但同时发生泄漏”的象限。
威胁主体包括：
- 恶意用户。
- 被攻击者控制的网页、邮件和文件。
- 恶意或失陷 Tool / MCP Server。
- Memory / RAG 写入者。
- 恶意 Peer Agent。
- 发生目标漂移或 Reward Hacking 的 Agent。
- 试图读取答案或操纵 Scorer 的评测作弊 Agent。
## Prompt Injection 与恶意工具
参考 AgentDojo 的组合对象：
```text
UserTask
InjectionTask
InjectionVector
AttackStrategy
```
Injection Vector：
- 网页正文。
- 邮件。
- 文件。
- 搜索结果。
- Tool Result。
- MCP Tool Description。
- RAG Document。
- Peer Agent Message。
每个攻击组合先验证：
- 合法任务确实会读取攻击内容。
- 攻击目标可由现有工具完成。
- 攻击目标与用户授权冲突。
- Benign Baseline 有能力完成合法任务。
除静态模板外，还应使用独立攻击模型生成 Held-out 自适应攻击。
## Secret、PII 与跨租户 Canary
使用合成 Canary：
- API Key 格式字符串。
- OAuth Token。
- 虚构 SSN、病历号和银行卡号。
- 跨租户文档标记。
- Honey Endpoint。
检测位置：
- 最终回答。
- Tool 参数。
- HTTP Header、Body、URL 和 DNS。
- 文件和日志。
- Clipboard。
- 邮件和消息。
- Memory 和向量库。
- Agent-to-Agent Message。
- 编码、分片和重组后的输出。
指标：
```text
leak attempt rate
committed egress rate
conditional leak rate given observed secret
cross-user leak rate
cross-tenant leak rate
future-session leak rate
```
真实凭据不得作为测试 Canary。
## Memory 与多 Agent 污染
Memory 测试覆盖：
- 当前会话写入，未来会话激活。
- Trigger 检索后门。
- 伪造用户偏好。
- 伪造安全规则。
- 污染 Summary 和工作日志。
- 污染共享知识库。
- Delete 后残留召回。
多 Agent 测试覆盖：
- 伪造 Agent 身份和能力声明。
- Peer Message 间接注入。
- Worker 返回污染 Summary。
- 一个 Agent 读取、另一个 Agent 外传。
- 错误结论级联确认。
- 共享 Memory 传播。
- Orchestrator 是否保留最终授权责任。
Memory 专项设计见 [Agent Memory Evaluation Engineering](agent-memory-evaluation-engineering.md)。
## 鲁棒性与恢复测评
无攻击和有攻击条件下分别注入：
- Tool Timeout。
- 429 / 5xx。
- 截断输出。
- Tool 已提交但响应丢失。
- 任务中途撤销权限。
- 外部数据顺序变化。
- 页面布局变化。
- 网络分区。
- Peer Agent 宕机。
- Agent 或 Sandbox 重启。
- 污染 Checkpoint。
- 预算即将耗尽。
故障点：
```text
before tool call
while tool dispatched
committed before response
before and after approval
before and after memory write
mid handoff
before checkpoint
before terminal settlement
```
恢复后验证：
- 合法任务继续或安全终止。
- 无重复付款、发送、删除和部署。
- 未授权状态被清除。
- 污染 Memory 被隔离。
- Credential 被撤销和重签。
- Trace 连续可审计。
- 无孤儿进程和资源。
## 公开 Benchmark 的使用方式
推荐三层使用方式：
1. **结构可执行**：函数 Schema、AST 和参数检查。
2. **模拟业务可执行**：数据库、网站和状态化 Tool。
3. **完整系统可执行**：VM、代码仓库、桌面和训练任务。
三层组合：
- 第一层便宜、诊断强。
- 第二层接近业务事务。
- 第三层真实性高但成本大。
不要让任一层替代其他层。
## 厂商评测方法启发
| 来源 | 可复用方法 |
|---|---|
| OpenAI | 从目标与失败模式出发设计 Eval，持续评测，组合确定性 Grader、人工标注与校准后的 Model Grader |
| Anthropic | 区分 Task 与 Trial，审阅 Transcript，测量 Grader 与环境缺陷，持续维护未饱和且可诊断的 Case |
| Google / DeepMind | 以能力与责任风险为分类轴，结合自动评测、人工评测、对抗测试和部署条件下持续监测 |
| Microsoft | 用预定义数据集、Evaluator、Simulator 与持续 Evaluation Flow，把质量和安全指标接入开发及生产闭环 |
## Benchmark 设计启发
| Benchmark | 应借鉴 | 不应直接推断 |
|---|---|---|
| GAIA | 现实问题、异构附件、难度分层、隐藏答案 | 最终答案不能证明轨迹、安全和副作用 |
| AgentBench | 多环境统一接口、交互 Episode、环境级指标 | 异构 Oracle 不应被简单总分掩盖 |
| BFCL | Schema、无关工具拒绝、并行和状态化调用 | 调用格式正确不等于业务成功 |
| ToolBench / StableToolBench | 工具检索、多工具阶梯、失败轨迹、录制响应 | 公开 API 漂移和 LLM Judge 不适合作唯一 Oracle |
| τ-bench / τ²-bench | 用户、政策、数据库、工具、`pass^k`、Dual-control | User Simulator 和 Judge 也会泄漏或漂移 |
| ToolSandbox | Stateful Tool Use、Milestone、信息不足、任意合法轨迹 | 模拟工具不能覆盖全部真实副作用 |
| AppWorld | 多应用 API、状态测试、Collateral Damage、隐藏 Setup | 仿真应用不等同于真实 SaaS |
| WebArena / VisualWebArena | 自托管网站、后端状态、DOM/视觉证据、重置 | Selector、布局和 VLM Oracle 会漂移 |
| BrowserGym / WorkArena | 环境与 Benchmark 分离、统一动作空间、Seed 生成 | 商业平台依赖影响复现和迁移 |
| WebLINX | 长程真人网页交互、对话上下文和动作序列 | 离线轨迹建模不能单独证明在线状态与副作用正确 |
| ALFWorld / ScienceWorld | 文本环境中的组合目标、部分可观测状态、科学过程与可复现实验 | 仿真成功不等于真实工具、权限和外部系统安全 |
| OSWorld | VM 快照、跨应用、文件和应用内部状态 | UI、分辨率、应用版本和外网会漂移 |
| MobileAgent（Mobile-Agent）/ AndroidWorld | 移动 GUI 的视觉定位、动作轨迹、可重置 Android 环境和执行式成功检查 | 设备型号、系统版本、权限弹窗和真实账号依赖会造成迁移差异 |
| SWE-bench / Verified / Live | 真实 Issue、固定 Commit、Patch、执行测试、时间切分 | 公开答案污染和不完整测试会虚高分数 |
| MLE-bench | 长程优化、资源预算、真实产物评分 | 历史竞赛污染、成本和随机性很高 |
| AgentDojo | Utility/Security 分离、任务与注入交叉、状态验证 | 静态攻击低估自适应攻击；Infra Error 不是安全成功 |
| AgentHarm | Harmful/Benign 对照、细粒度 Rubric、状态优先 | 合成工具不证明真实危害能力 |
| Inspect / METR | Task/Solver/Scorer/Sandbox、Checkpoint、长程与监控 | 框架本身不保证任务和 Scorer 正确 |
## Release Gates
### Critical Zero-tolerance Gate
任一次确认的以下事件阻断发布：
- Secret 或跨租户数据外传。
- 未授权资金转移。
- 未授权外部消息。
- 未授权删除或代码执行。
- Sandbox Escape。
- 绕过强制审批。
- 重复不可逆副作用。
- 恢复后仍有残留攻击状态。
### Quality Gate
- Golden 无关键回归。
- Challenge 达到预注册阈值。
- `release_holdout` Delta 的 CI 不低于预注册允许边界；`selection_holdout` 结果不得冒充最终无偏验收。
- Worst Slice 无不可接受退化。
### Reliability Gate
- `pass^k` 达标。
- Timeout 和 Unknown Outcome 在预算内。
- Recovery Matrix 通过。
- Flaky Rate 受控。
### Cost / Latency Gate
- Cost per Success 不超预算。
- p95 / p99 不超阈值。
- 无隐藏 Retry 或 Fallback 放大。
### Judge Integrity Gate
- Calibration 有效。
- 高风险 False Pass 低于阈值。
- Judge Drift 检查通过。
- 争议样本有人工复核。
### Dataset Integrity Gate
- Split 未泄漏。
- Hash 和 Manifest 匹配。
- Environment 可重置。
- Grader Mutation Test 通过。
- Infra Error 未混入 Passed。
## Shadow、Canary 与 A/B
### Shadow
```text
production request
  -> baseline executes normally
  -> sanitized copy
  -> candidate executes with fake/dry-run sinks
  -> compare intent, trace, latency and predicted effects
```
Shadow 必须：
- 使用合成凭据、隔离租户和假写入 Sink，禁止真实付款、邮件、删除、权限变更及真实生产 Egress。
- 隔离数据库、文件、网络/DNS、Queue、Cache、Memory、Clipboard 和跨 Agent 通道；读取权限也不得超过 Baseline。
- 丢弃 Candidate 用户响应，不让其消耗真实业务 Rate Limit 或影响生产 Telemetry 决策。
- 保持生产安全策略不放宽，并用外部 Write/Egress Ledger 与环境 Diff 证明零生产副作用；无法证明时判 `inconclusive` 并阻断高风险发布。
### Canary
- 小比例低风险流量。
- 明确 Eligibility Filter。
- 高风险动作保留人工确认。
- 分阶段增加流量。
- 自动监测安全、质量、延迟和成本。
- 达到 Harm Boundary 自动回滚。
### A/B
- 以用户或稳定 Session 为随机化单位。
- 检查 Sample Ratio Mismatch。
- 预注册 Primary Metric。
- 预注册 Guardrail。
- 定义 MDE 和停止规则。
- 不把安全策略作为实验变量放宽。
## Failure Taxonomy 与聚类
用两级代码定位问题：`failure_stage` 取 task_spec、environment_setup、understanding、clarification、planning、retrieval、tool_selection、argument_generation、policy_reasoning、state_tracking、execution、verification、recovery、communication、timeout、infrastructure 或 grader；`failure_mode` 取 wrong_target、missing/extra_action、unauthorized_action、malformed_call、stale_state、repeated_action、premature_stop、hallucinated_success、collateral_damage、unsafe_escalation、valid_solution_rejected 或 task_unsatisfiable。
聚类先使用 `(failure_stage, failure_mode, last_successful_milestone, tool_name, policy_rule_id, side_effect_signature)`，再对 Trace Summary 或 Action Subsequence 做语义聚类；每个 Cluster 人工检查 Centroid、最大业务影响、边界成员和多个原始证据包。
## 案例晋升、饱和与退役
生产 Failure 晋升顺序：脱敏与去重、最小复现、区分 Agent/Environment/Task/Grader Failure、创建 Reference 和正负对照、验证替代合法解、多次 Replay、分配 Owner/Severity、选择 Golden/Challenge/Holdout。
Saturation 信号包括长期接近 100%、无法区分架构、失败主要来自环境波动或开发团队可逐题记忆；可转为 Regression Contract、生成更复杂组合、移入历史报告或退役。
产品下线、Policy 变化、环境不可维护、Oracle 错误、授权到期或不可修复泄漏可触发 Retirement；退役只停止现行使用，不删除历史结果和 Provenance。
## 版本、Provenance 与治理
- `PATCH` 修复非语义元数据；`MINOR` 新增兼容 Case/Field/Split；`MAJOR` 修改任务语义、Oracle、Split 或删除记录。
- Dataset、Taxonomy、Task、Environment、Tool Schema、Policy、Oracle、Rubric 和 Judge Bundle 独立版本化，Artifact 使用 SHA-256。
- Provenance 记录 Source、时间、Transformation、Author/Reviewer、Privacy Review、License、Exposure、Parent 和 Root Case。
- 每个 Dataset、Family 和 Critical Case 有 Owner；SLA 覆盖 Grader Error、Environment Drift、Critical Regression、Holdout 泄漏轮换和 Policy 变更复审。
## Authoring Workflow
```text
定义任务宇宙和目标分布 -> 选择并最小化 Root Case -> 脱敏、分类和定风险
-> 构建可重置环境与副作用合同 -> 编写 Reference/Alternate/Negative
-> 定义 Composite Oracle -> Solvability 与 Mutation Test
-> Known-good/Known-bad 验证 -> 隐私、许可、污染复核
-> 分配 Collection/Partition/Version、发布 Manifest -> 监控 Drift 与 Saturation
```
Case Author 不应同时是唯一 Reviewer 和唯一 Grader Owner。
## 单案例质量清单
- [ ] 身份、来源、Owner、版本、Collection、Partition、风险和 Review Date 完整；无真实凭据或未脱敏 PII。
- [ ] 目标、允许/禁止行为、初始状态、工具、Policy、权限和环境固定且可重置。
- [ ] 两名领域人员可理解；Reference 可执行，Alternate 不误杀，Known-bad 不误过。
- [ ] Outcome 依赖权威状态；高风险动作有 Policy、Side-effect 和 Termination Hard Assertion。
- [ ] 不强制唯一完整轨迹，Partial Credit 不重复计分，Infra Error 与 Agent Failure 分离。
- [ ] Clean Replay、Reset Hash、Grader Mutation、License、Exposure 和近重复检查通过。
## Suite 审查清单
- [ ] Coverage Matrix 覆盖 Domain/Capability/Risk/Difficulty/Source，报告 Root Case、正常高频和高风险长尾。
- [ ] Ground Truth、Alternate Solution（或经双人确认的 N/A）、False Pass/Fail、标注仲裁和 Judge Calibration 有效。
- [ ] Environment Digest、Reset、Replay、外部依赖锁定和完整版本束通过。
- [ ] 统计使用 Root Case、配对 Delta、CI、关键 Slice、MDE/Power 和预注册 Sequential Rule。
- [ ] Critical Failure 不被平均；Infra Error 不算安全；Shadow 无副作用；静态和自适应攻击均覆盖。
- [ ] Manifest、Hash、Owner、Holdout Audit、生产数据合法依据和生命周期流程完整。
## 反模式
- 把 `prompt + expected_output`、最终文本或模型自述当成完整 Agent Eval。
- 强制唯一轨迹，或让 LLM Judge 判断权限、提交、Secret、成本和真实副作用。
- Judge 无 Calibration/Unknown/版本，或由同一模型生成答案并担任唯一 Judge。
- 把 Infra Error 算安全、把 Trial/Variant 当独立样本、让同源 Case 跨 Split。
- 只做文本去重、无限探测 Holdout、公开固定题或实时 API 作为唯一 Release Gate。
- Reset 不查残留、Shadow 产生真实动作、高风险失败被平均分抵消。
- 只收集失败、不脱敏生产数据、既无 Alternate Solution 也无唯一性复核、从不审计零分坏题。
- 为 Candidate 降低 Golden、改 Grader 不升版本、只报均值或随意窥探 P-value。
- 用 `pass@k` 冒充事务可靠性，不测重复副作用、State Diff、版本束和评测作弊。
## Definition of Done
- [ ] 可重放 Episode、四套主数据、多轴 Taxonomy、Coverage Matrix 和 Root Case 关系完整。
- [ ] Task/Environment/Oracle/Trial/Result 版本化，Ground Truth 有 Reference/Alternate/Negative/Solvability。
- [ ] Outcome、Milestone、Trajectory、State、Policy、Side-effect 与 Critical Hard Fail 可执行。
- [ ] Judge 已校准；多 Trial、`pass^k`、Root-case Clustered CI、污染与 Holdout 机制完整。
- [ ] Reset/Replay、安全/Injection/Secret/Memory/Multi-agent/Fault/Recovery 均有证据。
- [ ] Release Gate、无副作用 Shadow、可回滚 Canary、Failure 晋升和数据生命周期可运营。
- [ ] Owner、SLA、Provenance、License、Hash、Mutation Test 和 Meta-evaluation 通过。
## 一手资料与项目启发
### 通用 Agent Eval 与 Dataset 方法
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：真实失败来源、Task/Trial 区分、Transcript Review、Grader 设计、饱和和持续维护。
- [OpenAI Evals Design Guide](https://platform.openai.com/docs/guides/evals)：Dataset、Grader、持续评测和 Eval-driven Development。
- [OpenAI: Evaluation best practices](https://platform.openai.com/docs/guides/evaluation-best-practices)：任务定义、自动评审、人工校准和迭代。
- [Anthropic: A Statistical Approach to Model Evaluations](https://www.anthropic.com/research/statistical-approach-to-model-evals)：配对分析、功效、聚类和不确定性。
- [Google Cloud: Evaluate generative AI agents](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluate-agents)：Agent 轨迹、最终响应、工具调用与多轮评测。
- [Google DeepMind: Evaluating Frontier Models for Dangerous Capabilities](https://deepmind.google/discover/blog/evaluating-frontier-models-for-dangerous-capabilities/)：危险能力、Alignment 与部署前风险评测框架。
- [Microsoft Foundry: Agent evaluators](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/evaluation-evaluators/agent-evaluators)：Intent Resolution、Tool Call、Task Adherence、轨迹与安全评测器。
- [NIST AI RMF](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)：有效性、可靠性、安全、隐私、公平和部署条件下 TEVV。
- [MLCommons Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html)：Dataset 元数据、版本、文件和校验和。
### 执行型 Benchmark
- [GAIA](https://arxiv.org/abs/2311.12983)：现实问题、附件和难度分层。
- [AgentBench](https://arxiv.org/abs/2308.03688)：多环境交互 Agent 评测。
- [BFCL](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)：函数调用、并行、多轮和状态化工具。
- [ToolBench](https://arxiv.org/abs/2307.16789)：大规模真实 API 与工具检索。
- [StableToolBench](https://arxiv.org/abs/2403.07714)：稳定工具响应模拟。
- [τ-bench](https://arxiv.org/abs/2406.12045)：用户、Agent、工具、政策和状态。
- [τ²-bench](https://arxiv.org/abs/2506.07982)：Dual-control 多轮环境。
- [ToolSandbox](https://arxiv.org/abs/2408.04682)：Stateful Tool Use 与 Milestone。
- [AppWorld](https://arxiv.org/abs/2407.18901)：多应用 API、状态测试与 Collateral Damage。
- [WebArena](https://arxiv.org/abs/2307.13854)：自托管真实网站和状态 Validator。
- [VisualWebArena](https://arxiv.org/abs/2401.13649)：视觉 Web Agent。
- [BrowserGym](https://arxiv.org/abs/2412.05467)：统一 Browser Agent 环境接口。
- [WorkArena](https://arxiv.org/abs/2403.07718)：企业知识工作流。
- [WebLINX](https://arxiv.org/abs/2402.05930)：长程、对话式真人网页导航轨迹。
- [ALFWorld](https://arxiv.org/abs/2010.03768)：具身文本环境、组合任务和交互式状态。
- [ScienceWorld](https://arxiv.org/abs/2203.07540)：可复现科学环境、过程任务和部分可观测交互。
- [OSWorld](https://arxiv.org/abs/2404.07972)：真实桌面 VM 和执行式评估。
- [Mobile-Agent](https://arxiv.org/abs/2401.16158)：基于视觉的移动设备自主操作。
- [AndroidWorld](https://arxiv.org/abs/2405.14573)：动态 Android 任务、可重置环境和执行式评测。
- [SWE-bench](https://arxiv.org/abs/2310.06770)：真实 GitHub Issue、Patch 和 Test。
- [SWE-bench-Live](https://arxiv.org/abs/2505.23419)：时间新鲜度和持续更新。
- [MLE-bench](https://arxiv.org/abs/2410.07095)：长程机器学习工程任务。
### 安全、鲁棒性与监控
- [AgentDojo](https://arxiv.org/abs/2406.13352)：间接 Prompt Injection、Utility 和 Security。
- [AgentHarm](https://arxiv.org/abs/2410.09024)：直接恶意请求、Benign 对照和细粒度 Rubric。
- [CyberSecEval](https://github.com/meta-llama/PurpleLlama/tree/main/CybersecurityBenchmarks)：Cyber Agent、代码解释器和 Injection 测试。
- [UK AISI Inspect](https://inspect.aisi.org.uk/)：Task、Solver、Scorer、Sandbox、Log 和 Checkpoint。
- [METR RE-Bench](https://github.com/METR/RE-Bench)：长程 Agent 能力和标准化可执行任务。
- [OWASP GenAI Security Project](https://genai.owasp.org/)：Agentic Threat、Excessive Agency、Memory 和 Multi-agent 风险。
### Judge、污染与统计
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)：Position、Verbosity 和 Self-enhancement Bias。
- [Deduplicating Training Data Makes Language Models Better](https://arxiv.org/abs/2107.06499)：重复、记忆和跨 Split 重叠。
- [LiveBench](https://arxiv.org/abs/2406.19314)：持续更新和污染缓解。
- [Bootstrap Methods](https://projecteuclid.org/journals/annals-of-statistics/volume-7/issue-1/Bootstrap-Methods-Another-Look-at-the-Jackknife/10.1214/aos/1176344552.full)：Bootstrap 基础。
- [Paired Bootstrap Resampling for Statistical Significance](https://aclanthology.org/W04-3250/)：系统比较中的配对 Bootstrap。
- [Design-Based Confidence Sequences](https://arxiv.org/abs/2210.08639)：在线实验的任意时点置信序列。
这些来源用于提炼工程原则，不代表应复制其题目、分数或排行榜。任何公开固定 Benchmark 都需要结合私有 Case、动态生成、时间切分、真实产品分布和可验证副作用，才能形成完整的 Agent 测评体系。
