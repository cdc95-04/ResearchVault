# 把选好的论文导入 ResearchVault

已经选好论文后，可以把 DOI、arXiv ID 或支持的论文网址交给 `researchvault intake`。它会核对论文信息、检查是否重复、获取合法可用的 PDF，再按授权存入 Zotero，并创建原文记录和阅读笔记初稿。

一次可以输入多篇，但工具只处理你给出的论文，不会顺便搜索或添加相关文献。下面按“先检查，再导入，中断后继续”的顺序说明。

## 1. 先检查输入

在安装 ResearchVault 的源码目录中运行，需 Python 3.10 或更新版本：

```powershell
python -m pip install -e '.[pdf]'
researchvault --config config/local.yaml intake 10.9999/example 2401.01234v2 --dry-run
```

这里的标识都是**演示占位值**，请换成你已经选好的论文。文中的后续命令也使用这些占位值。

`--dry-run` 只检查输入格式：识别 DOI 的不同写法，保留 arXiv 的精确版本。不加操作参数时也只做这一步。它不联网、不创建文件，也不需要 Zotero 或凭据。

可接受的输入包括：

- DOI、带 `doi:` 前缀的 DOI，以及标准 `https://doi.org/` 链接。
- 新式 arXiv ID，以及 arXiv 官方的 `/abs/`、`/pdf/` 链接。
- PMLR、NeurIPS、ICLR、CVF 的官方论文介绍页。

其他出版社的网址请先换成 DOI。旧式 arXiv ID 和普通网页需要人工确认标识。带查询参数、片段、账号密码、非标准端口或指向私有网络的链接会被拒绝。无效输入会使整批命令返回非零退出码；错误信息用输入的哈希值标识该项，不回显可能夹带秘密的完整网址。

## 2. 联网核对论文和 Zotero 中的已有记录

```powershell
researchvault --config config/local.yaml intake 2401.01234v2 --resolve
```

`--resolve` 查询论文的正式元数据，并读取配置中指定的 Zotero 文献库，检查是否已经有这篇论文。它不下载 PDF，也不保存导入计划。

这一步需要联网，并且 Zotero Local API 必须可用。连不上 Zotero 会报告连接受阻，不会把它当成“库里没有论文”。arXiv 查询逐条进行，两次标识查询至少间隔三秒。

去重时以 DOI、arXiv 精确版本或支持的出版社标识为依据。标题可以帮助查找和发现冲突，但不单独用来决定两条记录是否相同。期刊 DOI 和相关的 arXiv 版本会分别保留，不会悄悄合并。已有 arXiv 记录没有版本、找到多个可能匹配的条目或 PDF、身份信息互相矛盾时，都需要先核对。

## 3. 确认后再允许导入

### Zotero 版本和写入凭据

新建文献条目和上传 PDF 需要 **Zotero Desktop 10+**，并开启“允许此计算机上的其他应用程序与 Zotero 通讯”。只读 API 请求不需要 key；写入需要这个 Zotero 实例签发的 **Local API key**，不能使用 zotero.org 网站上的 Web API key。

