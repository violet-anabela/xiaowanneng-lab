---
title: Agent Skills 原理详解
description: 所谓"调用 skill"，就是把一个 markdown 文件读进上下文——没有专门的 API，没有检索引擎
order: 2
---

# Agent Skills 原理详解

> 一句话结论：**所谓"调用 skill"，就是把一个 markdown 文件读进上下文。**
>
> 没有专门的 API，没有检索引擎。你的 agent 只要挂了一个读文件的工具，就能用 skill。

---

## 一、skill 是什么

**一个文件夹，里面放一份写给 AI 看的操作手册。**

```
csv-report/
└── SKILL.md        ← 手册正文，markdown 格式
```

手册开头有两行元信息：这份手册叫什么、什么时候该翻它。

```yaml
---
name: csv-report
description: 把 CSV 数据做成销售报告时使用。触发词：销售报告、月报、数据报表。
---

# CSV 销售报告
1. 跑 scripts/summarize.py 算指标
2. 格式规范见 references/format.md
...
```

就这样。**没有代码，没有配置，没有注册。** 一个文件夹，扔进指定目录就生效。

至于 agent 怎么找到它、怎么用它 —— 这是本文剩下部分要讲的，
但可以先记住结论：**靠一个普通的读文件工具，把这个 md 读进上下文。**

---

## 二、要解决的问题

假设你有 50 个领域的操作手册要教给 agent：怎么做财报、怎么写周报、
怎么处理客诉、怎么跑数据清洗……

**笨办法**：全塞进 system prompt。

几十份手册轻松上 8 万 token，而且**每一轮都要重发**。system prompt 尤其躲不掉：
历史消息你还能裁（滑动窗口、摘要压缩），但它是每次请求的固定开头。
更糟的是，用户问的是财报，其余全是噪音，还干扰模型注意力。

**skill 的办法**：先给目录，用到哪本再翻哪本。

实测一组真实 skill（35 个）：

| | ≈ token |
|---|---|
| 只装清单（名字 + 描述） | **4,538** |
| 所有正文全塞进去 | ~80,800 |

**省了 18 倍**，平均每个 skill 常驻 129 token。这就是
**progressive disclosure（渐进披露）**。

---

## 三、三个阶段

### 阶段 1：发现（Discovery）

启动时扫描 skill 目录，**只解析 YAML frontmatter，正文一个字不读**，
拼成一段文本注入 system prompt。

system prompt 大概长这样。**措辞不固定，你可以按自己的需要改写**，
但意思得是这个意思：

```
你是一个能使用 skill 的 agent。下面是可用 skill 清单，
只有名字、描述和文件路径，正文没有加载。

判断某个 skill 与当前任务相关时，先用 read_file 读它的 <location>，
再按里面的指示执行。SKILL.md 引用的其他文件（references/、scripts/、
assets/），只在真正需要时才读或执行。不相关就直接干活，不用勉强套。

<available_skills>
  <skill>
    <name>csv-report</name>
    <description>把 CSV 数据做成销售报告时使用。触发词：销售报告、月报、
    CSV 汇总、数据报表。不适用于：单纯读 CSV、写代码、做图表。</description>
    <location>/path/to/skills/csv-report/SKILL.md</location>
  </skill>
  <skill>
    <name>commit-msg</name>
    <description>用户要写、检查或修改 git commit message 时使用。
    触发词：commit message、提交信息。不适用于：写代码、做报告。</description>
    <location>/path/to/skills/commit-msg/SKILL.md</location>
  </skill>
</available_skills>
```

**模型知道该去读文件，是因为第二段那句话明确告诉了它。**

平心而论，这句不写，强一点的模型多半也能猜出来 —— `<location>` 是个 `.md` 路径、
`<description>` 写着什么时候用它、工具列表里有 `read_file`，串起来并不难。
明写是为了**稳定**：弱模型不说就真不读；"只在需要时才读 `references/`"
这类细节猜不出来；同一个任务你也不希望这次读了下次没读。

既然是自然语言，就没有标准答案。这段话只要说清三件事 —— 清单里是什么、
相关时怎么办、不相关时怎么办 —— 其余随你加，比如"一次只用一个 skill"、
"用之前先告诉用户你打算用哪个"、"找不到匹配就明说别硬凑"。
**触发太松就加约束，太紧就把语气放宽。**

几个细节：

- `read_file` 这个工具本身也要注册给模型（请求的 `tools` 参数里）。
  prompt 里**提到**它，和 `tools` 里**真的有**它，缺一不可
