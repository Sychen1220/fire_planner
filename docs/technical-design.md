# 半 FIRE Planner 技术设计文档

> 版本：V1.3｜对应 PRD：V0.6｜状态：技术设计，新增能力按阶段实现｜更新日期：2026-10-06
> 依据：[PRD](product-requirements.md)、[确认原型](prototypes/fire-planner-v0.6.html)。本次仅修订技术文档，不修改正式页面、算法、用户数据库或 Checklist。

### V1.3 变更说明

- 保留单体分层、原 Planner 兼容及确定性财务算法，明确架构完整性与首版实现范围的区别。
- 按 M1–M5 分期落实存储、实际、共享预测和 AI，降低通用幂等、并发与自动恢复的首版承诺。
- 增加 ContextService 唯一上下文构造入口，明确 Draft → Confirmed Plan 的显式确认边界。
- 强化 Decision Rule、AI 只读与 metric_ref 校验，新增 G01–G05 产品级 Golden Scenarios。
- 明确后续 `implementation-spec.md` 的职责与输入输出，不将本文直接当作逐任务执行指令。

## 1. 项目目标与实现基线

### 1.1 目标

在现有单用户 Planner 上增加月度实际和对话式消费判断。三个模块共享同一个计划、有效实际版本和最新预测：

1. 保留原有规划体验，完整保存用户选定的参考方案。
2. 实际收支改变最新预测，原目标保留用于比较。
3. 消费判断比较同一最新基线下的“买／不买”，由 AI 解释生活价值和计划代价。
4. 防止累计金额重复加总、已包含购买重复扣减、过期预测冒充最新结果。

不新建前后端分离项目、不重写原 Planner、不建设逐笔账本或独立复盘中心。原型的节点差额简算不能作为正式预测算法。

### 1.2 代码现状核对

| 文件 | 已存在能力 | 本次扩展边界 |
|---|---|---|
| `app.py` | 侧栏四页路由 | 添加三模块外壳；原路由和页面继续使用 |
| `ui/pages/home.py, living.py, assets.py` | 首页、生活预算、资产表单 | 保留布局、字段和原交互 |
| `ui/pages/calculation.py` | 多方案、逐月曲线、退出节点、公式；方案组装在 UI 内 | 提取纯组装适配，保证原计算输入输出一致 |
| `domain/forecast.py` | 整月现金流、事件、复利；负余额继续保留 | 复用月计算规则，新增实际替换与截点适配 |
| `domain/scenario.py` | 年度缺口、提款参考和候选节点状态 | 不将颜色等同购买许可或自动退出标准 |
| `domain/stress_test.py` | 压力测试函数和测试 | 尚未接页面；不以本次为由另建压力页面 |
| `infrastructure/storage.py` | SQLite `form_state` 保存预算、资产和负债表单值 | 保留兼容；不能当作完整方案或实际记录 |
| `application/plan_service.py, dto.py`、`infrastructure/db.py, repositories.py` | 仅模块说明的占位文件 | 实现服务、DTO、迁移和 Repository |
| `tests/` | 金额、模型、预算、预测、方案、压力、存储和校验 | 保留回归，再按本稿增加关键行为测试 |

当前默认数据库为项目根目录 `fire_planner.sqlite3`，由 `FIRE_PLANNER_DB_PATH` 覆盖。测算参数和方案尚未完整持久化。当前日期选择被旧引擎转换为月份并计算整月，不能据此宣称已经支持日终资产截点。

### 1.3 架构完整性与渐进实现

**Architecture completeness** 描述系统最终允许支持的模型、协议和一致性约束；目录、字段及状态全集不代表必须一次建齐。

**V1 implementation scope** 是首版按 M1–M5 逐步交付的必要能力，具体边界见第 12 节。Architecture 可以完整设计，但 V1 Implementation 必须渐进实现。不得因为未来可扩展性，在 M1 提前实现所有 revision、幂等、AI、stale、重试等复杂机制。

原 Planner 兼容性与财务正确性仍是最高优先级之一。简化实现不能改变计算口径、让草稿取代正式计划、允许 AI 写财务事实，或让 Actual／Forecast／Purchase 各自定义「最新」。同样，不为尚未进入的阶段预建空服务、整套状态机或供应商框架。

## 2. 技术栈

| 部分 | 采用方案 | 约束 |
|---|---|---|
| 语言 | Python 3.11+ | 延用当前项目 |
| 页面 | Streamlit `>=1.39,<2` | 三模块外壳、原页面、聊天组件；不引入 React |
| 图表 | Plotly `>=5.24,<7` | 原图表继续使用；月度列表不强行增加图表 |
| 数据库 | Python 标准库 sqlite3 | 本地单用户、短事务、外键与版本约束 |
| 领域数据 | dataclass、Enum、Decimal、datetime | 金额整数分，禁止浮点金额参与计算 |
| 数据序列化 | JSON + 显式校验 + schema_version | JSON 存整数分；M1 仅当前格式及旧库迁移，不建设通用多版本转换框架 |
| AI 接入 | `AiGateway` 协议 + 一个供应商适配器 | 首版不引入 Agent 框架或向量数据库 |
| 自动测试 | pytest `>=8.3,<9`、Streamlit AppTest | 数据库使用临时路径，模型使用桩 |
| 配置 | 环境变量／Streamlit secrets | 密钥不进入业务库、提示词日志或 Git |

现有依赖不因文档更新改变。AI 的供应商和模型尚未确认；M4 实现内部结构化契约、测试桩与一个供应商适配器，选定后只在适配层增加必要 SDK。完整供应商切换能力为 future-ready，不阻塞 M1–M3。没有真实供应商接入不能验收 P0-4。

拟定配置：`FIRE_AI_PROVIDER`、`FIRE_AI_MODEL`、`FIRE_AI_API_KEY`、`FIRE_AI_TIMEOUT_SECONDS`（默认 45）。供应商需要自定义端点时另配 `FIRE_AI_BASE_URL`，不从对话文本读取 URL。模型标识必须配置，不写死案例模型。当前版本尚未读取这些新配置。

## 3. 目录结构

以下标“新增／实现”的位置是架构规划，不代表已有文件或接口可调用；各文件按第 12 节阶段创建，不在 M1 全部搭建。

```text
fire_planner/
├── app.py                              # 三模块路由，保留原页面调用
├── docs/
│   ├── product-requirements.md          # PRD V0.6
│   ├── technical-design.md              # 本文
│   ├── implementation-spec.md           # 后续生成：按批次落实的执行规格
│   ├── prototypes/fire-planner-v0.6.html
│   └── archive/                        # 历史 PRD
├── src/fire_planner/
│   ├── domain/
│   │   ├── models.py, money.py, validation.py
│   │   ├── budget.py, forecast.py, scenario.py, stress_test.py
│   │   ├── planning.py                 # 新增：计划快照、月度排期、退出规则
│   │   ├── actuals.py                  # 新增：累计记录、可比性、资产截点
│   │   ├── projection.py               # 新增：原计划与实际合成、逐月重跑
│   │   └── purchase.py                 # 新增：增量支出、替换校验、双路径比较
│   ├── application/
│   │   ├── dto.py                      # 实现：命令、结果、统一错误
│   │   ├── plan_service.py             # 实现：计划保存、选定与恢复
│   │   ├── actual_service.py           # 新增：历史列表、累计修正
│   │   ├── context_service.py          # M3 新增：唯一上下文构造入口
│   │   ├── forecast_service.py         # 新增：同版本预测、失效与发布
│   │   ├── chat_service.py             # 新增：对话、模型、程序测算编排
│   │   └── ports.py                    # 新增：Repository、AiGateway、Clock
│   ├── infrastructure/
│   │   ├── storage.py                  # 原表单兼容接口
│   │   ├── db.py, repositories.py      # 实现：事务、查询、序列化
│   │   ├── migrations.py               # 新增：版本化迁移
│   │   └── ai_gateway.py               # 新增：配置、模型适配和错误映射
│   └── ui/
│       ├── pages/home.py, living.py, assets.py, calculation.py
│       ├── pages/actuals.py            # 新增：月度汇总、编辑
│       ├── pages/purchase_chat.py      # 新增：输入框和对话
│       ├── components.py               # 新增：参照栏、预测摘要、表单、消息
│       ├── planner_adapter.py          # 新增：旧 session 字段与计划 DTO 转换
│       ├── charts.py
│       └── formatters.py
├── tests/                              # 保留现有测试
│   ├── fixtures/                       # 新增：显式演示计划、实际、模型桩
│   ├── test_actuals.py, test_projection.py, test_purchase.py
│   ├── test_services.py, test_migrations.py, test_chat_service.py
│   └── test_ui_flows.py
└── pyproject.toml
```

