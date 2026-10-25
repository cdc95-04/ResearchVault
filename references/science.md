# 怎样记录研究问题、实验和结论

研究记录要能回答三个问题：开始时想检验什么，实际做过哪些尝试，最后的结论由哪些结果支持。这样，即使实验失败、方法改过或换人接手，也能还原判断过程。

本说明对应软件 0.1.0 的 schema 2 记录格式。验证器检查身份、已经固定的定义和证据记录；它不能判断科学结论是否正确，不能批准机器人运行，也不能提供可信时间戳。

## 先把问题、猜想和方案分开

这些记录各有用途，不需要为了走流程把它们全部造出来：

| 记录 | 用来写什么 | 类型与身份字段 |
| --- | --- | --- |
| Question | 想弄清楚的研究问题 | `research-question` / `question_id` |
| Gap | 文献中可能尚未解决的问题，以及目前查证到了哪一步 | `research-gap` / `gap_id` |
| Hypothesis | 可以被证据支持或反驳的猜想 | `research-hypothesis` / `hypothesis_id` |
| Idea | 打算怎样研究或解决问题 | `research-idea` / `idea_id` |

Idea 可以停留在提议阶段、开始推进、放弃、合并、缩小范围，也可以回到 `more-literature`，继续查文献。Project 负责把相关记录连起来。流程不要求你在证据不足时编出一个“研究空白”。

## 做实验前，先写清要检验什么

Research Card 把待检验的主张具体化。这些内容固定下来后，称为 **Claim Lock**：以后修改时必须留下版本和原因，不能看完结果再悄悄改成更容易成立的说法。

`research-card` 使用以下字段：

| 字段 | 需要记录的内容 |
| --- | --- |
| `card_id`、`claim_id` | 研究卡和主张的稳定身份 |
| `proposition` | 主张本身，用文字写清楚 |
| `scope` | 主张适用于哪些条件 |
| `comparisons` | 与什么比较 |
| `mechanism` | 认为效果如何产生，用文字说明 |
| `falsifiers` | 什么观察会反驳这个主张 |
| `evidence_obligations` | 要支持主张，必须补齐哪些证据 |

`scope`、`comparisons`、`falsifiers` 和 `evidence_obligations` 要写成明确的列表或映射，不能只留一句笼统描述。

## 再写清实验准备怎样做

Experiment Contract 记录实验方案。固定后的方案称为 **Design Lock**，用来保证分析时能查到当初约定的条件和规则。

`experiment-contract` 必须包含：

- 身份和关联：`experiment_id`、`card_id`、`claim_id`、`claim_digest`。
- 实验设置：`conditions`、`baselines`、`metrics`、`seeds`。
- 统计与处理规则：`denominator`、`exclusions`、`abort_policy`、`analysis_plan`。

`conditions` 使用互不重复的文本 ID，`seeds` 使用互不重复的整数。`baselines` 和 `metrics` 不能是空列表。`exclusions` 可以为空；有排除项时，每项都要写 `reason`。

计算成功率或平均值前，先约定哪些尝试算进分母。`denominator` 中的 `unit` 用文字说明统计单位，`include_statuses` 从 `completed`、`failed`、`aborted`、`excluded` 中选择。

`abort_policy` 写明允许中止的原因 `allowed_reasons`，并用布尔值 `include_in_denominator` 说明中止是否计入分母。这个决定必须与 `denominator` 中是否包含 `aborted` 一致。`analysis_plan` 用明确文字或映射说明分析方法，不能根据结果是否好看再决定处理规则。

## 固定定义后，怎样留下可追溯记录？

`process.freeze(settings, path, 'claim'|'design', apply=False, previous=None, reason=None, timing='pre-result')` 会返回拟写入的元数据和回执路径。回执（receipt）是保存定义及内容校验值的文件，供以后核对这次操作。

使用 `apply=True` 时，函数只创建 receipt，不会修改 Markdown 页面。先审核页面改动，再把建议的 `claim_digest`、`claim_receipt`、`claim_lock_status` 或对应的 design 字段写入页面。锁定状态使用 `locked` 或 `exploratory`；后者表示探索性分析。