- `location` 不是规范里的字段，是你的框架拼进去的 —— 模型得知道去 `cat` 哪个文件
- XML 标签也不是规范，markdown 列表、JSON 都行。选 XML 是因为边界清楚，
  模型不容易把 skill 描述跟你自己的提示词内容混在一起

### 阶段 2：激活（Activation）

用户说"帮我做个七月销售报告"。接下来发生的事，值得一步步拆开看。

**第 1 步：你的代码发请求。**

内容是「上面那段 skill 清单（在 system 里）+ 用户这句话」。
注意此时 SKILL.md 的**正文还躺在磁盘上，一个字都没进过上下文**。

**第 2 步：模型返回一个"我想读文件"的意图。**

模型看到清单里 `csv-report` 的描述写着"触发词：销售报告、月报……"，
对上了。于是它返回的不是文字，而是一个结构化字段：

```json
{"tool_calls": [{
  "id": "call_abc",
  "function": {"name": "read_file",
               "arguments": "{\"path\": \"/path/to/skills/csv-report/SKILL.md\"}"}
}]}
```

**关键：模型什么都没读。** 它没有文件系统，碰不到你的磁盘。
这只是一句"我想读这个路径，你帮我读一下"。

**第 3 步：你的代码执行这次调用。**

这就是 agent loop 里的「工具执行环节」：查表找到对应函数，调用它。
手写的话是这几行 ——

```python
DISPATCH = {"read_file": read_file, "bash": bash}   # 名字 → 函数

for tc in msg.tool_calls:
    out = DISPATCH[tc["name"]](**tc["args"])        # ← 真正执行的一行
    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": out})
```

用 LangGraph / LangChain 就不必自己写：框架看到 `tool_calls` 会自动路由到
`tools` 节点，查表、调用、把结果包成 `ToolMessage` 塞回去。你只要
`create_agent(model=..., tools=[read_file, bash], ...)` 把函数交出去。

**两种写法干的是同一件事**，区别只是查表和回填由谁负责。

**第 4 步：带着结果再问一次。**

把消息列表发回给模型 —— 这次里面多了 SKILL.md 的正文。

（`tool_call_id` 别忘了带上：模型一轮可能同时发好几个调用，
靠这个 id 才能把结果和请求对上号。）

**"激活"指的就是这件事：正文从磁盘搬进了上下文。** 模型看到手册内容，
开始照着上面写的步骤干活。

---

整个过程就是一次普通的工具调用往返。**你的 `read_file` 函数里没有一行代码
知道自己刚才读的是个 skill** —— 它只是读了个 md。

正因为如此，skill 才不需要框架支持：**任何挂了读文件工具的 agent，
天然就能用 skill。**

### 阶段 3：执行（Execution）

SKILL.md 正文进了上下文，模型照着上面的步骤干活。过程中可能：

- 读 `references/` 里的补充文档
- 跑 `scripts/` 里的脚本
- 复制 `assets/` 里的模板

**只在真正需要时才读**。用不上的文件一个字节都不进上下文。

### 另一条路：手动指定

不少 agent 支持 `/skill csv-report` 直接点名。这时**"该不该用"这个判断被跳过了**，
description 不再起作用 —— 清单照常注入，只是你替模型做了决定。

实现上通常是往**当轮的用户消息**里追加一段（不是 system prompt，
那个会话开始就拼好了）。要么给路径让模型自己读，走的还是上面那次往返；
要么直接把正文塞进去，省一次往返，代价是正文一定进上下文。

**这在调试时特别有用。** 模型没按预期用某个 skill，可能是 description
没触发，也可能是触发了但正文写得烂。用 `/skill` 强制跑一遍就分开了：
**结果变好 → 问题在 description；照样烂 → 问题在正文。**

---

## 四、目录结构

```
skill-name/
├── SKILL.md          必需。YAML frontmatter + markdown 正文
├── references/       可选。按需读的长文档
├── scripts/          可选。可执行代码
└── assets/           可选。模板、字体、schema 等原材料
```

规范里**只有 SKILL.md 是必需的**，其余全是可选，目录名也不强制。
Anthropic 自己的 skill 就用了 `themes/`、`templates/`、`examples/`、
`canvas-fonts/` 等各种名字。

**目录名没有魔法**，agent 是靠 SKILL.md 正文里那句
"模板在 `templates/viewer.html`" 找过去的。**指路写在正文里，才是真的。**

### 三个子目录的本质区别

差别不在内容，在**进不进上下文**：

