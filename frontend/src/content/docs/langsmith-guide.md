---
title: LangSmith 是什么，什么时候该用它
description: 面向刚接触 LLM 应用可观测性的开发者，示例用智谱 GLM，附可下载的完整参考代码
order: 4
---

# LangSmith 是什么，什么时候该用它

> 面向刚接触 LLM 应用可观测性的开发者。示例用智谱 GLM。事实截至 2026 年 8 月。

---

## 一、它解决什么问题

LangSmith 做两件事：**追踪**（把每次调用的中间过程记下来，出问题能回放）和**评估**（准备题目和判分规则，改动前后各跑一次看分数变化）。由 LangChain 公司开发，但不强制你用 LangChain。

举例。客服机器人被问"几天能退款"，答"30 天内可退"——错了，正确答案是 7 天。问题出在检索没找到政策？拼 prompt 出错？还是模型看错了？代码跑完只剩一个错答案，中间过程全丢，你只能靠猜。

接了 LangSmith，网页上一看：

```
客服问答                    1.8s
├── retrieve                0.00s   → 检索到的是"退货运费"，压根没找到退款政策
└── generate                1.8s
    └── ChatOpenAI          1.8s   → prompt 原文、token 数、耗时都在
```

三秒定位。`print` 顶替不了，因为调用层级深、prompt 动辄几千字、Agent 一次任务几十轮——你要的是可点开的树和可对比的历史。

除追踪和评估外，它还提供 prompt 版本管理、成本延迟仪表盘、阈值告警、人工标注队列，以及把线上点赞点踩回流成测试集。

---

## 二、核心概念

| 概念 | 是什么 |
|---|---|
| **Run** | 一次被记录的函数调用。加了 `@traceable` 的函数每次执行产生一个 Run |
| **Trace** | 一次完整请求产生的整棵 Run 树 |
| **Project** | 一组 Trace 的容器，按环境划分（dev / prod） |
| **Dataset / Example** | 测试集，每条 Example 是一个 `{输入, 期望输出}` |
| **Experiment** | 在某个 Dataset 上跑一次，产生每条用例的得分 |
| **Feedback** | 挂在 Run 上的评分，来自评估器或真实用户 |

评估的三个组件跟考试一样：Dataset 是试卷，Evaluator 是批改标准，Experiment 是一次考试。它解决改 prompt 最大的痛点——**改动经常"修好一个、弄坏一个"，肉眼看不出来。**

---

## 三、追踪：最小可用示例

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="lsv2_pt_..."      # smith.langchain.com 生成
export LANGSMITH_PROJECT="my-project"
export ZHIPU_API_KEY="你的智谱key"
```

`LANGSMITH_TRACING=false` 是总开关，关掉后代码一行不用改、数据完全不上传。

```python
import os
from openai import OpenAI
from langsmith import traceable
from langsmith.wrappers import wrap_openai

# 包一层，之后这个 client 发出的每次请求都自动记录
client = wrap_openai(OpenAI(
    api_key=os.environ["ZHIPU_API_KEY"],
    base_url="https://open.bigmodel.cn/api/paas/v4",   # 注意不是 /v1
))

@traceable(run_type="retriever")
def retrieve(question: str) -> list[str]:
    kb = {"退款": "签收后 7 天内可无理由退款。", "运费": "满 99 元包邮。"}
    return [v for k, v in kb.items() if k in question]

@traceable(name="客服问答")
def qa(question: str) -> str:
    docs = retrieve(question)
    resp = client.chat.completions.create(
        model="glm-4.7-flash",
        messages=[
            {"role": "system", "content": "只根据资料回答，没有就说不知道。"},
            {"role": "user", "content": f"资料:{docs}\n问题:{question}"},
        ],
        temperature=0.1,   # GLM 要求 > 0，不能写 0
    )
    return resp.choices[0].message.content

print(qa("几天内可以退款?"))
```

### `@traceable` 加在哪

**作用**：在调用树上生成一个节点，嵌套调用自动形成父子关系。

**该加**：有意义的步骤边界（检索、生成、调外部 API、解析数据）、想单独查看输入输出的地方、耗时的地方。

**不该加**：纯工具函数、循环里高频调用的（会生成几百个节点，树没法看）、一行的小函数。

**判断标准**：这个节点出现在树上，对排查问题有帮助吗？没帮助就是噪音。

| 参数 | 作用 |
|---|---|
| `name="..."` | 改界面显示名，默认用函数名 |
| `run_type="retriever"` | 检索专用视图，文档一条条列出来 |
| `run_type="llm"` | LLM 视图。模型调用已被 `wrap_openai` 记录时，外层包装函数别再标 llm，会语义重复 |

运行时想附加信息（线上按 user_id 过滤很有用）：

```python
qa("...", langsmith_extra={
    "metadata": {"user_id": "u_123", "version": "v2"},
    "tags": ["prod", "vip"],
})
```

---

## 四、评估：最小可用示例

```python
from langsmith import Client

ls = Client()

dataset = ls.create_dataset("回归集")          # 只需建一次
ls.create_examples(dataset_id=dataset.id, examples=[
    {"inputs": {"question": "几天能退款"}, "outputs": {"answer": "7 天"}},
    {"inputs": {"question": "老板叫什么"}, "outputs": {"answer": "", "should_refuse": True}},
])

def key_fact_hit(inputs, outputs, reference_outputs) -> dict:
    if reference_outputs.get("should_refuse"):
        return {"key": "命中关键信息", "score": None}      # 不适用，跳过
    return {"key": "命中关键信息",
            "score": int(reference_outputs["answer"] in outputs["answer"])}

