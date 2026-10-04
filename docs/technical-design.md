# 半 FIRE Planner 技术设计文档

**版本**：V1.0  
**状态**：MVP 实施基线  
**依据**：`半 FIRE Planner｜MVP 产品需求文档（PRD）V1.0`  
**技术形态**：Streamlit 单体应用 + Python 领域计算引擎 + SQLite

## 1. 技术目标

本系统帮助用户回答“按照目标生活方式，最早什么时候可以离开高强度工作”。MVP 的技术实现必须满足以下目标：

1. 输入真实的年度生活预算、金融资产、储蓄计划和离开后的主动收入。
2. 按月预测未来金融资产，并生成多个可选择的退出节点。
3. 在每个节点计算资产提款能力、主动收入、年度可支配资金和缺口。
4. 支持最多 3 个方案的对比，并展示“多工作几个月换来多少安全垫”。
5. 支持 0% 收益、资产一次性回撤、连续两年无主动收入和预算增加 20% 的压力测试。
6. 保证计算可重复、结果可解释，AI 和页面层不能自行改写计算结果。

MVP 不做投资推荐、自动交易、银行连接、税务规划、社保精算、房产估值和真实资产托管。

## 2. 技术决策

| 领域 | 决策 | 原因 |
| --- | --- | --- |
| UI | Streamlit | 快速验证个人工具，表单和图表开发成本低 |
| 计算 | 纯 Python 模块 | 便于单元测试、复用和未来接入 API 或 AI |
| 存储 | SQLite | 本地单用户、零运维，支持保存历史方案 |
| 图表 | Plotly | 支持资产折线、目标线、节点和悬浮明细 |
| 金额精度 | 以分为单位的整数存储，计算使用 `Decimal` | 避免浮点误差，保证金额可复核 |
| 日期粒度 | 月 | 与月净储蓄、月收入和退出节点保持一致 |
| 货币 | MVP 固定人民币 CNY | PRD 示例和用户输入均以人民币为主 |
| 部署 | 本地运行优先 | MVP 不需要用户账户和远端服务 |

## 3. 分层架构

```text
Streamlit 页面
    ↓ 表单 DTO / 页面状态
应用服务层
    ↓ 校验、编排、保存计算快照
领域计算引擎（无 Streamlit、无 SQLite 依赖）
    ↓ 结构化结果
SQLite Repository
    ↓
历史方案、输入快照、计算结果

Plotly 读取领域结果生成图表
```

### 3.1 目录建议

```text
fire_planner/
├── app.py
├── pyproject.toml
├── docs/
│   └── technical-design.md
├── src/fire_planner/
│   ├── domain/
│   │   ├── models.py
│   │   ├── money.py
│   │   ├── validation.py
│   │   ├── budget.py
│   │   ├── forecast.py
│   │   ├── scenario.py
│   │   └── stress_test.py
│   ├── application/
│   │   ├── plan_service.py
│   │   └── dto.py
│   ├── infrastructure/
│   │   ├── db.py
│   │   └── repositories.py
│   └── ui/
│       ├── pages/
│       ├── charts.py
│       └── formatters.py
└── tests/
    ├── test_budget.py
    ├── test_forecast.py
    ├── test_scenario.py
    └── test_stress_test.py
```

领域层只能依赖 Python 标准库。Streamlit、Plotly 和 SQLite 适配器放在外层，避免计算逻辑被页面状态或数据库耦合。

## 4. 领域概念与口径

### 4.1 金融资产

金融资产包括现金、银行存款、基金、股票和其他可用于规划的资产。它们的合计值是 `investable_assets`，用于提款能力计算。

自住房和其他非金融资产单独保存，只用于展示净资产信息，不计入半 FIRE 提款资产。房贷余额也不直接从金融资产中扣除；每月房贷还款必须计入生活预算，避免重复扣减。

### 4.2 生活预算

用户输入的是自己真正想要的年度生活预算，不区分“必要”和“享受”。月度项目乘以 12，年度项目按对应年份计入，旅行和搬家等一次性支出可以设置在具体年份。

```text
年度生活预算 = 月度项目合计 × 12
             + 年度项目合计
             + 当年一次性项目合计
```

系统不自动添加通胀。用户通过为不同年份建立不同预算表达预算变化。

### 4.3 资产预测

预测以 `as_of_date` 所在月份为起点，按月计算到规划结束月份。基础预测不假设投资收益，收益由压力测试显式表达。

