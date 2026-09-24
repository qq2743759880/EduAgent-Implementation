#!/usr/bin/env bash
set -euo pipefail
# TC2 盲测 B10/B11/B12 全量 runner（只读观察，零代码改动）
# 用法：bash test-reports/blind-b10-12/run_tc2.sh

ROOT="E:/stu/project/stu/EduAgent实施手册"
OUT="$ROOT/test-reports/blind-b10-12"
NODE="C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-2/node.exe"
MYSQL="/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql"

cd "$ROOT"
mkdir -p "$OUT"

echo "===== TC2 开始 $(date -Iseconds) ====="

# 登录拿 token（运行时注入，不落盘仓库）
curl -sS --noproxy '*' -m 10 -X POST http://127.0.0.1:9988/api/auth/login \
  -H "Content-Type: application/json" -d '{"account":"adm02test","password":"Test@123456"}' -o /tmp/tc2_adm.json
curl -sS --noproxy '*' -m 10 -X POST http://127.0.0.1:9988/api/auth/login \
  -H "Content-Type: application/json" -d '{"account":"user000001","password":"Test@123456"}' -o /tmp/tc2_stu.json
ADM=$(python -c "import json;print(json.load(open('/tmp/tc2_adm.json'))['data']['access_token'])")
STU=$(python -c "import json;print(json.load(open('/tmp/tc2_stu.json'))['data']['access_token'])")

echo "tokens ADM=${#ADM} STU=${#STU}"

DB_COUNT() {
  "$MYSQL" -h 127.0.0.1 -P 3306 -u root -p123456 edu -N -e "$1" 2>/dev/null
}

RUN_B10() {
  local page=$1 round=$2
  local token="$STU"
  export EDU_GATE_TOKEN="$token"
  "$NODE" "$ROOT/test-reports/ta1-3/cdp_stream_probe.mjs" --page "$page" \
    --query "请用三句话介绍 Python 这门编程语言的特点" \
    --out "$OUT/b10-${page}-r${round}.json"
}

RUN_B11() {
  local round=$1
  export EDU_TOKEN="$STU"
  "$NODE" "$OUT/blind_probe.mjs" --mode b11 --role student \
    --query "帮我把《Python 入门》这门课收藏起来，并简述你会怎么处理" \
    --out "$OUT/b11-r${round}.json" --shot "$OUT/b11-r${round}.png"
}

RUN_B12() {
  local round=$1 action=$2 title=$3
  export EDU_TOKEN="$ADM"
  "$NODE" "$OUT/blind_probe.mjs" --mode b12 --role admin --action "$action" \
    --query "帮我创建一门课程，名称叫做《${title}》，分类为编程，面向零基础学员" \
    --out "$OUT/b12-r${round}-${action}.json" --shot "$OUT/b12-r${round}-${action}.png"
}

echo "===== B10 静态 chat.html 3 轮 ====="
for r in 1 2 3; do
  echo "-- B10 static r$r"
  RUN_B10 chat.html "$r"
done

echo "===== B10 React /chat 3 轮 ====="
for r in 1 2 3; do
  echo "-- B10 react r$r"
  RUN_B10 react "$r"
done

echo "===== B11 黄条 3 轮 ====="
for r in 1 2 3; do
  echo "-- B11 r$r"
  RUN_B11 "$r"
done

echo "===== B12 HITL 卡 3 轮（approve + reject + reject） ====="
echo "-- DB before B12"
DB_COUNT "SELECT COUNT(*) FROM series;" > "$OUT/b12-db-before.txt"
cat "$OUT/b12-db-before.txt"

RUN_B12 1 approve "盲测B12验证课1"
echo "-- DB after approve r1"
DB_COUNT "SELECT COUNT(*) FROM series; SELECT id, series_code, series_name, created_at FROM series ORDER BY id DESC LIMIT 1;" > "$OUT/b12-db-after-approve.txt"
cat "$OUT/b12-db-after-approve.txt"

RUN_B12 2 reject "盲测B12拒绝课2"
echo "-- DB after reject r2"
DB_COUNT "SELECT COUNT(*) FROM series;" > "$OUT/b12-db-after-reject2.txt"
cat "$OUT/b12-db-after-reject2.txt"

RUN_B12 3 reject "盲测B12拒绝课3"
echo "-- DB after reject r3"
DB_COUNT "SELECT COUNT(*) FROM series;" > "$OUT/b12-db-after-reject3.txt"
cat "$OUT/b12-db-after-reject3.txt"

echo "===== TC2 runner 完成 $(date -Iseconds) ====="