Receipt 保存在配置的 metadata 文件夹下的 `receipts/`。为保证同一内容得到稳定结果，JSON 序列化不允许非有限数值、递归结构或非 JSON 值；YAML 日期会转成 ISO 格式。科学定义快照和包含它的 receipt 整体分别计算 SHA-256，全部内容先完成序列化，再创建文件。已有文件不覆盖。

修改已有定义时，必须提供最新的 `previous` 摘要值和非空的 `reason`。同一张 Card 的 `claim_id` 在历史中保持不变，换 ID 或删掉页面上的 receipt 引用，都不能把已有历史清零。

一旦已有结果，新锁必须使用 `timing='post-result'`，状态为探索性；这条修改历史不能再变回“结果产生前”。历史结果继续指向当时实际检验的主张和实验方案。

## 每次尝试都保留，包括失败和重试

一个 Trial 对应一次实际尝试。`experiment-trial` 要记录：

- 身份与方案：`trial_id`、`experiment_id`、`design_digest`、`condition`、`seed`。
- 实际运行条件：`robot`、`environment`、完整的 `git_commit`，以及记录实际生效配置的 `config` 映射。
- 产物与状态：`raw_artifacts`、`status`，以及布尔值 `included_in_denominator`。

产物路径相对 Vault 填写，并且必须位于 Vault 内。

中止的尝试写 `abort_reason`，排除的尝试写 `exclusion_reason`，两者都必须符合已经固定的规则。失败或中止后没有原始产物时，写明 `missingness_reason`；完成的试验必须有原始产物。

重试使用新的 `trial_id`，并通过 `retry_of` 指回保留的旧尝试。两次尝试的实验、方案和条件必须一致。验证器会报告找不到的前序尝试和循环引用。

## 汇总结果时，不挑选有利的尝试

Result Bundle 把一次实验方案下的全部尝试放在一起分析。`result-bundle` 包含：

- 身份与关联：`result_id`、`experiment_id`、`claim_id`、`claim_digest`、`design_digest`。
- 纳入的尝试和缺失情况：`trial_ids`、`missingness`。
- 分析及结论：`verdict`、`status`、`analysis_artifacts`、`evidence_ceiling`。

`trial_ids` 必须覆盖该实验和方案下已经登记的每次尝试，包括失败、排除、中止和重试。`missingness` 的每一项写明 `trial_id` 和 `reason`，不能在汇总时把已知缺失省略掉。

实验结论使用四种状态，和文献阅读的核实标签分开：

| `verdict` | 含义 |
| --- | --- |
| `SUPPORTED` | 证据支持主张 |
| `NOT_SUPPORTED` | 证据不支持主张 |
| `INCONCLUSIVE` | 现有结果无法作出明确判断 |
| `NOT_TESTED` | 尚未检验 |

要作出明确结论，必须有已完成且计入分母的试验，原始产物也不能有尚未解决的缺失。结果标为 `completed` 时，必须有可访问的分析产物和明确的适用边界。方案在结果产生后修改过，则需要 `analysis_status: exploratory`。

## 写结论时，说清证据覆盖到哪里

`evidence_ceiling` 记录结论能够覆盖的范围。每个维度都列出已有证据支持的值：

`setting`、`robot`、`morphology`、`task`、`environment`、`seeds`、`replication`、`ood`、`transfer`。

某个维度填空列表，表示没有证明该维度的覆盖范围。这里记录的是证据边界，软件不会替研究者判断这个范围是否在科学上成立。

写作时，Claim Ledger 把文中的主张连到实验结果和文献。`claim-ledger` 使用 `claim_id`、`verdict`、`result_ids`、`literature` 和 `evidence_ceiling`；其中的文献必须指向真实的 `literature-note`。

Ledger 不能把没有定论或相互冲突的关联结果写成确定结论；它声明的范围也不能超出任何一个关联结果的范围。确定性表述需要已经完成的 Results，不能只依赖分析草稿。文献本身不能替本实验得出实验结论。明确写出的数字对应关系，由单独的 evaluation 模块检查。

## 哪些记录需要额外保存来源快照？

重要对象可以使用可选的 `provenance.snapshot(...)`，把页面、明确声明的输入或来源文件哈希，以及可选的工具版本绑定在一起。它返回建议的 `provenance_digest` 和 `provenance_receipt`，不会自行编辑页面。普通 Concept 不需要这种 receipt。

所有验证器都只读。验证通过说明记录满足检查规则，科学判断仍由研究者负责。