依赖方向为 UI → Application → Domain；Infrastructure 实现 Application 的协议。Domain 不导入 Streamlit、SQLite 或模型 SDK。原页面的纯计算提取先用回归固定行为，不开展全仓重构。

## 4. 数据模型

### 4.1 共用约定

- 金额字段均以 `_cents` 结尾，整数，绝对值不超过现有 `10^12` 分；拒绝 bool、NaN、浮点隐式截断。
- 收入、资产和购买金额非负。净支出可为负（退款大于当月支出），需附说明；差额和预测余额允许负值。
- 比例为整数基点，350 表示 3.5%；预期收益率沿用 0～100%，提款率为 (0,100%]。负回报通过明确压力情景表示，不暗改旧校验。
- 月份 `YearMonth`／ISO `YYYY-MM`；截至日 ISO 日期，记录时间 UTC。业务“今天”通过可注入 Clock 与本地时区取得，禁止把原型的 2026-10-05 写死。
- 年份 1900～2200，预测起止相距最多 120 个月，包含起止两月，沿用旧行为。
- 未知是 null + 原因，已确认零是 0；用户输入、模型推测、计划估计分别保留来源。
- UUID 是持久化身份；UI 下标和“A/B/E”只是显示标签。

### 4.2 核心对象

| 对象 | 主要字段与含义 |
|---|---|
| `PlanRevision` | id、parent_id、effective_from_month、created_at、schema_version、完整 `PlanSnapshot`、当时 baseline_result、input_hash |
| `PlanSnapshot` | 初始资产与口径、起点语义、各年预算、稳定方案列表、收入路径、事件、收益率、提款率、预测期限、可选退出规则和明确资金底线 |
| `ScenarioSnapshot` | scenario_id、label、exit_month、退出前收入、退出后收入、独立事件；保存页面共用假设的值，不依赖会话再读取 |
| `PlannedMonth` | 月份、经常收入／支出、一次性事件、预算来源、可比性、原 plan_revision_id；原月均预算标为 smoothed，非真实排期 |
| `MonthlyActualRevision` | id、month、revision、supersedes_id、as_of_date、income_cents?、expense_cents?、asset_observation?、note、comparison_baseline、coverage_confirmations |
| `AssetObservation` | 同日日终金融资产、scope_id、现金流已覆盖到该日；嵌入实际修订，不与累计收支再相加 |
| `ForecastSnapshot` | id、ContextVersion、输入快照、逐月点、目标节点结果、可选候选退出月、质量、假设、遗漏和 engine_version |
| `Conversation` | id、标题、参考方案、created_at、updated_at、明确事实及来源 message_id；复杂 revision 演进为 future-ready |
| `Message` | id、conversation_id、sequence、role、正文、request_id、status、analysis_id?、created_at |
| `AnalysisSnapshot` | id、request_id、上下文和事实快照、购买假设、财务结果、AI 解释、状态、模型／提示词／算法版本 |
| `ContextVersion` | plan_revision_id、scenario_id、actual_revision、engine_version；仅由 ContextService 构造，作为预测一致性标识 |
| `PurchaseChange` | 金额、预计月份、是否已发生、资金来源、替换条目与确认来源、持续费用；缺失项不能默认填零 |

`MonthlyActualRevision` 保存整个有效记录，不是增量 patch。编辑表单预填；清空即 null。资产观测的日期与本条 as_of_date 一致；修改日期时必须重新确认该资产值的时点，不能静默搬到另一日。只有资产值、没有收入支出也允许保存；列表两侧显示未知。

`comparison_baseline` 固化首次记录时选用的历史计划修订、计划金额和 basis。补录月份无适用旧计划时设为不可比，不能把今天的新目标倒填历史。纠正事实默认沿用其历史基准。切换当前方案只改变预测参照，不改写历史对比。

`coverage_confirmations` 仅保存明确关联：来源消息／计划事件 ID、包含于本次总额或观测的确认及日期。总额修改后，这些确认重新校验；未知不能当已覆盖。它不是自动流水账。

### 4.3 持久化表与落地阶段

保留现有 `form_state`。下表是跨阶段架构清单，不是 M1 建表清单。M1 仅新增 `schema_migrations`、`app_state`、`plan_revisions`；M2 增加实际与最小保存去重，M3 增加预测，M4 增加对话与分析。JSON 内容由对应 schema 校验，不以 JSON 绕过关系约束。

| 表 | 主键、关系与关键字段 | 约束 |
|---|---|---|
| `schema_migrations` | version PK、applied_at | 版本递增，未知新版拒绝降级 |
| `app_state` | id=1、current_plan_revision_id FK、current_scenario_id；M2 增加 actual_revision | 当前方案必须存在于快照内；通用 state_revision 并发机制按需后置 |
| `plan_revisions` | id PK、parent_id FK、effective_from_month、snapshot_json、baseline_json、input_hash | 已确认修订不可变 |
| `actual_month_revisions` | id PK、month、revision、supersedes_id FK、payload_json、created_at | UNIQUE(month,revision)；最新修订为有效值 |
| `forecast_runs` | id PK、context_key UNIQUE、input_json、result_json、status、error_code、created_at | 结果只对应指定上下文；失败不伪造有效结果 |
| `conversations` | id PK、reference_scenario_id、facts_json、timestamps；revision 为后续扩展 | 事实附消息来源；无独立决定表 |
| `messages` | id PK、conversation_id FK、sequence、role、content、request_id、analysis_id? FK、status | UNIQUE(conversation_id,sequence)，同请求同角色只发布一次 |
| `analysis_runs` | id PK、conversation_id FK、request_id UNIQUE、context_key、input_json、result_json、status、metadata_json | 历史输入结果不随新实际覆盖 |
| `command_receipts` | operation_id PK、command_type、payload_hash、result_json | M2 可用此最小表实现实际保存去重，与原事务提交；通用命令框架和复杂收据生命周期后置 |

外键连接均启用；历史计划、分析和消息不做级联删除。初版不提供清空用户数据按钮。单用户实际账目全局共享，不能给 A/B/E 各造一套实际。

### 4.4 保存、修订与迁移

- M1 仅显式确认时事务性保存完整计划并更新当前指针；提交失败保留旧计划。确认时检查读取的当前计划指针是否已变化，拒绝覆盖更新，不要求通用 command_receipts 或完整命令版本框架。
- M2 实际保存带 operation_id、expected_revision；同 ID 同内容重试返回原结果，同 ID 不同内容报错。这个必要的去重与版本冲突能力不提前到 M1，也不扩展为全系统命令总线。
- 数据库写入使用短事务（需要读后更新时使用 `BEGIN IMMEDIATE`）；SQLite busy timeout 设为 5 秒。M2 在事务内执行实际版本比较、追加修订及更新指针；锁等待失败给出可读错误。
- M2 实际保存事务写入新修订并递增 actual_revision。M3 接入提交后的预测计算，失败不回滚真实账目。
- M3 预测发布前通过 ContextService 再次核对 ContextVersion，变化则结果标 stale，不替换当前预测；M1 不实现此状态。
- 首次迁移使用 SQLite backup API 创建带时间戳备份，短事务建表，重复运行无重复导入；开发测试绝不使用用户数据库。
- 保留 `form_state`，读旧值形成工作草稿。测算参数未保存的部分须重新确认，不伪造旧方案、资产日期或实际账目。
- `form_state` 是旧页面工作草稿的兼容存储，`plan_revisions` 是已确认计划，不能形成两个“当前正式计划”写入源。旧表单保存不自动切换参照；参照栏明确提示草稿与已确认计划有差异。
- 首次完整保存时快照包含全部方案和显示顺序，重新进入旧页面通过 adapter 恢复参数。不同会话不在正在编辑的表单上强制覆盖，只提示读取新版本。

数据库迁移版本与业务修订是两件事。M1 必须支持旧库升级、备份、事务回滚、重复运行及拒绝未知新版；通用 schema 转换链、所有未来对象的版本兼容和自动修复属于 future-ready，不作为 M1–M3 的前置条件。

### 4.5 Draft 与 Confirmed Plan

```text
Draft（session 草稿／兼容 form_state）
  → 用户显式「确认／保存计划」且应用校验通过
  → Confirmed Plan（不可变 PlanRevision + 当前指针原子更新）
```

编辑字段、旧页面保存表单、切换页面、Streamlit rerun、恢复 session 都不能隐式创建 PlanRevision。旧表单保存只保存工作草稿；首次确认和之后的计划调整均由独立的显式确认动作触发。重复渲染不重复提交。

`app_state` 只能有一个 `current_plan_revision_id`（尚未确认时为 null），所选 `current_scenario_id` 必须属于该修订。草稿允许继续试算，但须标为未确认，不能进入最新正式预测或消费分析。所有正式财务服务读取当前指针对应的已确认计划；`form_state` 与 `plan_revisions` 不是两个业务真相源。取消草稿或恢复 session 只影响编辑状态，不切换正式计划。

### 4.6 ContextVersion 的唯一构造入口（M3）

`ContextService.build_current_context()` 是唯一构造入口。它在同一次一致读取中取得当前计划指针、方案、有效实际版本及对应数据，返回不可变 `CurrentContext`：

- `version`：plan_revision_id、scenario_id、actual_revision、engine_version。
- `inputs`：对应已确认 PlanSnapshot、选定方案、该 actual_revision 的有效实际集合及必要计算配置。
- 明确的缺失信息；没有正式计划时返回 MISSING_CONTEXT／needs_input，不从草稿补造。

其他影响计算结果的版本字段只能在此入口统一增加。例如日历截点或计算配置若影响结果，必须进入输入快照及规范化 key，不能作为隐含 session 值；提示词或供应商版本只影响解释时，保存在 AnalysisSnapshot，不污染财务 key。

ContextService 统一规范化并生成 context key。ForecastService、Purchase compare（以后若拆 PurchaseService 也相同）、ChatService 不得分别拼接 key、读取各自的「最新版本」或手动构造 ContextVersion。ActualService 提交事实并递增版本，随后由 ContextService 提供新上下文；Actual 页面、Forecast 和 Purchase 都使用这一入口。

ForecastService 接收完整 CurrentContext 并调用确定性领域算法；Purchase 双路径共享同一个 context 和基线输入；ChatService 捕获该 context 后传递到比较流程。发布时再次调用唯一入口，核对版本是否仍相同。为核对版本而重新读取不能替换一次计算中途的部分输入。历史快照可读取原版本作溯源，但不得标为「当前」；首版不要求任意历史上下文重放服务。

## 5. 核心算法

### 5.1 原 Planner 计算保持兼容

```text
当月投资收益 = round_half_up(max(月初资产, 0) × 年收益率 / 12)
月末资产 = 月初资产 + 经常收入 - 经常支出
         + 一次性收入 - 一次性支出 + 当月投资收益
```

现有 `forecast_assets` 接收初始资产、起止月份、月结余、一次性事件、可选逐月结余和年收益率。初始资产要求非负；后续余额可负，负余额不产生收益。保留 ROUND_HALF_UP 到分；反推最低资产／收入时向上取整。

旧页面年度预算除以 12 的月均假设、未单填年份沿用所选预算年、退出当月仍用退出前收入、次月才用退出后收入，全部保留。原结果不因增加实际模块被静默替换；最新预测另行展示。

原测算日期被当作所在月份的整月起点。这是 legacy_month 模式。保存参照时标明该假设；要发布实际驱动预测，需确认起点代表月初计算前资产，或提供真实日期的日终观测。不能把月中真实余额悄悄当月初余额。

### 5.2 月度预实

```text
实际结余 = 实际收入 - 实际净支出
收入偏差 = 同期实际收入 - 同期计划收入
支出偏差 = 同期实际净支出 - 同期计划支出
结余偏差 = 实际结余 - 同期计划结余
```

计算条件：期间、资产／收支范围、排期口径一致且必要值已知。basis 为 `scheduled` 或用户确认的 `confirmed_monthly` 才能做精确月度差异。只有年度月均 `smoothed` 时，默认汇总列显示“—”，说明仅有月均预测假设；不能以此判定超支。

未到月末的记录标 partial；不与整月排期硬比较。年度未排期预算仍参与未来月均预测，不凭月度未支出推断年度额度可取消。历史表读取自己的 comparison_baseline，不被当前方案切换改写。

### 5.3 用实际构造最新路径

1. 从 ContextService.build_current_context() 取得同一个已确认 PlanRevision、所选 scenario 和有效实际集合；使用返回的不可变输入快照，不另行拼装上下文。
2. 确定资产锚点：同口径且已确认覆盖边界的最新日终观测优先；否则使用已确认的计划月初起点。缺少起点语义则返回 needs_input。
3. 锚点之前的记录只用于历史预实，不重新加到余额。日终观测有实际数值但范围／日期未确认时禁止作为新锚点。
4. 锚点之后逐月构造收入、支出及事件，按下述替换规则处理实际。
5. 未知部分采用明确计划估计并标 conditional；不能将估计写回实际。
6. 按现有月递推重跑后续路径，计算原目标月份资产、年度缺口和条件满足时的退出月份。
7. 输出 coverage 列表、遗漏期间、锚点、假设和版本；原目标仍保留。

完整月份的替换规则：

| 实际字段 | 当月预测合成 |
|---|---|
| 实际收入已知 | 该值已含当月工资、奖金等同口径一次性收入；替换经常收入，并清除已由该总额覆盖的计划收入事件 |
| 实际支出已知 | 替换当月同口径经常与一次性净支出；不另加已经计入总额的购买 |
| 单侧未知 | 仅该侧沿用计划，记录估计原因；已知侧仍生效 |
| 月份缺失 | 沿用计划，标记未核实，不生成零实际 |
| 实际提前覆盖未来计划事件 | 只有明确事件关联才能从未来移除；无法确认时列为待核对，不能暗扣两次或暗取消 |

实际收入不含投资收益／内部转账，故无观测时历史收益仍按模型假设估计；此路径是条件预测，不冒称真实资产。单月偏差不会自动改变未来收入或预算。

**必须重跑路径**：在 12% 年收益、期初 100,000 元、每月计划结余 1,000 元下，两个月计划资产为 102,000 → 104,020 元。首月实际结余为 0 后应为 101,000 → 103,010 元，第二月差额为 -1,010 元，不能只在原终点扣 1,000 元。

### 5.4 月中截点与资产观测

完整月末日终余额从次月进入整月引擎，不能把刚结束月份再计算一次。

月中日终观测：未来当月只加入该日之后的已排期现金流／用户确认的剩余金额。同月累计本身不能推出剩余收入或支出；资料不足返回 needs_input，或保留明确旧计划估计并标 conditional。工资不得未经确认按天平均分摊。

月中剩余收益采用明确近似：

```text
剩余收益 = round_half_up(max(日终观测资产, 0)
                       × 年收益率 / 12
                       × 剩余天数 / 当月天数)
```

剩余天数不包含观测当日。近似不计算后续日内资金变化的收益，向用户披露。月中实际无资产观测时，也必须有可解释的剩余安排才能构造完整月；不能将已发生累计当作全月最终额。

余额为负时保留缺口，收益为零。新增可接受有符号中间余额的内部递推函数；不放宽旧 `forecast_assets` 的公开初始资产校验。

金融资产口径沿用现金、存款、基金、股票、其他金融资产，不含房产，不再扣已单列的房贷余额。观测和模型余额的差异记为未解释资产变化，除非有事实支持，不归类为消费超支。

### 5.5 退出节点与退出月份

```text
年度主动收入 = 退出后月收入 × 12 + 其他年度主动收入
年度投资收益 = 退出资产 × 预期收益率
年度可支配 = 年度主动收入 + 年度投资收益
年度缺口 = 年度生活预算 - 年度可支配
提款参考 = 退出资产 × 规划提款率
```

提款率不是第二份收益。现有默认预期收益为 0%，提款率为 3.5%；原型收益 3.5% 只用于案例。现有 green/yellow/orange/red 状态保持，但 yellow 不能自动算“达到退出条件”。

退出月份属于可选结果，算法必须有明确的 ExitRule：

- `asset_target`：用户明确确认的资产门槛，显示为“达到资产门槛月份”，不能直接改名为安全退出月。
- `income_coverage`：用户明确选择年度缺口不大于零，并确认采用的收入／预算／收益假设；同时检查已确认现金底线。它是确定性条件，不是终身安全保证。
- 未确认规则或关键底线未知：仍比较固定目标月资产，退出月份返回 null + rule_missing／needs_input。
- 不支持未经设计的计划性耗尽本金规则；需要时先补充产品规则，不假设用户必须保本。

扫描候选月份时，每个候选都重建退出前后收入路径，候选月仍用工作收入，之后转半 FIRE 收入；不能从原退出月后的低收入曲线直接寻找“多工作几个月”的结果。同一规则下比较无购买与购买两条路径。区间内无解返回 not_reached，不扩展成精确延期天数。年预算为零／资产为负时使用明确状态，不调用拒绝该输入的旧 evaluate_scenario。

#### Decision Rule：产品判断依据

「半 FIRE 可行」不是模型自动推断的单一真值，必须由用户选择／确认的规则、范围和假设定义。首版支持上述 `asset_target` 与 `income_coverage`，由应用校验后交给 Domain 执行。AI 可以解释规则或建议用户考虑哪一种，但不能替用户确认未定义的 ExitRule，也不能从示例资产或状态颜色反推规则。

系统可以报告「在这些假设下达到资产门槛」或「年度收入覆盖预算」，不得扩展为「安全退休」「终身不会没钱」。指定目标月份是用户计划，不随测算自动移动；条件扫描得到的是另一个有规则依据的候选月份，两者分别展示。

购买判断优先输出消费金额、资产路径影响、目标月份的资产差异、规则成立时的候选月份差异、退出节点指标差异及需要满足的条件。缺少规则或区间内无解时给出原因，不编造月份差。不输出「购买评分 72/100」等未定义指标；只有 PRD 明确定义并由程序实现的计算规则才可产生评分。生活价值与计划代价供用户权衡，不由某个财务阈值自动否决消费。

### 5.6 消费模拟

```text
某月增量支出 = 新消费支出 - 同月被替换的未发生安排
购买路径 = 在同一 ForecastInput 上应用 PurchaseChange 后重新计算
本次影响 = 购买路径 - 未新增购买的最新路径
```

金额与月份缺失时先补问，或明确标为节点条件估计，不能默认今天购买。资金来源只影响资金可用性／替换关系，不把“减少储蓄”再作为第二笔支出。连续费用记录起止月份；一次性支出只计一次。

替换条目必须在基线中存在、有稳定 ID、未发生、额度足够并有确认来源；总额不可重复抵扣。只知道年度预算不能推断未用购物额度。暂缓保留原预算，不自动加储蓄。

已发生购买单独走覆盖核对：已在实际总额或资产观测中则不再增加模拟支出；覆盖未知时补问；用户明确未包含时引导修改当月总额，不由模型替用户自动入账。只标“决定买”仍是意图，不是现金流事实。

输出分别保留原目标差异、实际执行造成的差异、本次增量，包含支付现金／预留是否已确认。总金融资产足够不代表现金可支付。

## 6. 页面结构

```text
FIRE 计划
  ├─ 原首页／我的生活／我的资产／开始测算（保留）
  └─ 外层参照栏：保存完整计划、选定方案、最新预测与原目标对照
实际收支
  ├─ 月度历史表 + 记录／补录
  ├─ 点击月份直接编辑 → 保存回列表
  └─ 简短 FIRE 影响摘要 + 可展开依据
消费判断
  ├─ 当前方案的最新预测摘要
  ├─ 聊天记录 + 输入框 + 发送
  └─ 轻量新对话／历史入口，详细计算按需展开
```

全局三模块导航可用 Streamlit 原生单选／分段入口；模块内保留旧 `selected_page` 路由及首页跳转回调。不将所有页面同时塞进 tabs 重复执行计算或模型调用。

严禁重新加入被否定的单月详情面板、消费表单墙、固定方案卡片和强制选择／复盘流程。旧四页的主体布局不改变；新增状态放外层组件。

## 7. 组件边界

| 组件／服务 | 负责 | 不负责 |
|---|---|---|
| `render_module_navigation` | 模块选择、恢复上次页面 | 查询／写账、调用 AI |
| `render_reference_bar` | 展示与确认参照、提示未保存草稿 | 改写原表单的含义 |
| `render_forecast_summary` | 用同一 ForecastSnapshot 显示原目标与最新预测 | 本地重算或从 session 拼财务数字 |
| `render_monthly_history` | 月份、收支、结余、可比差额 | 投资收益归因、生成分类余额 |
| `render_actual_form` | 预填、校验提示、显式保存 | 重复累计旧值或自动加购买金额 |
| `render_chat_messages / composer` | 消息、状态、输入与重试 | 直接写计划、执行模型建议 |
| `planner_adapter` | 旧控件键与完整快照转换，稳定 ID 映射 | 当新的计算引擎 |
| `ContextService` | 唯一构造 CurrentContext／ContextVersion 及 context key，一致读取正式数据 | 财务计算、模型解释、写业务事实 |
| `ForecastService` | 使用统一 context，失效、领域重算与发布、Purchase 双路径比较 | 自拼 context key、决定生活价值 |
| `ChatService` | 对话上下文、AI 调用、领域计算、结果验证 | 赋予模型财务写权限 |
| Repository | 事务、修订、参数化 SQL、序列化 | 生成业务建议 |

## 8. 状态管理与一致性

SQLite 保存已确认业务事实。session_state 只持有 UI 位置、未提交草稿、当前请求标识，不是正式数据来源。

下表按阶段启用：M1 仅计划草稿和正式计划，M2 增加实际，M3 增加预测版本／质量与简单 stale 标记，M4 增加聊天请求和回复状态。stale 表示依据已变化，不要求通用状态机。复杂 conversation revision 与 interrupted 恢复为 future-ready。

| 状态 | 保存位置 | 生命周期 |
|---|---|---|
| 当前模块、原页面、正在编辑月份 | session_state | 切换保留，不改变财务依据 |
| 月度表单草稿／输入框草稿 | session_state | 当前会话保留；未发送内容不宣称重启可恢复 |
| 完整计划、有效月度记录、已发送消息 | SQLite | 重启可恢复 |
| 正在发送 request_id、操作 ID | session + SQLite 状态 | 重跑沿用，不能再发一个新请求 |
| 预测结果 | forecast_runs | 按 ContextVersion 缓存；依赖改变即失效 |
| 历史 AI 回复 | messages + analysis_runs | 原文和依据不变，UI 动态标识 stale |

预测 quality 为 `plan_only / conditional / updated / needs_input / failed`，另有是否 stale；updated 只表示采用当前确认输入，未来部分仍是假设，不代表收益保证。遗漏月份、未知侧、资产锚点日期必须随结果返回。

流程：

1. 实际保存成功即递增 actual_revision；返回保存结果及刷新状态。
2. ContextService.build_current_context() 返回一致快照与唯一 key，ForecastService 据此取缓存或重算。
3. 成功发布时版本仍匹配，两个模块都从同一查询接口读取；不分别持有“最新余额”。
4. 发布时通过 ContextService 检查 key；若更新导致变化，旧结果不变成当前，显示待刷新。重新计算必须重新获取完整 context，不在本次计算中混入新输入。
5. 聊天请求捕获输入版本，网络请求在数据库事务外。返回时不同版本则标 stale，提示继续按新依据分析，不静默重写历史。

只缓存纯函数或按完整 key 缓存结果；不能用无参数 `st.cache_data` 保存用户财务状态，也不跨会话共享可变 SQLite connection。模型请求只由显式发送／重试触发，不由页面 render 或 Streamlit 重跑触发。

## 9. API 与 AI 契约

### 9.1 内部应用 API

首版是单体 Streamlit，不新增 HTTP 服务。以下是拟实现 Python 应用接口，不是已经可调用的 REST 路由。

接口按阶段实现，不统一强制每种命令携带所有版本字段。M1 计划确认包含用户读取的当前计划指针，供提交时检查；M2 实际保存带 `operation_id: UUID`、`expected_revision: int`；M4 对话发送／重试使用稳定 request_id。返回 `CommandResult` 包含 id、适用的 new_revision、warnings；实际保存额外包含 `forecast_status`（M3 前明确为尚未接入），不能把“账目保存成功”和“预测成功”混成一个布尔值。

| 方法 | 主要输入 | 输出／副作用 |
|---|---|---|
| `PlanService.save_reference(command)` | 显式确认的完整 PlanSnapshot、选定 scenario_id、生效月、读取的当前计划指针 | M1 原子保存新修订、baseline 与指针；M3 起使旧预测失效 |
| `PlanService.select_reference(command)` | 已保存 revision_id、scenario_id | 仅切参照，账目不变，预测重新查询 |
| `PlanService.get_reference()` | 无 | 已确认计划与未保存草稿差异提示所需版本 |
| `ActualService.list_months(query)` | 可选年份、分页游标 | 月份倒序、有效值、历史比较依据 |
| `ActualService.get_month(month)` | YYYY-MM | 当前有效修订，编辑预填 |
| `ActualService.save_month(command)` | 月份、截至日、完整有效金额／资产／覆盖确认 | 追加修订，递增实际版本，触发预测刷新 |
| `ContextService.build_current_context()` | 当前正式计划／方案指针、有效实际及计算配置，由服务统一读取 | M3：不可变 CurrentContext，含唯一 ContextVersion、key 与输入快照 |
| `ForecastService.get_current(context)` | ContextService 返回的完整 CurrentContext | M3：ForecastSnapshot 或明确 needs_input/failed，不另选方案或重建 key |
| `ForecastService.compare_purchase(context, change)` | 同一 CurrentContext、经校验的 PurchaseChange | M3 可提供纯程序接口，M4 必须具备：同基线双路径及 differences；不写账 |
| `ChatService.start_conversation(command)` | 可选参照 | 空对话，不生成购买决定 |
| `ChatService.list_conversations(query)` | 游标 | 轻量历史 |
| `ChatService.send_message(command)` | conversation_id、message、request_id | 保存消息、分析状态及 AI 回复 |
| `ChatService.retry_turn(command)` | 原 request_id | 用户显式发起新尝试，不重复消息或财务写入；不要求阶段断点续跑 |
| `ChatService.get_messages(conversation_id)` | 对话 ID | 有序消息与依据是否过期 |

`save_month` 关键字段：

```text
month: YearMonth
as_of_date: date                   必须属于 month，不能在未来
income_cents: int | null
expense_cents: int | null
asset_observation: object | null
note: str                         负净支出必须说明
coverage_confirmations: list
expected_revision: int            无记录时为 0
operation_id: UUID
```

至少一项收入、支出或资产已知；0 是合法值。更换月份是另一次记录，不移动或删除原月。金额／日期校验、版本检测、去重收据与写入必须在服务层执行，不能只依赖控件。

错误统一为 `VALIDATION_ERROR / MISSING_CONTEXT / VERSION_CONFLICT / IDEMPOTENCY_CONFLICT / STORAGE_ERROR / FORECAST_ERROR / AI_UNAVAILABLE / AI_TIMEOUT / AI_INVALID_OUTPUT`，含用户可读说明与是否可重试。缺资料是可展示状态，不把所有情况变成异常或空白。

### 9.2 AI 处理流程

AI 不是财务计算器，也不是财务数据库操作员。M4 严格执行：用户自然语言 → AI 提取结构化事实候选 → 应用层验证 → Domain／ForecastService 计算 → AI 解释程序结果。

1. 保存用户消息，固定 request_id、消息序列和明确事实快照；通过 ContextService 获取当前 context。无计划也可进入价值讨论，但不能输出无依据的财务预测；不以复杂 conversation revision 为前提。
2. `AiGateway.extract` 返回新增事实候选、来源 message_id、关键问题、可计算的 PurchaseChange 草稿。
3. 应用层校验类型、金额、月份、来源和替换额度。用户未表达的数值为 unknown；模型猜测不能升级为事实。
4. 条件足够则将同一 CurrentContext 与已验证 PurchaseChange 传给 ForecastService 只读比较；不足时返回少量澄清问题。计算由 Domain 执行，不把计算任务交给模型。
5. `AiGateway.explain` 接收同一事实与程序结果，生成简短价值判断、倾向、条件和下一步问题。
6. 验证回复引用和数字，再保存 AI 消息及 AnalysisSnapshot；失败保留用户消息和已验证财务结果。

`extract` 输出：`facts[] {field,value,source_message_id,confirmation}`、`questions[]`、`purchase_draft?`。字段包括物品、金额、月份、期待、体验、资金来源、是否已发生与是否已包含。允许纠正，不能删除历史来源。

`explain` 输出：

```text
status: ask | advise | incomplete
stance: support | verify | wait | avoid | null
segments: list of text or metric_ref
reasons: list[str]
conditions: list[str]
questions: list[str]
```

金额、日期、延期等财务数字用 `metric_ref` 指向已验证输入或确定性程序结果，由渲染器格式化后嵌入聊天文本。所有影响财务结果的数字和衍生比较必须来自程序计算。未知引用、未通过引用提供的财务数字或矛盾金额均拒绝发布，不能依靠“AI 自己检查”作为唯一保障。M4 失败时保留程序结果并提供显式重试；自动 output repair 为后续可选扩展。相关事实和价值解释保留来源，不保存模型隐藏推理。

