长时程 Agent 记忆管理实践综述（2025 年 1–11 月）
1. 问题背景与挑战
长时程任务是指需要多个迭代步骤完成目标的任务，如跨网页搜索、代码修复、复杂规划等。这类任务中，Agent 需要在多轮 Thought-Action-Observation 循环中记住已做的事、外部世界状态和任务进度；仅使用 LLM 的上下文窗口会迅速填满并产生 context suffocation 或 “lost‑in‑the‑middle” 的问题[1]。因此，必须通过 记忆管理 技术，在有限上下文中保留关键信息并清除噪声。
2. 记忆类型与分层
2.1 内存层次
记忆层	功能及要求	典型实践
工作记忆 (Working Memory)	作为代理在当前轮决策的 scratchpad，存储计划、子目标、最新 observations 摘要、工具调用参数等。生命周期分钟到几小时，常驻上下文；应设置 TTL（如 30–120 分钟）并在步骤边界自动摘要[2]。在实现上，WorkingMemory 仅代表“当前 workflow/agent 的短期工作区”，不等同于“完整迭代记忆”；完整轨迹应由情景记忆负责。
使用结构化 step‑gist 保存最近 k 轮 (k≈3–5) 的 act + obs 摘要，并携带最新任务目标、约束和关键 ID 等 SoT（State‑of‑Truth）。
情景记忆 (Episodic Memory)	按时间记录任务执行事件（Observation、工具调用、决定等）的活动日志，类似“黑匣子”。可存数月至数年，用于审计、复盘、重放；应使用写入时单向追加日志并定期生成阶段性摘要[3]。
将完整的 {a_t, o_t} 序列以及原始工具结果存入外部存储（文件系统/数据库/向量库）；生成可索引摘要供检索。
语义记忆 (Semantic Memory)	持久化的知识库（事实、FAQ、SOP），供未来任务检索；需要可靠来源、拆分成小段并带标签[4]。
使用向量检索、知识图谱、时间知识图谱 (Zep/Graphiti) 等；存储来自外部文档及任务中生成的事实卡。
程序记忆 (Procedural Memory)	对“如何做”的技巧库，可以复用的脚本、工具组合、策略等[5]。
使用版本控制和流程模板，动态载入。
这一层次结构帮助将“需要在当前决策中使用的信息”与“长远保存供检索的信息”分离，减少上下文膨胀并保持可追溯性。[6] 建议针对长任务组合 小型工作记忆缓冲 与 持久的追加日志，方便恢复又不拖累上下文[7]。
3. 工作记忆管理策略
3.1 最近 k 轮与结构化摘要
多数实践使用 最近 k 轮 的 act + obs 摘要而不是全量历史，理由：
•	最近步骤往往包含当前决策所需的信息，过早步骤的重要信息已经融入 SoT 或被写入长期记忆；
•	摘要可以控制 token 数量并避免“工具输出暴雪”；
•	旧摘要通过向量检索可按需召回，无需常驻上下文。
k 可根据模型上下文长度动态调整（如 3–5），且常把最近 1–2 步摘要保存得更细致，其余更骨干。
3.2 压缩、删除与外存
对超过窗口的历史，可以选择：
1.	压缩/摘要：如 ACON 框架使用优化过的压缩提示将多轮 observations 和历史缩减为摘要，既减少 token 又保留必要信息；实验显示压缩后平均峰值 token 使用降低 26–54%，且决策质量不降反升[8][9]。
2.	Mask/删除：Complexity Trap 研究发现，在 SWE‑bench 任务中，仅用占位符替换旧的 observation 便可以达到与 LLM 摘要相当甚至更好的效果，而且成本更低[10][11]。观察 token 占上下文 84%，控制 observation 数量极为关键[12]。
3.	阶段性小结：ReSum 框架为 ReAct Agent 提供周期性调用摘要器，将累积的 Thought–Action–Observation 历史转化为简洁的 reasoning state，从而继续推理而不丢失重要发现[13][14]；其专门训练的 ReSumTool 提炼关键线索并指示下一步行动[15]。
3.3 动态或任务化记忆
•	子目标层级：HiAgent 将长任务分解为子目标，针对每个子目标维护独立的 working memory 块。当子目标完成，系统将其 actions‑observations 总结并更新父记忆，并可以在需要时检索详细轨迹[16][17]。这种分层记忆能提高成功率并减少上下文长度。
•	多粒度反思：Reflective Memory Management (RMM) 在每个回合后按话语、轮次和会话三个层次生成反思摘要，通过多粒度合并提升长期任务的记忆质量。
3.4 记忆作为操作（Memory‑as‑Action）
MemAct 将记忆管理视为一个可学习的动作（插入摘要、删除历史等），集成在代理策略中，替代手工启发式。由于编辑会使轨迹断裂，他们提出动态上下文策略优化以稳定训练；结果显示代理可自行学习何时保留、合并或丢弃历史[18][19]。这种方法使 agent 可以在长任务中主动管理记忆，而不依赖固定的 last‑K 或摘要逻辑。
3.5 IterResearch：马尔可夫式重建工作区
IterResearch 认为将所有交互积累在单一上下文会导致噪声累积和注意力稀释[1]。他们提出迭代深度研究范式：将长任务视为 马尔可夫决策过程，工作区仅包含 问题、逐渐演化的报告记忆和当前交互，周期性合成报告并遗忘不再需要的信息[20]。该方法使用几何奖励和适应性抽样优化，能够将 interaction 扩展到 2048 步而保持性能[21]。
4. 长期记忆与检索策略
4.1 语义和时间知识图谱
•	语义记忆要求将知识分割成小块、带标签并存储来源、日期，便于后续检索[4]。
•	时间知识图谱 (Temporal KG)：2025 年的 Zep/Graphiti 等项目将动态事实（如 API 配额、所有权变化）表示为带有效期的事实链，优于纯向量检索，支持查询当前和历史真相。此类系统在长任务中可做冲突消解和时间推理。
4.2 检索与重排
•	向量/关键词检索 + 时间衰减：根据当前子目标从情景记忆检索相关摘要或文档片段，并按相关性、时间距离和来源可信度排序。通过 score = α·semantic_sim + β·BM25 + γ·exp(-Δt/τ) 控制。
•	图式检索：AriGraph 将记忆建成语义‑情节混合的图，查询时按关系路径和社区取回，适合多跳连锁事实。GraphRAG/MemoRAG 等方法也结合图结构和递归摘要提高召回质量。
4.3 压缩与存储
•	KVzip：针对 LLM 的 KV 缓存提出压缩方法，保留重建未来所需的最小信息，将会话中间缓存压缩 3–4 倍、延迟提升 2 倍，还能处理 170k token 的对话[22][23]。这适用于服务端缓存层。
5. 新兴框架与实验（2025 年 1–11 月）
时间	主要工作/框架	关键贡献 & 工程启示
2025/02	Episodic Memory Position Paper	主张情节记忆需要快速绑定、情境敏感、选择性巩固、可检索、可组合；不应盲目扩充记忆而要可控、可审计。【参考】
2025/02	A‑MEM（Zettelkasten 风格记忆）	将记忆组织成可链接笔记网络，新记忆会自动更新旧记忆属性。
2025/03	ERMAR	动态排序与裁剪记忆项，在长任务中维持检索质量同时控制成本。
2025/04	Mem0/Mem1	提供可扩展的长期记忆层与 RL 学习记忆管理的初始尝试，显著降低 token 成本并提高性能。
2025/07	HiAgent (ACL 2025)	通过子目标记忆块与分层检索提高长任务成功率，工作记忆以 subgoal 层级组织[16][17]。

2025/08	Complexity Trap	实验证明简单 mask 会比 LLM summary 更高效且不掉性能，建议用占位符替代旧 obs[10][11]。

2025/09	ReSum & ReSum‑GRPO	在 ReAct Web agents 中定期通过专用摘要器压缩历史，取得 4.5%+ 的平均提升[13][14]。总结工具经过监督训练以提取线索并给出下一步指导[15]。

2025/09	Anthropic Context Editing + Memory Tool	服务端自动清理最老的 tool result，仅保留最近 N 组，并以占位文本替换；同时提供 memory 文件作为外部记忆，清理前提醒写入。评测显示仅清理提升 29%，加上记忆提升 39%。
2025/10	MemAct (Memory‑as‑Action)	将记忆管理作为 RL 动作，将插入摘要、删除历史和压缩纳入策略；为解决轨迹裂缝提出动态上下文优化[18][19]。

2025/10	IterResearch (Markovian Reconstruction)	将长任务视为 Markov 过程，通过周期性合成报告记忆和忘记冗余历史，支持扩展到 2048 步[20][21]。

2025/11	KVzip	压缩 KV 缓存，保持 essential context 并提升响应速度 2 倍，处理 170k token 对话[22][23]。

2025/11	AgentFold	提出主动上下文折叠（multi‑scale folding），在每一步对上下文执行细粒度或深层压缩，灵感来自人类记忆的反思巩固；实验超越多款开源及部分专有模型[24]。

