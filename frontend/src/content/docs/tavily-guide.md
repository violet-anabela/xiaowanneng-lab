---
title: Tavily 使用指南
description: 面向 LLM / AI Agent 的联网搜索 API，以及它的官方 Python SDK tavily-python
order: 3
---

# Tavily 使用指南

> 面向 LLM / AI Agent 的联网搜索 API，以及它的官方 Python SDK `tavily-python`

---

## 1. 这是什么

Tavily 是一个搜索 API，但它和 Google / Bing 那类搜索 API 的定位不同：**它的输出是给模型看的，不是给人看的。**

普通搜索 API 返回一堆链接和 meta description，你想拿到正文，还得自己写爬虫、处理反爬、解析 HTML、清掉导航栏和广告。Tavily 把这一整套做完了——你给一个 query，它去搜索引擎检索、抓取候选网页、提取正文、过滤噪音，最后返回结构化的干净内容，可以直接拼进 prompt 喂给模型。

所以它常见的用途是：

- 给 LLM 加联网能力（解决知识截止 / 实时信息问题）
- RAG 系统的外部检索层
- Agent 的 research / browse 工具
- 定向监控某几个域名的新闻更新

它是 LangChain、LlamaIndex、GPT Researcher 等框架里默认或常见的搜索后端。如果你在某个项目的依赖里看到 `tavily-python`，基本就是这个项目要给模型加联网搜索。

**注意包名和导入名不一致：**

| | 名称 |
|---|---|
| PyPI 包名 | `tavily-python` |
| Python 导入名 | `tavily` |
| 主类 | `TavilyClient` / `AsyncTavilyClient` |
| 许可 | MIT |
| 依赖 | `httpx`、`requests`、`tiktoken` |

---

## 2. 核心能力

SDK 覆盖 Tavily REST API 的全部功能，四个主要方法：

| 方法 | 作用 | 典型场景 |
|---|---|---|
| `search()` | 联网搜索，返回排序好的正文片段 | 给模型补充实时信息 |
| `extract()` | 给定 URL 抓取正文（单次最多约 20 个 URL） | 已知链接，要全文 |
| `crawl()` | 按自然语言指令遍历站点并抽取内容 | 抓一整个文档站 |
| `map()` | 只梳理站点结构，返回 URL 列表 | 先探路，再决定抓哪些 |

同步用 `TavilyClient`，异步用 `AsyncTavilyClient`，两者接口完全一致，只是后者所有方法都是协程。

---

## 3. 准备工作

### 拿 API Key

