# 半 FIRE Planner Implementation Specification

## 1. Scope

**Current Milestone: M1 — Plan Persistence & Compatibility**

执行状态（2026-10-06 导航复核）：M1-01～M1-04 的既有验证保留；M1-05 重新打开，导航归属待修正与验收。此前 [M1 验收记录](m1-acceptance.md) 的 128 项测试通过未覆盖其他模块中计划控件应隐藏的要求，不能作为新增 T25 的通过证据。下一项为完成本文 M1-05 导航修正，再进入 M2-01。本次仅修改文档，不修改页面代码；Current Code Baseline 保留原实施前审计。

本规格把 PRD V0.7 与 Technical Design V1.4 转换为当前一轮可执行的开发任务。页面层级修正覆盖旧“四页入口全部保留”的要求；历史计算基线继续有效。M1 只交付：

- 保留生活、资产、测算三个工作页及计算公式和表单交互；移除独立首页入口，必要摘要和引导归入已有工作区域；
- 将一次完整测算保存为正式的不可变 `PlanRevision`；
- 在 `app_state.current_plan_revision_id` 中保存唯一当前正式计划指针；
- 明确 `session_state` / `form_state` 草稿与 Confirmed Plan 的边界；
- 通过重启恢复已确认计划；
- 使确认和指针更新原子化，保存失败时保留旧计划；
- 修复已知的 BASE-01 跨页保存覆盖预算缺陷；
- 运行既有 Planner 回归测试及 M1 新增测试。

M1 不改变财务算法，不实现实际收支驱动预测、消费模拟、AI 或聊天。实现应以现有代码为基线，采用小型 adapter、正式快照和最小持久化，不重写 Planner。

## 2. Source Documents

- [产品需求](product-requirements.md)（PRD V0.7）：三个工作页、首页内容归置、A01、P0-1、数据边界及原财务能力兼容要求。
- [技术设计](technical-design.md)（V1.4）：条件路由、默认进入测算、旧首页状态归一、PlanSnapshot、PlanRevision、迁移、Draft → Confirmed 边界及 M1 阶段限制。
- [开发计划](development-plan.md)（V1.0）：M1-01 至 M1-05 的顺序和出口条件。
- [回归基线](regression-baseline.md)：既有计算、页面和 BASE-01 缺陷记录。
- [开发 Checklist](development-checklist.md)：当前进度记录；不改变本规格的任务边界。

Technical Design 是架构约束，本文件才是本轮 Coding Agent 的执行入口。Technical Design 中的未来对象只有在本文件列为 M1 任务时才可创建。

## 3. Current Code Baseline

### 3.1 实际存在的实现

| Area | Current behavior | M1 implication |
| --- | --- | --- |
| `app.py` | 通过 `PAGE_RENDERERS` 和 `selected_page` 提供“首页／我的生活／我的资产／开始测算”四页。 | 按 V0.7 保留后三个工作页，移除首页路由，默认进入测算；局部导航和计划操作仅在 FIRE 计划显示。 |
| `src/fire_planner/ui/pages/home.py` | 从 `session_state` 读取预算和可提款金融资产，提供进入测算按钮。 | 不再作为应用页面渲染；复用已有工作页摘要，缺失资料引导归入测算页；正式摘要由服务读取。 |
| `src/fire_planner/ui/pages/living.py` | `BUDGET_FIELDS`、按年份的 `budget_{year}_{field}` 控件、年度预算计算；保存调用 `save_form_state`。 | 预算输入仍保持原键和年度回退语义；保存必须变成页面范围的草稿保存。 |
| `src/fire_planner/ui/pages/assets.py` | 金融资产、房产和房贷控件；`get_investable_assets_cents` 排除房产和房贷余额；保存调用 `save_form_state`。 | 保留资产口径；保存不能覆盖其他页面刚保存的草稿。 |
| `src/fire_planner/ui/pages/calculation.py` | 在 UI 内组装 `ScenarioInput`，调用 `forecast_assets`、`evaluate_scenario`，方案 ID 目前是位置型字符串。 | 提取纯转换到 adapter；`_forecast_scenario`、`forecast_assets` 和结果语义保持不变。 |
| `src/fire_planner/domain/forecast.py` | 月初正资产按年收益率 / 12 计算 `ROUND_HALF_UP` 收益；负余额保留且不产生收益。 | 只复用，不改公式、初始资产校验或负余额语义。 |
| `src/fire_planner/domain/scenario.py` | 年度缺口、提款参考和现有状态计算。 | 保留现有输入输出；M1 不引入新的退出规则。 |
| `src/fire_planner/infrastructure/storage.py` | SQLite 中仅有 `form_state(key, value)`；按 session 全量写入，没有迁移、备份或正式计划。 | 保留 `form_state` 作为兼容草稿；增加迁移与页面范围写入，不把它升级为正式计划。 |
| `src/fire_planner/infrastructure/db.py`、`repositories.py` | 目前只有模块说明，没有可调用实现。 | M1 实现最小连接、迁移和 Plan Repository。 |
| `src/fire_planner/application/dto.py`、`plan_service.py` | 目前只有模块说明，没有 DTO 或服务。 | M1 实现计划命令、结果、保存／选择／恢复服务。 |
| `src/fire_planner/domain/models.py` | 已有 `Plan`、`Scenario`、`BudgetItem`、`AssetHolding` 等旧领域对象；没有 `PlanSnapshot`。 | 不破坏旧对象；新增规划快照模型时通过组合或新模块兼容它们。 |

### 3.2 当前状态与数据来源

