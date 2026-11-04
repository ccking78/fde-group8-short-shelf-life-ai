"""Save this conversation's AI conclusions and the user's actual classroom review."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
AI = OUT / "附件_AI查证记录"

P2 = """你是快餐门店经营异常调查助手。先确认数据来源和版本，区分爬取事实、派生值、模拟字段与未知。
收到经营事件后，检查现有计划能否在模拟需用时点提供合格供给。不能只凭未来需求大于当前可分配量宣称经营异常，也不能忽略已有待办重复加做。
选择需要的工具读取快照、制作进度、批次截止和来源；调用模拟工具比较维持与调整已有待办。数值引用工具输出，不能自行编造。
正常时维持并说明无需新增。出现风险时，写明发生时点、影响数量、证据、可选行动、假设与核实人。
缺制作规则时，可保留由已知预计完成时点支持的风险提示；受影响的调整方案数量留空，先请店长核规则、制作岗位核进度与产能，再重算并重新确认。
普通制作调整由制作岗位确认。采纳只更新已有待办，不增加库存；实际完成才登记入库。旧建议在输入变化后失效。
后续事件应重新评估，不把确认、预计恢复或模拟结果写成真实经营改善。到可售截止的排除量与实际报废分开。
输出：status、affected_task_id、proposed_task_quantity、additional_quantity、proposed_ready_minute、risk、evidence_ids、verification、human_review、follow_up、limitations。
本轮只使用1店1SKU和一条延迟事件；缺信息为删字段副本。正式增量规范与扩充等待用户指挥。
"""


def main():
    AI.mkdir(parents=True, exist_ok=True)
    prompt_dir = AI / "提示词"
    prompt_dir.mkdir(exist_ok=True)
    old = ROOT.parent / "coursework-20261103"
    for name in ["P0_本次基线.txt", "P1_最终版.txt"]:
        shutil.copy2(old / "prompts" / name, prompt_dir / ("历史_" + name))
    (prompt_dir / "P2_异常调查版.txt").write_text(P2, encoding="utf-8")
    results = {
        "normal": {
            "status": "normal", "action": "maintain_existing_task", "affected_task_id": "TASK-8",
            "proposed_task_quantity": None, "additional_quantity": 0, "proposed_ready_minute": None,
            "risk": "现有8份第4分钟完成，模拟15份需用均及时覆盖；无需新增待办",
            "evidence_ids": ["P2_normal-T02", "P2_normal-T03", "P2_normal-T04"],
            "verification": [], "human_review": "正常观察，不发起新制作审批",
            "follow_up": "待办预计完成时间或新增需求变化后重新评估",
        },
        "delay": {
            "status": "risk_pending_confirmation", "action": "reschedule_existing_task", "affected_task_id": "TASK-8",
            "proposed_task_quantity": 8, "additional_quantity": 0, "proposed_ready_minute": 8,
            "risk": "原待办第12分钟完成，第10分钟有1份不能及时覆盖；第12分钟可补供，不等于损失1份销量",
            "evidence_ids": ["P2_delay-T02", "P2_delay-T03", "P2_delay-T04", "P2_delay-T05", "P2_delay-T06"],
            "verification": ["制作岗位核实TASK-8尚未开工", "制作岗位核实调整顺序后确能第8分钟完成，产能支持8份"],
            "human_review": "真实课堂人工核对已收到；仅采纳调整，未登记实际完成",
            "follow_up": "采纳后只更新原待办；实际完成时间和数量到来后再复核及时覆盖情况",
        },
        "missing": {
            "status": "needs_verification", "action": "request_rule_verification", "affected_task_id": "TASK-8",
            "proposed_task_quantity": None, "additional_quantity": None, "proposed_ready_minute": None,
            "risk": "已知第12分钟预计完成仍支持第10分钟1份晚供提示；制作规则缺失，不能给可采纳调整量",
            "evidence_ids": ["P2_missing-T02", "P2_missing-T03", "P2_missing-T04", "P2_missing-T05"],
            "verification": ["店长核实prep_minutes及其适用来源", "制作岗位核实实际进度与备选产能"],
            "human_review": "未批准调整；补证据后重算并重新确认",
            "follow_up": "规则补齐不会自动采纳旧建议",
        },
    }
    summaries = []
    for case, result in results.items():
        folder = AI / ("P2_" + case)
        trace = [json.loads(s) for s in (folder / "tool_trace.jsonl").read_text(encoding="utf-8").splitlines()]
        result["limitations"] = ["本次为当前对话AI助手的工具查证，不是全新独立会话", "课堂页面回放这些记录，页面交互不调用在线模型",
                                  "源商品与交易字段真实，经营状态、时点、规则及效果为模拟", "不据本次记录推算准确率、ROI或企业采用意愿"]
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summaries.append({"case": case, "tool_calls": len(trace), "status": result["status"],
                          "input_sha256": trace[0]["input_sha256"], "first_call_utc": trace[0]["at_utc"],
                          "last_call_utc": trace[-1]["at_utc"], "prompt_frozen_before_run": False})
    review = {
        "state": "confirmed_classroom_simulation", "reviewer": "傅浩诚", "role": "课程项目参与者 人工核对",
        "user_exact_text": "核对无误，课堂模拟采纳调整原待办",
        "received_in_current_conversation": True, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "核对问句所列模拟数字与处理摘要，不表示逐条审阅原始工具输出或真实门店审批",
        "decision": {"task_id": "TASK-8", "action": "adjust_existing_task", "task_quantity": 8,
                     "additional_quantity": 0, "expected_ready_minute": 8},
        "premise": "课堂假设制作岗位已核实尚未开工且可调整至第8分钟完成",
        "inventory_at_acceptance": {"on_hand": 12, "reserved": 5, "available": 7},
        "actual_completion_recorded": False,
    }
    (OUT / "新版人工核对记录.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(old / "human_review.json", AI / "历史人工核对_仅旧加做案例.json")
    # Preserve independent historical experiments as historical evidence only.
    archive = AI / "历史P0P1独立运行_非新版对照"
    shutil.copytree(old / "runs", archive, dirs_exist_ok=True)
    manifest = {"runs": summaries, "total_tool_calls": sum(r["tool_calls"] for r in summaries),
                "run_identity": "当前对话AI助手真实选择并调用本地工具；未开启新独立会话",
                "comparison": "P0/P1历史输入无既有待办；本轮有既有待办。不同输入，不能声称P2准确性改善。",
                "prompt_note": "P2为本轮流程整理后的开发指令；未在运行前冻结，不声称隔离提示词实验。",
                "observed_change": "扩大了查证范围：已有待办、及时供给、正常不提醒、缺规则时分开观察与行动。",
                "model_and_cost": "本记录未提供精确后端型号、token和费用，未估算",
                "human_review": review["state"]}
    (OUT / "新版查证汇总.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
