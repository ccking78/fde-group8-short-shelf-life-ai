# 经典牛肉堡：等待补齐事实，暂不形成可采纳数量

- **status：blocked（阻断）**
- **product：B01／经典牛肉堡**
- **action：请求店长补齐并核实制作耗时，补齐事实后重新调用工具形成新计划，再交制作岗位确认。**
- **quantity：null（未提供可采纳数量，亦未建议维持为零）**

## evidence：事实、预测与假设

1. **观察事实**：`input.csv` 的 S1 为课堂模拟快照，在手 12 个、已预留 5 个、不可分配 0 个；`p1_missing-T01`（inspect）实际返回可分配量 7 个。0 是有效数值，已接订单已全部预留，不再计入新增需求。来源为 S1，工具规则为 `sim-rule-1`，没有后备配置。
2. **关键字段缺失**：S1 的 `prep_minutes` 为空；`p1_missing-T01` 返回 `status=blocked`、`missing_fields=[prep_minutes]`、`invalid_fields=[]`，核实角色为店长。现有 `sellable_minutes=30`、`batch_age_minutes=2` 和 `window_minutes=20` 不能替代制作耗时，因此不能确认新供给能否在需求前完成且届时可售。
3. **预测**：`p1_missing-T02`（forecast）使用 H1–H5 的 13、14、15、16、17 个，实际计算 `(13+14+15+16+17)/5=15`，预测未来 20 分钟尚未发生的新增需求为 15 个。预测大于可分配量，提示潜在供给不足，但不足以确定加做量。
4. **假设**：同一 forecast 将新增需求安排在第 5、10、15、20 分钟，分别为 4、4、4、3 个；这是情景假设，不是已观察的订单或未来真实销量。
5. **候选比较受阻**：`p1_missing-T03`（simulate，quantity=0，维持候选）和 `p1_missing-T04`（simulate，quantity=8，加做探索候选）均实际返回 `status=blocked`、`candidate_qty=null`，原因为关键条件不完整。8 仅是测试参数，不能采纳；两个候选均未获得有效模拟结果，不提供预计满足量、缺口或浪费量。工具进程均成功执行，没有工具执行失败；阻断来自缺失数据。

## missing_fields：待核实字段与恢复条件

| 字段 | 来源与问题 | 负责核实角色 | 恢复条件 |
|---|---|---|---|
| prep_minutes（制作耗时，分钟） | input.csv／S1 未提供；T01、T03、T04 均确认缺失 | 店长提供并核实适用于本商品、本次情景的耗时；制作岗位核对现场适用性 | 将有来源、当前有效、无冲突且合法的耗时补入输入后，重新运行 inspect、forecast、simulate；关键条件全部有效且候选通过到达时点与可售约束，才能形成新建议 |

制作岗位还需核实现场数量；这属于后续现场核对，不表示已获得确认。人员批准不能代替缺失证据。当前受影响商品 B01 的状态仍为阻断。

## confirmation

未获得店长或制作岗位的人工确认。当前只请求补齐事实；新计划形成后交制作岗位确认。人员采纳只建立待办，实际完成才增加成品，不自行批准或写经营账。

## limitations

- 全部来源为 `classroom_simulation`，不连接真实门店，不代表真实库存。
- 历史预测和到达时点是假设；情景比较不构成真实销量或食品安全承诺。
- 因制作耗时缺失，尚不能判定可执行的加做或维持方案。

## tools_used

全部使用 `course-tools-1.0`，输入 SHA-256：`62b08de45d00f042b867e4775d9234800eef14e1f92a323e287adaf6a29a86f2`。记录位于本目录的 `tool_trace.jsonl`。

- `p1_missing-T01`：inspect，执行成功，业务状态 blocked。
- `p1_missing-T02`：forecast，执行成功，预测 15 个。
- `p1_missing-T03`：simulate --quantity 0，执行成功，业务状态 blocked。
- `p1_missing-T04`：simulate --quantity 8，执行成功，业务状态 blocked。
