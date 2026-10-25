# ResearchVault

**把论文、阅读笔记和实验记录整理在一起，写结论时能找到依据。**

ResearchVault 是一套配合 **Zotero、Markdown 笔记和 AI 助手**使用的科研工具。它帮助你收集论文、记录阅读思路、整理研究问题，并把实验结果和最终结论连起来。笔记保存在你选择的文件夹里，可以用 Obsidian 或其他 Markdown 编辑器打开。

项目面向具身智能等需要阅读论文、设计实验的研究工作，适合个人研究者和小型团队。

[它能帮你做什么](#它能帮你做什么) · [先试一下](#先试一下) · [用自己的论文](#用自己的论文) · [更多文档](#更多文档)

## 它能帮你做什么

读完一篇论文，过一段时间再看笔记，常常分不清：这是作者的结论，还是自己的理解？一个实验结果又是在哪个设置下得到的？

ResearchVault 帮你把这些信息留下来：

| 你要做的事 | 它帮你整理什么 |
| --- | --- |
| 收集选好的论文 | 核对标题、作者和版本，检查是否重复，获取合法可用的 PDF 并存入 Zotero |
| 阅读论文 | 记录问题、方法、实验和局限；重要结论附上原文位置，分清作者主张与自己的解释 |
| 整理研究思路 | 对比多篇论文，把已有证据、疑问和待验证的想法分别记录 |
| 管理实验 | 保存实验设计、每次尝试、结果和分析，包括失败与负结果 |
| 写作 | 找回结论对应的论文或实验，检查显式标注的数字是否一致 |

例如，你可以让 AI 助手这样做：

> 使用 ResearchVault 阅读这篇论文。先讲清楚它解决什么问题，再解释方法和实验。每个重要结论标出原文位置，不确定的地方直接写出来。

> 对比我选中的这几篇论文：它们在哪些问题上结论一致，在哪些条件下不同？把证据不足的地方单独列出来。

> 整理这次实验：原来想验证什么，实际跑了哪些设置，结果支持什么、还不能说明什么。失败的尝试也要保留。

这些任务由 AI 助手配合项目里的 **Skills** 执行。Skills 可以理解为给助手的任务说明；Python 命令行工具负责保存文件、读取 Zotero 和检查记录。阅读和分析需要助手参与，实验模型仍由你自己的代码运行。

## 先试一下

需要 **Git 和 Python 3.10+**。先用自带示例检查安装，暂时不需要 Zotero、Obsidian 或 API key。

**1. 下载代码，创建虚拟环境。**

```sh
git clone https://github.com/cdc95-04/ResearchVault-release.git
cd ResearchVault-release
python -m venv .venv
```

**2. 激活环境。** 按你的系统选择一条：

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

**3. 安装并运行示例。**

```sh
python -m pip install -e ".[pdf]"
researchvault --version
researchvault --config examples/synthetic.yaml validate
researchvault --config examples/synthetic.yaml retrieve "mechanism"
```

`validate` 检查记录，`retrieve` 搜索笔记。示例检查应返回 `valid: true`；其中几篇示例笔记故意没有 PDF 和全文，因此会提示缺少来源。这些是演示数据，不会读取或修改你的文献库。

当前版本从源码目录安装，请保留这个目录。安装细节见 [INSTALL.md](INSTALL.md)。

## 用自己的论文

### 1. 安装给 AI 助手用的 Skills

如果希望在 Codex 中直接用自然语言完成上面的任务，按 [Plugin 安装说明](docs/CODEX_PLUGIN.md)安装 ResearchVault Plugin。

**Python 工具和 Plugin 要分别安装。** 前者提供命令，后者让助手知道怎样使用这套流程。只装 Plugin 不会自动安装 Python 工具或创建笔记目录。

### 2. 准备文献库和笔记文件夹

- **Zotero** 保存文献条目和 PDF。保持 Zotero Desktop 运行，并在设置中允许本机其他应用与它通信；新建条目和上传 PDF 需要 **Zotero 10+**。
- **Vault** 就是保存研究笔记的普通文件夹，可以作为 Obsidian 库打开。
- **Runtime** 保存下载缓存和处理进度，用来在中断后继续。

这两个数据文件夹都应放在代码仓库外，而且彼此不能嵌套。把路径写入 `config/local.yaml`；这个文件不会提交到 Git。按 [配置与初始化说明](CONFIG.md)先预览将创建的目录，再确认创建。

建议在本地配置里设置 `read_only: true`，需要写入时再明确开启。项目默认配置不会替你选择文献库路径，也不会自动开启只读保护。

### 3. 从一篇已选好的论文开始

配置好以后，先检查 Zotero 连接，再核对论文信息：

```sh
researchvault --config config/local.yaml zotero-inventory
researchvault --config config/local.yaml intake "<论文 DOI、arXiv 版本或支持的论文 URL>" --resolve
```

请把第二条命令里的占位内容换成真实标识。`--resolve` 会联网查元数据，并检查 Zotero 中是否已经存在；这一步不下载 PDF，也不创建条目。

确认论文和目标位置后，再按 [论文导入指南](docs/IDENTIFIER_INTAKE.md)授权下载与写入。已有的正确文献和 PDF 会优先复用；只有确认过身份的主论文 PDF 才会自动导入。新建条目需要 Zotero 签发的本地写入 key，网站上的 Web API key 不能代替它。当前工具不会自动申请这个 key；未配置时可以先预览或复用已有文献。凭据不要写进配置或提交到 Git。

归档后会得到原文提取记录和一份笔记初稿。接下来再让助手按原文阅读、补充分析；初稿不会自动被标记为“已读”或“人工审核通过”。

## 一轮研究怎么走

```text
选论文 → 收集全文 → 阅读和笔记 → 整理研究问题 → 记录实验 → 分析结果 → 写作
```

你可以从需要的环节开始。只读一篇论文，不必先建立实验；提出一个想法，也不代表已经找到了别人没研究过的问题。

研究资料按用途分开放在 Vault 中：

```text
research-data/
├── 01-knowledge/     # 多篇论文之间的概念、方法和联系
├── 02-papers/        # 单篇论文的阅读笔记
├── 03-fulltext/      # 提取的原文，供回查
├── 04-research/      # 研究问题、假设和想法
├── 05-projects/      # 具体项目
├── 06-experiments/   # 实验设计、运行记录和结果
└── 08-writing/       # 写作草稿及其依据
```

上面只列常用目录。源码在软件仓库中，原始 PDF 由 Zotero 管理，下载缓存放在单独的 Runtime 文件夹里。

<details>
<summary>查看全部 12 个 Skills</summary>

| 任务 | Skill |
| --- | --- |
| 找论文 | [literature-discovery](skills/literature-discovery/SKILL.md) |
| 获取全文 | [literature-acquisition](skills/literature-acquisition/SKILL.md) |
| 处理已选批次 | [ingest-orchestrator](skills/ingest-orchestrator/SKILL.md) |
| 读取 Zotero 文献 | [zotero-fetcher](skills/zotero-fetcher/SKILL.md) |
| 保存提取的原文 | [fulltext-archiver](skills/fulltext-archiver/SKILL.md) |
| 写阅读笔记 | [paper-note-writer](skills/paper-note-writer/SKILL.md) |
| 整理跨篇知识 | [knowledge-maintainer](skills/knowledge-maintainer/SKILL.md) |
| 搜索已有笔记 | [literature-retrieval](skills/literature-retrieval/SKILL.md) |
| 做系统综述 | [systematic-literature-review](skills/systematic-literature-review/SKILL.md) |
| 形成研究问题和假设 | [research-maintainer](skills/research-maintainer/SKILL.md) |
| 管理实验记录 | [experiment-manager](skills/experiment-manager/SKILL.md) |
| 整理写作依据 | [writing-support](skills/writing-support/SKILL.md) |

</details>

## 使用前需要知道

ResearchVault 会帮你检查文件和链接是否齐全、论文信息是否对应，并核对你明确指定要对照的数字是否一致。论文有没有读懂、实验能支持什么结论，还需要你结合原文和结果来判断。

做实验时，也请留下没有成功的尝试：当时用了什么设置，遇到了什么问题，为什么没有得到预期结果。以后回头看，这些记录同样有用。

导入论文或创建记录前，可以先预览要做的改动。确认后再允许写入，并用 `--apply` 执行；如果配置仍是只读，工具会停止。Zotero 导入只添加新内容，不覆盖已有条目，也不直接改数据库。任务中途断了，可以按[导入指南](docs/IDENTIFIER_INTAKE.md)检查进度后继续。

把论文、笔记和实验数据放在自己的数据文件夹里，不要连同本地配置一起提交到代码仓库。查询论文信息和下载全文需要联网；如果会把未公开的材料交给 AI 助手，请先确认所用服务的数据处理方式。

## 更多文档

| 你想了解 | 从这里开始 |
| --- | --- |
| 安装并开始使用 | [安装工具](INSTALL.md) · [安装 Codex 插件](docs/CODEX_PLUGIN.md) |
| 设置资料保存位置和读写权限 | [配置说明](CONFIG.md) |
| 导入论文，或继续上次中断的导入 | [论文导入指南](docs/IDENTIFIER_INTAKE.md) |
| 读懂论文，分清原文与自己的理解 | [怎样读论文](references/reading.md) · [怎样标注来源](references/evidence.md) |
| 记录研究想法、实验过程和结论 | [研究与实验记录](references/science.md) |
| 了解功能或修改代码 | [功能说明](SPECIFICATION.md) · [代码结构](ARCHITECTURE.md) |
| 把旧版配置和笔记转过来 | [旧资料迁移](MIGRATION.md) |

开发者可在安装后运行：

```sh
python -m unittest discover -s tests -v
python scripts/audit_repository.py
python scripts/audit_plugin.py
```

完整检查见 [CI 配置](.github/workflows/ci.yml)，支持 Windows、macOS 和 Ubuntu。软件测试使用隔离的示例数据，不访问个人文献库。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。第三方依赖和论文等外部材料保留各自的许可，详见[许可说明](LICENSE_STATUS.md)和[第三方声明](THIRD_PARTY_NOTICES.md)。项目的来源记录见[来源说明](PROVENANCE.md)。
