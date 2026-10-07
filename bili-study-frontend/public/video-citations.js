(function (global) {
  "use strict";
  function escape(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function stamp(value) {
    var seconds = Math.floor(value);
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }
  global.EduVideoCitations = function (docs) {
    if (!Array.isArray(docs)) return "";
    var links = [];
    docs.forEach(function (doc, index) {
      if (!doc || !Number.isInteger(doc.series_id) || doc.series_id <= 0 ||
          !Number.isInteger(doc.session_id) || doc.session_id <= 0 ||
          !Number.isInteger(doc.video_id) || doc.video_id <= 0 ||
          !Number.isFinite(doc.start_seconds) || !Number.isFinite(doc.end_seconds) ||
          doc.start_seconds < 0 || doc.end_seconds <= doc.start_seconds) return;
      var params = new URLSearchParams({ series_id: String(doc.series_id), session_id: String(doc.session_id), t: String(doc.start_seconds) });
      links.push('<li><a href="learning.html?' + escape(params.toString()) + '">doc[' + (index + 1) + '] · ' +
        escape(doc.series_name || "本课视频") + ' · ' + stamp(doc.start_seconds) + '–' + stamp(doc.end_seconds) +
        ' · 跳到视频依据</a></li>');
    });
    return links.length ? '<div class="video-citations"><b>视频依据</b><ul>' + links.join("") + '</ul></div>' : "";
  };
})(window);
