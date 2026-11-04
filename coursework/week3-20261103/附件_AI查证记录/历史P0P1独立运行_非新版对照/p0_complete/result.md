# 经典牛肉堡：未来 20 分钟制作建议

- **status：** 待人工确认
- **product：** 经典牛肉堡（B01）
- **action：** 建议现在加做，交制作岗位确认后建立待办。
- **quantity：** 8 个

## evidence

| 类型 | 来源与工具记录 | 证据 |
| --- | --- | --- |
| 观察事实（课堂数据） | input.csv / S1；inspect：p0_complete-T01 | 在手 12 个、已预留 5 个、不可分配 0 个，可分配量为 7 个。已接订单已全部预留，不再加入新增需求。 |
| 观察事实（课堂规则字段） | input.csv / S1；inspect：p0_complete-T01 | 制作耗时 4 分钟，可售时长 30 分钟，现有批次已存放 2 分钟。规则版本为 sim-rule-1，来源仅为 S1 字段。 |
| 预测 | input.csv / H1—H5；forecast：p0_complete-T02 | 五个可比的 20 分钟历史窗口需求为 13、14、15、16、17 个，均值为 15 个；工具预测未来 20 分钟新增需求为 15 个。 |
| 模拟假设 | forecast：p0_complete-T02；simulate：p0_complete-T03、p0_complete-T04 | 假设第 5、10、15、20 分钟分别新增需求 4、4、4、3 个。加做批次第 4 分钟完成，早于首批假设需求；现有批次可售截止第 28 分钟，新批次截止第 34 分钟，均覆盖本次窗口。 |
| 维持现状候选 | simulate --quantity 0：p0_complete-T03 | 模拟满足 7 个，未满足 8 个，窗口结束剩余可分配量 0 个，过期量 0 个。 |
| 加做候选 | simulate --quantity 8：p0_complete-T04 | 模拟满足 15 个，未满足 0 个，窗口结束剩余可分配量 0 个，过期量 0 个。按上述假设，加做 8 个能覆盖预测缺口。 |

## missing_fields

无计算必需字段缺失；inspect 返回 missing_fields=[]、invalid_fields=[]。不可分配量 0 是有效值。真实未来需求尚未发生，使用预测表示。

## confirmation

尚未获得人工确认。请制作岗位核实现场在手、预留、不可分配数量及制作可行性，并确认是否采纳加做 8 个；请店长核实制作耗时和可售规则。人员采纳仅建立待办，实际完成才增加成品。此回答没有自行批准制作或写入经营账。

## limitations

本次仅使用课堂模拟数据。历史均值是预测，需求到达时点和即时开始制作是假设；模拟结果不代表真实未来销量，也不是食品安全承诺。若现场数量、需求到达、制作完成时间或可售规则变化，应核实后重新比较。

## tools_used

以下调用均成功执行，工具版本均为 course-tools-1.0：

- p0_complete-T01：inspect，参数 {}。
- p0_complete-T02：forecast，参数 {}。
- p0_complete-T03：simulate，参数 {"quantity":0}。
- p0_complete-T04：simulate，参数 {"quantity":8}。
