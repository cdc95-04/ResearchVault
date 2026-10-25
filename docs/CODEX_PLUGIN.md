# 在 Codex 中使用 ResearchVault

安装这个插件后，Codex 可以按 ResearchVault 的步骤帮你读论文、查笔记、整理研究问题和记录实验。插件包含现有的 12 个 Skills，以及共用的参考文档和模板。

**插件和 Python 工具需要分别安装。** 插件给 AI 助手提供任务说明；Python 工具负责文件处理、API 调用和确定性的检查。先按 [安装说明](../INSTALL.md) 运行 `python -m pip install -e ".[pdf]"`，再按本页安装插件。安装插件本身不会运行 pip、创建 Vault、扫描个人文件或修改其他应用。

## 安装前需要准备什么

以下 Git 安装方式已在 **Codex CLI 0.160.0** 上完成验证。其他版本可先运行 `codex plugin --help` 确认命令是否可用。个人插件清单位于 `~/.agents/plugins/marketplace.json`，`~` 表示你的用户主目录。这里的 marketplace 是一份插件来源清单，不是把项目发布到公共商店。

需要 Git、支持 `codex plugin` 命令的 Codex CLI，以及能够访问的仓库版本。后续编辑仍在原仓库完成；不要修改 Codex 安装缓存中的副本。

## 安装步骤

先在原仓库运行 `git rev-parse HEAD`，取得完整 commit SHA，并确认这个提交已经推送到 GitHub。下面的 `<commit-sha>` 必须替换成这个值，不能原样保留。

### 第一次创建个人插件清单

如果 `~/.agents/plugins/marketplace.json` 不存在，创建缺少的 `.agents/plugins/` 目录，再将下面的完整 JSON 保存为 `marketplace.json`。不要把它保存进 ResearchVault 仓库，也不要覆盖已有文件。

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal plugins"
  },
  "plugins": [
    {
      "name": "researchvault",
      "source": {
        "source": "url",
        "url": "https://github.com/cdc95-04/ResearchVault.git",
        "sha": "<commit-sha>"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

这个结构和 Git 来源写法见 [OpenAI 官方插件文档](https://developers.openai.com/plugins/build/plugins#marketplace-metadata)。`personal` 是这份清单的名称，不是操作系统用户名。

### 已经有个人插件清单

保留现有文件中的 `name`、`interface` 和其他插件。只把上面 `plugins` 数组里的 `researchvault` 对象加入已有数组；如果已经有同名条目，只更新它的 `source.sha`，不要再加第二份。JSON 对象之间需要逗号，最后一项后不加逗号。

### 安装并检查

如果清单顶层的 `name` 是 `personal`，执行：

```sh
codex plugin marketplace list --json
codex plugin add researchvault@personal --json
codex plugin list --json
```

如果已有清单使用别的名称，把 `researchvault@personal` 中的 `personal` 换成那个名称。第一条命令应列出你的清单，最后一条应列出已安装的 `researchvault`。

Codex 会发现默认位置的个人插件目录。如果清单放在别处，先运行 `codex plugin marketplace add <marketplace-root>`，其中目录内应有 `.agents/plugins/marketplace.json`。如果 GitHub 提示需要仓库权限，使用 Git 的正常认证方式；不要把 token 写进插件声明或清单。仓库可见性不会由安装命令改变。

安装完成后，新建一个 Codex 会话；桌面应用也可以重启，以刷新插件列表。

## 为什么从 Git 安装

在已验证的 Codex 0.160.0 中，直接安装本地目录会递归复制文件，**不会按 `.gitignore` 排除内容**。如果直接指向日常开发目录，被忽略的本地配置和其他私人文件也可能被复制。

上面的 Git 来源会先取出已提交的内容，再完成安装，避开对整个工作目录的复制。安装缓存仍可能保留克隆产生的 Git 元数据。`file://` Git 来源虽能通过参数解析，但尚未完成实际执行验证，所以本说明使用已验证的 HTTPS 方式。

这些行为可对照固定版本的官方实现：[复制插件文件](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core-plugins/src/store.rs#L736)、[获取 Git 来源](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core-plugins/src/loader.rs#L1747)。

安装副本通常位于 `$CODEX_HOME/plugins/cache/personal/researchvault/0.1.0`。已验证的安装中，39 个 Skill、参考文档和模板文件与仓库原文件逐字节一致，没有包含被忽略的 QA 文件、虚拟环境、本地配置或 PDF。缓存只是运行副本，不是另一份开发仓库。

## 以后怎样更新

1. 在原仓库修改、检查、提交并推送。
2. 把个人插件条目的 `sha` 改成新的完整提交 SHA。
3. 再运行 `codex plugin add researchvault@personal --json`。
4. 新建会话，加载更新后的插件。

即使版本号仍是 0.1.0，重新安装也会刷新缓存。不需要为了刷新而编造新版本号，更不要直接编辑缓存。

marketplace 的 `upgrade` 用于刷新来自 Git 的插件目录；这里的个人目录是本地文件，应修改插件的提交 SHA 后重新安装。

如果之前单独安装过 ResearchVault 用户 Skills，先确认插件列表正常，再删除或禁用那套旧入口，避免两套同名任务同时生效。原仓库中的 Skills 和其他资源应保留。

## 怎样让它开始工作

在新会话中直接说具体任务，例如：

- “用 ResearchVault 阅读这篇已确定的机器人论文，整理成 Paper Note。”
- “用 ResearchVault 查看 Zotero 中已有的这篇论文。”
- “在我的 ResearchVault 笔记里，查找机器人自我模型与形态适应之间的证据。”
- “根据已有的 ResearchVault 资料，帮我提出一个能通过实验检验的研究假设。”
- “围绕这个研究问题，对明确限定的文献范围做系统综述。”

这些请求分别对应论文笔记、Zotero 读取、本地检索、研究问题和系统综述的现有 Skills。无关的 Python 修复不需要加载它们。

每次只读取相关 Skill 和必需的资料。读一篇论文，不需要顺便加载全部综述或实验文档。

## Python 工具不可用时怎么办

执行文件处理或校验前，先在当前环境运行 `researchvault --version` 或 `python -m researchvault --version`。

如果两者都不可用，应报告 `runtime unavailable`，按 [安装说明](../INSTALL.md) 处理。此时可以继续不依赖 Python 工具的说明和资料整理，但不能用一段文字或临时编写的检查器替代记录格式检查、研究主张固定版本（Claim Lock）的摘要计算等安全检查。

资料目录和只读模式仍由被 Git 忽略的本地配置明确设置，见 [配置说明](../CONFIG.md)。插件安装不会替你放宽这些限制。

## 打包与验证范围

仓库根目录的 [plugin.json](../plugin.json) 是 Agent Plugins 声明文件。Skills 保留在 `skills/`，通过相对链接使用共用的 `references/` 和 `templates/`；已验证的安装不需要额外兼容层、MCP、hooks 或 apps。

软件版本来自 `pyproject.toml`，打包检查会确认它与 `plugin.json` 一致。Vault 的 schema 2 表示记录格式，独立于插件和软件版本。格式说明见 [OpenAI 官方插件文档](https://developers.openai.com/plugins/build/plugins)。

插件检查使用示例提示词和测试数据，不读取个人 Zotero 或 Vault。通过检查说明插件的文件和配置符合要求，科学内容仍需单独审核。维护用的论文评估及待审核事项见[语义与检索评估记录](SEMANTIC_RETRIEVAL_EVALUATION.md)。

项目采用 [MIT 许可证](../LICENSE)。这些步骤只安装插件，不会改变 GitHub 仓库的可见性或发布到公共插件目录。