模型没有 Repository 写权限，不执行 SQL、Python、网页访问或付款动作。用户消息、商品文案和历史对话都作为数据，不得通过提示词改变写入边界。“可以了”只结束交流语义，不生成 buy 状态。

AiGateway 不持有 Repository、数据库连接或财务写工具；ChatService 仅可持久化对话与分析，不向模型暴露 PlanService／ActualService 写入口。禁止 AI 自算最终财务数字、修改资产、写实际收支、修改 PlanRevision、把「决定购买」变成「已购买」、执行 SQL 或自行定义 ExitRule。模型可以提出建议；财务事实只能由相应页面的用户显式操作，经应用校验后写入。

### 9.3 超时、重试与数据范围

- M4 每次尝试通常为 extract、explain 两次调用；资料不足时可不进入 explain。每次默认 45 秒超时。网络或输出失败即记录可读错误，用户可显式重试；首版不自动多轮重试或自动 output repair。
- M4 仅需区分请求处理中、完成、失败，以及依据是否 stale；可采用 `pending / running / completed / failed` 加 stale 标记。重启后未完成请求显示未完成并允许用户重试，不自动续跑，也不发布半成品。完整 `interrupted` 状态恢复和阶段断点续跑为 future-ready。
- 用户原消息 request_id 不变，重试可记录简单 attempt，不再插入同一用户消息；同一对话首版串行发送，不建设多请求并行编排。供应商可能已处理但响应丢失时不能承诺外部计费恰好一次，应用发布只允许一次。
- 无密钥只禁用生成回复，仍保留原功能和用户输入；不返回虚构 AI 分析。
- 发送范围为必要的方案摘要、当前数据日期与质量、相关对话、用户明确事实、计算结果；不发送全部账本、数据库文件或密钥。
- 日志只记录 request_id、版本、模型名、耗时、错误类别；默认不记录财务原文。

架构可支持有上限的自动重试、受控输出修复、复杂 conversation revision 和供应商切换，均属 future-ready／phased implementation；启用前须明确触发条件、调用／费用上限和测试。它们不阻塞 M1–M3，也不是首版 M4 的默认验收要求。

## 10. 测试数据与预期结果

以下均为测试／演示数据，不导入用户库。金额表以元便于审阅，fixtures 写整数分。固定时钟为 2026-10-05，测试中可替换。

### 10.1 原型节点案例

| 方案 | 退出月 | 节点资产 | 半 FIRE 月收入 | 年预算 | 示例收益 |
|---|---|---:|---:|---:|---:|
| A | 2027-04 | 1,600,000 | 5,000 | 120,000 | 3.5% |
| B | 2027-08 | 1,710,000 | 5,000 | 120,000 | 3.5% |
| E | 2028-04 | 2,100,000 | 5,000 | 120,000 | 3.5% |

这是节点 fixture，没有完整积累路径，不能用于验证真实退出延期算法。Niki 未发生、17,000 元、长期喜欢且试背认可、资金来自 FIRE 储蓄。原 B 年缺口 150 元，节点扣款后为 745 元。不给购买许可，也不把“可以了”记成买。

原型月度数据：7 月 50,000/9,500，8 月 50,000/12,500，9 月 50,000/11,000；每月演示计划 50,000/10,000。结余差额分别 +500/-2,500/-1,000，累计 -3,000。10 月截至 5 日收入 0、支出 1,800，未满月，不与整月计划硬比较。仅在原型简算下得到 B 1,707,000 元、年缺口 255；再扣 17,000 得到 1,690,000、缺口 850。

### 10.2 完整逐月 fixture

`monthly_zero_return`：2026-07 月初资产 1,150,000 元、结束 2027-10、退出前月收入 50,000、月支出 10,000、B 原退出月 2027-08、次月收入 5,000、年收益 0、无事件；所有月份的 10,000 元支出明确为排期可比。14 个月工作期结余 560,000，原退出节点为 1,710,000 元。与上表的 3.5% 节点 fixture 独立，不混用收益假设。

代入上面的 7–9 月完整实际并保留其他月计划：2027-08 为 1,707,000 元；2026-10 的 partial 记录缺少剩余安排，完整预测标 conditional 并披露未纳入部分。若用户确认 10 月剩余收入 50,000、支出 8,200，则该月总额仍为 50,000/10,000，可消除这项缺口。假设 2026-11 新增 Niki 支出，退出节点为 1,690,000 元。

### 10.3 自动测试矩阵

| 编号 | 输入／操作 | 预期 |
|---|---|---|
| T01 | 无实际的 legacy_month 与旧测试输入 | 所有原月点与节点结果保持一致 |
| T02 | 完整逐月 fixture，7–9 月实际 | 节点少 3,000；将 9 月支出改 21,000 后少 13,000；原目标不变 |
| T03 | 100,000 起点，12% 收益，计划结余每月 1,000；首月实际 0 | 两个月 101,000、103,010；与原路径差 1,000、1,010 |
| T04 | 支出 8,000 修正为 10,000；同 operation_id 重试 | 有效值 10,000，只有一份新修订，不为 18,000 |
| T05 | 实际支出已含 2,000 购买，聊天记录已买 | 总额不增加，模拟不再次扣款 |
| T06 | 已确认 9-30 资产 1,267,000，下一月结余 40,000、收益 0 | 10 月末 1,307,000；不重放 7–9 月 |
| T07 | 30 天月份的 15 日日终 100,000，12% 收益；剩余收入 0、支出 2,000 | 剩余收益 500，月末 98,500；无剩余安排则 needs_input |
| T08 | 实际收入含工资 50,000+奖金 10,000，计划同月已有奖金事件 | 当月收入 60,000，不为 70,000 |
| T09 | 只有支出、另一侧 null；单月超支 | 未知侧有明确估计标记，未来不自动延续超支 |
| T10 | 10,000 起点、0 收益、本月消费 17,000 | 月末 -7,000，之后负余额收益为零 |
| T11 | 替换已确认未发生 10,000，购买 17,000 | 增量 7,000；重复替换或虚构条目拒绝 |
| T12 | 起点 90,000，工作月结余 10,000，用户确认资产门槛 100,000，0 收益 | 无购买首月达门槛；首月买 10,000 则次月达门槛，候选路径保持工作收入直到候选月 |
| T13 | 无退出规则／区间内无解／0 收益且主动收入低于预算 | 分别 rule_missing／not_reached，不凭除法编造延期 |
| T14 | 补录在最新资产锚点之前的实际 | 历史行变化，锚点之后预测不重复变化 |
| T15 | 一方保存后另一会话用旧 expected_revision 保存 | VERSION_CONFLICT，不覆盖第一次保存 |
| T16 | AI 运行期间实际版本变化 | 回复标 stale，不作为最新；下一轮读取新 key |
| T17 | 模型返回不存在 metric_ref 或矛盾金额 | 不发布该财务回复，原消息与程序结果仍可恢复 |
| T18 | 重复发送、页面重跑、超时重试、应用重启 | 同请求用户消息和发布回复各至多一条，失败可重试 |
| T19 | 迁移故障、数据库锁、未知 schema version | 回滚／可读错误／拒绝降级，旧数据保留 |
| T20 | 新目标生效后查看历史月份 | comparison_baseline 不被新目标重写 |
| T21 | 退款净额 -1,000 并附说明；内部转账 | 净支出正确增加结余；内部转账不作为收支 |
| T22 | 月中观测已含此前支出，再更新累计；跨年与闰年 | 只计算观测后的安排，正确使用剩余天数 |
| T23 | 同一次实际更新后，由 ContextService 获取 context，传入预测、消费比较和聊天；处理中再次更新 | 三者引用同一 ContextVersion；发布前发现版本改变则标 stale；业务服务不得自拼 key |
| T24 | 修改字段、保存旧表单、切页、rerun、恢复 session，再显式确认计划 | 确认前不新增 PlanRevision、不改当前指针；确认成功后原子生成修订与唯一当前指针；失败保留旧计划 |

