/* EduMD：极简 Markdown→HTML（AI 回答渲染用，离线零依赖，~55 行手写）
   规则：先整体 HTML 转义（& < > "）再做 Markdown 转换 → 标签/属性注入全部失效（防 XSS）；
   支持 #~#### 标题、无序(-*•)/有序(1. 1、1))列表、```围栏代码块（流式未闭合也按代码块渲染）、
   行内 code（反引号）、**加粗**、*斜体*、[文字](链接)（仅放行 http(s)/站内相对/#，其余替换为 #）、
   空行分段 + 段内单换行转 <br> */
(function (global) {
  function mdToHtml(src) {
    var s = String(src == null ? "" : src).replace(/\r\n?/g, "\n")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    var blocks = [];
    s = s.replace(/```[\w-]*\n?([\s\S]*?)(?:```|$)/g, function (m, code) {
      blocks.push('<pre class="md-pre"><code>' + code.replace(/\n+$/, "") + "</code></pre>");
      return "\u0000B" + (blocks.length - 1) + "\u0000";
    });
    function inline(x) {
      var codes = [];
      x = x.replace(/`([^`\n]+)`/g, function (m, c) {
        codes.push("<code>" + c + "</code>");
        return "\u0000C" + (codes.length - 1) + "\u0000";
      });
      x = x.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, function (m, t, u) {
        var href = /^(https?:\/\/|\/|#)/i.test(u) ? u : "#";
        return '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + t + "</a>";
      });
      x = x.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
      x = x.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<i>$2</i>");
      return x.replace(/\u0000C(\d+)\u0000/g, function (m, i) { return codes[+i]; });
    }
    var lines = s.split("\n"), out = [], i = 0;
    while (i < lines.length) {
      var line = lines[i];
      var bm = line.match(/^\u0000B(\d+)\u0000\s*$/);
      if (bm) { out.push(blocks[+bm[1]]); i++; continue; }
      var h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) { var lv = h[1].length + 2; out.push('<h' + lv + ' class="md-h">' + inline(h[2]) + "</h" + lv + ">"); i++; continue; }
      var isUl = /^\s*[-*•]\s+/.test(line), isOl = /^\s*\d+[.、)]\s+/.test(line);
      if (isUl || isOl) {
        var tag = isUl ? "ul" : "ol";
        var re = isUl ? /^\s*[-*•]\s+(.*)$/ : /^\s*\d+[.、)]\s+(.*)$/;
        var items = [];
        while (i < lines.length) { var lm = lines[i].match(re); if (!lm) break; items.push("<li>" + inline(lm[1]) + "</li>"); i++; }
        out.push('<' + tag + ' class="md-list">' + items.join("") + "</" + tag + ">");
        continue;
      }
      if (!line.trim()) { i++; continue; }
      var para = [line]; i++;
      while (i < lines.length && lines[i].trim() &&
             !/^\u0000B\d+\u0000/.test(lines[i]) && !/^(#{1,4})\s/.test(lines[i]) &&
             !/^\s*([-*•]|\d+[.、)])\s+/.test(lines[i])) { para.push(lines[i]); i++; }
      out.push("<p>" + para.map(inline).join("<br>") + "</p>");
    }
    return out.join("").replace(/\u0000B(\d+)\u0000/g, function (m, i) { return blocks[+i]; });
  }
  global.EduMD = { toHtml: mdToHtml };
})(typeof window !== "undefined" ? window : globalThis);