```text
月末资产 = 上月末资产
         + 月净储蓄
         + 当月一次性收入
         - 当月一次性支出
```

其中月净储蓄已经代表常规收入减常规支出。一次性收入包括年终奖、赔偿和股票兑现，一次性支出包括旅行、搬家和大额消费。

退出月份的资产定义为该月计划收入、一次性事件完成后的月末资产。退出月份发生的事件需要在输入中明确归属该月，不能按天拆分。

### 4.4 半 FIRE 快照判定

对某个退出方案，系统先计算年度可支配资金：

```text
年度提款能力 = 退出金融资产 × 规划提款率
年度主动收入 = 半 FIRE 后月收入 × 12 + 年度额外收入
年度可支配资金 = 年度提款能力 + 年度主动收入
年度缺口 = 年度生活预算 - 年度可支配资金
覆盖率 = 年度可支配资金 / 年度生活预算
```

规划提款率默认为 3.5%，可由用户修改。它表示长期规划参数，不表示投资产品收益保证。

完全 FIRE 参考值为：

```text
完全 FIRE 参考资产 = 年度生活预算 / 规划提款率
```

该值只作为参考线，不改变半 FIRE 判定。

### 4.5 状态等级

状态计算必须是确定性的：

| 状态 | 条件 |
| --- | --- |
| `green` 可行 | `年度缺口 <= 0` |
| `yellow` 接近 | `0 < 年度缺口 <= 年度生活预算 × 5%` |
| `orange` 有明显缺口 | 缺口超过 5%，但规划中存在可通过延后退出或调整收入解决的候选节点 |
| `red` 暂不可行 | 缺口超过 5%，且当前规划范围内没有可行候选节点 |

橙色需要同时返回 `required_monthly_income` 和 `next_feasible_exit_month`，否则降为红色。页面不得仅凭颜色做主观判断。

## 5. 核心数据模型

以下模型是领域层的逻辑模型，金额字段在 Python 中使用 `Decimal`，落库时使用整数分。

### 5.1 Plan

```python
Plan:
    id: str
    name: str
    currency: Literal["CNY"]
    as_of_date: date
    current_monthly_saving_cents: int
    withdrawal_rate_bps: int = 350
    planning_end_month: YearMonth
    created_at: datetime
    updated_at: datetime
```

`withdrawal_rate_bps=350` 表示 3.50%。规划结束月份默认为退出候选范围最后一个月，MVP 默认不超过起始月份后 120 个月。

### 5.2 AssetHolding

```python
AssetHolding:
    id: str
    plan_id: str
    asset_type: Literal["cash", "bank_deposit", "fund", "stock", "other_financial"]
    amount_cents: int
    included_in_fire_assets: bool = True
    note: str | None
```

### 5.3 NonFinancialAsset 和 Liability

```python
NonFinancialAsset:
    id: str
    plan_id: str
    asset_type: Literal["primary_residence", "other_property", "other"]
    estimated_value_cents: int
    note: str | None

Liability:
    id: str
    plan_id: str
    liability_type: Literal["mortgage", "other"]
    balance_cents: int
    monthly_payment_cents: int
    annual_interest_rate_bps: int | None
    remaining_months: int | None
```

非金融资产和负债不会自动改变 FIRE 资产。若房贷月供没有包含在生活预算中，应用服务层必须提示用户补充预算项目。

### 5.4 BudgetItem

```python
BudgetItem:
    id: str
    plan_id: str
    year: int
    category: str
    cadence: Literal["monthly", "annual", "one_off"]
    amount_cents: int
    note: str | None
```

同一计划、年份、分类和频率可只保留一条记录。自定义分类使用 `category` 字符串保存，页面提供预设分类：房贷、吃饭、水电、保险医疗、日用品、交通、兴趣、旅行、娱乐社交、其他。

### 5.5 AssetEvent

```python
AssetEvent:
    id: str
    plan_id: str
    event_month: YearMonth
    event_type: Literal["annual_bonus", "severance", "stock_vesting", "other_income", "extra_expense"]
    amount_cents: int
    note: str | None
```

收入事件使用正数，支出事件也保存为正数，由预测引擎按 `event_type` 决定加减，避免用户输入负号造成重复减法。

### 5.6 Scenario

