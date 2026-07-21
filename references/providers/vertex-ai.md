# Google Vertex AI / Gemini

> 调研基线：2026-07-20。不要混淆 Gemini Developer API 与 Vertex AI 的认证、资源、配额和数据治理。

## 推荐接口

Gemini 模型优先使用 Google Gen AI SDK 和原生接口：

```text
generateContent
streamGenerateContent
countTokens
embedContent
```

REST 资源通常形如：

```text
projects/{project}/locations/{location}/publishers/google/models/{model}
```

已有 OpenAI SDK 代码可使用 Vertex OpenAI 兼容 endpoint，但新项目应优先原生 `Content` / `Part`，避免丢失 Gemini 特有能力。

## 认证

生产优先：

- Application Default Credentials；
- Service Account；
- Workload Identity；
- Workload Identity Federation；
- IAM 最小权限。

API Key 更适合测试或明确支持的场景。OAuth access token 会过期，长进程必须使用可刷新的 credential provider。

## Location 与模型标识

Global：

```text
location = global
endpoint = aiplatform.googleapis.com
```

Regional：

```text
location = us-central1
endpoint = us-central1-aiplatform.googleapis.com
```

模型可能是 Gemini model ID、MaaS model ID、完整 publisher model resource，或调优/自部署 endpoint。

不要为了缓解 429 自动跨区域，除非数据驻留策略允许。

## SDK

- Python：`google-genai`
- TypeScript：`@google/genai`
- Java：`com.google.genai:google-genai`
- Go：`google.golang.org/genai`

旧 Vertex AI SDK 的 `vertexai.generative_models` 等 GenAI 模块已在 **2025-06-24** 弃用，并于 **2026-06-24** 到达移除节点；新代码不要继续生成旧 SDK 用法。

## 工具调用

工具 schema 使用 OpenAPI/JSON Schema 风格。常见模式：

- `AUTO`
- `ANY`
- `NONE`
- `VALIDATED`（支持状态按模型核对）

模型返回 `functionCall`，应用执行后以 `functionResponse` Part 回传。支持情况允许时，应处理并行调用和流式函数参数。

## 结构化输出

使用 response MIME type 与 response schema 控制 JSON 输出。Schema 是受支持子集，应用端仍需校验。

结构化最终输出与 function calling 是独立能力，不要混用。

## 流式与多模态

`Content.parts[]` 可表达文本、图片、音频、视频、PDF、inline bytes、Cloud Storage URI、function call 和 function response。

流式时不要假设每个 chunk 只有文本；finish reason、safety 和 usage metadata 可能在后续 chunk 才出现。

Live API 用于低延迟双向音频/视频；Imagen、Veo 等生成能力使用相应专用接口。

## Agent 与 RAG

Vertex Agent 平台包括 ADK、Agent Runtime/Agent Engine、会话、Memory Bank、Code Execution、工具和可观测性。部分能力可能仍是 Preview。

Vertex AI Extensions 已于 **2026-05-26** 宣布弃用，计划在 **2026-11-26** 后关闭；新 Agent 应迁移到当前 Agent 平台。

RAG Engine 提供文档摄取、切块、embedding、corpus、检索、reranking 和 grounding。数据驻留与透明度能力需要按官方限制单独核验。

## Batch

Gemini Batch Prediction 支持 GCS JSONL 或 BigQuery。BigQuery 输入通常包含 `request` JSON 列，内容遵循 GenerateContentRequest；输入、输出和 job 区域要匹配。

## OpenAI 兼容层

典型 base URL：

```text
https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints/openapi
```

限制：

- 使用 Google Cloud Auth；
- token 需要刷新；
- 并非所有 Gemini Parts、grounding、thought signatures、Live API 和工具能力都能映射；
- 文件、缓存和资源 ID 不能假设与 Gemini Developer API 通用。

## 429 与容量

429 可能来自动态共享容量或 Provisioned Throughput。使用截断指数退避、平滑突发并读取错误信息。需要稳定 SLA 时评估 Provisioned Throughput。

## 最小 Python 示例

```python
import os
from google import genai

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
)

response = client.models.generate_content(
    model=os.environ["VERTEX_MODEL_ID"],
    contents="解释工具调用。",
)

print(response.text)
```

## 最小 TypeScript 示例

```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({
  vertexai: true,
  project: process.env.GOOGLE_CLOUD_PROJECT!,
  location: process.env.GOOGLE_CLOUD_LOCATION ?? "global",
});

const response = await ai.models.generateContent({
  model: process.env.VERTEX_MODEL_ID!,
  contents: "解释工具调用。",
});

console.log(response.text);
```

## 官方文档

- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent
- https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling
- https://docs.cloud.google.com/agent-builder/agent-engine/overview
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/quotas
- https://cloud.google.com/vertex-ai/generative-ai/docs/start/openai
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk
