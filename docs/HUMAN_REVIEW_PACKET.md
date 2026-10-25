# 人工审核包：9 个语义案例 + 1 个 SAC 修订

状态：`human_review_status: pending`。以下判定均为 Astra Ultra 的独立 agent review，尚非人工 Ground Truth。

原定十项审核仍全部待填；末尾增加一项本轮新发现的 DDIM 来源差异，当前共 **11 项 pending**。

请对每条填写 `ACCEPT_GOLD`、`REVISE_GOLD` 或 `REJECT_CASE`。前者接受当前来源解释和案例；修订时保留原值及证据并另建版本；拒绝时保留拒绝原因。未填写不会被当作同意。

PDF 页码为一基页码；来源版本及哈希见 [冻结清单](../validation/golden/b2/freeze.json)。这里只给最小来源释义；完整候选和十维判定见 [语义结果](../validation/golden/b2/semantic_results.json)。

## sac2018--wrong_numeric_observation

论文／来源：Soft Actor-Critic (ICML 2018)，PDF p.7，Section 5.1, Figure 1 protocol。

来源释义及预期解释：第6–7页为Gym/rllab基准。每算法5个种子，每1000环境步评估一次；均线与阴影分别为回报均值及极值。

候选的错误字段（`observation`）：The reported success rate is 98765 percent.

Agent verdict：**FAIL**。正文协议成立；锚定指标为回报，observation捏造成功率且数值越界。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sac2018--overbroad_scope

论文／来源：Soft Actor-Critic (ICML 2018)，PDF p.7，Section 5.1, Figure 1 protocol。

来源释义及预期解释：第6–7页为Gym/rllab基准。每算法5个种子，每1000环境步评估一次；均线与阴影分别为回报均值及极值。

候选的错误字段（`scope`）：Proves universal success on every robot and task.

Agent verdict：**FAIL**。正文与重复观察获支持；scope却宣称普遍成功，超出有限实验或设置证据。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sac2018--wrong_table_condition

论文／来源：Soft Actor-Critic (ICML 2018)，PDF p.7，Section 5.1, Figure 1 protocol。

来源释义及预期解释：第6–7页为Gym/rllab基准。每算法5个种子，每1000环境步评估一次；均线与阴影分别为回报均值及极值。

候选的错误字段（`observation`）：These measurements are from every physical robot with unseen tasks.

Agent verdict：**FAIL**。正文成立且scope有限定；observation与之冲突，把局部仿真证据说成全部实机的未见任务结果。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## diffusion_policy2023--wrong_numeric_observation

论文／来源：Diffusion Policy (RSS 2023)，PDF p.6，Table II Transport ph; Table I caption and Section V.B on page 7。

来源释义及预期解释：第6页视觉Transport PH列：C为1.00/0.93，LSTM-GMM为0.88/0.62；表注及第7页说明最佳/末10检查点、3种子×50初始化，属仿真。

候选的错误字段（`observation`）：The reported success rate is 98765 percent.

Agent verdict：**FAIL**。正文主张成立，但observation捏造成功率；整条候选不受支持。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## diffusion_policy2023--overbroad_scope

论文／来源：Diffusion Policy (RSS 2023)，PDF p.6，Table II Transport ph; Table I caption and Section V.B on page 7。

来源释义及预期解释：第6页视觉Transport PH列：C为1.00/0.93，LSTM-GMM为0.88/0.62；表注及第7页说明最佳/末10检查点、3种子×50初始化，属仿真。

候选的错误字段（`scope`）：Proves universal success on every robot and task.

Agent verdict：**FAIL**。正文与重复观察获支持；scope却宣称普遍成功，超出有限实验或设置证据。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## diffusion_policy2023--wrong_table_condition

论文／来源：Diffusion Policy (RSS 2023)，PDF p.6，Table II Transport ph; Table I caption and Section V.B on page 7。

来源释义及预期解释：第6页视觉Transport PH列：C为1.00/0.93，LSTM-GMM为0.88/0.62；表注及第7页说明最佳/末10检查点、3种子×50初始化，属仿真。

候选的错误字段（`observation`）：These measurements are from every physical robot with unseen tasks.

Agent verdict：**FAIL**。正文成立且scope有限定；observation与之冲突，把局部仿真证据说成全部实机的未见任务结果。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sim2real2018--wrong_numeric_observation

论文／来源：Sim-to-Real (arXiv v3)，PDF p.4，Section IV.C。

来源释义及预期解释：第4页描述95项仿真随机化；质量/阻尼每回合固定，步长/观测噪声逐步变化。第5–6页澄清步长分布参数λ回合内固定。

候选的错误字段（`observation`）：The reported success rate is 98765 percent.

Agent verdict：**FAIL**。正文主张成立，但observation捏造成功率；整条候选不受支持。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sim2real2018--overbroad_scope

论文／来源：Sim-to-Real (arXiv v3)，PDF p.4，Section IV.C。

来源释义及预期解释：第4页描述95项仿真随机化；质量/阻尼每回合固定，步长/观测噪声逐步变化。第5–6页澄清步长分布参数λ回合内固定。

候选的错误字段（`scope`）：Proves universal success on every robot and task.

Agent verdict：**FAIL**。正文与重复观察获支持；scope却宣称普遍成功，超出有限实验或设置证据。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sim2real2018--wrong_table_condition

论文／来源：Sim-to-Real (arXiv v3)，PDF p.4，Section IV.C。

来源释义及预期解释：第4页描述95项仿真随机化；质量/阻尼每回合固定，步长/观测噪声逐步变化。第5–6页澄清步长分布参数λ回合内固定。

候选的错误字段（`observation`）：These measurements are from every physical robot with unseen tasks.

Agent verdict：**FAIL**。正文成立且scope有限定；observation与之冲突，把局部仿真证据说成全部实机的未见任务结果。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## sac2018-c01-revision

论文／来源：Soft Actor-Critic，publisher PDF p.3，§3.2 Eq.1 及紧随段落。

来源释义及预期解释：Eq.1在期望奖励中加入α加权的策略熵。紧随段落说明α决定熵相对奖励的权重及最优策略随机性，并在α→0时恢复常规期望奖励目标。

原 capture：奖励加熵目标及温度权重，遗漏 α→0 的极限。原 Gold 与原 partial 判定均保留。

新候选：The maximum entropy objective adds policy entropy to expected reward; temperature alpha controls their relative weight and therefore policy stochasticity. The conventional expected-reward objective is recovered as alpha approaches zero.

Agent verdict：**PASS**。三项所需内容均获锚定段落支持；未把有限α的最大熵目标等同于常规目标。optimal一词可提高措辞精度，不改变此处目标函数语境下的支持结论。 无实质性遗漏；将policy stochasticity精化为optimal-policy stochasticity更贴合原文。支持范围是该目标函数下的最优策略，不是任意当前策略的保证。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。

## 附加待核：diffusion-policy-ddim-source-discrepancy

本轮发现的来源差异，标记 **GOLDEN_REVIEW_REQUIRED**；冻结 Gold 未修改。

来源／原值：Diffusion Policy 主文 PDF p.4 §III.D 是 DDIM 100 训练去噪步／10 推理步、Nvidia 3080 上 0.1 s；附录 p.14 D 为实机 16 推理步，p.15 表 VI–VII 的 CNN 和 Transformer 实机行均为 100／16。

预期解释：原 Golden c2 保留主文 100／10／0.1 s 的数值和 locator。候选同样保留主文值，但未披露附录差异，不能作为全文无条件统一事实。

Agent verdict：**HUMAN_REVIEW_REQUIRED**。原文未把两组推理步数对应到不同设置；不能把 10 步的延迟移接到 16 步。请核对主文限定是否充分、是否另建 Gold revision；保留两处原值及证据。

User decision：**待填** — `ACCEPT_GOLD` / `REVISE_GOLD` / `REJECT_CASE`。
