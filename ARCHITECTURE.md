# ResearchVault 的代码怎样组织

ResearchVault 把文件处理、外部服务访问和科学分析分开。Python 工具负责保存文件、核对标识和执行明确的检查；Skills 指导 AI 完成阅读、比较和整理，科学结论仍需要研究者审核。

这份文档供需要理解或修改代码的人使用。具体行为要求见 [功能说明](SPECIFICATION.md)，使用方法见 [README](README.md)。

Python 包名是 `researchvault`，命令行可以用 `researchvault` 或 `python -m researchvault`。软件版本来自 `pyproject.toml` 和安装包元数据，不读取用户配置中的版本号。Vault 的记录格式目前是 schema 2，与软件版本独立管理。

## 各模块负责什么

以下模块都在 `researchvault/` 下。修改时优先放回已有职责所在的模块，避免在命令行入口重新实现一遍。

| 模块 | 主要工作 |
| --- | --- |
| `config`、`documents` | 读取明确指定的目录，防止路径越界，安全读取 YAML 和 Markdown，只创建新文件。 |
| `identity`、`validation` | 核对文献库、论文和附件的身份，以及记录之间的证据链接。 |
| `fulltext` | 保存原始提取文本，记录未完成状态，分层检索本地资料，生成迁移计划。 |
| `zotero`、`discovery`、`acquisition` | 访问官方 API、确认候选论文身份、下载选中的 PDF 并保存可恢复的进度。 |
| `resolution`、`intake`、`notes` | 解析明确给出的论文标识，协调导入步骤，为未完成的阅读笔记整理带来源的正文。 |
| `provenance` | 为记录生成规范化快照，保存修订关系，校验来源和内容是否改变。 |
| `process`、`review` | 管理实验约定、每次尝试的统计、综述覆盖范围和固定版本的文献集合。 |
| `evaluation` | 按明确标准评测结构化输出，结合来源比较结果，核对跨记录的数值。 |
| `cli` | 解析参数并调用模块，不做科学推理，也不暗中发起网络访问。 |

## 一篇论文怎样进入 Vault

已有的 `ingest` 命令负责归档选定批次的来源材料，继续保持兼容。需要从 DOI、arXiv 标识或官方论文 URL 开始时，使用独立的 `intake` 入口。更广的、已经明确选定范围的工作流程由已有 Skill 协调。

`intake` 的离线预览不执行导入任务的外部读写。实际执行时，它把来源检查和写入交给已有模块，并完成这些工作：

1. 固定本次使用的来源元数据，避免恢复任务时换成另一份来源。
2. 按顺序执行工作流，并将进度保存到 runtime。
3. 恢复前核对已持久保存的写入意图和回执，先查明上一次操作是否成功。
4. 先暂存新记录并计算 hash，再以只创建、不覆盖的方式写入 Vault；成对记录写到一半中断时，按恢复记录处理。

生成的 Paper Note 保持未完成状态，分别放置原文摘录、AI 分析和待验证猜想。正文格式化程序只整理这些输入，不替作者完成科学分析。已有研究记录需要先检查差异，再决定是否修改。写入前置条件和恢复方法见 [论文导入指南](docs/IDENTIFIER_INTAKE.md)。

## 本地检索为什么分两层

`fulltext.retrieve` 按词查找候选文件。它不理解概念，也不按语义相关性排序。

`literature-retrieval` Skill 负责理解问题、有限扩展查词、区分别名和相关概念、多次调用检索，以及按文献库身份去重。最终是否相关，要读过来源后再判断。因此测试时分别观察原始检索结果和 Skill 最后给出的答案。

## 文件和状态保存在哪里

研究者可直接阅读的 Markdown 是主要记录。只有重要结论的来源记录、综述文献集合、不可修改的科学快照或导入批次，才配套保存辅助文件。原始证据不会被分析文字覆盖。hash 用来发现内容变化，不能证明结论正确、记录先后顺序可信或操作已经获准。

