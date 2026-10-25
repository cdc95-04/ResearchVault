# 配置自己的资料目录

ResearchVault 不会自动选择你的个人笔记库。默认配置的 `vault_root` 是 `null`；准备使用真实资料时，需要明确告诉工具：笔记放在哪里、下载文件放在哪里、连接哪个 Zotero 文献库，以及是否允许写入。

## 先准备一份本地配置

把 `config/default.yaml` 复制为被 Git 忽略的 `config/local.yaml`，再填写自己的路径。下面的路径只是可移植示例：配置文件保存在 `config/` 时，它们会指向仓库之外的两个目录。

```yaml
schema_version: 2
vault_root: ../../personal-research-data
runtime_dir: ../../research-downloads
synthetic: false
read_only: true
zotero:
  library_id: null
  api_key_env: RESEARCHVAULT_ZOTERO_KEY
acquisition:
  enabled: false
  max_bytes: 104857600
  interval: 1.0
discovery:
  enabled: true
  limit: 10
```

这里的 `read_only: true` 是建议的起步设置，不是默认配置已经替你开启的保护。它让你先检查连接、路径和已有记录，再决定是否允许写入。

运行时明确指定这份文件：

```sh
researchvault --config config/local.yaml validate
```

工具按以下顺序选择配置，只使用最先找到的来源：

1. 命令行中的 `--config`。
2. 环境变量 `RESEARCHVAULT_CONFIG`。
3. 当前目录下的 `config/default.yaml`（如果存在）。

`config/local.yaml` 不会因为文件名叫 local 就被自动加载。YAML 中的相对根目录从**配置文件所在目录**计算；命令行 `--vault` 会覆盖配置中的 Vault 路径，并从**当前工作目录**计算相对路径。

## 资料应该放在哪里

`vault_root` 是长期保存笔记和研究记录的目录；`runtime_dir` 是下载等运行文件所在的目录。两者必须分开，真实资料也必须放在代码仓库之外。

`paths` 对应 13 类目录用途，`folders` 定义各类目录下的分类。默认值统一保存在 `researchvault/config.py` 中。检查会拒绝互相重叠的目录用途、越界路径、不适用于当前系统的根路径，以及通过符号链接逃出指定目录的路径。

仓库内部只允许明确标为 synthetic 的示例目录，位置限于 `examples/`、`tests/fixtures/` 或 `synthetic-vault/`。

## 只读模式保护哪些操作

`read_only: true` 会在写入前阻止修改操作，`--apply` 也不能绕过它。全局选项 `--read-only` 可以开启同一保护；命令行的默认值不能关闭配置中已经开启的只读模式。这个配置只接受真正的 YAML 布尔值，例如 `true`，不接受字符串 `"true"`。

`validate` 在两种模式下都只读。开启只读保护后，诊断仍保留错误代码和严重程度，但不输出自由文本详情或外部路径。这个设置只约束 ResearchVault 的相关入口，不是用来限制任意外部脚本的文件系统沙箱。

## 连接 Zotero

- `library_id: null` 表示 Personal Library，对应 Local API 的 `users/0`。
- 正整数表示群组库，对应 `groups/<id>`。
- `api_key_env` 指定存放凭据的环境变量名。凭据值只能放在该环境变量中，不能写进 YAML。

