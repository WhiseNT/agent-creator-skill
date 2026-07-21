# Cost Governance Engineering 细粒度工程设计

> 本设计把 Agent 成本治理定义为跨 Model、Prompt、Context、Tool、State、Policy、Harness、Provider Runtime、Event 和 Evaluation 的可计算控制平面。仅依据本地参考架构、工程文档和五个参考项目源码调研结论，不把 README 当作规范，不新增网络调研结论。

## 目录

1. [目标与非目标](#目标与非目标)
2. [职责边界](#职责边界)
3. [成本模型](#成本模型)
4. [总体架构与控制面](#总体架构与控制面)
5. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
6. [Usage Ledger 与 Price Catalog](#usage-ledger-与-price-catalog)
7. [预算层级、Quota 与 Rate Limit](#预算层级quota-与-rate-limit)
8. [Preflight、Reservation 与 Settlement](#preflightreservation-与-settlement)
9. [Routing Trade-offs 与成本决策](#routing-trade-offs-与成本决策)
10. [Retry、Fallback、Compaction 与 Subagent 归因](#retryfallbackcompaction-与-subagent-归因)
11. [成本分摊、Chargeback 与 Showback](#成本分摊chargeback-与-showback)
12. [异常检测、Cap 与 Approval](#异常检测cap-与-approval)
13. [Forecast、告警与多币种版本](#forecast告警与多币种版本)
14. [隐私、对账与计费失败](#隐私对账与计费失败)
15. [生命周期与状态机](#生命周期与状态机)
16. [决策流程](#决策流程)
17. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
18. [故障恢复与业务连续性](#故障恢复与业务连续性)
19. [CI 与生产成本测试](#ci-与生产成本测试)
20. [可观测性、指标与报告](#可观测性指标与报告)
21. [反模式](#反模式)
22. [实施清单](#实施清单)
23. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 目标与非目标

### 目标

- 把模型、token、tool、provider、embedding、rerank、storage、egress、worker、queue、artifact 和人工审批成本统一成可解释 ledger。
- 在动作前估算、预留预算，在动作后按 provider usage、receipt 或计量数据结算。
- 让预算从 organization、tenant、workspace、user、session、run、turn、attempt、tool 和 provider 可追溯。
- 区分估算、预留、实际、对账和冲销，避免并发运行导致预算超卖或重复计费。
- 把 retry、fallback、compaction、memory、subagent、cache miss 和失败 attempt 的成本纳入归因。
- 在价格变化、多币种、区域、折扣、套餐、最低计费单位和版本漂移下保持可重演。
- 让路由决策同时权衡 capability、latency、reliability、egress、privacy、quality 和成本。
- 支持 soft cap、hard cap、审批、降级、限流、暂停和 break-glass 的明确语义。
- 让 CI、离线评测、shadow、canary 和生产任务都可以设置成本预算与回归门禁。

### 非目标

- 不把成本优化变成静默降低质量、能力、安全或数据驻留要求。
- 不在 Provider Adapter 内偷偷切换模型、租户、价格或预算。
- 不用 token 单位替代 tool compute、存储、网络、worker 和人工成本。
- 不把供应商账单 API 当作唯一实时 source of truth。
- 不把用户内容、完整 prompt、文件路径或 secret 放入公共成本标签。
- 不规定财务总账、发票、税务或组织会计政策的全部实现。
- 不允许模型自行修改预算、价格、cap、chargeback owner 或币种。
- 不以平均 cost 隐藏失败重试、重复副作用或异常高峰。

### 核心原则

```text
estimate before action
reserve before concurrency
settle after observed usage
reconcile against authoritative receipt
attribute every attempt
never trade away policy for cost
```

## 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| Cost Control Plane | 预算、价格、quota、cap、规则版本 | 执行模型或工具 |
| Usage Collector | provider/tool/storage/worker 计量 | 修改 provider 账单 |
| Usage Ledger | 不可变 usage、reservation、settlement、adjustment | 直接扣款 |
| Price Catalog | 价格、单位、货币、有效期、来源和版本 | 选择租户预算 |
| Model Router | 在有效策略内选择路线 | 绕过 egress、policy 或预算 |
| Preflight Estimator | 估算 token、tool、storage、egress 和时间成本 | 声称实际账单 |
| Budget Manager | 层级预算、余额、reservation 和 cap | 改写 provider usage |
| Provider Runtime | request、stream、usage、错误和 provider metadata | 租户 chargeback |
| Tool Runtime | effect、duration、bytes、worker 使用和 receipt | 价格策略 |
| Context Runtime | token 估算、cache、compaction、embedding 使用 | 最终财务归属 |
| Event/Observability | 事件、trace、latency、usage projection | 作为结算唯一事实 |
| Billing Adapter | provider/内部账单导入和映射 | 业务路由 |
| Allocation Service | tenant/user/workspace/session/run 等维度分摊 | 伪造 usage |
| Finance/Owner | showback、chargeback、预算批准和风险接受 | 绕过技术 cap |
| Evaluation | 成本断言、回归、ablation 和 baseline | 使用生产真实扣款 |
| Host | 显示预算、估算、告警和审批 | 自行推断 ledger truth |

### 结算责任

- Provider usage 是模型服务的主要实际依据，但缺失时必须标记 estimated。
- Tool、worker、storage 和 egress 使用各自 backend 的计量或 receipt。
- Ledger 负责合并同一 idempotency key，拒绝重复 settlement。
- Allocation 只能引用已结算 entry，不得从 UI 文本估算 chargeback。
- Finance 导入的账单差异生成 adjustment，不修改历史 entry。

## 成本模型

### 成本维度

```text
Model = input tokens + output tokens + reasoning + cached read/write + provider surcharge
Tool = invocations + execution time + CPU + memory + process + network + external fee
Provider = request + region + deployment + reserved capacity + failure/retry + minimum unit
Embedding = input tokens + vector dimension + batch + index write
Storage = artifact bytes + event bytes + snapshot + cache + backup + retention duration
Egress = provider bytes + artifact download + webhook/message + cross-region transfer
Worker = queue time + runtime + CPU/memory/disk + scheduler + idle reservation
```

- model 成本按 attempt 记录，不能只按最终 run 记录。
- tool 既要有调用次数，也要有 duration、CPU、memory、bytes 和外部账单。
- storage 是 `bytes × duration × class`，删除和压缩产生 adjustment 或节省事实。
- egress 区分 provider 上传、工具网络、artifact 下载和跨 region。
- worker cost 包含等待、执行、重试、恢复和长期 lease，避免只看模型 token。
- embedding、rerank、memory extraction 和 compaction 是独立 operation。
- 固定费、最低承诺、保留容量、套餐折扣和共享基础设施按明确分摊规则处理。

### 成本单位

```typescript
type CostOperation =
  | "main_model" | "retry" | "fallback" | "compaction"
  | "memory_extraction" | "embedding" | "rerank" | "subagent"
  | "tool_execution" | "worker" | "storage" | "egress"
  | "reservation" | "adjustment";
type UsageUnit = "token" | "byte" | "millisecond" | "request" | "item" | "vector" | "gb_month" | "currency";
```

- 每个 entry 只使用一个主计量单位，复合成本使用 breakdown 子项。
- 单位转换必须记录 factor、rounding、source 和 version。
- 小数、最低单位和舍入只在结算边界执行，不能在每个 delta 丢失精度。

### 成本不变量

- 实际成本不能少于已确认 provider/tool/storage/egress 事实，除非有 adjustment。
- reservation 不能被两个互不相关的 action 同时消费。
- child cost 的父级总和不超过其 reserved parent budget；settlement 可释放未用预留。
- retry/fallback 产生新 attempt 与新 cost entry，不覆盖失败 attempt。
- reconciliation 是追加事件，不重写原始 usage。
- cost 估算未知时返回区间或 unknown，不写确定金额。

## 总体架构与控制面

```text
Policy/Tenant Budget -> Price Catalog -> Cost Rules -> Model/Tool Router
                                  |
Request -> Cost Preflight -> Reservation -> Kernel/Harness execution
                                  |
Provider/Tool/Worker/Storage meters -> Usage Collector
                                  |
Usage Ledger -> Settlement -> Reconciliation -> Allocation
                                  |
Metrics/Forecast -> Alerts -> Approval/Cap/Route controls
                                  |
Showback/Chargeback/Billing report -> Host/Finance
```

### 控制面对象

- `BudgetPolicy`：层级预算、周期、currency、soft/hard cap、审批和降级。
- `PriceCatalog`：provider、model、tool、storage、egress、worker 价格和版本。
- `RoutingCostPolicy`：质量下限、延迟目标、成本权重、隐私和区域约束。
- `QuotaPolicy`：速率、并发、token、bytes、工具次数和排队行为。
- `AllocationPolicy`：共享成本、标签、owner、归因 fallback 和 rounding。
- `AnomalyPolicy`：基线、阈值、窗口、检测动作和免疫规则。
- `BillingPolicy`：周期、账单来源、reconciliation、adjustment 和失败处理。

### 配置版本

```typescript
interface CostConfigSnapshot {
  snapshotId: string;
  budgetPolicyVersion: string;
  priceCatalogVersion: string;
  routingPolicyVersion: string;
  quotaPolicyVersion: string;
  allocationPolicyVersion: string;
  currency: string;
  effectiveAt: string;
  tenantScope: string;
  hash: string;
}
```

- run 内冻结 snapshot；配置变化只影响新 preflight 或显式 reauthorize。
- 账单报告可按历史 snapshot 重演，不读取当前价格覆盖过去成本。
- schema、默认值、优先级、币种和租户 scope 在发布前校验。

## 核心数据模型与 TypeScript 接口

### Usage

```typescript
interface UsageVector {
  inputTokens?: number;
  outputTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
  cacheWriteTokens?: number;
  toolCalls?: number;
  toolBytes?: number;
  wallClockMs?: number;
  cpuMs?: number;
  memoryByteMs?: number;
  storageBytes?: number;
  storageByteMs?: number;
  egressBytes?: number;
  embeddingTokens?: number;
  vectors?: number;
  workerMs?: number;
}
interface UsageSource {
  kind: "provider" | "tool" | "worker" | "storage" | "network" | "estimate" | "billing";
  sourceId?: string;
  meterVersion: string;
  observedAt: string;
  confidence: "estimated" | "observed" | "reconciled";
}
```

### Money 与 CostBreakdown

```typescript
interface Money {
  currency: string;
  micros: number;
}
interface CostComponent {
  operation: CostOperation;
  unit: UsageUnit;
  quantity: number;
  unitPriceMicros: number;
  money: Money;
  priceVersion: string;
  estimated: boolean;
  sourceRef?: string;
}
interface CostBreakdown {
  components: CostComponent[];
  subtotal: Money;
  discounts?: Money;
  taxes?: Money;
  total: Money;
  estimated: boolean;
  calculationVersion: string;
}
```

### Cost Attribution

```typescript
interface CostAttribution {
  organizationId?: string;
  tenantId: string;
  workspaceId?: string;
  principalId?: string;
  sessionId?: string;
  runId?: string;
  turnId?: string;
  attemptId?: string;
  toolExecutionId?: string;
  subagentRunId?: string;
  provider?: string;
  apiFamily?: string;
  model?: string;
  deployment?: string;
  region?: string;
  costCenter?: string;
  project?: string;
  purpose?: string;
  tags: Record<string, string>;
}
```

- attribution 字段从受信 execution context 继承，模型输出不能覆盖。
- user、workspace、project 等高基数值用于 ledger/query，不直接作为公开 metric label。
- 共享成本必须使用版本化 allocation rule，并保留原始总额和分配结果。

### LedgerEntry

```typescript
interface UsageLedgerEntry {
  entryId: string;
  idempotencyKey: string;
  operation: CostOperation;
  parentEntryId?: string;
  attribution: CostAttribution;
  usage: UsageVector;
  source: UsageSource;
  cost: CostBreakdown;
  status: "estimated" | "reserved" | "settled" | "reconciled" | "voided" | "adjusted";
  reservationId?: string;
  providerReceiptRef?: string;
  configSnapshotId: string;
  occurredAt: string;
  recordedAt: string;
}
```

### Reservation 与 Budget

```typescript
interface CostReservation {
  reservationId: string;
  parentReservationId?: string;
  attribution: CostAttribution;
  requested: CostEstimate;
  reserved: Money;
  consumed: Money;
  released: Money;
  status: "pending" | "active" | "settled" | "released" | "expired" | "cancelled";
  expiresAt: string;
  idempotencyKey: string;
}
interface BudgetNode {
  budgetId: string;
  parentBudgetId?: string;
  scope: "organization" | "tenant" | "workspace" | "principal" | "session" | "run" | "tool";
  scopeId: string;
  period: { start: string; end: string; timezone: string };
  currency: string;
  limit: Money;
  softCap?: Money;
  hardCap?: Money;
  reserved: Money;
  settled: Money;
  forecast: Money;
  status: "active" | "warning" | "paused" | "exhausted" | "closed";
  policyVersion: string;
}
```

### Estimate 与决策

```typescript
interface CostEstimate {
  estimateId: string;
  operation: CostOperation;
  lower: Money;
  expected: Money;
  upper: Money;
  assumptions: string[];
  usageForecast: UsageVector;
  priceVersion: string;
  confidence: number;
  validUntil: string;
}
interface CostDecision {
  action: "proceed" | "reserve" | "ask" | "throttle" | "downgrade" | "queue" | "deny" | "dry_run";
  reasons: string[];
  estimate?: CostEstimate;
  reservationId?: string;
  requiredApproval?: string;
  routeChange?: string;
  capState: "within" | "soft_exceeded" | "hard_exceeded" | "unknown";
}
```

### Price Catalog

```typescript
interface PriceCatalogEntry {
  priceId: string;
  provider?: string;
  apiFamily?: string;
  model?: string;
  deployment?: string;
  operation: CostOperation;
  unit: UsageUnit;
  currency: string;
  microsPerUnit: number;
  minimumQuantity?: number;
  tier?: { from: number; to?: number; microsPerUnit: number }[];
  discounts?: string[];
  effectiveFrom: string;
  effectiveTo?: string;
  source: string;
  version: string;
  verifiedAt?: string;
  status: "draft" | "active" | "retired";
}
```

### Reconciliation 与 Allocation

```typescript
interface BillingReceipt {
  receiptId: string;
  source: string;
  provider?: string;
  period: { start: string; end: string };
  currency: string;
  amount: Money;
  dimensions: Record<string, string>;
  lineItems: BillingLineItem[];
  sourceHash: string;
  importedAt: string;
}
interface ReconciliationResult {
  reconciliationId: string;
  receiptId: string;
  matchedEntryIds: string[];
  unmatchedReceiptAmount: Money;
  unmatchedLedgerAmount: Money;
  adjustments: string[];
  tolerance: Money;
  status: "matched" | "variance" | "blocked" | "accepted";
}
interface AllocationRecord {
  allocationId: string;
  sourceEntryId: string;
  ruleVersion: string;
  targets: { attribution: CostAttribution; shareBps: number; amount: Money }[];
  residual: Money;
  createdAt: string;
}
```

## Usage Ledger 与 Price Catalog

### Ledger 原则

- 每个执行动作先产生 estimate/reservation 事实，完成后追加 observed/settled 事实。
- `idempotencyKey` 至少包含 tenant、operation、execution/receipt、meter version 和 attempt。
- 增量 usage 可以进入 ephemeral projection，但最终 usage/cost 必须 durable。
- provider usage 缺失时记录 tokenizer、估算器版本、输入输出 hash 和不确定区间。
- cost entry 不允许删除；错误通过 void、adjustment 或 reconciliation entry 修正。
- parent/child entry 通过 parentEntryId、runId 和 subagentRunId 关联。

### 采集流程

```text
request metadata -> preflight estimate -> reservation
-> provider/tool/worker meters -> normalized usage
-> price lookup -> settlement -> allocation projection
-> billing import -> reconciliation -> adjustment/report
```

### Price Catalog 管理

- catalog 记录 provider、API family、model、deployment、region、operation、unit、tier 和有效期。
- 缺少 price、过期 price 或未知 deployment 时输出区间/unknown，不伪造确定金额。
- price 版本与模型目录、adapter、currency conversion 和合同来源关联。
- 供应商价格回溯修改不覆盖旧版本；新版本从 effectiveFrom 生效。
- minimum quantity、batch、cache、reasoning、input/output、免费层和折扣要单独表示。
- price 变更先对最近 usage replay，比较预算、route 和 chargeback 影响。

### 价格查找顺序

```text
exact provider+apiFamily+deployment+region+operation
-> provider+model+operation
-> catalog fallback profile
-> unknown interval
```

- 不允许用另一 provider 的价格默认为当前 provider。
- fallback model 产生新 price lookup 和新 attempt attribution。
- currency conversion 记录 source、timestamp、rate version 和 rounding。

## 预算层级、Quota 与 Rate Limit

### 层级关系

```text
organization -> tenant -> workspace -> principal -> session -> run -> turn/attempt/tool
```

- 子节点 limit 不能超过父节点可用 limit，除非有显式共享池规则。
- reserved、settled、forecast 和 released 分开，避免把未来成本当实际成本。
- budget period 使用明确 timezone；跨周期 run 按每个 operation 的 occurredAt 分桶。
- quota 限制资源速率和并发；budget 限制金额；二者同时生效。
- hard cap 阻止新 reservation；已有不可逆动作继续 settle 并标记超额。
- soft cap 触发告警、审批、降级、低成本 route 或更严格 quota。

### Quota 模型

```typescript
interface QuotaPolicy {
  quotaId: string;
  scope: BudgetNode["scope"];
  resource: "requests" | "input_tokens" | "output_tokens" | "tool_calls" | "egress_bytes" | "worker_ms" | "concurrency";
  windowMs: number;
  limit: number;
  burst: number;
  action: "queue" | "throttle" | "deny" | "fallback";
  priorityClasses: Record<string, number>;
  version: string;
}
```

- quota key 绑定 tenant/workspace/route/tool，避免跨租户共享桶。
- retry 和 fallback 计入原 owner 的 quota，不能用新 attempt 绕过。
- subagent fan-out 先预留 child 数量、tokens、cost 和 concurrency。
- rate limit 的拒绝、等待、取消和超时都进入 usage/diagnostic。

### BudgetTree 操作

1. 从受信 scope 找到从 root 到 action 的 BudgetTree。
2. 读取当前 settled、reserved、forecast 和 cap state。
3. 检查 operation、route、sensitivity、priority 和 period。
4. 对每个祖先节点原子 reserve，任一失败则全部释放。
5. 成功后生成 reservation ID 和 expiry。
6. 结算时沿树扣 actual、释放余量、更新 forecast。
7. 对账差异生成 adjustment 并保留原 reservation 证据。

## Preflight、Reservation 与 Settlement

### Preflight 输入

- model、provider、deployment、API family、region 和 capability。
- ContextPlan 输入 token、输出 reserve、reasoning reserve、tool reserve 和 cache 状态。
- tool 数量、effect、预计 duration、CPU、memory、bytes、外部 fee 和并发。
- artifact、storage、embedding、rerank、egress 和 worker 预算。
- retries、fallback、compaction、subagent 和未知 outcome 风险。
- price、currency、policy、tenant budget、quota、hard/soft cap 和历史基线。

### 估算算法

```text
collect operation plan -> select price version -> estimate usage interval
-> add retry/fallback/compaction reserve -> add tool/worker/storage/egress
-> apply discounts/minimums -> convert currency -> compare budget/cap
-> return proceed/ask/queue/downgrade/deny
```

- `lower` 用已知最小动作，`expected` 用历史或规则均值，`upper` 用 hard bound 或保守上界。
- 未知输出长度使用 output reserve；未知 tool duration 使用 policy ceiling。
- 预估必须列 assumptions，不把不确定性藏在单一数字。
- context overflow 或 provider capability 失败后，新的 estimate 重新计算。

### Reservation 规则

- reservation 是控制事实，不是最终账单。
- 并发动作必须先 reserve，不能先发请求再检查余额。
- reservation TTL 防止 worker 崩溃永久占用预算。
- 未使用部分在 settlement/release 中返回父级；已使用部分按 observed usage 结算。
- reservation idempotency 防止 retry 双重占用。
- reservation 超过剩余 budget 时可要求 approval 或选择更低成本 route，不能静默超支。

### Settlement

```text
execution terminal -> collect final usage -> calculate components
-> commit ledger atomically with execution settlement
-> release reservation remainder -> update budget tree
-> emit usage.updated/cost.settled -> project allocation/forecast
```

- model stream 断开仍保存已观测 token 和失败 attempt cost。
- tool `unknown_outcome` 使用 provisional settlement，receipt 查询后 reconcile。
- artifact/storage 结算可延迟，但必须有 period 和 byte snapshot。
- settlement timeout 不代表零成本；状态为 pending reconciliation。

## Routing Trade-offs 与成本决策

### 路由目标

```text
maximize quality/reliability/latency fit
subject to policy + capability + egress + privacy + budget + quota
minimize expected total cost, not only model token price
```

- cheapest model 不一定最便宜：更多 turns、tool calls、retry 和人工接管会放大总成本。
- 高质量模型若减少失败、上下文重复和工具循环，可能具有更低 cost per successful task。
- latency、provider availability、region、data residency 和 structured output 是硬约束时不可用价格抵消。
- routing decision 必须记录候选、拒绝原因、price version、policy version 和选择理由。

### RoutingCandidate

```typescript
interface RoutingCandidate {
  model: string;
  provider: string;
  apiFamily: string;
  deployment: string;
  region?: string;
  capabilityFit: number;
  expectedCost: CostEstimate;
  expectedLatencyMs?: number;
  reliabilityScore?: number;
  privacyFit: boolean;
  policyFit: boolean;
  reasonCodes: string[];
}
interface RoutingPolicy {
  qualityFloor: number;
  latencyTargetMs?: number;
  maxExpectedCost?: Money;
  weights: { quality: number; cost: number; latency: number; reliability: number };
  allowedFallbacks: string[];
  version: string;
}
```

### 路由决策流程

1. 构造候选 provider/model/deployment。
2. 过滤 capability、tenant policy、egress、region、credential 和 sandbox 兼容性。
3. 获取健康、quota、circuit、price 和历史成功/延迟信号。
4. 为每个候选计算 expected total cost 和 cost per success。
5. 应用 quality floor、hard cap、privacy 和 latency 硬约束。
6. 按稳定 tie-break 选择，记录全部 rejected reason。
7. 在 fallback 时重新执行 1-6，创建新 attempt。

### Fallback 成本规则

- fallback 只能由 policy、健康、能力或明确 retry 分类触发。
- 失败 primary 的 tokens、连接、工具准备和 reservation 不得抹掉。
- fallback 需重新做 context、egress、price、budget 和 approval 检查。
- fallback 不能把高敏感数据发送到更便宜但未允许的 provider。
- route change 进入 durable ModelChange/Fallback entry，并显示给成本报告。

## Retry、Fallback、Compaction 与 Subagent 归因

### 操作分类

| 操作 | 是否新 attempt | 是否新 ledger | 成本 owner |
|---|---:|---:|---|
| transport retry | 否，保留 transport attempt | 是/合并按 meter | 原 attempt/run |
| agent retry | 是 | 是 | 原 run、原因标签 |
| fallback | 是 | 是 | 原 run、provider 维度 |
| compaction | 否或独立 operation | 是 | 触发的 run/context |
| memory extraction | 独立 operation | 是 | session/workspace policy |
| embedding/rerank | 独立 operation | 是 | feature/purpose owner |
| subagent | child run | 是 | parent + child attribution |
| tool retry | 新 execution | 是 | 原 tool/run |

### Retry amplification

- 记录 `attempts_per_success`、失败成本、等待成本和重复 context tokens。
- retry budget 从 run/tenant 预算预留，不能无限用主模型预算。
- deterministic schema/policy deny 不应盲目 retry。
- unknown side effect 先查询，不创建第二个 execution。
- provider 429 使用 Retry-After、backoff、jitter 和总时限。

### Compaction 归因

- compaction input/output tokens、summarizer provider、latency 和 artifact bytes 独立记录。
- compaction 节省的未来 tokens 是 estimated saving，不抵销已经发生的成本。
- 失败重压缩、context overflow 和 cache miss 都保留原因。
- summary hash、source event range 和 token accounting 必须可重放。

### Subagent 归因

- parentRunId、childRunId、assignmentId、task node 和 owner 全部进入 ledger。
- child 预算是 parent remaining 的子集，预留先于 spawn。
- child model、tool、artifact、retry、compaction、embedding 和 worker 成本都单独列出。
- fan-out 共享成本按 declared allocation rule 分摊，不按最后完成者隐式归属。
- parent 只采用 validated result，但不删除失败 child 的成本。

## 成本分摊、Chargeback 与 Showback

### Allocation 维度

```text
tenant -> user/principal -> workspace -> project/cost center
session -> run -> turn -> attempt -> tool -> provider/model/region
```

- 直接成本优先按 run/attempt/tool/provider 归属。
- 共享成本按 tokens、requests、bytes、worker time、active tenants 或固定比例分摊。
- allocation rule 版本化，先保留 source amount，再生成 target amounts。
- residual、rounding 和无法归属的 orphan 成本进入明确 suspense bucket。
- 不得以用户输入文本或模型声明替代 execution context。

### Chargeback 与 Showback

- showback 是透明报告，不一定扣款；chargeback 需要 Finance 认可的 rule 和周期。
- 报告同时显示 actual、estimated、reconciled、adjustment、discount 和未分摊金额。
- tenant 只能看到本 tenant scope，管理员访问跨 tenant 聚合需 purpose 和 audit。
- 每个 invoice period 锁定 catalog、currency、allocation、usage cutoff 和 report version。
- 账单争议引用 entry、receipt、calculation version 和 reconciliation evidence。

### CostReport

```typescript
interface CostReport {
  reportId: string;
  period: { start: string; end: string; timezone: string };
  scope: CostAttribution;
  currency: string;
  totals: { estimated: Money; settled: Money; reconciled: Money; adjusted: Money };
  byOperation: Record<CostOperation, Money>;
  byProviderModel: Record<string, Money>;
  byOwner: Record<string, Money>;
  anomalies: string[];
  priceVersion: string;
  allocationVersion: string;
  generatedAt: string;
}
```

## 异常检测、Cap 与 Approval

### 异常维度

- 当前 run 相对同类 task 的 tokens、tool calls、latency、cost per success。
- tenant/workspace/principal 的日周趋势、突发、夜间偏离和 provider 分布。
- retry、fallback、compaction、subagent、cache miss 和 artifact egress 放大。
- 新模型、价格、policy、toolset 或 provider route 发布后的成本漂移。
- 失败 run、deny storm、queue backlog、worker idle 和未知 settlement。

### AnomalyRecord

```typescript
interface AnomalyRecord {
  anomalyId: string;
  scope: CostAttribution;
  metric: "cost" | "tokens" | "tool_calls" | "egress" | "retry" | "latency";
  observed: number;
  expected: { lower: number; upper: number; method: string };
  reasonCodes: string[];
  confidence: number;
  action: "observe" | "alert" | "throttle" | "ask" | "pause" | "deny";
  status: "open" | "acknowledged" | "resolved" | "false_positive";
  detectorVersion: string;
}
```

- 规则阈值与统计基线同时使用，且按 task、model、tenant 和 seasonality 分层。
- 新租户、新模型和低样本 scope 使用保守阈值和人工确认。
- anomaly detector 不直接改变不可逆业务状态，只触发 cap、queue、approval 或 policy action。
- 误报记录原因、免疫窗口和到期时间，不能永久关闭检测。

### Cap 语义

- soft cap：提示、报告、审批、低成本 route、降低并发或排队。
- hard cap：阻止新高成本 reservation，允许 settlement、查询、取消和安全恢复。
- emergency cap：incident/abuse 时临时 deny-all 或指定工具/provider，带 owner、TTL 和回滚。
- cap 命中产生 durable event，包含剩余额度、estimate、决策和 policy version。
- cap 不能阻止记录真实已发生的成本。

### 成本 Approval

- 预计超过 soft cap、昂贵模型、长 worker、跨 region、批量 egress 或高 fan-out 时可 ask。
- approval 显示 estimate interval、assumptions、route、provider、数据等级和可替代方案。
- approval 绑定预算 scope、cost ceiling、operation、route、有效期和 actor。
- 运行时超过批准 ceiling、改变 route 或新增副作用必须重新审批。
- approval host 断开保持 pending，不自动批准。

## Forecast、告警与多币种版本

### Forecast

```typescript
interface ForecastPoint {
  timestamp: string;
  lower: Money;
  expected: Money;
  upper: Money;
  method: "fixed_rate" | "rolling_average" | "seasonal" | "task_model" | "manual";
  confidence: number;
}
interface BudgetForecast {
  budgetId: string;
  asOf: string;
  points: ForecastPoint[];
  projectedEnd: Money;
  remaining: Money;
  scenarios: Record<string, Money>;
  assumptions: string[];
  modelVersion: string;
}
```

- forecast 使用 settled、reserved、pending、季节性、增长和 route mix。
- 只用实际成功请求会低估失败、retry、fallback 和 denied overhead。
- scenario 至少包括 baseline、高峰、provider failure、价格变化和 cap policy。
- forecast 变化超过阈值触发 owner、tenant 或 finance 告警。

### 告警

- 预算使用率达到 50/75/90/100% 等阶段阈值。
- reservation 长时间不 settlement、settlement drift 或 orphan cost。
- provider 价格、usage、账单或 currency conversion 变化。
- cost per successful task、retry amplification 或 egress 突增。
- catalog stale、unknown price、reconciliation variance 和 allocation residual。
- cost report 未及时生成、SIEM/ledger lag 或 projector mismatch。

### 多币种

- 账本保存 source currency 和 reporting currency，不覆盖原币金额。
- 汇率记录 source、timestamp、rate version、方向和 rounding。
- provider 账单以 provider currency 对账，再转换到 tenant/organization reporting currency。
- 价格 catalog 和 budget policy 的 currency 必须显式，不默认按环境变量猜。
- 报告显示 conversion gain/loss 或 rate variance，不混入 usage 误差。

## 隐私、对账与计费失败

### 隐私

- cost attribution 默认使用受信 ID、hash 和预定义标签，避免完整 prompt、路径、文件名和用户内容。
- cost per task 可用 task class、purpose、model/operation，不保存业务文本。
- 多租户报告使用聚合和 scope filter，导出有最小权限、expiry 和访问审计。
- 价格、预算和 provider credential metadata 也按 tenant sensitivity 保护。
- debug cost trace 使用 content hash、token count、artifact ref，不把 secret 放入标签。

### Reconciliation 流程

```text
close billing period -> import provider receipts -> normalize line items
-> match request/usage/receipt -> classify variance
-> create adjustment or investigation -> owner approval
-> lock report -> publish showback/chargeback
```

- 匹配优先 request ID、provider receipt、deployment、period、usage 和维度 hash。
- 供应商账单可能延迟、聚合、含最低费用或折扣；variance 不自动归咎模型。
- unmatched receipt、unmatched ledger、price mismatch、currency mismatch 和 duplicate 分别分类。
- tolerance、处理人、证据和最终 adjustment 必须可审计。
- 报告锁定后新账单使用 adjustment，不原地修改历史数字。

### Billing failure

- 账单导入失败不删除 usage ledger；状态变为 pending reconciliation 并告警。
- provider 账单不可用时，继续使用估算/observed 数据控制预算，但报告标记 provisional。
- payment/credit 失败按业务策略暂停新高成本 reservation，不伪造成功。
- provider API、内部 usage、财务账单和 chargeback 的失败分别归因。
- recovery 后重新导入、幂等匹配、修正报告并通知差异。

## 生命周期与状态机

### Cost Operation

```text
planned -> estimated -> preflight_checked -> reserved
-> running -> metered -> settled -> allocated -> reconciled -> reported
```

```text
estimated -> denied | queued | approval_pending
reserved -> expired | released | cancelled
settled -> adjusted | disputed | closed
```

- `planned` 保存操作、owner、route 和 scope。
- `estimated` 保存区间、假设、price version 和 confidence。
- `reserved` 原子扣减层级预算，带 TTL 和 idempotency。
- `metered` 收集 provider/tool/worker/storage/egress 事实。
- `settled` 计算成本并释放未用 reservation。
- `reconciled` 关联 authoritative receipt 或记录 variance。

### Budget 状态机

```text
active -> warning -> exhausted -> paused -> reset/renewed -> active
active -> emergency_capped -> recovering -> active
```

- warning 可继续执行但触发 policy obligation。
- exhausted 阻止新 reservation，不隐藏已发生成本。
- paused 可由 owner、incident 或 billing failure 触发。
- reset/renewed 记录 period、actor、policy 和 previous balance。

### Routing 状态机

```text
candidates -> filtered -> estimated -> approved -> selected
selected -> executing -> settled
selected -> rejected | fallback_candidate
```

- 每次 route 选择有 candidate snapshot 和 rejected reason。
- fallback 不能复用 primary attempt ID 或 approval。

## 决策流程

### 一次请求

```text
identity/tenant scope -> load CostConfigSnapshot -> classify task
-> resolve model/tool candidates -> context/token estimate
-> price lookup -> include retry/fallback/tool/worker/egress
-> check quota/budget/cap -> request approval if needed
-> reserve parent and child budgets -> execute
-> settle actual -> allocate -> reconcile/report
```

### Preflight 决策表

| 情况 | 决策 |
|---|---|
| price 已知、预算充足、低风险 | reserve and proceed |
| price unknown 或 catalog stale | 区间估算，必要时 ask/deny |
| soft cap 超过 | 告警、审批、低成本 route 或 queue |
| hard cap 超过 | deny new reservation 或安全恢复 |
| capability/egress 不兼容 | 过滤 route，不因便宜而降级安全 |
| context 超预算 | compaction/retrieval narrowing 后重估 |
| provider 429/capacity | bounded retry 或 policy-approved fallback |
| tool side effect unknown | query receipt，禁止盲目重试 |
| child budget 不足 | 缩小 assignment、queue 或拒绝 spawn |
| billing receipt 缺失 | provisional settlement，保持 reconciliation |

### 结束判定

- 成本控制完成不等于业务 run 成功；必须同时等待 tool、event、artifact 和 state settlement。
- run terminal 前至少有 estimate、reservation settlement、usage source、cost status 和 policy snapshot。
- unknown cost 不能报告为零；应报告 pending、interval 或 reconciliation required。

## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成

### Model

- Model Router 读取 capability、health、price、egress、quality 和 budget snapshot。
- Provider Runtime 为每个 attempt 记录 input/output/reasoning/cache tokens、usage source、request ID 和价格版本。
- transport retry 与 agent retry 分开归因；fallback 创建新 attempt。
- adapter 不能选择租户预算、偷偷替换 provider 或绕过 hard cap。

### Prompt

- Prompt 编译可说明 cost mode、预算边界、工具上限和何时请求审批。
- Prompt 不做预算 enforcement，不让模型修改 cost ledger。
- prompt version、section hash、token count 和 truncation 进入 preflight evidence。
- 低成本 mode 可能改 prompt/context/toolset，但必须创建新 mode/config snapshot 并可比较。

### Context

- Context 编译计算 token、byte、artifact、cache 和 compaction 成本。
- ContextPlan 保存 input/output reserve、source、provider egress、cache strategy 和 price assumption。
- summary、embedding、rerank、memory extraction 分独立 operation，不隐藏在主模型 cost。
- context overflow 后先 compaction/retrieval narrowing，再创建新 estimate/reservation/attempt。
- 不以机械截断换取低 token 而破坏 tool call/result、approval 或安全上下文。

### Tool

- Tool profile 提供 effect、duration、CPU、memory、network、storage、external fee 和 retryability。
- 工具调用前预估，运行中 meter，完成后通过 receipt/usage settle。
- 大输出 artifact storage 与 egress 分开计费，摘要成本归触发 run。
- unknown side effect 使用 provisional entry，查询后 reconcile。
- 工具结果不应让模型通过伪造数字修改 ledger。

### State

- Session 保存 CostEstimate、Reservation、Usage、Settlement、BudgetWarning、RouteChange 和 Adjustment 语义 entry。
- Event Store 保存不可变 usage/decision/settlement 事件；projector 生成预算和报表视图。
- replay 只重建 ledger/projection，不再次调用 provider、tool、billing 或 payment。
- compaction 保留预算、pending approval、reservation、unknown cost 和 reconciliation cursor。

### Policy

```text
identity/scope -> allowed operation -> egress/capability
-> estimate -> budget/quota -> cap/approval -> route
-> execution meter -> settlement -> audit
```

- 成本 policy 不能放宽安全 policy；低成本 route 仍需 capability、egress 和 privacy 合规。
- policy 变化使 estimate/reservation 失效时，必须重新 preflight。
- cap、quota、approval、priority 和 fallback 的顺序要版本化。

### Harness

- Harness 负责 BudgetTracker、ReservationManager、Cancellation、Retry/Fallback 和 child budget。
- 在 model/tool/subagent/worker 前预留，在事件后 settlement。
- 父取消传播到 child、provider、tool、queue 和 worker，释放未用 reservation。
- Harness 把 cost events 与 durable state、audit、trace 和 Host 分开投影。
- UI 显示 estimate、actual、pending 和 cap state，不从文本推断账单。

## 故障恢复与业务连续性

### 故障分类

- price catalog stale、unknown model、currency rate unavailable。
- budget store conflict、reservation timeout、quota service unavailable。
- provider usage missing、stream EOF、tool meter crash、worker loss。
- event append、ledger、artifact、billing adapter 或 reconciliation failure。
- provider 429/5xx、fallback storm、retry amplification 和 subagent fan-out。
- process crash 位于 reservation、side effect、usage、settlement 或 release 边界。

### 恢复算法

```text
load last checkpoint -> verify config/price/budget versions
-> inspect reservation and in-flight operation -> query usage/receipt
-> classify spent/unknown/unspent -> settle provisional or release safely
-> rebuild budget projection -> resume, queue, cap or manual review
```

- reservation 已存在但 operation 未开始且能证明未执行时释放。
- provider request 已发出但 usage 不明时保留 provisional cost，不自动归零。
- tool side effect 可能发生时先查询 receipt/idempotency，再决定补写或补偿。
- ledger append 重试使用 idempotency key；失败不再发起第二次外部动作。
- price/FX 不可用时使用受限估算和 hard safety cap，不能无限允许未知成本。
- budget projection 不一致时以 ledger replay 重建，报告暂时 stale。

### 降级矩阵

| 故障 | 允许 | 禁止 |
|---|---|---|
| Price Catalog 不可用 | 已缓存版本、区间估算、低风险任务 | 报确定价格或无限高成本请求 |
| Budget Store 不可用 | 已预留小任务或只读模式 | 无 reservation 的高成本写入 |
| Usage provider 缺失 | provisional settlement | 报告零成本 |
| Billing 导入失败 | ledger/forecast 控制 | 删除本地 usage |
| Artifact meter 失败 | metadata-only 小结果 | 无界存储/外发 |
| Worker 崩溃 | checkpoint/reconcile | 并行重复不可逆任务 |
| FX rate 缺失 | source currency 暂存 | 伪造 reporting currency |

## CI 与生产成本测试

### 成本测试模型

- unit：token estimator、price lookup、rounding、budget tree、reservation CAS、allocation。
- component：Usage Collector、Ledger、Catalog、Router、Forecast、Alert 和 Billing Adapter。
- deterministic scenario：scripted model/tool、fixed clock/IDs、固定价格和 fake receipt。
- replay：provider raw frame、tool meter、event、billing line item 和 reconciliation。
- load/soak：并发 reservation、fan-out、queue、event throughput、storage meter。
- fault injection：crash、duplicate、timeout、price stale、usage missing、billing delay。
- production shadow：真实 task 的 sanitized metadata + dry-run/fake tool，不执行副作用。

### CostAssertion

```typescript
interface CostAssertion {
  type: "budget" | "operation_cost" | "cost_per_success" | "allocation" | "reconciliation" | "forecast";
  severity: "hard" | "soft";
  maxCost?: Money;
  maxTokens?: number;
  maxToolCalls?: number;
  maxRetries?: number;
  maxEgressBytes?: number;
  expectedOperations?: CostOperation[];
  requiredSources?: UsageSource["kind"][];
  tolerance?: Money;
}
```

### CI 门禁

- presubmit：估算、价格解析、预算树、reservation 幂等、单 operation ledger。
- merge：retry/fallback/compaction/subagent 归因、provider replay、allocation 和 cost regression。
- scheduled：多 seed、load、soak、forecast、billing reconciliation、price update 和 anomaly calibration。
- release：关键 tenant/task、hard cap、egress、shadow/canary、生产配置 snapshot 和回滚。
- hard gate：预算越界、重复 settlement、漏计 retry、未知成本报零、cross-tenant allocation、重复副作用。
- soft gate：实时 provider 波动、开放式质量与 cost/latency trade-off，需要人工审查。

### 必测场景

1. 同一 idempotency key 重复 settlement 只产生一个实际成本。
2. 并发 child reservation 不超卖 parent/tenant budget。
3. provider 断流保留失败 attempt usage，fallback 成本独立归因。
4. compaction、embedding、rerank、memory 和 subagent 不漏计。
5. tool side effect 后 crash 不重复执行，provisional entry 可对账。
6. price catalog 版本切换后历史 report 仍可重演。
7. multi-currency rounding、FX 缺失和 provider billing variance。
8. soft/hard/emergency cap、approval、queue、deny 和 recovery。
9. anomaly detector 对 retry storm、fan-out 和 egress flood 告警。
10. tenant/user/workspace/session/run/tool/provider 分摊总和与 source total 一致。
11. replay 不重新请求 provider、tool、billing 或 payment。
12. CI cost budget 失败时保存 evidence、版本和首次失败结果。

## 可观测性、指标与报告

### Trace 层级

```text
session -> run -> preflight -> price lookup -> reservation
-> model/tool/worker execution -> usage meter -> settlement
-> allocation -> reconciliation -> report/alert
```

### 字段

```text
trace_id tenant_hash workspace_hash session_id run_id turn_id attempt_id
operation provider api_family model deployment region price_version
config_snapshot budget_id reservation_id ledger_entry_id parent_entry_id
usage_vector estimated/observed/reconciled cost currency retry/fallback
compaction/subagent/tool/storage/egress worker dimensions cap/approval
reconciliation status anomaly_id code/config/dataset version
```

- 完整 prompt、secret、用户路径和业务 payload 不进入普通 cost trace。
- 高基数维度只在受控 ledger/query 使用；metrics 使用低基数分类。
- cost report、ledger、billing 和 dashboard 的版本必须可关联。

### 指标

- preflight latency、estimate confidence、estimate-to-actual error。
- reservation success/conflict/expiry/release、reserved-to-settled ratio。
- cost by operation/provider/model/route/tenant/workspace/purpose。
- cost per run、cost per success、cost per accepted side effect。
- input/output/cache/reasoning/tool/embedding/storage/egress/worker 占比。
- retry amplification、fallback rate、compaction overhead、subagent overhead。
- budget utilization、soft/hard cap hit、approval wait、quota throttle。
- unknown/provisional settlement、reconciliation variance、unmatched amount。
- forecast error、price freshness、FX freshness、allocation residual。
- queue delay、worker idle、artifact retention 和 cache savings。

### SLO 示例

```text
ledger durability = durable entries / accepted operations
settlement completeness = settled or provisional entries / terminal operations
reservation correctness = no double-spend and no orphan beyond TTL
allocation conservation = allocated total + residual = source total
reconciliation timeliness = closed reports / billing periods
cost control safety = hard-cap bypasses = 0
```

- SLO 分母包括失败、取消、retry、fallback、unknown 和 denied where applicable。
- 不以只统计成功请求的平均 cost 作为唯一指标。
- report 需区分 estimated、settled、reconciled、adjusted、pending 和 disputed。

### 报告与告警

- tenant report：周期、actual、forecast、budget、cap、top operation、provider mix、异常和建议。
- engineering report：cost per success、retry waste、cache、tool/worker/storage/egress 分布。
- finance report：source receipt、line items、currency、discount、allocation、variance 和 adjustment。
- operator alert：reservation stuck、unknown cost、hard cap bypass、price stale、ledger lag 和 forecast breach。
- 安全敏感数据只在受控 report 中展示，访问本身写 audit。

## 反模式

1. 只用最终回答 token 计费。
2. 忽略失败 attempt、retry、fallback、compaction、memory、embedding、rerank 和 subagent。
3. 先执行后检查 budget，或并发执行不做 reservation。
4. 以 provider adapter 内部逻辑偷偷换低价模型。
5. 用当前价格覆盖历史 usage，无法重演旧账。
6. price unknown 时写零或写任意默认价格。
7. 将 reservation 当作 actual，或不释放未使用 reservation。
8. settlement retry 没有 idempotency key。
9. tool、worker、storage、egress 成本全部塞入 model cost。
10. 只按 tenant 归因，丢失 run、tool、provider 和 operation 维度。
11. 共享成本按最后完成者或模型自述归属。
12. 高基数 user/path/prompt 直接作为 metrics label。
13. 多币种没有 source currency、FX version 和 rounding 证据。
14. 对账差异直接改历史 ledger，而非追加 adjustment。
15. billing failure 时删除本地 usage 或报告零成本。
16. hard cap 只阻止 UI，不阻止 worker、subagent 或 fallback。
17. soft cap 没有审批、告警、降级或 queue 语义。
18. anomaly detector 直接改变不可逆业务状态。
19. 用最便宜模型牺牲 capability、privacy、egress 或 safety。
20. 只测试 happy path，不测试 crash、unknown、duplicate、replay 和账单延迟。
21. 把 shadow/cost test 接到真实付费副作用工具。
22. 把 forecast 当财务结算或把账单当实时预算余额。
23. report 未标 estimated、provisional、reconciled 与 disputed。
24. 删除 ledger 以“修复”误计，而不保留审计和 adjustment。
25. 把模型自述的“节省了成本”当作计量事实。

## 实施清单

### V1：Ledger 与预算

- [ ] 定义 UsageVector、Money、CostComponent、LedgerEntry 和 idempotency key。
- [ ] 建立 PriceCatalog，支持 provider/model/deployment/operation/unit/version。
- [ ] 建立 BudgetNode、QuotaPolicy、Reservation 和原子父子预算扣减。
- [ ] 实现 preflight estimate 的 lower/expected/upper 与 assumptions。
- [ ] 实现 observed/estimated/reconciled source 状态和 provisional settlement。
- [ ] 覆盖 retry、fallback、compaction、embedding、rerank、memory、subagent。

### V2：路由与归因

- [ ] 实现 capability/egress/policy/health/price/quality 过滤。
- [ ] 实现 expected total cost、cost per success 和稳定 route 选择。
- [ ] 记录 RoutingCandidate、rejected reason、ModelChange 和 fallback attempt。
- [ ] 实现 tenant/user/workspace/session/run/turn/attempt/tool/provider attribution。
- [ ] 实现 shared cost allocation、residual、rounding 和 rule version。
- [ ] 提供 tenant showback、owner view 和 finance chargeback report。

### V3：异常与财务闭环

- [ ] 实现 soft/hard/emergency cap、approval、queue、throttle 和 deny。
- [ ] 实现异常检测、baseline、anomaly suppression 和恢复动作。
- [ ] 实现 forecast、budget alert、price freshness、FX freshness 和 variance alert。
- [ ] 实现 provider billing import、line item match、reconciliation 和 adjustment。
- [ ] 实现多币种 source/reporting amount、rate version 和审计。
- [ ] 定义 billing failure、pending、dispute、period lock 和重导入流程。

### V4：测试与生产运营

- [ ] 建立 deterministic model/tool/worker/store/billing testkit。
- [ ] 在 reservation、side effect、usage、settlement、release、allocation、reconciliation 前后注入 crash。
- [ ] 建立 provider/tool/storage/egress/worker meter conformance。
- [ ] 建立 CI presubmit/merge/scheduled/release 成本门禁。
- [ ] 运行 shadow、canary、load、soak、forecast 和 cost anomaly calibration。
- [ ] 建立成本报告、SLO、告警、owner、runbook 和季度预算回顾。

## 五个参考项目的启发来源

### Pi

- headless agent loop、统一 EventStream、AgentSession/session tree 启发 usage、cost、attempt 和父子运行归因。
- provider event、tool loop、compaction 和可恢复 session 启发失败 attempt、context compaction、stream usage 与 settlement 边界。
- CLI/TUI/RPC 共用 runtime 启发 cost control 不能绑定某个 UI，报告应从 durable state 投影。
- 依据：本地参考架构、Agent Harness、Provider Runtime、Event/State 文档已记录的源码范围。

### Grok Build

- Session/ChatState/Sampler actor 启发单写者预算状态、attempt 计量和并发 reservation 的顺序性。
- sampler 多层、permission、folder trust、sandbox 和输出限制启发 route、policy、tool/worker 成本与安全约束联合决策。
- 并行工具和路径锁启发 tool cost 的 execution ID、资源 owner、并发上限和结果归因。
- 依据：本地 session、sampler、tools、permission、sandbox 源码归纳。

### OpenCode

- client/server、session/message/part、事件总线和 projector 启发 Usage Ledger、成本事件、重放和多客户端报告。
- snapshot/patch/revert 启发 artifact、storage、diff、worker 和副作用成本的可验证基线。
- permission、MCP/LSP 与 server 分离启发 provider/tool/extension 成本的独立维度和 provenance。
- 依据：本地 session、server、tool、permission、snapshot 源码归纳。

### Claude Code

- permission modes、hooks、skills、subagents、memory、计划和任务工作流启发 cost mode、子 Agent 预算、审批和最小必要 context。
- 长任务、compaction 与任务状态启发 retry/fallback/compaction/subagent 不能隐藏成本，必须可恢复和可归因。
- 公开能力和安全语义以本地文档已标注的 Anthropic 官方资料为准，辅助源码不作为规范。
- 依据：本地 Context、Harness、Permission/Sandbox、Subagent、Evaluation 文档归纳。

### OpenClaw

- AgentHarness registry 与 agent-core 分层启发 Model/Tool/Worker/Provider 成本控制通过 registry 组合，而非 adapter 私藏规则。
- Gateway/channel、后台运行和 session key 启发 background worker、queue、delivery、lease 和 cost attribution 解耦。
- tool/sandbox/elevated、事务化插件和 memory flush 启发 worker、扩展、artifact、恢复和失败回滚成本治理。
- 依据：本地 agent-core、harness/registry、openclaw-tools、plugins、Gateway 源码归纳。

本设计的实现审查应回到已有本地参考文档及其记录的一手源码范围；若增加 provider、价格、税务、区域、合同或组织 chargeback 规则，应另行补充来源、版本、迁移和契约测试。