T23 在 M3 先验证统一上下文与预测，纯程序消费接口若在 M3 实现则一并验证；M4 补齐消费与聊天覆盖。T24 在 M1 验证。原 T01–T22 编号及财务断言保留，按第 12 节分阶段落实；T12 的候选扫描在 M3 验证，购买分支最迟 M4 补齐。T18 要求可见失败、消息去重和用户显式重试，不要求自动断点恢复或多轮模型修复。

### 10.4 UI 与人工验收

用 AppTest 验证三模块切换、月度表单、原页面路由、对话发送和服务错误状态；如果当前 Streamlit 版本不能直接覆盖某交互，在服务集成测试外补人工步骤，不改写原页面来迁就测试。

人工案例包括：长期喜欢但不急、临时冲动、刚需替换、愿意延后退出、无完整计划、已购买未确认覆盖、用户说“可以了”。评审是否复用已知信息、承认价值、准确引用计算、清楚表达条件；不要求固定措辞。

### 10.5 Golden Scenarios：产品级真实场景

Golden Scenarios 同时验证「代码正确」与「产品决策正确」，不替代单元测试。以下是待实现的独立合成 fixture 与验收规范，不是用户的正式计划，也不是已通过的运行结果。M3 起建立确定性结果基准，M4 检查解释，M5 汇总完整路径、程序证据与 UI 人工验收。

#### 共用基线与审阅方式

G01–G04 使用以下显式基线；每次只改变场景指明的因素，不累计其他场景变化：

- 两个独立起始资产案例：2026-01 月初金融资产 1,250,000 元／1,600,000 元，均为计算前余额。
- 退出前月收入 20,000 元；退出当月仍采用此收入，次月起半 FIRE 月收入 5,000 元。
- 每年基础生活 70,000 元、享受型支出 30,000 元、旅行预算 20,000 元，合计 120,000 元；逐月预测按 10,000 元支出。这里是明确月均假设，不宣称旅行实际按月发生或可精确判定月度超支。
- 年化收益率 3.5%，规划提款率 3.5%，分别使用，不重复相加；无其他事件。
- 指定退出月份 2026-12，预测至 2028-12，共 36 个整月；明确金融资产底线 100,000 元，逐月检查候选退出至期末的余额。
- fixture 明确确认 `income_coverage`：候选退出节点的年度收入覆盖预算，同时满足上述底线。该确认只属于测试数据，不自动成为用户规则。另用 T12 验证 `asset_target`。

每个场景输出完整逐月表：月初资产、经常／一次性收支、收益、月末资产、计划或实际来源；另列指定目标月与规则候选退出节点的资产、年度可支配、年度缺口及条件。候选扫描必须重建收入路径；未达到条件显示 not_reached，不能省略此结果或写成零个月差异。基准预期由独立人工复算／独立参考表核对，不从被测函数生成期望值再自证正确。

#### G01｜基准半 FIRE

分别跑 125 万和 160 万本金的完整路径，解释本金、工作期储蓄、收益和三类生活预算如何影响结果。人工检查点：首月收益分别为 3,645.83／4,666.67 元，月末资产分别为 1,263,645.83／1,614,666.67 元；2026-12 仍使用工作收入，2027-01 转为 5,000 元。

验收：36 个月路径完整且可解释，明确区分「指定月份退出后的结果」与「按已确认规则何时达标」；不能因年预算合并而遗漏旅行或享受型支出，也不能把一个状态色当作终身保证。

#### G02｜大额消费：17,000 元 Niki

在 G01 同一个 CurrentContext 内比较不购买与 2026-01 购买 17,000 元两条路径。购买尚未发生，来自 FIRE 储蓄，无替换额度和持续费用；长期喜欢、试背认可、暂不购买也不影响日常生活作为价值背景。

必须输出：

- 两条完整资产路径及逐月差异；购买月末资产差为 -17,000 元，后续差异包含收益路径变化。
- 原指定目标月仍为 2026-12，列出该月资产差异，不自动改用户日期。
- 在相同 ExitRule 下的候选目标月份及月份差异；任一路径未达标或缺少条件时说明原因，不伪造具体延期。
- 指定退出节点及各自候选退出节点的资产、年度可支配、年度缺口差异，区分共同日期比较和不同日期节点比较。
- 本次增量仅为本次消费与后续收益变化；原计划与实际偏差单列，不混入购买代价。

验收：程序解释成本，AI 讨论生活价值与可接受条件；不给无规则评分或自动许可，不把「愿意买」写成已发生支出。

#### G03｜半 FIRE 收入从 5,000 降为 3,000 元／月

从 G01 基线独立修改退出后收入，工作期收入保持不变。分别运行原方案与调整方案，呈现年度收入减少 24,000 元及后续资产路径、节点和候选月份变化。此为待比较方案，不自动生成新的正式 PlanRevision。

验收：用户能比较增加本金、延后退出、降低支出三种调整。按 3.5% 收益、120,000 元年预算，仅年度收入覆盖条件对应的最低本金由 1,714,285.72 元变为 2,400,000 元（向上取整到分）；这不是含完整路径与底线检验的安全本金结论。保持同节点资产和收益时，年预算减少 24,000 元可抵消收入缺口的增量；不能将其冒充整体计划已经可行。延后退出必须程序重跑候选路径，区间无解如实展示，调整由用户确认。

#### G04｜预期收益率从 3.5% 降为 1%

从 G01 基线独立修改预期收益率，收入和预算保持原值，提款率仍为 3.5%。比较完整资产路径、指定目标月、节点年度缺口和候选退出月份。

验收：展示方案具体变化，不能只给「可以买／不能买」。在每月主动收入 5,000 元和年预算 120,000 元下，仅年度收入覆盖所需本金变为 6,000,000 元；完整方案仍需路径与底线校验。两条预测均来自程序；不能用提款率补足下降的预期收益，更不能沿用原收益路径只修改终点标签。

#### G05｜计划收支替换为实际收支

使用 10.2 的 `monthly_zero_return` 独立完整 fixture：计划 B 节点 1,710,000 元；7–9 月实际替换后为 1,707,000 元；9 月支出由 11,000 改为 21,000 后为 1,697,000 元。该场景不叠加 G02 购买或未确认的 10 月 partial 数据；有完整实际替换的月份使用已确认月度排期。

再用 T03 非零收益案例检查后续复利重跑，用 T14 检查历史修改被资产观测覆盖时不再次影响未来余额。验证实际仅替换对应期间，未涉及月份保持原假设；更正同月不累计旧值，已包含购买不再扣款。

验收：Actual 页面、FIRE 摘要及消费比较引用 ContextService 提供的同一有效上下文；保存实际后版本更新，旧预测不得冒充最新。UI 能说明差异源于实际执行还是购买增量，原目标仍保留。

## 11. 验收标准与需求映射

| PRD | 交付证据 |
|---|---|
| A01 / P0-1 | 四原页回归 + 原测算 fixture 一致 + 完整方案重启恢复 + T24 草稿确认边界 |
| A02–A04 / P0-2 | 月份倒序、编辑回表、无单月详情区、未知与零区分、幂等替换 |
| A05–A08 / P0-3 | T02/T03/T06/T07/T14/T16/T20/T23 通过；Actual、Forecast、Purchase 同有效上下文；实际保存失败与预测失败区分 |
| A09–A11 / P0-4 | 真实 AI 对话可运行；无问卷卡片墙；同基线计算与 T05/T11 通过；Niki 人工评审 |
| A12–A14 / P0-5 | 持久化、冲突、超时、数据变化、迁移与隐私验证；示例库隔离 |