- `st.session_state` 同时承载控件值、页面位置和当前草稿；目前没有正式计划状态。
- `form_state` 保存预算、金融资产、非金融资产和负债字段，默认路径为项目根目录 `fire_planner.sqlite3`，可由 `FIRE_PLANNER_DB_PATH` 覆盖。
- 计算页的起点使用 `date.today()` 并按 `YearMonth` 运行整月 legacy 模式；测算日期、预测月数、收益率、提款率、半 FIRE 收入、方案及一次性收入目前未持久化。
- 现有方案显示标签“节点 1／节点 2”等是位置型 UI 标签，不是正式身份。
- `pyproject.toml` 声明 Python 3.11+、Streamlit、Plotly 和 pytest；实际测试必须使用临时数据库，不得使用用户数据库。

### 3.3 已有测试基线

现有测试覆盖金额、预算、预测、方案、压力测试、存储、校验和 Streamlit AppTest。`docs/regression-baseline.md` 记录的 2026-10-05 基线为 **77 passed、1 strict xfailed**；xfailed 用例是 BASE-01。当前工作环境直接运行 `pytest -q` 因未安装声明的 `streamlit` 而在收集阶段失败，不能把该失败当作产品回归；实现前应按 README 安装 `.[dev]` 后重新执行。

## 4. M1 Goal

用户可以继续用原 Planner 试算，在明确点击“确认／保存计划”且校验成功后生成一个新的完整 `PlanRevision`。应用重启或切换页面后，正式计算只读取 `app_state.current_plan_revision_id` 指向的修订；未确认编辑只显示为草稿。任何 Streamlit rerun、页面切换、刷新、session 恢复或表单字段修改都不能生成修订。

确认一次必须在同一 SQLite transaction 中完成：

```text
insert immutable plan_revisions
+ update app_state.current_plan_revision_id
```

任一步失败都回滚，旧指针和旧计划仍可读取。选择已有修订只改变当前指针，不新建修订；选择的 `scenario_id` 必须属于该修订。

## 5. Architecture Invariants

1. **唯一正式来源**：正式 Planner 计算只读取 `plan_revisions` 中由当前指针选中的快照；不得直接读取 Draft。
2. **`form_state` 只表示 Draft / compatibility state**：它可帮助旧页面恢复工作值，但不能作为第二个正式计划来源。
3. **显式确认才创建修订**：只有用户明确点击确认／保存并且校验成功才可插入 `PlanRevision`。
4. **修订不可变**：创建后不得更新 `snapshot_json`、`baseline_json`、`input_hash` 或业务字段；修改计划必须新建修订并设置 `parent_id`。
5. **单一当前指针**：`app_state.id = 1` 最多有一个 `current_plan_revision_id`，未确认时允许为 `NULL`；`current_scenario_id` 必须属于当前修订。
6. **确认原子化**：插入修订和更新指针在同一事务中完成；冲突或数据库异常不能留下半保存状态。
7. **Legacy 计算不变**：继续使用整数分、基点、`ROUND_HALF_UP`、年度预算除以 12、退出当月仍使用退出前收入、负余额不产生收益、房产及房贷余额不改变可提款金融资产等现有语义。
8. **Adapter 不重写引擎**：`planner_adapter` 只负责旧控件／草稿与 `PlanSnapshot` 的双向转换，不能成为新的 Forecast Engine。
9. **M1 不提前实现未来模块**：Actual、ForecastService、Purchase、Conversation、AI 及复杂 stale／retry／command receipt 均不属于本轮。
10. **单位与身份固定**：金额用整数分；比率用 basis points（例如 `350 = 3.5%`）；月份为 `YYYY-MM`，日期为 ISO；持久化身份为 UUID，A/B/E 或节点标签仅用于显示。
11. **页面层级固定**：顶层三个模块；FIRE 计划仅含我的生活、我的资产、开始测算三个工作页。没有独立首页、计划首页或同义概览页。新会话默认进入测算，旧首页路由回退测算；同会话返回恢复上次工作页。子导航及计划操作仅在 FIRE 计划分支渲染；其他模块只允许按需展示只读正式摘要。导航变化不产生业务写入。

## 6. Implementation Tasks

### M1-01 Audit and freeze the legacy Planner baseline

以下为原实施前基线。V0.7 调整后的目标不再要求保留首页导航及其跳转按钮；M1-05 可更新对应 UI 断言，所有财务 fixture、金额、日期语义和表单保存断言保持不变。

**Goal**

把现有 Planner 的计算、页面、存储和已知缺陷固定为 M1 的回归门槛。

**Input**

`app.py`、四个现有页面、`domain/forecast.py`、`domain/scenario.py`、`domain/money.py`、`tests/`、`docs/regression-baseline.md`。

**Output**

可重复的 legacy 测试命令、关键逐月结果和明确的 BASE-01 记录；M1 后必须运行同一组测试。

**Files to Change**

- 新增文件：`None`
- 修改文件：`None`（基线测试和记录已经存在；若安装依赖后发现缺少关键回归，只能新增对应测试，不改业务实现。）

**Dependencies**

无。

**Must**

- 在实现前运行 `pytest -q` 和 `python -m compileall -q app.py src tests`。
- 固定 `tests/test_planner_baseline.py` 的逐月资产、节点、目标曲线和图表断言。
- 固定 `tests/test_existing_ui.py` 的四页导航、默认收益／提款率、保存恢复、方案和收入行交互。
- 保留 BASE-01 的严格 xfail，直至 M1-05 修复并转为通过。

**Must Not**

- 不修改预期数字以掩盖回归。
- 不重写 `forecast_assets`、`evaluate_scenario` 或原页面布局。
- 不把当前环境缺少 `streamlit` 的收集失败记录成代码已通过。

**Acceptance Criteria**

- 安装项目声明依赖后，基线达到文档记录的 77 passed、1 strict xfailed，或对差异给出独立说明。
- 2027-11 至 2028-02 的两个方案逐月资产和退出结果与现有断言一致。
- 四个旧页面和图表仍可通过 AppTest，BASE-01 仍清晰标为待修复。

**Test Cases**

- `tests/test_planner_baseline.py::test_existing_scenario_monthly_path`
- `tests/test_planner_baseline.py::test_existing_node_results_and_chart_use_the_same_monthly_paths`
- `tests/test_existing_ui.py::test_original_pages_and_home_calculation_action`
- `tests/test_existing_ui.py::test_saved_budget_and_assets_restore_and_feed_monthly_calculation`

### M1-02 Add the migration and SQLite transaction foundation

**Goal**

在不破坏旧 `form_state` 的前提下建立 M1 所需的版本化 schema、连接和短事务能力。

**Input**

当前 SQLite 文件、`FIRE_PLANNER_DB_PATH`、现有 `storage.py` 读写行为以及 Technical Design 的 M1 表定义。

**Output**

版本化迁移、旧库备份、外键开启、`app_state` 单例、`plan_revisions` 空表和可复用 transaction helper。

**Files to Change**

- 新增：`src/fire_planner/infrastructure/migrations.py`
- 修改：`src/fire_planner/infrastructure/db.py`、`src/fire_planner/infrastructure/repositories.py`、`src/fire_planner/infrastructure/storage.py`
- 新增测试：`tests/test_migrations.py`（可扩展 `tests/test_storage.py`）

**Dependencies**

M1-01。

**Must**

- 建立 `schema_migrations(version PRIMARY KEY, applied_at)`；M1 使用明确的当前 schema version。
- 保留 `form_state(key PRIMARY KEY, value TEXT NOT NULL)` 及其已有值。
- 建立 `app_state(id = 1, current_plan_revision_id NULL 或 FK, current_scenario_id NULL)` 和 `plan_revisions(id, parent_id, effective_from_month, created_at, schema_version, snapshot_json, baseline_json, input_hash)`；开启 foreign keys。
- 首次迁移用 SQLite backup API 建立带时间戳备份；迁移失败回滚并保留旧库可读。
- 重复运行迁移幂等；发现数据库版本高于当前支持版本时拒绝降级或静默修改。
- 连接设置合理的 busy timeout，写事务保持短；不引入分布式锁。
- 保持数据库路径和临时测试路径可配置；测试不得触碰项目根目录用户库。

**Must Not**

- 不创建 `actual_month_revisions`、`forecast_runs`、`conversations`、`messages`、`analysis_runs` 或 `command_receipts`。
- 不删除、重命名或批量改写现有 `form_state`。
- 不建设通用 schema 转换框架、自动修复或全局命令总线。

**Acceptance Criteria**

- 含旧 `form_state` 的临时旧库升级后，所有 key/value 与迁移前相同。
- 同一数据库重复初始化不会新增迁移行、重复表或重复数据。
- 注入 DDL／提交异常时，迁移返回可读错误，旧表和旧值仍可读取。
- 高于支持版本的 `schema_migrations` 被拒绝，且不会降级覆盖数据库。
- `app_state` 只有一行；`plan_revisions` 的外键和不可变字段约束可被测试观察。

**Test Cases**

- 技术测试 `T19` 的旧库升级、备份、失败回滚、未知 schema version。
- 空库初始化、含旧 `form_state` 初始化、重复初始化。
- foreign key 约束和 `app_state.id = 1` 唯一性测试。

### M1-03 Define PlanSnapshot and PlanRevision persistence

**Goal**

把旧 Planner 的完整可计算输入和结果封装成经过校验的正式快照，并能无会话依赖地往返持久化。

**Input**

旧页面控件值、`build_budget_items`、`build_financial_assets`、`ScenarioInput`、一次性收入行、测算参数和 M1-02 的表。

**Output**

`PlanSnapshot`、`ScenarioSnapshot`、`PlanRevision` 的 Python 模型／DTO、JSON schema version 1、规范化 `input_hash` 和 Repository 读写。

**Files to Change**

- 新增：`src/fire_planner/domain/planning.py`
- 修改：`src/fire_planner/application/dto.py`、`src/fire_planner/infrastructure/repositories.py`
- 新增测试：`tests/test_planning.py`、`tests/test_plan_repository.py`

**Dependencies**

M1-02；M1-01 的 legacy 输入和断言。

**Must**

- `PlanSnapshot` 至少包含：起点日期／legacy_month 语义、预测期限、金融资产与非金融资产口径、负债展示值、年度预算及来源、年收益率、提款率、退出后收入、全部稳定方案、退出前收入、一次性事件、显示顺序和选定方案。
- 保存完整方案集合，而不是只保存当前 UI 位置或一个结果卡片；方案、预算和事件使用 UUID 或稳定 ID，节点标签只做显示。
- 金额字段以整数分保存；费率以基点保存；日期／月份使用 ISO；禁止 float money、bool 冒充数值或隐式截断。
- 快照和修订包含 `schema_version`、`created_at`、`effective_from_month`、`parent_id`、完整 `snapshot_json`、当时 `baseline_json` 和规范化输入 hash。
- JSON 序列化前后进行显式字段校验；缺字段、未知当前格式、错误单位或 scenario 不完整时拒绝保存。
- Repository 读取结果不依赖 `st.session_state`；重建的快照可重新喂给现有 Planner adapter，保留 legacy 计算语义。
- 使用不可变 dataclass 或等价不可变边界；不得提供更新旧 revision 内容的接口。

**Must Not**

- 不把 `form_state` 直接序列化成正式快照而跳过 schema。
- 不引入 Actual、Forecast、Purchase、Conversation 等未来对象。
- 不把房产或房贷余额自动并入可提款金融资产，不改变现有预算年度回退。

**Acceptance Criteria**

- 用当前 fixture 构建的快照包含所有预算、资产、负债、日期、假设、方案和一次性收入；JSON round-trip 后字段和顺序稳定。
- 通过同一快照恢复旧页面所需的输入，现有 2027-11 至 2028-02 结果逐分一致。
- 两个不同输入不会得到相同规范化 `input_hash`；相同输入不会因 JSON 键顺序变化而得到不同 hash。
- 直接尝试更新已保存 revision 被拒绝；新计划只能通过新 revision 表达。

**Test Cases**

- 完整快照 round-trip、schema 校验、金额／基点／日期边界和 UUID 身份测试。
- 两个 scenario、跨年预算、一次性收入、房产／房贷排除和退出当月收入语义测试。
- Repository 保存后关闭连接，再读取并重建快照的测试。

### M1-04 Implement PlanService save/select with atomic confirmation

**Goal**

提供唯一的正式确认入口，原子创建修订、更新当前指针并支持选择既有修订。

**Input**

M1-03 的已校验快照、用户显式确认命令、`scenario_id`、生效月份和用户读取的当前指针；M1-02 的 transaction helper。

**Output**

`PlanService.save_reference`、`select_reference`、`get_reference` 及对应 command/result DTO 和明确错误类型。

**Files to Change**

- 修改：`src/fire_planner/application/plan_service.py`、`src/fire_planner/application/dto.py`、`src/fire_planner/infrastructure/repositories.py`
- 新增测试：`tests/test_plan_service.py`

**Dependencies**

M1-02、M1-03。

**Must**

- `save_reference` 只接受显式确认动作产生的完整快照；在 `BEGIN IMMEDIATE` 内校验 expected current pointer、scenario 归属、插入不可变 revision、写 baseline 并更新 `app_state`，之后提交。
- 首次确认允许 current pointer 为 `NULL`；后续确认设置 `parent_id` 为旧 revision，且指针只指向新 revision。
- 任一校验、插入、指针更新或提交失败都 rollback；旧 pointer、旧 snapshot 和旧 baseline 仍可读取。
- current pointer 已被其他写入改变时返回可识别冲突，不覆盖他人的正式计划。
- `select_reference` 只选择已有 revision 和其内部 scenario，更新指针但不创建 revision、不写 `form_state`、不改变实际数据。
- `get_reference` 返回当前正式快照、选定方案和草稿差异所需版本信息；没有正式计划时明确返回 `NULL`／未确认状态。
- 同一个 Streamlit rerun、页面 render 或服务读取不得调用保存命令。

**Must Not**

- 不提供通过字段编辑、页面切换、刷新、session 恢复自动保存的隐式路径。
- 不在 M1 添加 `operation_id` 全局收据、Actual revision、预测缓存、stale 状态机或 AI retry。
- 不让 UI 或模型直接写 `plan_revisions` 或 `app_state`。

**Acceptance Criteria**

- 首次确认产生恰好一个 revision，`app_state.current_plan_revision_id` 指向它。
- 从 revision #1 编辑并确认新快照时产生 revision #2，#1 内容不变，#2 的 `parent_id` 为 #1。
- 选择旧 revision 后 revision 数量不变，current pointer 和 scenario 合法更新。
- 注入数据库失败后 revision 数量、current pointer 和旧计划可读性均与失败前相同。
- expected pointer 不匹配时拒绝写入，不能覆盖当前计划。

**Test Cases**

- 技术 `T24` 的确认前／确认后／指针／事务失败测试。
- 首次保存、重复显式确认、修改后新 revision、选择旧 revision、非法 scenario 和 expected pointer 冲突。
- 模拟 insert 或 pointer update 异常，断言 transaction rollback。

### M1-05 Adapt the legacy UI, Draft boundary, and restart recovery

状态：重新打开。已有保存／恢复和 BASE-01 验证保留；本次追加导航修正任务，待实现与验证。

**Goal**

让生活、资产、测算三个工作页继续工作并明确归属 FIRE 计划，移除多余首页层级并归置其必要内容；用 adapter 和明确的 Confirm 操作连接正式计划，验证跨页保存、跨模块草稿保留、非当前模块控件隐藏及重启恢复。

**Input**

M1-03 的 adapter contract、M1-04 的 PlanService、现有 `session_state` 控件键、`form_state` 兼容数据和 AppTest。

**Output**

旧控件 ↔ `PlanSnapshot` 的 adapter、最小参照栏／确认／选择交互、页面范围的草稿保存、重启恢复和通过 BASE-01 的 UI 测试。

**Files to Change**

- 新增：`src/fire_planner/ui/planner_adapter.py`；如需拆分渲染，新增 `src/fire_planner/ui/components.py`，只包含 M1 参照栏和模块入口。
- 修改：`app.py`、`src/fire_planner/infrastructure/storage.py`、`src/fire_planner/ui/pages/home.py`、`src/fire_planner/ui/pages/living.py`、`src/fire_planner/ui/pages/assets.py`、`src/fire_planner/ui/pages/calculation.py`
- 修改或新增测试：`tests/test_existing_ui.py`、`tests/test_planner_adapter.py`

**Dependencies**

M1-01、M1-03、M1-04。

**Must**

- 生活、资产、测算仍使用原 widget keys、预算年度回退、资产口径、方案输入、图表和计算函数；adapter 只转换输入／输出，不重写算法。首页导航及按钮断言允许按新结构更新，财务预期不得改变。
- 将 session 草稿和兼容 `form_state` 与当前正式快照分开保存；草稿可以继续试算，但正式摘要和正式计算只能读取 current pointer。
- 只有用户点击明确的“确认／保存计划”按钮且校验成功时调用 `save_reference`；字段编辑、旧页面保存草稿、page switch、rerun、browser refresh、session restore 都不创建 revision。
- 草稿保存采用页面范围或读改写合并：保存生活预算不能写回旧预算，保存资产不能覆盖刚保存的预算；修复并移除 BASE-01 strict xfail。
- 有 current plan 时重启加载完整快照，恢复预算、资产、日期、假设、全部方案、事件和 selected scenario；没有正式计划时不得从草稿伪造已确认计划。
- 参照栏显示当前 revision、选定方案及“草稿未确认”差异；选择已保存 revision 走 `select_reference`。
- 顶层提供 FIRE 计划、实际收支、消费判断三个模块。FIRE 计划仅有“我的生活／我的资产／开始测算”三个工作页；移除“首页”路由，不新增全局首页、计划首页或同义概览页。模块入口与工作页导航应清楚区分层级。
- 新会话默认进入 FIRE 计划 → 开始测算；`selected_page` 缺失或仍为旧值“首页”时回退“开始测算”。已有会话返回模块时优先恢复合法的上次工作页；路由归一不得修改任何财务数据。
- `app.py` 先按 `selected_module` 分支；仅 FIRE 计划分支渲染 `selected_page` 子导航、当前原页面和 `render_reference_controls`。其他两个模块只显示明确的“尚未在 M1 实现”状态；不得创建实际或聊天页面、不得触发 M2–M4 服务。
- 仅 FIRE 计划可显示：三个工作页导航、草稿参考方案、确认／保存计划、取消草稿／读取最新正式计划、历史修订及方案选择、设为正式参照。其他模块中这些控件必须不存在；按需共享摘要时拆分只读入口，从正式计划读取，M1 不强制新增摘要。
- 旧首页的年度预算与金融资产摘要复用已有工作页指标；完全 FIRE 参考值沿用测算的公式与当前提款率，不搬入固定 3.5% 的重复展示。资料缺失引导归入测算页并跳转对应工作页；移除重复的“进入测算”按钮和欢迎页，不将默认值当成已确认资料。正式摘要与草稿展示保持来源区分。
- 处理 Streamlit widget 清理：把 FIRE 子页位置及完整会话草稿与控件生命周期分离。离开模块不丢预算／资产／测算参数、方案与事件 UUID、草稿所选方案；返回先恢复状态再实例化控件。保持本轮编辑进入确认快照的原有时序。
- 切换模块不写 `form_state`，不调用 `save_reference`／`select_reference`，不自动确认、取消或重新载入正式快照覆盖草稿；新会话启动与显式取消仍遵循原恢复规则。
- M1 保留生活、资产、测算三个工作页主体和财务语义；允许必要的页内资料引导及移除首页导航壳，不把场景标签 A/B/E 作为持久化 ID。

**Must Not**

- 不在 render 函数、`on_change`、rerun 回调或加载函数中调用 `save_reference`。
- 不把当前草稿自动替换正式计划，不因恢复 session 或刷新而递增 revision。
- 不新增 `actuals.py`、`projection.py`、`purchase.py`、`actual_service.py`、`context_service.py`、`forecast_service.py`、`chat_service.py` 或 AI gateway。
- 不增加单月实际详情面板、消费表单墙、强制决定／复盘流程或原型演示数据。
- 不在实际收支／消费判断分支实例化 FIRE 工作页导航或计划管理控件；不能以 disabled 或 CSS 隐藏替代条件渲染，也不能通过执行隐藏页面来保留 widget 状态。
- 不把旧首页改名为“概览”后继续保留第四个子页，不把原首页整页嵌入 FIRE 计划之上形成重复欢迎区；保留有效信息不要求保留旧页面容器。

**Acceptance Criteria**

- **Case A — edit without confirm**：已确认 160 万，编辑草稿为 180 万后 rerun、切页、刷新／恢复 session，current pointer 和正式计算仍为 160 万，revision 数量不变。
- **Case B — confirm**：草稿 180 万并点击 Confirm 后只创建一个新 revision，pointer 指向新 revision，重启显示 180 万。
- **Case C — repeated rerun**：连续三次 Streamlit rerun 不增加 revision，也不改 pointer。
- **Case D — save failure**：确认新计划时注入 DB failure，旧 revision 仍可读，pointer 仍指向旧 revision，界面不显示保存成功。
- **Case E — restart**：保存后新建 AppTest／重启应用，完整方案与旧 Planner 逐月计算结果一致。
- 同会话先保存 11,000 元预算，再到资产页保存资产，重启后预算仍为 11,000 元；BASE-01 strict xfail 可删除。
- **Cases J–M — module hierarchy**：无正式计划及已有正式计划两种状态下，验证 FIRE 计划仅有三个工作页，无首页或同义概览；新会话和旧首页状态进入测算。从各工作页切到其他模块再返回，子页、草稿和身份保留，正式指针、修订数量及已保存草稿不变，非当前页面 renderer 和计划写服务未执行。

**Test Cases**

- `tests/test_existing_ui.py::test_saving_assets_does_not_revert_budget_saved_in_the_same_session`
- AppTest 覆盖 Cases A–E、页面切换、刷新、草稿取消、正式计划选择和无正式计划状态。
- `tests/test_planner_adapter.py` 覆盖旧字段到 snapshot、snapshot 到旧页面输入、stable ID 和 legacy_month 标记。
- M1-04 的 service transaction tests 在 UI 入口再次验证，确保 render 不隐式写入。
- 在 `tests/test_existing_ui.py` 补充 Cases J–M／技术 T25：精确检查三个工作页及默认路由，验证首页／概览入口不存在，非当前模块控件不存在；用调用记录验证未执行非当前页面和计划写服务。这些测试为待新增，不能用原 128 项通过替代。
- `test_original_pages_and_home_calculation_action` 应改为三个工作页与默认测算入口测试；其他测试中经首页按钮进入测算的辅助步骤改为新入口。原资产、预算、逐月结果、图表与保存恢复的断言继续保留，不通过删掉财务断言适配结构变化。

**导航修正执行顺序**

1. 调整 `app.py` 条件路由及导航层级：移除首页项及 renderer 调用，保留三个工作页 keys，定义默认测算及旧首页回退；调整 `ui/components.py` 调用边界，必要摘要／资料引导按 PRD 归入现有区域。
2. 在 `ui/planner_adapter.py` 或现有会话适配中保留局部页面位置与草稿，处理控件未渲染时的清理；不修改数据库结构或财务算法。
3. 补齐上述 AppTest，并运行原计算、保存及恢复回归；人工核对三个模块的导航和操作可见范围。
4. 通过后再更新 M1-05、A01、T25 和验收记录；届时同步开发计划、Checklist 与 README 的完成状态。本次文档修订不代表导航修复已交付。

## 7. Dependency Graph

```text
M1-01 legacy baseline
    ↓
M1-02 migrations / SQLite foundation
    ↓
M1-03 PlanSnapshot / PlanRevision model and repository
    ↓
M1-04 PlanService atomic save/select
    ↓
M1-05 planner_adapter + Draft boundary + UI recovery
    ↓
M1 exit gate: legacy regression + T19 plan migration + T24 + BASE-01
```

M1-02、M1-03 和 M1-04 可以分别单元测试，但不能跳过依赖的 schema 或 contract。M2 只能在 M1 exit gate 通过后开始；M1 不等待 AI、Actual 或 Forecast 接口。

## 8. Files to Create / Modify

### Files to Create

- `docs/implementation-spec.md`（本文件，已生成）
- `src/fire_planner/infrastructure/migrations.py`
- `src/fire_planner/domain/planning.py`
- `src/fire_planner/ui/planner_adapter.py`
- `tests/test_migrations.py`
- `tests/test_planning.py`
- `tests/test_plan_repository.py`
- `tests/test_plan_service.py`
- `tests/test_planner_adapter.py`
- `src/fire_planner/ui/components.py`（仅当参照栏／最小模块入口无法保持在现有页面和 `app.py` 内）

### Files to Modify

- `src/fire_planner/infrastructure/db.py`
- `src/fire_planner/infrastructure/repositories.py`
- `src/fire_planner/infrastructure/storage.py`
- `src/fire_planner/application/dto.py`
- `src/fire_planner/application/plan_service.py`
- `app.py`
- `src/fire_planner/ui/pages/home.py`
- `src/fire_planner/ui/pages/living.py`
- `src/fire_planner/ui/pages/assets.py`
- `src/fire_planner/ui/pages/calculation.py`
- `tests/test_storage.py`
- `tests/test_existing_ui.py`

### Files to Preserve

以下文件的现有行为必须保持；只有为调用 adapter 而做的最小导入／边界接线允许修改：

- `src/fire_planner/domain/forecast.py`
- `src/fire_planner/domain/scenario.py`
- `src/fire_planner/domain/budget.py`
- `src/fire_planner/domain/money.py`
- `src/fire_planner/domain/validation.py`
- `src/fire_planner/domain/stress_test.py`
- `src/fire_planner/ui/charts.py`
- `src/fire_planner/ui/formatters.py`
- 现有 `tests/test_budget.py`、`test_forecast.py`、`test_models.py`、`test_money.py`、`test_scenario.py`、`test_stress_test.py`、`test_validation.py` 的既有断言

### Files Out of Scope

M1 不创建或实现：

- `src/fire_planner/domain/actuals.py`、`projection.py`、`purchase.py`
- `src/fire_planner/application/actual_service.py`、`context_service.py`、`forecast_service.py`、`chat_service.py`
- `src/fire_planner/infrastructure/ai_gateway.py`
- `src/fire_planner/ui/pages/actuals.py`、`purchase_chat.py`
- `actual_month_revisions`、`forecast_runs`、`conversations`、`messages`、`analysis_runs`、`command_receipts` 表
- MonthlyActualRevision、ActualService、ContextVersion、ForecastService、PurchaseChange、Conversation、AI、metric_ref、stale／retry／output repair、Golden Scenario 全量 E2E、分布式锁、微服务或通用 event sourcing

## 9. Files That Must Not Be Modified

V0.7 的明确例外：可以修改 `app.py` 的首页路由、`home.py` 接线和首页入口相关 UI 测试，以落实三个工作页结构；相应功能信息按 PRD 归置。该例外不允许改变下面的领域算法、金额预期或日期语义。

除 M1-05 明确的最小兼容接线外，不得修改以下文件的业务行为或断言：

- `src/fire_planner/domain/forecast.py`、`src/fire_planner/domain/scenario.py`、`src/fire_planner/domain/money.py`、`src/fire_planner/domain/budget.py`、`src/fire_planner/domain/validation.py`
- `src/fire_planner/ui/charts.py`、`src/fire_planner/ui/formatters.py`
- 现有 Planner 计算和页面测试的输入、预期数字、日期语义及方案交互
- Technical Design 所列的 M2–M5 文件和表（不得以空壳文件满足目录完整性）

禁止通过禁用保存按钮、改变原表单交互、隐藏 xfail 或修改期望值来规避 BASE-01。