真实 Vault、runtime 和 Zotero 目录都要明确配置，并放在代码仓库之外。仓库内只允许明确标为合成数据的示例和测试位置。

仓库的固定内容包括：

- `templates/`：模板的唯一原本。
- `skills/`：十二个任务 Skill。
- `references/`：各任务按需读取的规则和说明。
- `tests/`：自动化测试。
- `evals/` 和 `validation/golden/`：维护用的评测材料。

项目没有额外数据库、后台自主运行服务或机器人执行器。

## Python 模块之间的接口

下面保留准确名称，方便查代码。这些是本项目自己的接口，不是旧原型内部函数的兼容别名。

### 配置和 Markdown

`config.Settings` 提供：

| 字段或方法 | 类型／返回值 |
| --- | --- |
| `vault`、`repository` | `Path` |
| `runtime` | `Path \| None` |
| `options` | `dict` |
| `folder(name)`、`resolve(relative)` | `Path` |
| `relative(path)` | `str` |

`load_settings(config_path=None, vault=None, synthetic=False, cwd=None)` 读取显式配置。真实使用没有指定必要目录时会报错。

`documents.Record` 包含 `path: Path`、`relative: str`、`data: dict`、`body: str`。Markdown 的读取、新建和扫描分别通过 `read_record(path, root)`、`write_new(path, data, body)`、`scan(settings)` 完成。`scan` 返回 Record 列表，跳过模板、元数据目录和 `.git`。

`load_yaml(text)` 拒绝重复键；`diagnostic(code, path, detail, level='error')` 返回 `{code,path,detail,level}`，让各检查使用一致的诊断格式。

### 验证和内容校验

各验证模块提供 `check(settings, records) -> list[dict]`。主验证器汇总结果，区分错误与未完成状态的警告，全程不写入文件。验证模块不依赖 CLI。

标识解析复用现有的 PDF 引用解析器，并保留其来源约束，让元数据核对与 PDF 核对使用相同的论文来源规则。

`provenance.canonical(value) -> bytes` 统一日期等值的表示，拒绝递归对象、非有限数值和不能表示为 JSON 的数据；`digest(value) -> str` 对规范化结果计算摘要。

### 冻结记录和快照

```python
process.freeze(settings, path, kind, apply=False,
               previous=None, reason=None, timing='pre-result')

review.freeze(settings, path, apply=False, previous=None, reason=None)

provenance.snapshot(settings, path, inputs=(), sources=(),
                    tool_version=None, apply=False,
                    previous=None, reason=None)
```

`process.freeze` 用于 Claim／Design，`review.freeze` 用于综述。前两者都返回建议的元数据和回执路径，不改写研究者原页面；`provenance.snapshot` 提供通用的来源快照。

### 网络测试

网络模块允许测试传入替代的请求与验证实现。外部服务接口以官方规范为依据。最初实现阶段的测试不需要凭据、真实网络流量或操作个人文献库；这些测试与真实环境验收分开报告。

## 维护用评测与运行工具分开

`validation/golden/b2/` 保留固定的基准输入、盲审 AI 输出、按规则得出的判断，以及待人类决定的事项。

| 文件 | 用途和边界 |
| --- | --- |
| `scripts/semantic_contract.py` | 检查评测结构和来源完整性，不判断正文的科学含义。 |
| `scripts/benchmark_retrieval.py` | 在新建的临时 Vault 中分别测试两层检索，不访问个人文献库，也不添加语义检索后端。 |
| `scripts/_validation_common.py` | 共享 JSON、摘要、路径检查、已固定的公开论文身份和已审查的数值对应检查。 |

维护脚本不会互相充当库，也不把不同科学判断合并起来。共享 helper 不属于运行时 Python 包；合成校准与公开论文的候选基准仍分别维护。

原始 `scripts/validate_golden.py` 本身是 B2 历史证据，因此保留原始字节，不随共享代码整理而改写。这是保留旧评测运行器的明确例外。