本地 key 只能在运行时通过 Zotero 的授权弹窗取得。按[官方授权说明](https://www.zotero.org/support/dev/web_api/v3/local_api#authorizing_writes)，授权客户端先读取 `/api/` 返回的 Server ID，再带这个 ID 向 `/api/local/authorize` 发送应用名称。用户在 Zotero 中确认后，客户端才能取得 key。一次导入包含多次写入，因此需要用户选择“始终允许”后返回的 `remember: true` key；单次“允许”的 key 会在首次写入后失效。

**当前 ResearchVault CLI 没有首次授权入口，也不会自动打开这个弹窗。** 如果还没有通过上述流程取得的 key，先使用 `--resolve` 预览，或复用 Zotero 中已经存在且核验通过的论文和 PDF。不要为通过这一步改用 Web API key、读取数据库或关闭凭据检查。已有受保护凭据可由你信任的凭据工具注入当前进程，不需要重新授权。

如果你已经安全取得可复用的本地 key，Windows PowerShell 可以这样让它只供这次终端中的导入使用。先完成下方的数据目录设置，确认论文并允许本次写入，再运行；把论文标识占位符换成实际值。输入时不会显示 key，也不会把 key 写进命令历史：

```powershell
if (Test-Path Env:RESEARCHVAULT_ZOTERO_KEY) {
    throw '环境变量已存在；直接使用下方导入命令，无需重复输入 key。'
}
$localKeyInput = Read-Host '输入已获授权的 Zotero Local API key' -AsSecureString
try {
    $env:RESEARCHVAULT_ZOTERO_KEY = [System.Net.NetworkCredential]::new('', $localKeyInput).Password
    researchvault --config config/local.yaml intake '<arxiv-id-and-version>' --apply --enable --allow-zotero-create
} finally {
    Remove-Item Env:RESEARCHVAULT_ZOTERO_KEY -ErrorAction SilentlyContinue
    $localKeyInput.Dispose()
}
```

示例使用默认的环境变量名；若配置改了 `api_key_env`，应对应修改。它不会写入或删除系统凭据管理器里的 key。其他系统也应由可信凭据工具向当前进程注入环境变量，避免在 shell 命令里直接写密钥。不要打印环境变量、授权响应或 HTTP 认证头。

### 允许本次操作

先按[配置说明](../CONFIG.md)准备数据目录：Vault 保存研究记录，Runtime 保存下载和处理进度。它们必须分别放在代码仓库外，彼此不能嵌套。通过 `init` 预览并创建缺少的目录和模板，本地配置继续由 Git 忽略。

配置中的目标可以是个人文献库（`library_id: null`，API 路径 `users/0`），也可以是明确指定的一个群组库。

执行导入前，需要你确认本次论文列表，并在这份本地配置中设置 `read_only: false`。命令不会替你改这个开关；完成后请恢复 `read_only: true`。如果让 AI 助手操作，也应明确授权本次范围。

```powershell
# 写入凭据需事先通过配置指定的环境变量提供。
# 不要把凭据值直接写进命令、YAML、日志或 Git。
researchvault --config config/local.yaml intake 2401.01234v2 --apply --enable --allow-zotero-create

# DOI 下载途径可能还需要提供给 Unpaywall 的联系邮箱：
researchvault --config config/local.yaml intake 10.9999/example --apply --enable --allow-zotero-create --email you@example.org
```

这三个参数各有用途：

| 参数 | 允许做什么 |
| --- | --- |
| `--apply` | 实际执行，不再停在预览 |
| `--enable` | 仅为本次操作开启全文获取，不修改全局 `acquisition.enabled` |
| `--allow-zotero-create` | 允许新建 Zotero 文献条目和附件；仍需有效凭据，也不能绕过只读设置 |

如果 Zotero 中已有核验通过的论文和 PDF，可以只读复用，不需要 Zotero 写入凭据。但把它归档到 Vault 仍需要明确授权并允许写入 Vault。

缺少凭据、网络不可用或 Zotero 无法连接时，相应步骤会停止。这个命令不会读取数据库来替代 API，也不会自行弹出授权申请。

### PDF 怎样获取和核对

开始下载前，工具会保存并固定本次查到的论文信息和来源响应，先检查 Zotero 中的已有记录。作者姓名按来源保留，使用 Zotero 的单字段 `name` 写法，不猜测姓名如何拆分。

下载依次尝试：已有且核验通过的 Zotero PDF、论文元数据中记录的官方合法开放获取地址、Unpaywall 返回的出版社或资料库开放获取地址。各途径逐个尝试，失败原因分别记录。不绕过付费墙或验证码，不使用登录 Cookie，也不使用盗版来源。

下载成功还要检查是否真是选定的那篇、那个版本的主论文。只有核验为 `VERIFIED`，且选择的版本、文件中识别出的版本、下载来源的版本一致时，才会自动导入。仅为 `PROBABLE`、身份不明确、论文不符、补充材料或损坏文件，都会停止这一项。能否下载、是否允许使用和文件身份是分开的检查，不能相互替代。

Runtime 按 SHA-256 保存 PDF，相同字节可以复用，但不会因此合并不同文献身份。本命令没有核验通过的 PDF 就不新建 Zotero 条目；选中的论文及失败原因仍会保存在处理记录中。

### 怎样确认 Zotero 确实存好了

每次写入前先保存操作意图，完成后保存结果回执，供中断时核对。流程是：创建文献条目后重新读取，再上传 PDF 附件并重新读取。最后通过 `/file/view/url` 找到 Zotero 中的实际附件，对照 API 的 MD5 和下载文件的 SHA-256。

随后创建的 Fulltext 指向已核实的 Zotero 附件，不只是临时下载文件。整个过程不打开或修改 SQLite 数据库。

缺少写入凭据时会返回 `ZOTERO_WRITE_CREDENTIAL_REQUIRED`；已经合法下载并核验通过的文件会保留。Zotero Local API 不可用时返回 `ZOTERO_LOCAL_API_UNAVAILABLE`。

相关服务的接口说明：[Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[Unpaywall](https://data.unpaywall.org/products/api)、[arXiv](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md)、[Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)。

## 4. 任务中断后怎样继续

使用指向同一论文身份的输入，并加上 `--resume`：

```powershell
researchvault --config config/local.yaml intake 2401.01234v2 --apply --enable --allow-zotero-create --resume
```

恢复时沿用已固定的元数据、精确版本、来源响应和文件哈希，不会改查更新版本。如果已有处理记录却没带 `--resume`，会返回 `RESUME_REQUIRED`。缓存中的论文信息或 PDF 哈希出现冲突时，也会停止。

每次运行会锁定 Runtime 中的 intake 任务，避免同时处理。进程被强制结束可能留下 `intake/workflow.lock`。先确认没有进程还在运行，再检查状态和回执；只有确认是遗留锁后，才由操作者移除。工具不会自动删锁，也不会在不清楚上一次写入是否成功时直接重试。

如果回执是 `MANUAL_RECONCILIATION_REQUIRED`，需要先通过只读查询核对真实状态。即使重新查看文献库时出现一个看似匹配的条目，也不能据此自动继续写入。

Fulltext 和 Paper Note 会先在配置指定的 metadata 目录下暂存并记录哈希，默认位置是 `.meta/imports/intake/`。文件内容写入完成后，再通过同一文件系统内的硬链接创建正式记录。不支持这种操作的文件系统会停止，而不会降级为可能覆盖内容的写入。

如果两份记录只创建了一份，恢复时使用原来的暂存内容补齐缺少的那份。Zotero 和本地文件不是一个能整体回滚的事务：已完成的工作会保留，不会因另一篇失败而删除。已有记录被编辑过则报告冲突；修改它需要走已有的差异审查流程，不能静默覆盖。

## 5. 导入后怎样开始阅读

自动生成的 Paper Note 包含全部 17 节、准确的 Zotero 和 Fulltext 关联、PDF 与提取文本的 SHA-256，以及文献信息的来源。它仍是初稿：

| 字段 | 自动归档后的状态 |
| --- | --- |
| `status` | `draft` |
| `read_status` | `partial` |
| `evidence_status` | `unverified` |
| `human_review_status` | `pending` |

没有提供阅读分析时，结果是 `ARCHIVED_ANALYSIS_PENDING`：资料已归档，科学阅读还没完成。生成的 `analysis-handoff.json` 会告诉已有的 `paper-note-writer` Skill 到哪里找原文、还需要核查什么。

### 把已有分析交给导入命令

如果助手已经按原文阅读，可以用 `--analysis analysis.json` 提供明确的分析记录。JSON 以**解析后固定的论文 ID**为键，例如：

```json
{
  "arxiv:2401.01234v2": {
    "pdf_sha256": "<64 lowercase hex digits from the verified PDF>",
    "facts": [{
      "statement": "An agent paraphrase, still labelled interpretation.",
      "quote": "An exact excerpt that actually occurs on the specified page.",
      "page_index": 1
    }],
    "interpretations": ["Model analysis, explicitly not a paper fact."],
    "hypotheses": ["An unverified hypothesis for a later experiment."]
  }
}
```

示例里的正文、引文和哈希都必须换成真实内容。`page_index` 是提取文本中的页序号，从 1 开始，不是论文印刷的页码。PDF 哈希、页序号和逐字引文都要匹配。

找到同一句原文，只能证明引文存在，不能证明助手的解释成立。印刷页码、图表、公式和提取是否完整仍需核查。助手的转述会标为 `interpretation`，研究猜想会标为 `speculative`，不会自动升级为已证实的结论或文献已经确认的研究空白。

CLI 不内置大模型服务，也不引入模型凭据；科学阅读由已有 Skill 配合助手完成。恢复任务时提供新的分析，也不会悄悄重写已存在的笔记。

## 去哪里看进度和失败原因

每篇论文的运行记录在 `runtime/intake/workflows/<hash>/`：

| 文件 | 内容 |
| --- | --- |
| `candidate.json` | 固定后的论文信息 |
| `state.json` | 当前处理进度 |
| `events.jsonl` | 按时间追加的事件，不改写旧事件 |
| 文献条目和附件的回执 | 需要写入 Zotero 时，记录写入意图与结果 |

PDF 存在 `runtime/intake/artifacts/<sha256>.pdf`，相同文件只存一份。错误日志只写固定状态码和异常类别，不记录远程异常原文、API key 或联系邮箱。

这些文件用于恢复操作，不能代替 Zotero 文献条目或 Vault 研究记录。PDF、Runtime 状态和本地配置都不应提交到 Git。

CLI 输出 JSON，退出码含义如下：

| 退出码 | 含义 |
| --- | --- |
| `0` | 预览成功，或资料归档完成；`ARCHIVED_ANALYSIS_PENDING` 仍表示阅读待完成 |
| `1` | 整批中有部分失败或受阻，逐项查看结果 |
| `2` | 配置、权限保护或任务锁等全局问题，无法继续 |

某篇失败不会回滚其他论文，也不会隐藏已经完成的写入。

## 怎样检查安装和测试结果

```powershell
python -m unittest discover -s tests -p test_resolution.py -v
python -m unittest discover -s tests -p 'test_identifier*.py' -v
python -m unittest discover -s tests -v
researchvault --config config/local.yaml validate
```

端到端自动测试会使用真实的解析、PDF 检查与提取、Zotero 客户端、回执和 Vault 检查代码，但把网络接口换成可控响应，文档也使用合成数据。因此测试通过不代表出版社现在能下载，也不代表你的 Zotero 已经完成真实写入验收。

实现范围见[导入功能说明](IDENTIFIER_INTAKE_AUDIT.md)，测试覆盖见[测试记录](IDENTIFIER_INTAKE_RESULTS.md)。实际安装可按[环境连接检查](PHASE1_ENVIRONMENT_DIAGNOSTICS.md)和[真实环境验收步骤](PHASE1_REAL_ACCEPTANCE.md)验证。真实路径、条目 key、个人文献清单、源文件哈希和运行日志留在本地，不提交到版本库。