```python
Scenario:
    id: str
    plan_id: str
    name: str
    exit_month: YearMonth
    post_fire_monthly_income_cents: int
    post_fire_annual_income_cents: int = 0
    enabled: bool = True
```

每个计划最多同时启用 3 个方案。退出月份必须落在资产预测时间线内。

### 5.7 CalculationResult

```python
ScenarioResult:
    scenario_id: str
    exit_assets_cents: int
    annual_budget_cents: int
    annual_withdrawal_capacity_cents: int
    annual_active_income_cents: int
    annual_available_cents: int
    annual_gap_cents: int
    coverage_ratio: Decimal
    status: Literal["green", "yellow", "orange", "red"]
    required_monthly_income_cents: int
    next_feasible_exit_month: YearMonth | None
```

计算结果还应保留 `input_hash`、`engine_version` 和 `calculated_at`，这样历史结果可追溯，代码升级后不会误认为旧结果由新口径计算。

## 6. SQLite 数据库设计

数据库文件默认放在用户数据目录，不提交到 Git。首次启动时执行版本化迁移。

### 6.1 `plans`

```sql
CREATE TABLE plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'CNY'),
    as_of_date TEXT NOT NULL,
    current_monthly_saving_cents INTEGER NOT NULL CHECK (current_monthly_saving_cents >= 0),
    withdrawal_rate_bps INTEGER NOT NULL CHECK (withdrawal_rate_bps > 0 AND withdrawal_rate_bps <= 10000),
    planning_end_month TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 6.2 其他表

```sql
CREATE TABLE asset_holdings (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    included_in_fire_assets INTEGER NOT NULL DEFAULT 1,
    note TEXT
);

CREATE TABLE non_financial_assets (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    estimated_value_cents INTEGER NOT NULL CHECK (estimated_value_cents >= 0),
    note TEXT
);

CREATE TABLE liabilities (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    liability_type TEXT NOT NULL,
    balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0),
    monthly_payment_cents INTEGER NOT NULL CHECK (monthly_payment_cents >= 0),
    annual_interest_rate_bps INTEGER,
    remaining_months INTEGER,
    note TEXT
);