6. Observation 摘要与数据抽象
不同工具的返回结果格式多样，为了让 LLM 能理解，需要建立统一的 Observation 适配层：
1.	存储原始结果：工具执行后，先把 raw result 写入情景记忆或外部存储，记录 trace_id 或 blob_url 以备后续检索。
2.	生成结构化 obs 对象：根据 tool_name + args + raw_result 调用专用适配器或通用 summarizer 输出统一 schema，包括：
3.	tool, status：成功或失败标识；
4.	args_digest：参数摘要；
5.	gist：人类可读摘要；
6.	state_delta：对 SoT 的更新，如新的约束、子任务变更；
7.	evidence_handles：引用（URL、trace id等）；
8.	meta：结果大小、延迟等元数据。
9.	放入工作记忆与情景记忆：
10.	工作记忆只保留 gist + state_delta + 关键 evidence 等精简信息；
11.	情景记忆保存完整 Observation 和 raw result 供检索与复盘。
通过这种方案，即使原始工具结果不进入工作记忆，agent 仍能根据 state_delta 和 gist 理解发生了什么，并通过 trace_id 在需要时回溯原始数据。不同工具可通过 TOOL_OBS_ADAPTER 实现定制摘要；对未覆盖工具使用通用 summarizer。
7. 工作记忆与情景记忆关系
•	工作记忆：当前 prompt 中的内容，仅包含 SoT 和少量步骤摘要，用于当前决策；其大小与模型上下文强相关。
•	情景记忆 / 轨迹：完整的 {a_0, o_0, ..., a_{t-1}, o_{t-1}} 序列，包括 raw result、错误信息、耗时等，通常存储在外部存储或数据库；不直接进入 prompt。情景记忆是工作记忆的来源，通过检索或摘要方式提供必要信息。
8. 实践建议总结
1.	状态优先：构建清晰的 State‑of‑Truth（任务目标、约束、关键资源 ID、最新事实），每轮根据 obs 的 state_delta 立即更新 SoT，并在工作记忆中携带最新状态。
2.	分层记忆管理：
3.	工作记忆只保留最近 k 步的 step‑gist（高密+骨干）与 SoT；
4.	情景记忆保存完整轨迹并支持检索；
5.	语义记忆/时间知识图谱保存长久的事实和文档。
6.	动态压缩与清理：根据任务阶段和模型上下文容量选择压缩或 mask 历史；可通过 context editing + memory tool 或 ACON、ReSum 等框架实现自动压缩与外存写入。
7.	工具抽象与 obs 适配：实现统一 Observation schema，将多样化工具结果转换成结构化摘要；使用适配器和通用 summarizer，根据工具特性处理。
8.	检索与重排：结合向量检索、关键词检索、时间衰减与图式检索，按需召回旧信息。对于链式推理，可先召回阶段性摘要，再下钻原始轨迹。
9.	策略性记忆：在强化学习场景中，可以使用 Memory‑as‑Action 或 IterResearch 的框架，让 agent 学会自主管理记忆，选择何时摘要、保留或丢弃历史。
10.	技术演进与未来工作：2025 年大量研究表明单纯扩大上下文不足以解决 long‑horizon 问题；需要更主动、可解释、可审计的记忆管理策略。未来可关注 RL‑驱动的记忆操作、基于认知科学的多层折叠记忆（如 AgentFold）、以及综合图谱和知识演化的长期存储。
________________________________________
声明：本文参考了 2024–2025 年多个公开论文和实践经验，包括 Practical Memory Patterns for Reliable, Longer‑Horizon Agent Workflows[2][3]、HiAgent[16][17]、ACON[8][9]、Complexity Trap[10][11]、ReSum[13][14]、Memory‑as‑Action[18][19]、IterResearch[20][21] 等，以及 2025 年最新的技术新闻如 KVzip[22][23] 和 AgentFold[24]。上述总结旨在提供对长时程代理记忆管理技术的整体理解，供科研和工程实践参考。
________________________________________
[1] [20] [21] IterResearch: Rethinking Long-Horizon Agents via Markovian State Reconstruction
https://arxiv.org/html/2511.07327v1
[2] [3] [4] [5] [6] [7] Practical Memory Patterns for Reliable, Longer-Horizon Agent Workflows - Applied Information Sciences
https://www.ais.com/practical-memory-patterns-for-reliable-longer-horizon-agent-workflows/
[8] [9] ACON: Optimizing Context Compression for Long-horizon LLM Agents
https://arxiv.org/pdf/2510.00615.pdf
[10] [11] [12] The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management
https://arxiv.org/pdf/2508.21433.pdf
[13] [14] [15] ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization
https://arxiv.org/pdf/2509.13313.pdf
[16] [17] 2025.acl-long.1575.pdf
https://aclanthology.org/2025.acl-long.1575.pdf
[18] [19] Memory as Action: Autonomous Context Curation for Long-Horizon Agentic Tasks
https://arxiv.org/pdf/2510.12635.pdf
[22] [23] SNU researchers develop AI technology that compresses LLM chatbot ‘conversation memory’ by 3–4 times | EurekAlert!
https://www.eurekalert.org/news-releases/1105074
[24] [2510.24699] AgentFold: Long-Horizon Web Agents with Proactive Context Management
https://arxiv.org/abs/2510.24699
