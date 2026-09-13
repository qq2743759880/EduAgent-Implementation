import re
src = open(r"E:\stu\project\stu\EduAgent实施手册\edu-frontend\public\admin-questions.html", encoding="utf-8-sig").read()
# 逐个 <script> 开始标记，找无 src= 的内联脚本，其 body 含「真实接入」
pat = re.compile(r"<script([^>]*)>")
output = []
for m in pat.finditer(src):
    attrs = m.group(1)
    if "src" in attrs:
        continue
    start = m.end()
    end = src.find("</script>", start)
    body = src[start:end] if end != -1 else src[start:]
    if "真实接入" in body:
        output = body
        break
print("inline real-logic block length:", len(output))
open(r"E:\stu\project\stu\EduAgent实施手册\test-reports\tmp_task107.js", "w", encoding="utf-8").write(output)