CREATE TABLE budget_items (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    category TEXT NOT NULL,
    cadence TEXT NOT NULL CHECK (cadence IN ('monthly', 'annual', 'one_off')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    note TEXT
);

CREATE TABLE asset_events (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    event_month TEXT NOT NULL,
    event_type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    note TEXT
);

CREATE TABLE scenarios (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    exit_month TEXT NOT NULL,
    post_fire_monthly_income_cents INTEGER NOT NULL CHECK (post_fire_monthly_income_cents >= 0),
    post_fire_annual_income_cents INTEGER NOT NULL DEFAULT 0 CHECK (post_fire_annual_income_cents >= 0),
    enabled INTEGER NOT NULL DEFAULT 1
);
```

### 6.3 计算快照

```sql
CREATE TABLE calculation_runs (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    engine_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    input_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL
);
```

结果以 JSON 保存是为了保留完整的时间线和压力测试明细；页面读取最新有效快照，用户修改任意输入后必须重新计算。

## 7. 计算引擎接口

### 7.1 资产预测

```python
def forecast_assets(
    *,
    initial_assets_cents: int,
    as_of_month: YearMonth,
    end_month: YearMonth,
    monthly_saving_cents: int,
    events: Sequence[AssetEvent],
) -> list[AssetPoint]:
    """返回每个月月末资产，基础预测不包含投资收益。"""
```

每个月必须返回：月份、月初资产、常规储蓄、一次性收入、一次性支出、月末资产。若月末资产小于 0，仍保留该点并标记 `is_negative=True`，不能静默截断为 0。

### 7.2 预算计算

```python
def calculate_annual_budget(
    *,
    budget_items: Sequence[BudgetItem],
    year: int,
) -> AnnualBudget:
```

`AnnualBudget` 至少包含总额和按分类的明细。分类明细用于方案解释和“提高旅行预算后节点后移”的洞察。

### 7.3 方案计算

```python
def evaluate_scenario(
    *,
    scenario: Scenario,
    exit_assets_cents: int,
    annual_budget_cents: int,
    withdrawal_rate_bps: int,
    candidate_results: Sequence[ScenarioResult] = (),
) -> ScenarioResult:
```

所有金额计算使用整数分或 `Decimal`，最后由展示层转换为元和“万”。状态函数不得读取 UI 文本或颜色。

### 7.4 所需资产和收入

为了给用户可操作的调整方向，增加两个反推函数：

```python
def required_assets_for_budget(
    *, annual_budget_cents: int,
    annual_active_income_cents: int,
    withdrawal_rate_bps: int,
) -> int:

def required_monthly_income(
    *,
    annual_budget_cents: int,
    exit_assets_cents: int,
    withdrawal_rate_bps: int,
) -> int:
```

结果向上取整到 1 分，页面展示时再向上取整到元，避免把不足误显示为充足。

## 8. 压力测试设计

压力测试不改变用户保存的基础方案，只创建临时计算上下文。MVP 预置以下四种场景：

| 场景 | 参数变化 | 判定 |
| --- | --- | --- |
| 零收益 | 年化组合收益率 0% | 24 个月资产是否非负、每年缺口是否可覆盖 |
| 资产回撤 | 退出月份月初施加一次 -20% 资产冲击，之后收益率 0% | 回撤后是否仍满足提款率约束 |
| 两年无主动收入 | 退出后前 24 个月主动收入为 0 | 24 个月内是否出现资金耗尽或超额提款 |
| 预算上升 | 所有退出后年度预算乘以 1.20 | 是否仍有可覆盖方案 |

压力测试采用逐月现金流模型：

```text
月末资产 = 月初资产 × (1 + 月收益率)
         + 主动收入
         - 生活预算 / 12
```

每个月额外返回：可用提款上限、实际需要从资产支付的金额、当月缺口和资产余额。若实际需要从资产支付的年度化金额超过 `资产 × 规划提款率`，标记 `withdrawal_rate_exceeded=True`。这一步与方案首页的年度快照区分开：快照回答“长期能力”，压力测试回答“在指定冲击下能否撑住”。

## 9. Streamlit 页面与交互

### 9.1 首页：半 FIRE 状态

展示最新有效计算结果：

- 最早可行节点
- 更平衡节点
- 高安全节点
- 当前年度生活预算
- 半 FIRE 后目标收入
- 推荐资产目标
- 完全 FIRE 参考值

所有结论必须链接到对应方案详情。没有有效输入时展示缺失项列表，不展示伪造的默认结论。

### 9.2 Page 1：我的生活

- 编辑预设和自定义预算分类。
- 选择月度、年度或一次性项目。
- 按年份复制或修改预算。
- 实时显示年度总预算和分类汇总。
- 金额不能为负；空分类不参与计算。

### 9.3 Page 2：我的资产

- 编辑五类金融资产。
- 单独编辑自住房、其他房产和负债。
- 明确显示“可提款金融资产”和“非金融资产”。
- 房贷月供提供“一键加入生活预算”的操作，默认不自动加入，避免隐式修改。

### 9.4 Page 3：我的资产增长

- 编辑当前月净储蓄、规划提款率和预测结束月份。
- 添加年终奖、赔偿、股票兑现、旅行和大额支出。
- 展示月末资产时间线。
- 允许点击时间线节点创建退出方案。

### 9.5 Page 4：我的方案

- 显示所有候选节点。
- 最多勾选 3 个方案进入对比。
- 每个方案显示资产、提款能力、主动收入、可支配资金、预算、缺口、覆盖率和状态。
- 显示所需月收入、所需资产和下一可行月份。

### 9.6 Page 5：FIRE 跑道

Plotly 图表至少包含：

1. 月末金融资产预测线。
2. 退出节点标记。
3. 根据当年预算计算的半 FIRE 目标资产线。
4. 完全 FIRE 参考线。
5. 资产小于 0 时的危险区段。

点击节点后显示该节点的完整 `ScenarioResult`。图表数据来自领域结果，不在 Plotly 回调中重新计算。

## 10. 应用服务流程

用户点击“保存并计算”时执行以下流程：

1. 从页面状态组装 `PlanInput`。
2. 执行字段、金额、日期和业务规则校验。
3. 汇总金融资产并生成月度资产时间线。
4. 计算每个启用退出方案的年度预算和半 FIRE 结果。
5. 计算完全 FIRE 参考值、下一可行节点和洞察数据。
6. 执行四组压力测试。
7. 计算输入 JSON 的稳定哈希，保存输入和结果快照。
8. 更新页面状态，显示结果和需要用户处理的警告。

用户修改任意输入后，旧结果标记为过期，直到重新计算前首页显示“结果需要更新”。

## 11. 校验与错误处理

### 11.1 输入校验

- 金额必须是非负数，且不超过 `10^12` 分。
- 月净储蓄、主动收入和一次性收入不能使用负数；支出通过事件类型表达。
- 提款率必须大于 0 且不超过 100%。
- 规划结束月份不早于 `as_of_date` 所在月份。
- 退出月份必须在预测范围内。
- 年份必须在 1900 到 2200 之间。
- 同一方案最多启用 3 个对比方案。
- 未输入生活预算时禁止生成“可行”状态。

### 11.2 警告

- 自住房被排除在 FIRE 资产之外。
- 房贷余额存在但月供未加入预算。
- 当前资产或预测资产为负。
- 方案依赖超过 3.5% 的提款率。
- 结果覆盖率低于 95%。

### 11.3 失败处理

领域计算失败时返回结构化错误，不显示部分旧结果。数据库写入使用事务；快照写入失败不能覆盖上一次有效快照。

## 12. 安全与隐私

MVP 默认只在本机保存数据，不上传银行信息，不调用外部财务服务。数据库文件不应提交到 Git，仓库应提供忽略规则：

```gitignore
*.sqlite3
*.db
.streamlit/secrets.toml
```

导出功能如在后续版本加入，应明确提示导出文件包含个人财务数据。AI 功能（V2）只能读取结构化计算结果，不能绕过计算引擎直接生成资产和收入数字。

## 13. 测试策略

### 13.1 单元测试

- 月度储蓄、一次性收入和一次性支出按月份正确累计。
- 月度、年度和一次性预算的年度汇总正确。
- 3.5% 提款率计算精确到分。
- 缺口边界分别覆盖 0、5% 和超过 5%。
- 资产不足时不被截断为 0。
- 退出月份事件包含在退出资产中。
- 完全 FIRE 参考值使用同一年度预算和提款率。
- 压力测试能识别资产耗尽和提款率超限。

### 13.2 验收样例

输入：

```text
当前金融资产：125 万
月净储蓄：3 万
年终奖：10 万
赔偿：20 万
半 FIRE 后月收入：5000
年度生活预算：12 万
规划提款率：3.5%
```

引擎必须能够：

1. 计算未来每个月的资产。
2. 生成至少两个不同退出月份的候选节点。
3. 计算每个节点的退出资产和年度可支配资金。
4. 输出缺口、覆盖率和状态等级。
5. 生成最多 3 个方案的对比结果。
6. 运行四种压力测试并返回逐月结果。
7. 为 FIRE 跑道图提供完整的月度序列。

### 13.3 属性测试方向

- 增加月净储蓄不会降低同一退出月份的基础预测资产。
- 增加生活预算不会提高覆盖率。
- 提高主动收入不会降低年度可支配资金。
- 在其他输入不变时，提高提款率不会降低提款能力。
- 方案排序按退出月份递增且稳定。

## 14. 可观测性与可追溯性

MVP 不接入远端监控，但每次计算记录：

- `engine_version`
- `input_hash`
- 计算时间
- 计划 ID
- 结果状态和警告数量

开发环境记录异常堆栈，用户界面只展示可理解的错误信息。日志不得输出完整资产明细或数据库路径之外的敏感数据。

## 15. 实施顺序

1. 建立 Python 包、金额类型、月份类型和基础领域模型。
2. 实现预算汇总和月度资产预测，并为公式补齐单元测试。
3. 实现方案判定、反推指标和压力测试。
4. 建立 SQLite 迁移与 Repository，保存计划和计算快照。
5. 实现 Streamlit 的生活、资产和资产增长页面。
6. 实现方案对比、FIRE 跑道图和首页结论。
7. 使用验收样例进行端到端验证，补充输入校验和警告。
8. 增加本地运行说明、数据库忽略规则和导出前的隐私提示。

## 16. 后续演进边界

V2 的 FIRE Copilot 通过结构化工具调用以下接口：

```text
get_current_plan()
simulate_change(change_set)
compare_scenarios(scenario_ids)
run_stress_test(test_id)
```

模型只能负责理解自然语言、构造参数和解释结果；所有金额、月份、状态和缺口必须由领域计算引擎返回。未来若拆分后端，优先把当前 `application` 层封装为 API，领域层和 SQLite 快照格式保持不变。