## 10. Acceptance Criteria

M1 的验收证据必须同时证明：

1. 空库和旧 `form_state` 库都能完成当前迁移，重复迁移幂等，未知新版拒绝降级，迁移失败回滚。
2. `PlanSnapshot` 包含一次完整测算所需的预算、资产、负债、日期、假设、收入、事件、所有方案和选定方案，并通过单位／schema 校验。
3. `PlanRevision` 创建后不可变；新计划通过新 revision 表达，旧 revision 可追溯。
4. 只有明确 Confirm 创建 revision；rerun、切页、刷新、session 恢复和草稿保存都不创建 revision。
5. `app_state.current_plan_revision_id` 唯一、可空且始终指向存在的 revision；选定 scenario 属于该 revision。
6. revision 插入和 current pointer 更新同事务；注入失败后旧计划仍然可读且指针不变。
7. 重新启动后正式计划、全部方案和 legacy 计算结果恢复一致。
8. BASE-01 通过，三个工作页的表单行为、旧图表、原公式及财务测试均无回归；首页入口相关 UI 断言按新需求调整。
9. 不需要 AI 配置，不创建 M2–M5 业务写入或服务。
10. FIRE 计划仅有三个工作页及模块内计划管理，无首页或同义概览入口；新会话和旧首页状态进入测算。其他模块不运行 Planner renderer 或计划写服务；切换返回保留上次工作页及完整草稿，T25 通过。

## 11. Test Cases

| Case | Setup / action | Expected result | Traceability |
| --- | --- | --- | --- |
| A | Confirmed plan = 160w；编辑 draft = 180w；rerun、page switch、reload | current confirmed plan 仍为 160w；revision count 和 pointer 不变 | PRD A01、Technical T24 |
| B | Draft = 180w；显式 Confirm | 恰好一个新 `PlanRevision`；pointer 指向新 revision；旧 revision 不变 | PRD P0-1/A01、Technical 4.5 |
| C | 连续三次 Streamlit rerun | revision count 不变；无重复插入 | PRD A01、Technical T24 |
| D | 旧 revision #1；Confirm 新计划并注入 DB failure | pointer 仍为 #1；旧计划仍可读；UI 不显示成功 | PRD A14、Technical T24 |
| E | Confirm 后关闭并重新启动应用 | 同一 confirmed snapshot、scenario 和 Planner 逐月结果恢复 | PRD A01/A04、Technical T01 |
| F | 旧库含 `form_state`；运行迁移两次 | 原 key/value 保留；无重复迁移／导入 | PRD A14、Technical T19 |
| G | 迁移中途异常或 schema version 高于当前 | rollback／可读错误；不降级、不损坏旧库 | PRD A14、Technical T19 |
| H | 同会话先保存预算再保存资产 | 后一次保存不覆盖前一次预算；严格 xfail 删除并通过 | PRD A01/A14、`regression-baseline.md` BASE-01 |
| I | 复现既有 12% 收益、退出当月收入、负余额 fixture | 逐月结果、`ROUND_HALF_UP`、负余额收益为零与基线一致 | PRD P0-1、Technical T01 |
| J | 无正式计划；依次进入 FIRE 计划、实际收支、消费判断 | FIRE 计划仅显示生活、资产、测算三个子页入口；所有模块均无首页／概览入口；其他模块仅显示待开发及可选只读摘要，无计划编辑控件，不要求先确认计划 | PRD A01、Technical T25 |
| K | 已确认计划且有未确认编辑；从每个 FIRE 子页分别切到另外两个模块，再返回 | 非 FIRE 模块没有子导航、草稿方案、确认／取消及历史选择控件；返回恢复上次子页、输入及 UUID；正式指针、修订数和 form_state 不变 | PRD A01、Technical T24/T25 |
| L | 记录 renderer 与计划写服务调用；在其他模块重复 rerun 后返回 FIRE 计划 | 其他模块不调用任何原页面 renderer、`save_reference` 或 `select_reference`；返回只渲染选中的原页面，不自动确认 | PRD A01、Technical T25 |
| M | 新建会话；或带旧 `selected_page = 首页` 的会话重新运行；分别有／无正式计划 | 进入 FIRE 计划时展示开始测算，不渲染 home；缺失资料有对应工作页入口，默认值仍为草稿；不创建修订、不写 form_state、不改变正式指针；合法的上次工作页不被默认值覆盖 | PRD A01、Technical T25 |

实现前和实现后都必须运行同一 legacy 测试集合；新增测试必须使用临时 SQLite 路径和固定 fixture。无法在缺失依赖的环境中执行的测试必须明确标记为未验证，不能宣称通过。

## 12. M1 Definition of Done

- [ ] FIRE 计划仅含生活、资产、测算三个工作页，移除首页层级；默认路由、条件渲染及 PRD A01／Technical T25 验收通过。
- [x] Draft 与 Confirmed Plan 明确分离，`form_state` 没有成为第二个正式来源。
- [x] `PlanSnapshot`、`PlanRevision` 和 UUID／单位／schema 校验已实现。
- [x] `plan_revisions` 正确持久化，`app_state.current_plan_revision_id` 正确指向当前计划。
- [x] Confirm 是唯一创建 revision 的正式入口；PlanRevision immutable。
- [x] Confirm transaction atomic；DB failure 不破坏旧计划。
- [x] 旧库迁移、备份、重复迁移、未知新版拒绝和失败回滚有测试证据。
- [x] 重启恢复完整 confirmed plan、全部方案和选定 scenario。
- [x] BASE-01 修复；既有 Planner 计算、页面和图表行为不变。
- [ ] legacy 财务回归与新 UI 测试均通过（既有 128 项已通过；首页相关 UI 测试待调整，新增 Cases J–M／T25 待实现与验证）。
- [x] 没有 M2/M3/M4/M5 实现泄漏，没有第二个正式计划来源。