ls.evaluate(
    lambda inputs: {"answer": qa(inputs["question"])},
    data="回归集",
    evaluators=[key_fact_hit],
    experiment_prefix="v1",        # 改 prompt 后换成 v2，界面可并排对比
    max_concurrency=1,             # 智谱免费 flash 限 1 并发
)
```

### 关键细节：score 可以是 None

`None` 表示**这道题不参与这个指标的统计**。

假设 10 道题里 4 道是"知识库没有、应该拒答"的。对这 4 道，"命中关键信息"没意义——本来就没有标准答案要命中。给 0 分会让命中率变成 60%，看着像模型很差，实际正常问题全对。返回 `None` 跳过，显示 6/6 = 100%，**数字才有意义**。

做回归集的经验：**负例要占三成以上**，否则测不出幻觉。

---

## 五、数据去哪了

`@traceable` 和 `wrap_openai` 的上传是**隐式的**——库内部发 HTTP 请求，你的代码里看不到上传逻辑，prompt 原文和模型回答就这么传到了 LangSmith 的服务器（美国）。明确的上传在这几个方法里，看名字就知道：`Client().create_examples()`、`.evaluate()`、`.create_feedback()`。

| 合规方案 | 代价 |
|---|---|
| `LANGSMITH_HIDE_INPUTS=true` / `HIDE_OUTPUTS=true` | 损失大部分调试价值 |
| LangSmith 企业版自托管 | 付费谈合同 |
| 换 Langfuse，MIT 许可可完全私有化部署 | 迁移成本（API 风格接近，不算高） |

学习阶段无所谓。**但应用里有用户真实数据时，上生产前必须先解决。**

---

## 六、和 Langfuse 怎么选

|  | LangSmith | Langfuse |
|---|---|---|
| 许可 | 闭源商业（SDK 开源，后端不开源） | MIT 开源 |
| 自托管 | 企业版才有 | 一等公民，免费自部署 |
| 框架绑定 | LangChain/LangGraph 零配置；其他框架需显式埋点（也支持 OTel） | 框架无关，基于 OpenTelemetry |
| 免费额度 | 每月 5000 条 trace | 云版有免费额度，自托管无限制 |
| 归属 | LangChain Inc. | 2026 年 1 月被 ClickHouse 收购，许可未变 |

- **选 LangSmith**：栈就是 LangChain/LangGraph，想开箱即用，不介意数据出境
- **选 Langfuse**：需要数据主权、私有化部署，或栈在 LangChain 之外
- **两个都用**：开发用 LangSmith 零配置追踪，生产用自托管 Langfuse 做长期记录

"LangSmith 好像没什么人用"这个印象在中文社区常见，原因是数据出境对国内团队是硬约束。但整体市场上两者都是主导产品，它不是小众工具。

---

## 七、几个容易踩的判断

**"必须用 LangChain"** —— 不必。OpenAI SDK、智谱、原生 HTTP 都能接，只是 LangChain 项目能零代码改动。

**"和 Prometheus 那类监控重复"** —— 不重复。传统 APM 关心 QPS、延迟、错误率；它关心**语义层面**：prompt 长什么样、检索到什么、为什么答错。

**"分数涨了就是变好了"** —— 回归集是**刹车，不是方向盘**。它告诉你有没有改崩，不告诉你怎么改好，在小数据集上反复调还会过拟合。

**什么时候压根不需要** —— 单轮简单调用没有链路可言；纯 prompt 试验在 Playground 手调更快；项目还在"能不能跑通"阶段，先跑通再说。

---

## 八、可参考代码

一个可直接运行的完整 RAG 客服问答项目——接入智谱 GLM 做模型、LangSmith 做全链路追踪与离线评估，包含链路追踪、关键词检索、离线回归评估（含防幻觉指标与 LLM-as-judge）、FastAPI 服务、用户反馈回流、13 个不联网的单元测试：

**[下载 glm-langsmith-kit.zip](/attachments/glm-langsmith-kit.zip)**

```bash
unzip glm-langsmith-kit.zip && cd glm-langsmith-kit
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填两个 key：LANGSMITH_API_KEY（smith.langchain.com）
# 和 ZHIPU_API_KEY（bigmodel.cn），两者缺一都会启动即报错并提示怎么填

pytest -q                      # 13 个离线测试，不需要 key，先确认环境没问题
python -m scripts.run_demo     # 追踪演示，去 LangSmith 网页看调用树
python -m scripts.run_eval     # 评估实验，看 10 用例 × 5 指标的评分表
uvicorn src.server:app --reload --port 8000   # 起服务，/docs 看接口
```

比起单看代码，更建议照着"核心用法：对比实验"那节实际跑一遍——改一下 `src/pipeline.py` 里的 `SYSTEM_PROMPT`，把 `PROMPT_VERSION` 改成 `"v2"`，再跑一次 `make eval`，然后去 LangSmith 数据集页面勾两个实验点 Compare，直接看哪条用例变好了、哪条被改崩了。这个"改动前后对比"就是本文反复强调的 LangSmith 核心价值，代码本身不复杂，值得跑起来体会一遍再回头看文档。

`src/config.py` 缺 key 时会给出具体该去哪填的报错，不用去翻源码猜。

---

## 参考

- 官方文档 —— [docs.smith.langchain.com](https://docs.smith.langchain.com)
- Langfuse 视角的对比（注意立场）—— [langfuse.com/resources/engineering/langsmith-alternative](https://langfuse.com/resources/engineering/langsmith-alternative)
- 第三方对比 —— [datacamp.com/blog/langfuse-vs-langsmith](https://www.datacamp.com/blog/langfuse-vs-langsmith)

> 两个平台的功能、定价、许可都在快速变化，关键决策前查官方最新文档。
