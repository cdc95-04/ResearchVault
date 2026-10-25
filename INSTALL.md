# 安装 ResearchVault

ResearchVault 分为两部分：**Python 工具负责处理文件和检查记录，Codex 插件负责指导 AI 助手完成研究任务。** 只想先试命令行，可以先安装 Python 工具；要在 Codex 中使用这些任务，再安装插件。

你需要 Python 3.10 或更新版本，以及这个仓库的本地副本。安装不需要旧原型项目、Zotero 数据库、真实 PDF 或已有的 Obsidian 笔记库。

## 1. 安装 Python 工具

在仓库目录中创建虚拟环境：

```sh
python -m venv .venv
```

激活虚拟环境：PowerShell 使用 `.venv\Scripts\Activate.ps1`，macOS、Linux 等 POSIX shell 使用 `source .venv/bin/activate`。

然后安装并检查：

```sh
python -m pip install -e ".[pdf]"
researchvault --version
python -m researchvault --config examples/synthetic.yaml validate
python -m unittest discover -s tests -v
python scripts/audit_repository.py
```

这组命令使用仓库自带的示例数据。安装检查不需要连接个人文献库，也不要在这一步开始真实文献验收。

`PyYAML` 是必需依赖；`[pdf]` 会额外安装 `pypdf` 和 `fonttools`，用于提取 PDF 文本、检查页数和诊断字体映射。完整测试和 CI 都使用这个安装选项。安装 Python 包不会安装 AI 助手运行环境、浏览器自动化工具、Obsidian 插件或 Codex 插件，也不会修改其他应用。

**请保留这个仓库目录。** 0.1.0 支持上面的 `-e` 安装方式：工具仍从仓库读取模板、Skills 和参考文档。独立 wheel 安装后的资源布局尚未验证。安装完成后，可以从其他目录运行命令，但要明确提供配置文件路径或 Vault 根目录。

## 2. 准备自己的资料目录

先按 [配置说明](CONFIG.md) 创建被 Git 忽略的 `config/local.yaml`，把真实路径写在那里。全局选项要放在子命令前面：

```sh
researchvault --config config/local.yaml init
researchvault --config config/local.yaml init --apply
researchvault --config config/local.yaml validate
```

- 第一条只预览将要创建的目录和模板。
- 第二条创建缺少的目录和模板，保留已有文件及用户修改。配置为 `read_only: true` 时，即使加了 `--apply` 也不能写入。
- 第三条检查配置和记录，不修改资料。

## 3. 在 Codex 中安装插件

插件把现有的 12 个 Skills、参考文档和模板交给 Codex。Skill 是一份任务说明，告诉 AI 助手该读取哪些材料、如何完成某类工作。

通过个人插件目录安装仓库根目录中的插件，并用明确的 commit SHA 固定版本。具体步骤、更新方法，以及 Python 工具不可用时的处理方式，见 [Codex 插件安装说明](docs/CODEX_PLUGIN.md)。插件安装不会替你执行 pip，也不会创建资料目录。

后续修改只在原仓库中完成；Codex 缓存中的副本仅供运行，不要把它当成第二份开发源码。也不要再把 12 个 Skills 单独复制到用户 Skills 目录，以免同时出现两套相同任务。

使用时，只加载与当前任务有关的 `skills/<name>/SKILL.md` 及其引用的资料，不必一次读取所有 Skills。

## 版本和开发检查

软件版本统一来自 `pyproject.toml` 的 `project.version`。安装后的包信息会提供 `researchvault.__version__`、命令行版本和对外请求中的版本标识。导入 Python 包前需要先安装；项目没有另行维护一份“未安装源码版本”。配置文件不能改变软件版本，记录中的 `schema_version: 2` 则是另一回事：它表示数据格式版本。

GitHub Actions 在临时环境中运行测试，并下载公开依赖。若要运行 `scripts/audit_dependencies.py`，需另行安装 `pip-audit`。它检查实际安装的 PyYAML、pypdf、fonttools 及其在当前环境中生效的传递依赖，不向漏洞查询服务发送私有包信息。
