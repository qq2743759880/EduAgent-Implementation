// C6-PBI-ITER2-TYPES 真库打靶：FILL / DRAG_SORT / MATCH 三题型 next -> submit 判定
// 走真实 HTTP + 真实后端 8000（student user000001/Test@123456）
const BASE = 'http://127.0.0.1:8000';

async function jreq(method, path, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const raw = await res.text();
  let json = null;
  try { json = JSON.parse(raw); } catch (e) { json = raw; }
  return { status: res.status, json };
}

(async () => {
  // 1) 登录
  const lg = await jreq('POST', '/api/auth/login', { account: 'user000001', password: 'Test@123456' });
  console.log('LOGIN status=' + lg.status);
  const token = lg.json && lg.json.data && lg.json.data.access_token;
  if (!token) { console.log('LOGIN FAILED: ' + JSON.stringify(lg.json)); process.exit(1); }
  console.log('LOGIN OK token len=' + token.length);

  // 2) 逐题型打靶：因 next 优先到期错题（与 question_type 无关），改走 /question/{custom_code} 精确取 target mock 题
  const cases = [
    {
      type: 'FILL', code: 'Q-EN-FILL-BIGGER',
      correctAns: ['bigger'],
      wrongAns: ['biiger'],
      partialAns: null,   // 单空，无部分得分分支
    },
    {
      type: 'DRAG_SORT', code: 'Q-MATH-DRAG-OP',
      correctAns: ['C', 'B', 'A'],   // 括号 -> 乘除 -> 加减
      wrongAns: ['A', 'B', 'C'],
      partialAns: ['C', 'A', 'B'],   // 仅第1位对 -> 1/3 位置分
    },
    {
      type: 'MATCH', code: 'Q-EN-MATCH-ANTONYM',
      correctAns: [{ left_id: 'L1', right_id: 'R1' }, { left_id: 'L2', right_id: 'R2' }, { left_id: 'L3', right_id: 'R3' }],
      wrongAns: [{ left_id: 'L1', right_id: 'R2' }, { left_id: 'L2', right_id: 'R1' }, { left_id: 'L3', right_id: 'R3' }],
      partialAns: null,
    },
  ];

  for (const c of cases) {
    // 取题
    const nq = await jreq('GET', '/api/interactive/quiz/question/' + c.code, null, token);
    const q = nq.json && nq.json.data;
    if (!q) { console.log('DETAIL ' + c.type + ' FAILED: ' + JSON.stringify(nq.json)); continue; }
    console.log('\n== ' + c.type + ' == custom_code=' + q.custom_code + ' title=' + q.title);
    console.log('  sent fields: items=' + JSON.stringify(q.items) + ' pairs=' + JSON.stringify(q.pairs) + ' has_correct=' + (q.correct !== undefined) + ' (correct excluded=' + (q.correct === undefined) + ')');
    const code = q.custom_code;
    const qid = q.question_id;

    const sub = async function (label, ans) {
      const s = await jreq('POST', '/api/interactive/quiz/submit', { custom_code: code, question_id: qid, question_type: c.type, answer: ans, time_spent_sec: 12 }, token);
      const r = (s.json && s.json.data) || {};
      const added = r.added_to_wrong_book === true;
      console.log('  SUBMIT ' + label + ' -> is_correct=' + String(r.is_correct) + ' score=' + String(r.score) + '/' + String(r.score_max) + ' wrongbook=' + String(added) + ' explain=' + (r.explain_text ? r.explain_text.split('\n')[0] : '-'));
      return r;
    };

    await sub('correct', c.correctAns);
    const rw = await sub('wrong  ', c.wrongAns);
    if (c.partialAns) await sub('partial', c.partialAns);
    if (rw.is_correct !== false) console.log('  !! WRONG ANS NOT GRADED WRONG');
  }

  // 3) wrong-book 归集 check（上述故意答错应已入错题本，含三题型）
  const wb = await jreq('GET', '/api/interactive/quiz/wrong-book?status=ACTIVE&page=1&page_size=20', null, token);
  const items = (wb.json && wb.json.data && wb.json.data.items) || [];
  const types = {};
  items.forEach(function (it) { types[it.question_type] = (types[it.question_type] || 0) + 1; });
  console.log('\nWRONG-BOOK total=' + (wb.json && wb.json.data && wb.json.data.total) + ' byType=' + JSON.stringify(types));
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(1); });