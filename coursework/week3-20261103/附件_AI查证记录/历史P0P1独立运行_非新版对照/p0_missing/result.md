# 经典牛肉堡：待核实制作时间后再确定加做量

- **status**：blocked（关键条件缺失，待核实）。
- **product**：B01／经典牛肉堡。
- **action**：请店长补充并核实制作时间及可售规则，制作岗位核实现场数量；补齐后重新模拟，提交加做建议供制作岗位确认。
- **quantity**：null（暂不能确定可采纳的加做数量）。

## evidence

1. **观察事实**：input.csv 的 S1 记录在手 12 个、已预留 5 个、不可分配 0 个；inspect 记录 `p0_missing-T01` 实算可分配量为 7 个。已接订单已全部预留，不能再次计入新增需求；不可分配量 0 是有效数据。
2. **缺失条件**：S1 的 `prep_minutes` 未提供。`p0_missing-T01` 返回 `status=blocked`、`missing_fields=["prep_minutes"]`。S1 填有可售时长 30 分钟及批龄 2 分钟；这些课堂规则仍需店长核实。
3. **预测**：forecast 记录 `p0_missing-T02` 使用 H1—H5 的五个 20 分钟历史窗口（13、14、15、16、17 个），按均值向上取整，预测未来 20 分钟新增需求 15 个。此数值是预测，尚未发生。
4. **模拟假设与候选比较**：维持现状（加做 0 个，`p0_missing-T03`）与加做 8 个（仅候选参数，`p0_missing-T04`）均已实际调用 simulate。两次调用执行成功，但业务结果均为 `blocked`，`candidate_qty=null`，原因均为缺少 `prep_minutes`。因此无法确认新增供给能否在需求前完成且届时可售，也无法得出可采纳的数量或有效的优劣比较。

## missing_fields

- `prep_minutes`：制作时间未提供；请店长核实并补充。

## confirmation

尚无人工作出确认。请店长核实规则，制作岗位核实现场数量，并在补齐条件、重新模拟后确认建议。人员采纳只建立待办；只有实际制作完成才增加成品数量。

## limitations

- 输入来源为 `classroom_simulation`，不能视为真实门店库存或真实销量。
- 预测工具采用假定到达时点：第 5、10、15、20 分钟分别新增 4、4、4、3 个需求；实际到达节奏未知。
- 模拟仅用于假设比较，不能保证未来销量、制作完成时间或食品安全。
- 四次工具调用均成功执行；其中 inspect 及两次 simulate 的业务状态为阻塞，并非已完成可采纳的经营判断。

## tools_used

工具来源：共享只读 `E:\FDE培训作业\coursework-20261103\tools.py`，版本 `course-tools-1.0`，规则版本 `sim-rule-1`（课堂假设）；输入指纹 `62b08de45d00f042b867e4775d9234800eef14e1f92a323e287adaf6a29a86f2`。

- `p0_missing-T01`：inspect，执行成功，业务状态 blocked。
- `p0_missing-T02`：forecast，执行成功，预测新增需求 15 个。
- `p0_missing-T03`：simulate，参数 quantity=0，执行成功，业务状态 blocked。
- `p0_missing-T04`：simulate，参数 quantity=8，执行成功，业务状态 blocked。
