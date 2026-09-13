(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var candyP = style.getPropertyValue('--candy-purple').trim();
  var candyY = style.getPropertyValue('--candy-yellow').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  function baseTooltip() {
    return { trigger: 'axis', axisPointer: { type: 'shadow' }, appendToBody: true };
  }

  /* ---------- Chart 1: 纪律校验矩阵 ---------- */
  var checks = echarts.init(document.getElementById('chart-checks'), null, { renderer: 'svg' });
  var checksData = [
    { label: '前端测试 495 通过', v: 100 },
    { label: 'tsc --noEmit', v: 100 },
    { label: 'eslint（触达文件）', v: 100 },
    { label: 'next build 成功', v: 100 },
    { label: 'grep text-[15px] 归零', v: 100 },
    { label: 'grep 5 项色规 0 违规', v: 100 },
  ];
  checks.setOption({
    animation: false,
    grid: { left: 8, right: 40, top: 10, bottom: 8, containLabel: true },
    tooltip: baseTooltip(),
    xAxis: { type: 'value', max: 100, axisLabel: { color: muted, formatter: '{value}%' }, splitLine: { lineStyle: { color: rule } } },
    yAxis: { type: 'category', data: checksData.map(function (d) { return d.label; }), axisLabel: { color: ink, fontSize: 13 }, axisTick: { show: false }, axisLine: { lineStyle: { color: rule } } },
    series: [{
      type: 'bar', data: checksData.map(function (d) { return d.v; }),
      barWidth: 16,
      itemStyle: { color: function (p) { var c = [accent, '#ff8a5c', accent2, '#5bd4e6', candyP, candyY]; return c[p.dataIndex % c.length]; }, borderRadius: [8, 8, 8, 8] },
      label: { show: true, position: 'right', color: ink, fontWeight: 700, formatter: function (p) { return 'PASS'; } },
    }],
  });
  window.addEventListener('resize', function () { checks.resize(); });

  /* ---------- Chart 2: 契约测试用例构成 ---------- */
  var tests = echarts.init(document.getElementById('chart-tests'), null, { renderer: 'svg' });
  var testsData = [
    { label: 'query-client · mutation 401/403', v: 4, color: accent },
    { label: 'query-client · query 静默', v: 3, color: candyY },
    { label: 'query-client · 端到端 wiring', v: 2, color: accent2 },
    { label: 'EditUserDialog · 组件级（含 401）', v: 2, color: candyP },
    { label: 'MarkdownView · 字号回归', v: 4, color: '#57cf8a' },
  ];
  tests.setOption({
    animation: false,
    grid: { left: 8, right: 30, top: 8, bottom: 8, containLabel: true },
    tooltip: baseTooltip(),
    xAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
    yAxis: { type: 'category', data: testsData.map(function (d) { return d.label; }).reverse(), axisLabel: { color: ink, fontSize: 13 }, axisTick: { show: false }, axisLine: { lineStyle: { color: rule } } },
    series: [{
      type: 'bar', data: testsData.map(function (d) { return d.v; }).reverse(),
      barWidth: 18,
      itemStyle: { color: function (p) { return testsData[testsData.length - 1 - p.dataIndex].color; }, borderRadius: [0, 8, 8, 0] },
      label: { show: true, position: 'right', color: ink, fontWeight: 700, formatter: function (p) { return p.value + ' 用例'; } },
    }],
  });
  window.addEventListener('resize', function () { tests.resize(); });
})();