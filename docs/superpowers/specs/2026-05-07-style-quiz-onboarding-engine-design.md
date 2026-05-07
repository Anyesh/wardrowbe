# Style Quiz Onboarding Engine 设计文档

- 日期：2026-05-07
- 项目：wardrowbe（miniapp + backend）
- 状态：已评审（待实现）
- 负责人：产品/研发协同

## 1. 背景与目标

### 1.1 背景
当前系统已有 `preferences`、`onboarding_completed`、以及设置页基础编辑能力，但缺少“新用户首次进入时的风格偏好测评流程”。现有偏好采集分散，无法形成统一可扩展的引导框架。

### 1.2 本次目标
1. 新用户首次进入小程序时，触发**强制弹窗式 style-quiz 流程**。
2. 测评完成后，结果直接写入现有 `preferences` 字段（不新增偏好主表）。
3. 结果由“规则映射为主 + AI 文案解释为辅”。
4. 后续用户可在 `settings` 页面修改 **全部** `preferences` 字段。
5. 方案需可扩展为通用 Onboarding Engine，支持后续增加新步骤。

### 1.3 非目标
- 不在本期引入复杂推荐重训流程。
- 不重构现有推荐主链路。
- 不替换现有 `/users/me/preferences` 接口契约。

---

## 2. 需求确认摘要（来自本轮确认）

- 首次触发策略：**强制完成**（未完成不可进入主流程）。
- 题型：**5~7 道快速题**。
- 偏好落库：**直接映射现有 preferences**。
- 入口形态：**新用户进来弹窗 style-quiz 流程**。
- 结果生成：**规则映射主导，AI 仅生成解释文案**。
- 后续编辑：`settings` 页面支持修改 **所有 preferences 字段**。
- 方案选择：**C（全局引导框架）**。

---

## 3. 总体方案（Onboarding Engine）

### 3.1 分层
1. **前端引导层（MiniApp）**
   - 启动时检查 onboarding 状态。
   - 若有 mandatory 且 pending 步骤，弹出阻塞式 quiz。
2. **后端编排层（Onboarding Orchestrator）**
   - 统一返回步骤状态、处理提交、推进状态机。
3. **偏好映射层（Preference Mapper）**
   - 统一执行“答案 -> PreferenceUpdate”。
4. **解释生成层（AI Insight）**
   - 使用映射结果生成风格解释文案，失败时降级模板文案。

### 3.2 设计原则
- 规则只在后端定义，前端只负责展示和采集。
- onboarding 过程状态与偏好主数据解耦。
- 对历史/审计友好（保留答题与结果快照）。
- 失败可降级，不阻断关键路径（尤其 AI 调用失败）。

---

## 4. 数据模型设计

在不修改 `user_preferences` 主体结构的前提下，新增引导域模型。

### 4.1 user_onboarding_states
- `user_id` (PK, FK -> users.id)
- `current_version` (string, default `v1`)
- `is_blocking` (bool)
- `created_at`
- `updated_at`

用途：描述当前用户是否被引导阻塞，以及使用的引导版本。

### 4.2 user_onboarding_steps
- `id` (UUID, PK)
- `user_id` (FK -> users.id)
- `step_key` (string, e.g. `style_quiz`)
- `status` (`pending|completed|skipped`)
- `answers_json` (JSONB)
- `result_json` (JSONB)
- `completed_at` (nullable)
- `created_at`
- `updated_at`

约束建议：
- `(user_id, step_key)` 唯一键。

---

## 5. 后端接口设计（/api/v1/onboarding）

### 5.1 GET /api/v1/onboarding/state
返回当前引导状态：
- `is_blocking`
- `current_version`
- `current_step`
- `active_steps[]`
- `completed_steps[]`

### 5.2 GET /api/v1/onboarding/steps/style-quiz
返回题目定义（由后端维护）：
- 问题列表（5~7）
- 选项
- 必填标识
- 版本号

前端据此渲染，不内嵌业务映射。

### 5.3 POST /api/v1/onboarding/steps/style-quiz/submit
输入：
- `answers`（结构化答题）
- `quiz_version`

处理流程：
1. 校验题目完整性与选项合法性。
2. 规则映射生成 `PreferenceUpdate`。
3. 调用现有 `PreferenceService.update_preferences` 更新偏好。
4. 调用 AI 生成解释文案（失败降级）。
5. 写入 `answers_json/result_json`，更新 step=completed。
6. 若 mandatory 步骤全部完成：
   - `users.onboarding_completed=true`
   - `user_onboarding_states.is_blocking=false`

输出：
- `updated_preferences`
- `style_insight`
- `next_step`（当前版本下通常为空）