完成定义：相关阶段自动测试通过，原 Planner 无回归，人工场景通过；M5 汇总 G01–G05 完整证据。文档按实际能力更新状态，并注明未支持或后置能力，不把整份 future-ready 设计标为已实现。测试桩或原型可点击不等于真实 AI 上线；无资料时诚实降级不是算法缺陷，但不能所有输入都只显示“待重算”就宣布预测能力完成。

本轮仅文档变更，检查术语、链接、接口与模型一致性、测试示例计算即可；不对用户 SQLite 运行迁移，不宣称上述新测试已存在或通过。

## 12. Implementation Scope：首版渐进实现

以下是 V1 各阶段必须落实的技术边界。对象全集、目录和 API 清单服务于 Architecture completeness，不能覆盖本节的阶段限制。[开发计划 V1.0](development-plan.md)与 Checklist 保留原进度，本轮不修改；其中 M1 通用幂等或 M4 自动恢复等较早要求，后续生成执行规格时须按本节收敛并同步计划，不能据旧条目提前扩大实现范围。

| 阶段 | 必须实现 | 本阶段不实现／边界 | 独立验收 |
|---|---|---|---|
| M1 | 完整 PlanSnapshot、显式确认的 PlanRevision、唯一当前计划／方案指针、旧 Planner adapter、数据库 migration、原 Planner 回归 | 不实现 AI、Purchase、Actual 重跑、完整对话、AI retry、output repair、复杂 stale 状态机或全局 command_receipts | 无 AI 配置也能保存、选择、恢复完整参照；T01/T24 与计划迁移测试通过，原四页兼容，BASE-01 跨页覆盖缺陷修复 |
| M2 | MonthlyActualRevision、actual_revision、月度历史、comparison_baseline、幂等保存、version conflict、基本资产观测 | 仅记录与校验观测，不把「已存资产」等同预测截点已实现；不做 AI 或共享预测状态机 | T04/T15/T20/T21 及未知值／恢复测试通过；预测未接入时明确标识 |
| M3 | 唯一 ContextService、唯一 ForecastService、Actual → Forecast 重跑、ContextVersion、简单 stale、needs_input／conditional／updated 等质量、ExitRule | Purchase 双路径可先提供纯程序接口，不接 AI；不做聊天恢复或供应商框架 | T02/T03/T06–T10/T12–T14/T22 及 T23 财务部分通过；实际影响同版本预测，G01/G03/G04/G05 可人工解释 |
| M4 | Conversation／Message／AnalysisSnapshot、AiGateway、ChatService、extract → validate → calculate → explain、metric_ref 校验、timeout／用户显式 retry／invalid output | 补齐 Purchase 双路径，接一个真实供应商；不强制复杂 conversation revision、自动多轮重试、output repair 或 interrupted 断点恢复 | P0-4 真实链路、T05/T11/T16–T18 与 T23 聊天部分通过；G02 比较与价值解释通过 |
| M5 | 端到端、Golden Scenarios、UI 人工验收、迁移恢复演练、文档最终状态更新 | 不以「架构已描述」为理由追加 future-ready 能力，不自动部署外部环境 | PRD A01–A14、T01–T24 适用测试及 G01–G05 证据齐全，明确已实现与后置项 |

M1 的 UI 工作只服务于原页兼容和显式保存／选择参照，不因三模块架构提前实现实际或聊天页面。M1 必须能够独立开发和验收，不依赖 AI 供应商、密钥或后续数据模型。

### 12.1 Future-ready / Phased Implementation

| 架构预留 | V1 最小要求 | 后置能力 |
|---|---|---|
| conversation revision | M4 消息顺序、事实来源与请求输入快照 | 复杂会话修订链、并行分支合并 |
| interrupted | M4 识别未完成请求，保留消息，允许显式重试 | 自动断点续跑、恢复编排 |
| AI retry / output repair | M4 超时与输出校验，用户显式重试，不重复发布 | 自动多轮重试、模型输出自动修复 |
| schema version | M1 当前格式校验、旧库安全迁移、拒绝未知新版 | 全面多版本演进与通用转换框架 |
| command_receipts | M2 实际保存最小去重与冲突检测 | 所有命令统一收据框架、复杂过期与恢复机制 |
| 并发控制 | 短事务；M1 确认时核对指针；M2 实际乐观锁；M3 发布版本检查；M4 单对话串行请求 | 大量并发请求协调、分布式锁、后台任务队列 |
| 供应商切换 | M4 AiGateway 协议与一个适配器 | 多供应商路由、自动故障切换及全供应商兼容 |

保留这些扩展可能性不等于承诺首版交付；任何升级为必做能力的变更须先明确需求、验收与阶段。若新增独立复盘、分类账或改变旧页面交互，先更新 PRD 再修改此设计。

## 13. Implementation Spec 的上下游关系

本文是 Technical Design，不直接作为 Coding Agent 的逐任务执行指令。

```text
已确认 PRD／原型
  → Technical Design V1.3（系统应该如何设计）
  → implementation-spec.md（Coding Agent 下一步具体应该做什么）
  → 按批次实现、测试与验收证据
  → 更新开发计划／Checklist／已实现文档状态
```

后续从本文生成 `implementation-spec.md`，沿用 M1–M5 阶段与已有任务 ID，把每批任务明确为以下字段：

| 字段 | 职责 |
|---|---|
| Task | 本次具体任务、所属阶段与要解决的问题 |
| Input | 依赖的现有代码、模型、用户动作及测试 fixture |
| Output | 可验证交付物、返回结果、状态或数据变化 |
| Files to change | 限定修改文件和必要新增文件 |
| Dependencies | 前置任务、契约和已具备条件 |
| Must | 本阶段必须满足的算法、边界与兼容行为 |
| Must Not | 禁止改动或提前实现的能力，尤其财务写权限与未来状态机 |
| Acceptance Criteria | 可独立验收的行为、错误情况和完成条件 |
| Test Cases | 对应 T／G 编号、输入、独立预期与人工检查步骤 |

执行规格应将 M1 的输入限定为旧 Planner、草稿和已确认计划，无须等待 M2–M4 接口落地；不能把整份架构对象清单复制成 M1 开发任务。生成时核对现有代码和已完成证据，保留正确实现，识别开发计划中的旧范围并同步修订。本次不生成该文件，也不标记任何开发任务完成。

## 14. V1.3 文档修订核对

以下为设计核对，非代码验收：

1. 原 Planner 兼容优先：保留四页主体、旧计算口径与回归门槛（1、5.1、12）。
2. Actual／Forecast／Purchase 共享有效上下文，聊天引用相同依据（4.6、8、9）。
3. ContextVersion 与 key 仅由 ContextService.build_current_context() 构造（4.6）。
4. Draft 与 Confirmed Plan 分离，显式确认才产生修订，当前正式计划仅一个指针（4.5、T24）。
5. AI 无 Repository／SQL／财务写权限，ChatService 只写对话与分析（9.2）。
6. 财务结果由确定性程序计算，模型通过 metric_ref 引用（5、9.2）。
7. Golden Scenarios 覆盖基准生活、大额消费、收入与收益变化、实际更新（10.5）。
8. M1 无须实现或配置 AI 即可独立完成验收（12）。
9. implementation-spec.md 的上游依据、任务字段与阶段限制明确（13）。
10. future-ready 能力不扩大 V1 范围，不阻塞 M1–M3（1.3、12.1）。