| 目录 | 怎么用 | 进上下文的部分 |
|---|---|---|
| `scripts/` | **跑它** | 只有 stdout |
| `references/` | **模型读它** | 全文 |
| `assets/` | **别人用它** | 通常不进 |

`scripts/` 这条特别值钱：一个 500 行的转换脚本，模型可能一行源码都没看过，
只写了 `python scripts/convert.py in.docx` 然后看返回结果。
**源码是给 Python 解释器读的，不是给模型读的。**

`assets/` 最容易想岔。以字体文件为例：模型读进去只能看到一堆 `\x00\x01`，
学不到东西还烧 token。实际发生的是它在 SKILL.md 里看到路径，
写一行 `shutil.copy(...)` —— **文件内容确实被读了，被 `shutil.copy` 读的、
被浏览器读的，只是没经过模型的上下文窗口。**

所以判断标准不是目录名，而是**这个文件最终给谁看**：

- 给**模型**看的（它得理解内容才能干活）→ 进上下文
- 给**程序 / 浏览器 / 最终产物**看的（模型只要路径）→ 不进上下文

粗略规律：**二进制的一定不读；文本的看你要不要改它。**

---

## 五、SKILL.md 怎么写

### frontmatter

```yaml
---
name: csv-report          # 必填，≤64 字符，小写字母数字连字符，必须和文件夹名一致
description: ...          # 必填，≤1024 字符
---
```

可选字段有 `license`、`compatibility`、`metadata`，还有实验性的
`allowed-tools`。这些**一般不注入上下文** —— 是给人和工具链看的，
进上下文纯属浪费 token。

### description 决定触发准不准

system prompt 是全局的一句话，而**决定"哪个 skill 在什么时候被翻开"的，
是每个 skill 自己的 description**。日常绝大部分调优工作都花在这上面。

对照一下。差的写法：

```yaml
description: 处理 Word 文档。
```

好的写法（Anthropic 官方 docx skill 的真实描述）：

> Use this skill whenever the user wants to create, read, edit, or manipulate
> Word documents (.docx files) or Word templates (.dotx files). Triggers include:
> any mention of 'Word doc', 'word document', '.docx', '.dotx', or requests to
> produce professional documents with formatting like tables of contents,
> headings, page numbers, or letterheads. ... If the user asks for a 'report',
> 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file,
> use this skill. **Do NOT use for PDFs, spreadsheets, Google Docs, or general
> coding tasks** unrelated to document generation.

它干了三件事：

1. **穷举触发词** —— 用户可能说的原话尽量都塞进去
2. **列举具体动作** —— 插图、查找替换、修订、提取内容，而非笼统说"处理 Word"
3. **明确划边界** —— 最后那句 `Do NOT use for...` 特别重要，
   不写的话相邻的 skill 会互相抢

一句话：**"干什么"和"什么时候用"都要写，后者才真正影响触发率。**

### 正文

正文写操作步骤即可。几条经验：

- **超过几百行就该拆到 `references/`**，否则渐进披露的意义就没了
- **命令要能直接复制执行**。写 `python scripts/foo.py <输入>` 是不合格的 ——
  相对哪里？`<输入>` 填什么？模型只能猜，猜错几次它就放弃跑脚本自己干了
- **关键步骤要明写"失败就停，不要绕过"** —— 模型碰到失败的默认反应是绕路。
  脚本跑不通，它很可能直接读原始数据自己算，而且结果可能碰巧是对的，
  你未必发现得了

---

## 六、代码有多少

整个机制两个函数，加起来不到 40 行：

```python
def discover(skill_dirs):
    """阶段1：扫目录，只读 frontmatter，正文一个字不碰。"""
    out = []
    for d in skill_dirs:
        for md in sorted(Path(d).glob("*/SKILL.md")):
            fm = parse_frontmatter(md)          # 只取 name / description
            if fm:
                out.append({"name": fm["name"], "desc": fm["description"],
                            "path": str(md.resolve())})
    return out


def build_system_prompt(skills):
    """拼成 XML 塞进 system prompt。"""
    catalog = "\n".join(
        f"  <skill>\n    <name>{s['name']}</name>\n"
        f"    <description>{s['desc']}</description>\n"
        f"    <location>{s['path']}</location>\n  </skill>"
        for s in skills
    )
    return ("你是一个能使用 skill 的 agent。下面是可用 skill 清单，"
            "只有名字、描述和路径，正文没有加载。判断相关时，先用 read_file "
            "读它的 <location>，再按里面的指示做。\n\n"
            f"<available_skills>\n{catalog}\n</available_skills>")
```

接进任何 agent 都只要一行：