### 5.4 兼容策略
- 保留现有 `POST /users/me/onboarding/complete`（兼容旧路径）。
- 新路径由 Orchestrator 自动置位 `onboarding_completed`。

---

## 6. 题目与规则映射

## 6.1 题目集（首版 6 题）
1. 常见穿衣场景（通勤/休闲/运动/约会/正式）
2. 风格倾向（极简/休闲/正式/运动/个性）
3. 色彩偏好（低饱和/中性/亮色）
4. 想避免的颜色（可多选）
5. 体感偏好（怕冷/正常/怕热）
6. 穿搭变化偏好（稳定/适中/多变化）

### 6.2 映射目标字段
- `style_profile`
- `default_occasion`
- `color_favorites`
- `color_avoid`
- `temperature_sensitivity`
- `layering_preference`
- `variety_level`

### 6.3 映射规则
- style 维度：每题对命中维度加权，最终值 clamp 到 0~100。
- default_occasion：由主场景题映射（如休闲 -> `casual`）。
- color 字段：去重，并复用现有“喜好/避免互斥清洗”。
- 体感题：映射 `temperature_sensitivity` 与 `layering_preference`。
- 变化偏好题：映射 `variety_level`。

### 6.4 幂等策略
- 同用户重复提交 `style_quiz` 时：覆盖最新答案与结果。
- `preferences` 以最新提交为准。

---

## 7. AI 解释文案策略

### 7.1 输入
- 映射后的结构化偏好（不是原始自由文本）。

### 7.2 输出
- 60~120 字中文风格画像文案。
- 用于 quiz 完成态展示与可选存档。

### 7.3 失败降级
- AI 超时/不可用时返回模板文案：
  - 基于 `style_profile` top2
  - + `color_favorites`
  - + `default_occasion`

降级不影响 onboarding 完成判定。

---

## 8. 小程序前端设计

### 8.1 全局 Onboarding Gate
在 `app.ts` 外层注入全局 Gate：
- App 启动、切前台、登录后刷新时查询 `/onboarding/state`。
- 若 `is_blocking=true`：显示阻塞弹窗并禁用底层交互。

### 8.2 StyleQuizModal
- 多步问答（上一题/下一题/进度条）
- 必填校验
- 强制流程：未提交前不可退出
- 提交后显示“风格画像”并关闭 gate

### 8.3 Settings 全字段编辑
`settings` 页面扩展覆盖所有 preferences 字段：
- 颜色喜好/规避
- style_profile 五维
- default_occasion
- 温度与层搭偏好
- repeat/variety 策略
- ai_endpoints

仍沿用 `PATCH /users/me/preferences`。

---

## 9. 测试策略

### 9.1 后端单测
- 状态机：pending -> completed 的切换。
- 提交校验：非法选项、缺失必填。
- 映射器：输入答案 -> 预期 PreferenceUpdate。
- AI 降级：模拟失败时仍返回可用结果。

### 9.2 前端联调
- 新用户首次登录：必弹窗 + 阻塞主流程。
- 完成 quiz 后：gate 解除。
- 老用户：不弹窗。
- settings 全字段保存回写正确。

### 9.3 回归重点
- 登录同步与 token 生命周期。
- 建议生成链路未受 onboarding 引入影响。

---

## 10. 发布与回滚

### 10.1 发布顺序
1. 后端（含 DB migration + onboarding API）
2. 小程序（Gate + Quiz + Settings 扩展）
3. 灰度验证新账号路径

### 10.2 回滚策略
- 后端按镜像 tag 回滚。
- 前端回退至上一版小程序体验版。
- 保留 onboarding 表，不删除历史数据。

---

## 11. 风险与缓解

1. **风险：强制流程影响新用户转化**
   - 缓解：题数控制在 5~7、总时长 <45 秒。
2. **风险：AI 不稳定影响体验**
   - 缓解：AI 仅文案增强，失败降级模板。
3. **风险：字段全量编辑复杂度高**
   - 缓解：分组展示、基础校验、逐步增强交互。
4. **风险：多端一致性**
   - 缓解：映射逻辑仅后端单点维护。

---

## 12. 验收标准（Definition of Done）

- 新用户首次进入必触发 style-quiz 阻塞流程。
- 未完成前不可进行主功能交互。
- 提交后 `preferences` 正确更新。
- `users.onboarding_completed` 被自动置为 `true`。
- 设置页可编辑并保存所有 `preferences` 字段。
- AI 服务异常不阻断 onboarding 完成。

---

## 13. 实现拆分建议（执行阶段）

- Block A：后端 onboarding 数据模型与 API
- Block B：映射器与 AI 文案器
- Block C：miniapp 全局 gate + quiz modal
- Block D：settings 全字段编辑
- Block E：测试、灰度、发布