## 13. Out of Scope

以下内容即使 Technical Design 已描述，也必须留到后续里程碑：

- M2：`MonthlyActualRevision`、实际页面、actual ledger/history、comparison baseline、资产观测用于预测、实际幂等和 version conflict。
- M3：`ContextService`、`ContextVersion`、`ForecastService`、Actual → Forecast 重跑、退出规则扫描、conditional／needs_input／stale 预测状态。
- M4：Purchase comparison、`PurchaseChange`、Conversation、ChatService、AiGateway、AI extraction／explanation、`metric_ref`、AI retry／invalid output。
- M5：Golden Scenario 全量 E2E、完整三模块集成、生产 hardening、外部部署。
- 任何 universal command bus、distributed lock、provider failover、generic schema conversion、generic event sourcing、microservices 或 frontend/backend split。

## 14. Source of Truth

| Data | Source of Truth | Writer |
| --- | --- | --- |
| Draft | `session_state` / compatibility `form_state` | UI 草稿保存适配 |
| Confirmed Plan | `plan_revisions` | `PlanService.save_reference` |
| Current Plan | `app_state.current_plan_revision_id` | `PlanService.save_reference` / `select_reference` |
| Financial calculation | 现有 `domain/forecast.py`、`domain/scenario.py` 计算路径 | Domain / planner adapter 仅提供输入 |
| Actuals | M2，不属于当前 scope | — |
| Forecast | M3，不属于当前 scope | — |
| Purchase | M4，不属于当前 scope | — |
| AI explanation | M4，不属于当前 scope | — |

任何新代码都不能再引入一个“当前正式计划”字段、表或 session key。正式服务只沿 current pointer 读取；草稿差异必须显式标注。

## 15. Task → Acceptance → Test → PRD Mapping

| Implementation task | Acceptance evidence | Test evidence | PRD requirement |
| --- | --- | --- | --- |
| M1-01 | Legacy 页面、公式、逐月值与图表不变 | Existing planner/UI regression suite | A01、P0-1 |
| M1-02 | 旧库安全迁移、备份、幂等、失败回滚、未知版本拒绝 | `test_migrations.py`、T19 计划迁移部分 | A14、P0-5 |
| M1-03 | 完整快照 round-trip、单位和 stable identity 正确 | `test_planning.py`、`test_plan_repository.py` | A01、P0-1 |
| M1-04 | Confirm 唯一入口、immutable revision、单指针、atomic rollback | `test_plan_service.py`、T24 | A01、A14、P0-1/P0-5 |
| M1-05 | 草稿隔离、重启恢复、BASE-01 通过；三个工作页、无首页、默认测算及模块内计划操作；跨模块草稿保留，结构部分待修正 | AppTest Cases J–M／T25 待新增；首页入口 UI 断言待调整；保留 adapter 与财务回归 | A01、A04、A14、P0-1/P0-5 |

如果实现过程中出现无法对应 PRD、Technical Design 或本表的新增任务，应先登记为 scope risk，并暂停扩大 M1；不能通过“future-ready”理由自动加入。

## 16. Open Issues / Baseline Conflicts

当前问题 NAV-01：`app.py` 无条件渲染四页导航，`render_reference_controls` 在全部模块调用，导致 FIRE 计划编辑控件泄漏到其他模块；NAV-02：直接把原首页纳入 FIRE 计划，形成没有独立任务的多余层级。按 PRD V0.7 的三个工作页结构、M1-05 路由／状态规则及 T25 修正；完成前不能认定 M1 页面层级验收通过。以下表格保留原实施前问题记录，不代表这些历史问题仍全部存在。

| Conflict | Impact | Recommended minimal resolution | Can implementation proceed? |
| --- | --- | --- | --- |
| Technical Design 规划了完整对象和目录，但实际 `application/*.py`、`infrastructure/db.py`、`repositories.py` 只有占位说明。 | 不能直接调用所述 API；M1 必须先落地最小实现。 | 按 M1-02～M1-04 逐步创建本规格列出的文件和接口，不创建未来模块空壳。 | Yes, after M1-01 baseline. |
| Technical Design 的相对路径写作 `ui/pages/...`，实际代码位于 `src/fire_planner/ui/pages/...`。 | Coding Agent 可能修改错误路径。 | 以当前仓库 `src/` 布局为准；本规格所有文件路径均使用实际路径。 | Yes. |
| 当前 `storage.py` 把整个 session 全量写回 `form_state`，已知会触发 BASE-01。 | 跨页保存会回滚刚保存的预算，破坏兼容性。 | M1-05 使用页面范围保存或读改写合并，保留旧键和值，并把严格 xfail 转为通过。 | Yes, blocked until M1-05 for exit. |
| 旧页面方案 ID 为位置字符串，Technical Design 要求 UUID。 | 直接复用会导致删除／重排后的身份不稳定。 | snapshot 内生成稳定 UUID；保留“节点 N”作为 display label，并在 adapter 中维护映射。 | Yes. |
| 现有测算参数和方案尚未持久化，且起点按整月处理。 | 无法声称重启恢复完整正式计划或支持真实日终截点。 | M1 快照明确保存 `legacy_month` 语义和全部输入；真实资产截点留给 M3。 | Yes. |
| 当前执行环境未安装 `streamlit`，本次 `pytest -q` 在收集阶段失败。 | 本次无法重新验证 77/1 基线。 | 按 README 安装 `.[dev]` 后再执行 M1-01；不要修改代码绕过导入。 | Yes, with dependency setup. |