去 [app.tavily.com/home](https://app.tavily.com/home) 注册登录，key 就在 dashboard 的 API Keys 区块。新账号会自动生成一个，不需要手动创建；要多个就点旁边的 `+`。

Key 以 `tvly-` 开头。免费额度是每月 1000 credits，不需要绑卡。

> **国内网络提示：** `app.tavily.com` 和 `api.tavily.com` 都需要代理才能访问，注册那一步就得先挂上。

### 安装

```bash
pip install tavily-python python-dotenv
```

### 配置 Key

不要硬编码在代码里。项目根目录建 `.env`（记得加进 `.gitignore`）：

```
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx
```

---

## 4. 最小示例

```python
import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

response = client.search(
    "Anthropic 2026 年 8 月发布的新模型",
    topic="news",
    time_range="month",
    include_answer="advanced",
    max_results=5,
)

print("总结:", response["answer"], "\n")

for item in response["results"]:
    print(item["title"])
    print(item["url"])
    print(item["content"][:200], "...\n")
```

关于这个 query 的两点说明，时效性查询很容易踩：

- **别只写「最近」「最新」**。搜索引擎不知道「最近」指什么时候，容易把两年前的旧文章排上来。把具体年月写进 query 里，配合 `topic="news"` + `time_range` 才靠得住。
- **`include_answer` 必须显式开**，默认是 `False`，不开 `response["answer"]` 就是 `None`。

### 返回结构

```python
{
    "query": "...",
    "answer": "综合总结",              # 需要 include_answer，否则为 None
    "follow_up_questions": None,        # 需要 include_follow_up_questions
    "images": [],                       # 需要 include_images
    "results": [
        {
            "title": "网页标题",
            "url": "https://...",
            "content": "已提取好的正文片段",   # ← 关键字段
            "score": 0.87,                      # 相关性分数
            "raw_content": None,                # 需要 include_raw_content
            "id": "5e9f7d-00",
        },
        # ...
    ],
    "response_time": 1.06,
    "request_id": "9a65c9b8-...",
}
```

**顶层那几个 `None` / `[]` 不是 bug**，是对应的 `include_*` 开关没打开。Tavily 默认只返回 `results`，其他都要显式索取——因为生成 answer 要额外过一遍 LLM，`raw_content` 会让响应体积暴涨，默认全开不合理。

`results` 是个 list，`response` 本身是 dict。早期文档里写过 `response.results` 的属性访问方式，现在不适用，要用 `response["results"]`。

---

## 5. 常用参数

```python
response = client.search(
    query="特斯拉最新财报",
    search_depth="advanced",          # basic（默认）/ advanced，后者更深但更慢更贵
    topic="news",                      # general（默认）/ news / finance
    time_range="week",                 # day / week / month / year，也接受 d/w/m/y
    max_results=5,                     # 默认 5，一般上限 20
    include_domains=["reuters.com"],   # 只搜这些域名
    exclude_domains=["example.com"],   # 排除这些域名
    include_answer="advanced",         # False（默认）/ True 或 "basic" / "advanced"
    include_raw_content=False,         # 是否附带完整正文（会显著增大响应）
)
```

几个值得注意的点：

- **`search_depth`** 是延迟与质量的权衡。`basic` 通常 1-2 秒，`advanced` 2-5 秒且消耗更多 credits。做 agent 循环时延迟会累积，别默认全开 advanced。
- **`topic="news"`** 对时效性强的查询效果明显好于 `general`。财经类可以试 `finance`。
- **`include_answer`** 默认关闭，不开的话 `response["answer"]` 是 `None`。取值三档：`True` / `"basic"` 是简短一句话，`"advanced"` 给更详细的综合回答。
- **`include_answer`** / **`include_raw_content`** / **`max_results`** 都直接影响响应体积和 token 消耗，建议显式指定而不是留给默认值。
- **`include_domains`** 是控制信息质量最有效的手段。与其让模型在一堆内容农场里筛，不如直接限定几个可信源。

### 直接要答案

如果只想拿一句话结论，不想自己处理 `results`：

```python
answer = client.qna_search("Messi 现在效力于哪支球队?")
print(answer)   # 返回的是 str，不是 dict
```

这个方法 `search_depth` 默认就是 `advanced`，适合直接注册成 agent 的工具。

---

## 6. 抓取指定网页

已经知道 URL，只想要正文：

```python
response = client.extract([
    "https://en.wikipedia.org/wiki/Lionel_Messi",
    "https://en.wikipedia.org/wiki/Cristiano_Ronaldo",
])

for page in response["results"]:
    print(page["url"], len(page["raw_content"]))
```

单次调用可以传多个 URL，比一个个抓省往返。

---

## 7. 异步用法

批量查询时用异步能明显缩短总耗时：

```python
import asyncio
import os
from dotenv import load_dotenv
from tavily import AsyncTavilyClient

load_dotenv()

client = AsyncTavilyClient(api_key=os.environ["TAVILY_API_KEY"])

async def main():
    queries = ["AI 芯片市场规模", "英伟达最新财报", "台积电产能"]
    results = await asyncio.gather(*(client.search(q, max_results=3) for q in queries))

    for q, r in zip(queries, results):
        print(f"\n=== {q} ===")
        for item in r["results"]:
            print("-", item["title"])

asyncio.run(main())
```

---

## 8. 接到 LLM 上

这是 Tavily 最典型的用法——把搜索结果作为上下文喂给模型。

为了不锁死在某一家厂商上，推荐统一走 **OpenAI 兼容协议**：绝大多数国内外模型服务（DeepSeek、通义千问、Kimi、智谱、以及本地部署的 vLLM / Ollama、聚合网关 one-api / new-api）都提供 OpenAI 格式的接口，只要换 `base_url` + `api_key` + `model` 三个值就能切换，代码一行不用改。

### 配置

```bash
pip install tavily-python openai python-dotenv
```

`.env`（记得加进 `.gitignore`）：

```
TAVILY_API_KEY=tvly-xxxxxxxx

LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL=deepseek-chat
```

base_url 和模型名以各家最新文档为准。Anthropic 官方 API 不走 OpenAI 协议，要用它就装 `anthropic` 包单独调，或者挂在支持转换的网关后面。

### 代码

```python
import os
from dotenv import load_dotenv
from tavily import TavilyClient
from openai import OpenAI

load_dotenv()

tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

llm = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
)
MODEL = os.environ["LLM_MODEL"]


def build_context(results: list[dict]) -> str:
    """把搜索结果拼成带编号的引用块"""
    return "\n\n".join(
        f"[来源 {i}] {r['title']}\n{r['url']}\n{r['content']}"
        for i, r in enumerate(results, 1)
    )


def ask_with_search(question: str, **search_kwargs) -> str:
    # 1. 先搜
    search = tavily.search(
        question,
        max_results=search_kwargs.pop("max_results", 5),
        **search_kwargs,
    )
    if not search["results"]:
        return "没搜到相关内容。"

    # 2. 拼上下文
    context = build_context(search["results"])

    # 3. 再问
    completion = llm.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你根据用户提供的搜索结果回答问题。"
                    "只使用搜索结果里的信息，在句末用 [1][2] 标注来源编号。"
                    "如果搜索结果不足以回答，直接说明不确定，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": f"搜索结果:\n{context}\n\n问题:{question}",
            },
        ],
        temperature=0.3,
    )
    return completion.choices[0].message.content


if __name__ == "__main__":
    print(ask_with_search(
        "2026 年上半年 AI 领域最重要的进展是什么?",
        topic="news",
        time_range="month",
    ))
```

要换模型，只改 `.env` 里那三个值，代码不动。

### 让模型自己决定要不要搜

上面是「每次都先搜」。更省 credits 的做法是把 Tavily 注册成 function calling 工具，由模型判断：

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取实时信息。只在问题涉及时事、最新数据或你不确定的事实时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    },
}]