```python
# 手写 loop
messages = [{"role": "system", "content": build_system_prompt(skills)}, ...]

# LangGraph
agent = create_agent(model=..., tools=[read_file, bash],
                     system_prompt=build_system_prompt(skills))
```

**然后就没了。** 剩下的全在普通 agent loop 里发生。

---

## 七、安全

**skill 本质是"往你 agent 的上下文里注入指令 + 往你机器上放可执行脚本"。**

恶意 skill 可以利用运行环境、外泄数据、执行有害操作。**只从可信来源装。**

自建时至少要有：

- **bash 沙箱** —— 裸 `subprocess.run(shell=True)` 意味着模型让干啥就干啥
- **token 预算和轮次熔断**
- **trace** —— 把每一步记下来：选了哪个 skill、发了什么命令、
  退出码和错误输出、耗时。agent 的执行过程默认是黑箱，你只看到最后的结果，
  中间读了什么、哪步报错了全看不见 —— 出问题无法归因，跑通了也不确定
  是不是真跑通了
- **skill 来源审查** —— 尤其是第三方分发的

`allowed-tools` 字段可以做权限预授权，但注意它**只是预授权，并不阻止
模型用其他工具**；真要限制得配上项目级的 deny 规则。

---

## 八、动手验证

理解这套东西最快的方法是做一个实验：

**把某个 skill 的 description 改成笼统的一句话**，比如：

```yaml
description: 处理数据。
```

再跑同样的任务，大概率不触发了。改回带具体触发词的版本，又好了。

**这个实验比读十篇文章都管用** —— 你会直观感受到，
整套机制的准确率押在那一段自然语言上，不在代码里。

---

## 九、可参考代码

本文用到的最小 agent 实现——发现/激活/执行三阶段的完整代码，加两个示例
skill（`csv-report` 三件套齐全、`commit-msg` 纯文本对照）——可以直接下载跑起来：

**[下载 skill-agent-demo.zip](/attachments/skill-agent-demo.zip)**

```bash
unzip skill-agent-demo.zip && cd skill-agent-demo
pip install -r requirements.txt
# 编辑 config.yaml，填上自己的 api_key（默认配的是智谱，免费模型 glm-4.7-flash）
python agent.py "把 sales.csv 做成七月销售报告"
```

比起单看代码，**更建议直接跑一遍，然后在每个阶段停下来看看输入输出到底是什么**：

- **阶段 1（发现）**：`skills_core.py` 的 `build_system_prompt()` 拼出来的 system
  prompt 具体长什么样？`<available_skills>` 里到底塞了什么？
- **阶段 2（激活）**：模型返回的 `tool_calls` 参数是什么样？真正读进去的
  SKILL.md 正文有多长、跟你写的原文一字不差吗？
- **阶段 3（执行）**：`scripts/summarize.py` 跑完之后，进了上下文的到底只有
  stdout 那几行，还是把脚本源码也带进去了？

这几个地方顺手加几行 `print()`（`agent.py` 里已经打开了 `verbose`，能看到
三阶段的分界）就能看清楚，比读代码直观得多——毕竟整篇文章的结论就是
"这套机制没什么魔法"，眼见为实。

---

## 附：延伸阅读

- **Anthropic 官方工程博客**（最该先看）
  `anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills`
- **规范** —— 2025 年 12 月 18 日作为开放标准发布，`agentskills.io`。
  目前四十多个平台支持，Claude、OpenAI Codex、Snowflake Cortex Code 都在内
- **代码示例** —— `github.com/anthropics/claude-cookbooks/tree/main/skills`
- **官方课程**（含 `allowed-tools` 限权、脚本免上下文等进阶项）
  `anthropic.skilljar.com/introduction-to-agent-skills`

---

## 一页速查

```
skill = 一个文件夹 + 一个 SKILL.md

阶段1 发现   注入「一句指令 + name/description 清单」  ← 你的代码做这个
阶段2 激活   模型自己判断相关，read_file 读正文       ← 模型做这个
阶段3 执行   按需读 references/assets、跑 scripts   ← 模型做这个

/skill 手动指定 = 跳过阶段1的判断，直接进阶段2

scripts/     跑它     → 只有 stdout 进上下文
references/  读它     → 全文进上下文
assets/      别人用它 → 通常不进上下文

代码量：40 行（discover + build_system_prompt）
调优重心：description

三条铁律：
  · description 要穷举触发词 + 划清边界
  · SKILL.md 里的命令必须能直接复制执行
  · 关键步骤明写"失败就停，不要绕过"
```