新建条目和上传 PDF 需要 **Zotero 10+** 签发的本地 API key；它与 zotero.org 网站上的 Web API key 不通用。只读 API 请求不需要 key。首次授权的限制和已有 key 的使用方式见[导入指南](docs/IDENTIFIER_INTAKE.md#zotero-版本和写入凭据)。

填对库标识不等于连接已经可用，也不代表已经验证过有文献的真实库。请按 [Zotero 只读检查说明](docs/REAL_READONLY_VALIDATION.md) 检查你实际使用的 Zotero。

## 本地文件相关命令

以下命令的全局选项仍须放在子命令前，例如 `researchvault --config config/local.yaml init`。

| 命令 | 用来做什么 |
| --- | --- |
| `init [--apply]` | 预览或创建缺少的目录和模板 |
| `validate` | 只读检查记录、证据链接、科研记录格式和审核状态；不判断科学结论是否正确 |
| `resolve --zotero-key KEY` | 在本地解析笔记身份；也可明确提供 DOI、arXiv 或标题作为查询输入 |
| `archive metadata.yaml source.txt [--method cache] [--note-path ...] [--apply]` | 保存原文；提取 PDF 时使用 `--method pdf` |
| `retrieve QUERY [--supplementary]` | 搜索本地笔记和知识记录，必要时补充搜索 Fulltext 原文 |
| `ingest selected-batch.json [--apply]` | 处理明确列出的归档任务，分别保留未能完成的条目及原因 |
| `diff record.md proposed.md` | 查看拟修改内容与原记录的差异，不应用修改 |
| `migration-plan` | 列出需要人工对应到新格式的记录 |
| `claim-lock record.md` / `design-lock record.md` | 预览研究主张或实验设计的固定版本记录及配套元数据 |
| `corpus-freeze protocol.md` | 预览综述方案和文献集合的固定版本记录 |
| `snapshot record.md` | 按需保存通用的来源快照 |

固定版本记录和快照使用 receipt（回执文件）保存操作依据。这些命令接受 `--apply`、`--previous DIGEST` 和 `--reason TEXT`。研究主张和实验设计的锁定命令还接受 `--timing post-result`；结果出来后才做的修订必须按探索性工作处理。

命令不会把建议的元数据自动塞进正文。先查看输出，再有意识地修改页面，最后运行检查。

`ingest` 的输入是 JSON 或 YAML 列表，每项包含 `record`（文献库、论文父条目和 PDF 身份）、`source_path`，以及可选的 `method` 和 `note_path`。它不会替你生成论文分析笔记。源文件必须是代码仓库和真实 Vault 之外的原文或 PDF；已经归档的相同来源可以复用，有冲突的已有内容不会被替换。

## 需要联网或写入 Zotero 的命令

`discover QUERY` 从 Crossref 查找文献。`acquire candidates.json --select DOI --enable --email CONTACT` 为选定论文寻找合法公开全文，只在外部运行目录中保存下载状态，不修改 Zotero。

下载默认关闭，必须由配置开关或本次命令的显式 `--enable` 允许。一次下载许可不等于允许所有网络操作或 Zotero 写入。

`zotero-inventory` 和 `zotero-resolve` 只读访问配置中的 Local API。`zotero-create metadata.json` 和 `zotero-import candidate.json PARENT PDF` 则先预览新增内容。真正执行需要 `--apply`，还需要通过 `--receipt` 指定一个相对于配置中 **Runtime 目录**的持久回执文件，例如 `--receipt zotero-receipts/paper-create.json`。不要把回执放进 Vault 或代码仓库，也不要为重试同一次写入换一个回执名。

如果已有回执显示写入结果不确定，先核对 Zotero 中的实际状态，不要盲目重试。已有批注和附件不会被替换。协议细节见 [论文下载和导入规则](references/intake.md)。

实际写入前，仍需确认你已授权本次操作。自动化测试用模拟网络响应检查这些分支，不会因此获得访问或修改个人文献库的权限。

## 评估命令和旧配置

`eval-run SUITE CAPTURES [--output RESULT]`、`eval-compare LEFT RIGHT` 和 `numbers INPUT` 用于研究评估。它们读取明确指定的捕获结果和数值映射文件，不需要 Vault 根目录。输入格式和结果局限见 [评估工具说明](evals/README.md)。

旧配置中的 `project_version`、`language` 和 `zotero.data_dir` 必须删除，即使值是 `null` 也会报错。这些字段没有对应功能：软件版本来自安装包，没有运行时语言设置，也不通过这里指定 Zotero 数据库目录。

如需单独只读检查文件系统，使用 `scripts/validate_environment.py --zotero-data ROOT --vault ROOT --workspace ROOT`，并明确提供来源根目录和隔离的输出目录。

软件版本由 `pyproject.toml` 的 `project.version` 定义，运行时从安装包信息读取。记录中的 `schema_version: 2` 表示数据格式版本，不能与软件版本混用。
