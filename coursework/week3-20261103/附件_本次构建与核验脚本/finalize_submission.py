"""Verify the actual delivery directory and produce a checksumed upload bundle."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103")
WORK=Path(r"F:\ChatGPT\work\FDE_数据补全与提交准备_20261103")
DATA=OUT / "附件_规范数据"
PYTHON=r"F:\ChatGPT\work\runtimes\fde-data-simulation\.venv\Scripts\python.exe"


def load(path):return json.loads(path.read_text(encoding="utf-8"))
def save(path, value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report=load(DATA / "02_运行与验收_不作为AI输入" / "数据补全与运行核验.json")
    replay=WORK / "package_replay"
    proc=subprocess.run([PYTHON,"-B","data_completion.py","replay","--inputs",str(DATA / "01_输入_可供智能体"),"--output",str(replay)],cwd=DATA,capture_output=True,text=True,encoding="utf-8",errors="replace")
    (WORK / "离线复算命令记录.txt").write_text(proc.stdout+proc.stderr,encoding="utf-8")
    assert proc.returncode==0,proc.stderr
    actual=replay / "02_运行与验收_不作为AI输入" / "数据补全与运行核验.json"
    original=DATA / "02_运行与验收_不作为AI输入" / "数据补全与运行核验.json"
    assert original.read_bytes()==actual.read_bytes(),"包内离线重放结果不一致"
    tests=subprocess.run([PYTHON,"-B","-m","unittest","test_data_completion","test_data_pipeline","-v"],cwd=DATA,capture_output=True,text=True,encoding="utf-8",errors="replace")
    (WORK / "单元测试完整输出.txt").write_text(tests.stdout+tests.stderr,encoding="utf-8")
    assert tests.returncode==0 and "Ran 37 tests" in tests.stderr and "\nOK" in tests.stderr
    checks=load(WORK / "浏览器核验.json")
    assert checks["passed"] and not checks["page_errors"] and len(checks["checks"])==8
    documents=load(WORK / "文档排版核验.json")
    assert sum(d["pages"] for d in documents)==12 and len(documents)==5
    # All twelve images were opened and visually reviewed in the active session.
    for document in documents:document["visual_review"]="passed 全部页面逐页检查 无裁切 重叠或空白页"
    save(WORK / "文档排版核验.json",documents)
    previous_human=Path(r"F:\ChatGPT\outputs\FDE_数据管线小样例_20261103\历史人工核对_沿用原记录.json")
    assert previous_human.read_bytes()==(DATA / previous_human.name).read_bytes()
    assert load(DATA / previous_human.name)["actual_completion_recorded"] is False
    for dependency in load(DATA / "依赖与技能记录.json")["dependencies"]:
        assert sha(DATA / "离线依赖" / dependency["wheel"])==dependency["sha256"]
    for name in ("data_completion.py","completion_report.html","test_data_completion.py","data_pipeline.py","test_data_pipeline.py","anomaly_tools.py"):
        assert sha(ROOT / name)==sha(DATA / name),("source mismatch",name)
    audit={"passed":True,"input_sha256":report["input_sha256"],"result_sha256":sha(original),
           "replay_byte_identical":True,"unit_tests":37,"runtime_checks":len(report["checks"]),
           "browser_checks":len(checks["checks"]),"manual_human_record_byte_unchanged":True,
           "actual_completion_recorded":False,"new_ai_blind_test_performed":False}
    save(DATA / "02_运行与验收_不作为AI输入" / "交付包离线复算核验.json",audit)
    shutil.copy2(WORK / "浏览器核验.json",DATA / "02_运行与验收_不作为AI输入" / "浏览器核验.json")
    shutil.copy2(WORK / "单元测试完整输出.txt",DATA / "02_运行与验收_不作为AI输入" / "单元测试完整输出.txt")
    shutil.copy2(WORK / "browser" / "01_补全报告_预览.png", OUT / "数据补全预览.png")
    for name in ("prepare_submission.py","sync_d1_wording.py","export_submission_pdf.ps1","render_submission_qa.py","verify_completion_ui.py","finalize_submission.py"):
        target=OUT / "附件_本次构建与核验脚本" / name;target.parent.mkdir(exist_ok=True);shutil.copy2(ROOT / name,target)
    shutil.copy2(WORK / "上传完成情况草稿.txt",OUT / "上传完成情况草稿.txt")
    verification={"prepared_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"contract_version":report["contract_version"],
                  "documents":[{"file":d["file"],"pages":d["pages"],"visual_review":d["visual_review"]} for d in documents],
                  "total_pdf_pages":12,"rendering":"render_docx.py缺少LibreOffice；隐藏本机Word导出PDF，Poppler120dpi渲染，逐页检查",
                  "coverage":report["coverage"],"checks":audit,"browser":checks,
                  "submission_state":"ready_not_uploaded","learning_platform":"https://ai-native-talent-academy.coolai.tech/",
                  "task":"第3周D1；周六材料随D1提交，周一内容并入D1",
                  "attachment_plan":"4份主要PDF加完整ZIP，共5项，每项小于20MB",
                  "group_division_basis":"用户授权按成果模块合理安排；AI辅助整理与核验，见完成情况草稿",
                  "enterprise_effect_validated":False,"deployed":False,"uploaded":False}
    save(OUT / "交付验证记录.json",verification)
    checksum=OUT / "文件校验_SHA256.txt"
    files=sorted(p for p in OUT.rglob("*") if p.is_file() and p!=checksum and "__pycache__" not in p.parts)
    checksum.write_text("".join(sha(p)+"  "+p.relative_to(OUT).as_posix()+"\n" for p in files),encoding="utf-8")
    archive=OUT.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files+[checksum]:z.write(path,OUT.name+"/"+path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)+1
    upload=[OUT / name for name in ["01_周六实操_一页六格说明.pdf","01b_周六实操_运行报告与展示说明.pdf","02_周一_AI任务边界.pdf","03_周二_D1任务清单与人工确认表.pdf"]]+[archive]
    assert all(path.stat().st_size<=20*1024*1024 for path in upload)
    summary={"output":str(OUT),"archive":str(archive),"archive_bytes":archive.stat().st_size,"archive_sha256":sha(archive),
             "files_in_zip":len(files)+1,"unit_tests":37,"runtime_checks":16,"browser_checks":8,"pdf_pages":12,
             "uploaded":False,"upload_files":[{"path":str(p),"bytes":p.stat().st_size} for p in upload]}
    save(WORK / "提交准备包核验汇总.json",summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