def chat_with_tools(question: str, max_rounds: int = 3) -> str:
    messages = [{"role": "user", "content": question}]

    for _ in range(max_rounds):
        resp = llm.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content

        for call in msg.tool_calls:
            import json
            query = json.loads(call.function.arguments)["query"]
            result = tavily.search(query, max_results=5)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": build_context(result["results"]),
            })

    return "超出最大轮数。"
```

注意 function calling 的支持程度各家不一，尤其本地小模型经常不稳定；上线前对着你实际用的模型测一遍。

### 用 LangChain

如果项目已经在用 LangChain，有单独的封装包（注意是**另一个** pip 包和导入路径）：

```bash
pip install langchain-tavily
```

```python
from langchain_tavily import TavilySearch

tool = TavilySearch(max_results=5, topic="general")
```

LangChain 侧同样可以用 `ChatOpenAI(base_url=..., api_key=..., model=...)` 接任意 OpenAI 兼容服务。

---

## 9. 计费

Tavily 按 credits 计费，免费额度每月 1000。不同请求消耗不同：

- `search_depth="basic"` 比 `advanced` 便宜
- `extract` / `crawl` 按处理的页面数计
- 具体倍率看官方 [Credits & Pricing](https://docs.tavily.com/documentation/api-reference/credits-and-pricing) 页面

开发调试阶段很容易在循环里把额度烧掉，建议：

- 本地加一层结果缓存（相同 query 直接返回，别重复打 API）
- 循环测试时把 `max_results` 调小
- dashboard 里能给每个 key 单独设用量上限

---

## 参考链接

- 官方文档 —— [docs.tavily.com](https://docs.tavily.com)
- Python SDK 快速上手 —— [docs.tavily.com/sdk/python/quick-start](https://docs.tavily.com/sdk/python/quick-start)
- GitHub —— [github.com/tavily-ai/tavily-python](https://github.com/tavily-ai/tavily-python)
- PyPI —— [pypi.org/project/tavily-python](https://pypi.org/project/tavily-python)
- Dashboard（拿 key）—— [app.tavily.com/home](https://app.tavily.com/home)
