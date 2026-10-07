/* Video learning content is an independently authorized, replaceable derivative. */
(function () {
  "use strict";
  var panel = document.getElementById("videoKnowledge");
  if (!panel || !window.EAPI) return;
  var request = 0, currentSession = null;
  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function stamp(seconds) {
    var t = Math.max(0, Math.floor(Number(seconds) || 0));
    return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0");
  }
  function seek(seconds) {
    var video = document.querySelector("video.real-video");
    if (!video || !Number.isFinite(seconds) || seconds < 0) return;
    function jump() {
      video.currentTime = Math.min(seconds, Number.isFinite(video.duration) ? video.duration : seconds);
      video.focus();
      video.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (video.readyState > 0) jump();
    else video.addEventListener("loadedmetadata", jump, { once: true });
  }
  function timeButton(text, time, cls) {
    var button = el("button", text, cls || "vk-jump");
    button.type = "button";
    button.dataset.seconds = String(time);
    button.addEventListener("click", function () { seek(time); });
    return button;
  }
  function render(data) {
    panel.replaceChildren();
    panel.hidden = false;
    panel.dataset.artifactId = data.artifact_id;
    var header = el("div", null, "vk-header");
    header.appendChild(el("h3", "本节 AI 学习资料"));
    var transcriptLabel = data.transcript_origin === "asr" ? "基于视频 ASR 转写" : "基于课程原生字幕";
    header.appendChild(el("span", transcriptLabel + " · " + data.transcript.segments.length + " 段", "vk-origin"));
    if (data.exercise_count) {
      var practice = el("button", "本课练习 · " + data.exercise_count + " 题", "vk-jump");
      practice.type = "button";
      practice.addEventListener("click", function () { var link = document.getElementById("coursePracticeLink"); if (link) link.click(); });
      header.appendChild(practice);
    }
    panel.appendChild(header);
    panel.appendChild(el("p", data.summary.overview, "vk-overview"));
    var chapters = el("section", null, "vk-chapters");
    chapters.appendChild(el("h4", "章节 · 点击跳转"));
    data.chapters.forEach(function (chapter) {
      var row = el("div", null, "vk-chapter");
      row.appendChild(timeButton(stamp(chapter.start) + "  " + chapter.title, chapter.start));
      row.appendChild(el("p", chapter.summary));
      chapters.appendChild(row);
    });
    panel.appendChild(chapters);
    var nav = el("div", null, "vk-nav");
    nav.setAttribute("role", "tablist");
    nav.setAttribute("aria-label", "视频学习资料");
    var views = [];
    ["AI 笔记", "带时间戳字幕", "思维导图"].forEach(function (title, index) {
      var button = el("button", title);
      button.type = "button";
      button.id = "vk-tab-" + index;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", "vk-view-" + index);
      button.setAttribute("aria-selected", String(index === 0));
      button.addEventListener("click", function () {
        views.forEach(function (view, i) { view.hidden = i !== index; });
        Array.from(nav.children).forEach(function (b, i) { b.setAttribute("aria-selected", String(i === index)); });
      });
      nav.appendChild(button);
      var view = el("section", null, "vk-view");
      view.id = "vk-view-" + index;
      view.setAttribute("role", "tabpanel");
      view.setAttribute("aria-labelledby", button.id);
      view.hidden = index !== 0;
      views.push(view);
    });
    if (window.EduMD) views[0].innerHTML = window.EduMD.toHtml(data.knowledge_note);
    else views[0].appendChild(el("pre", data.knowledge_note));
    var transcript = el("div", null, "vk-transcript");
    data.transcript.segments.forEach(function (segment) {
      var row = timeButton(stamp(segment.start) + "  " + segment.text, segment.start, "vk-line");
      row.dataset.end = String(segment.end);
      transcript.appendChild(row);
    });
    views[1].appendChild(transcript);
    views[2].appendChild(window.EduVideoMindMap(data.mindmap, seek));
    panel.appendChild(nav);
    views.forEach(function (view) { panel.appendChild(view); });
    var player = document.querySelector("video.real-video");
    if (player) player.addEventListener("timeupdate", function () {
      Array.from(transcript.children).forEach(function (row) {
        row.classList.toggle("vk-current", player.currentTime >= Number(row.dataset.seconds) && player.currentTime < Number(row.dataset.end));
      });
    });
    var intro = document.getElementById("introText");
    if (intro) intro.textContent = data.summary.title + " · 可结合下方笔记、章节和字幕学习。";
  }
  function load(sessionId) {
    currentSession = sessionId;
    var seq = ++request;
    panel.hidden = false;
    panel.replaceChildren(el("p", "正在加载本节 AI 学习资料…"));
    window.EAPI.get("/api/study/sessions/" + sessionId + "/video-knowledge").then(function (data) {
      if (seq === request) render(data);
    }).catch(function (error) {
      if (seq !== request) return;
      panel.replaceChildren(el("p", error && error.status === 404 ? "本节 AI 学习资料尚未发布。" : "AI 学习资料暂不可用，可以继续观看视频。"));
      var retry = el("button", "重新加载", "vk-jump");
      retry.type = "button";
      retry.addEventListener("click", function () { load(currentSession); });
      panel.appendChild(retry);
    });
  }
  window.addEventListener("edu:session-ready", function (event) {
    load(event.detail.session_id);
    var params = new URLSearchParams(window.location.search);
    var raw = params.get("t");
    if (raw != null && Number.isFinite(Number(raw)) && Number(raw) >= 0) seek(Number(raw));
  });
})();
