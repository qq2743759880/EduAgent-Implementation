# Icon and Emoji Inventory

Scope: `edu-frontend/public/*.html`, captured before the clay-theme page rollout. The dispatch expected 19 pages; the live directory contains 25, so this inventory covers all 25.

Reproduce the primary scan:

```powershell
rg -n --glob '*.html' '<svg\b|<img\b' edu-frontend/public
```

Emoji were detected with JavaScript Unicode property `\p{Extended_Pictographic}`. Counts below list unique glyphs, not occurrences.

| Page | Current glyphs/assets | Current semantics | Rollout disposition |
|---|---|---|---|
| achievements.html | 🏆 🔑 🚀 🏅 ⏱ 🎖 📍 😵 🔄 💸 🪙 🔒 ✨ ⬆ ⬇ 👑 🥈 🥉 | achievements, keys, speed, medals, time, location, errors, retry, money, lock, rank | Replace structural glyphs with trophy/certificate/check/warning/arrow icons; keep no emoji as icons. |
| admin-course-detail.html | ⚠ ▶ | warning, play | `ic-warning`, `ic-play`. |
| admin-courses-recycle-proto.html | 🧪 ♻ ⚠ 🗑 ✋ 📚 | prototype, recycle, warning, delete, stop, courses | `ic-warning`, `ic-trash`, `ic-book-open`; recycle/stop require a later sprite extension if this prototype is promoted. |
| admin-courses.html | 📭 ⚠ 🗑 👁 ♻ ✋ 📚 🧩 | empty, warning, delete, view, recycle, stop, courses, extension | Use warning/trash/book/search; add eye/recycle only when the page rollout reaches this file. |
| admin-dashboard.html | 👥 ⚡ 🚀 🚫 🧭 👑 🛠 👩 🏫 🎓 📅 🏆 ⏳ 📭 😵 ⚠ | users, activity, launch, forbidden, navigation, admin, tools, education, calendar, ranking, pending, empty/error | Use users/graduation/trophy/warning; extend only for true actions, not decoration. |
| admin-mcp.html | ✅ ▶ ⚠ ❌ 📭 | success, run, warning, failure, empty | `ic-check-circle`, `ic-play`, `ic-warning`, `ic-x`. |
| admin-question-detail.html | ✏ 💾 ⚠ | edit, save, warning | `ic-pencil-simple`, `ic-warning`; save can be text-labelled until a floppy icon is added. |
| admin-questions.html | ⬆ 📭 ⚠ 🧩 🗑 📚 | upload, empty, warning, extension, delete, course | `ic-upload-simple`, `ic-warning`, `ic-trash`, `ic-book-open`. |
| admin-rag-upload.html | ✅ 🗂 ⏳ 🔒 📭 🗃 ⚠ plus one progress-ring SVG | success, collection, pending, lock, empty, storage, warning, chart | Use check/warning/bookmark; preserve the data-bearing progress SVG as a chart, not an icon. |
| admin-users-refine-proto.html | 🧪 ℹ 🚫 🔍 ⚠ 📏 | prototype, info, forbidden, search, warning, measure | `ic-info`, `ic-magnifying-glass`, `ic-warning`. |
| admin-users.html | ⚠ 🔍 🚫 | warning, search, forbidden | `ic-warning`, `ic-magnifying-glass`. |
| chat.html | 💬 🗂 🗑 🦊 😊 🤖 🔎 📎 ⚠ ✨ 😵 🧠 🛡 ⏰ | chat, collection, delete, avatars/bot, search, attach, warning, error, knowledge, safety, time | Use chat/bookmark/trash/search/warning/send/copy; avatars remain content, not structural emoji. |
| community-post.html | ✨ 🐣 📌 👁 👍 ⭐ 💬 🎉 🔒 🔍 🛋 😵 🔄 | decoration/avatar, pin, view, like, favorite, chat, celebration, lock, search, empty/error/retry | Use star/heart/chat/bookmark/search/warning; no decorative emoji. |
| community.html | 💬 👍 ↔ ✨ 🐣 🧩 🔥 🕒 🔍 🎒 🏝 📌 🔒 👁 😵 🔄 plus one CSS data-URI caret SVG | chat, like, sort, decoration/avatar, hot/time, search, topics, pin, lock, view, error/retry | Use chat/heart/search/caret/warning; replace the hand-authored data-URI caret during page rollout. |
| coupons.html | 🎟 🧾 🎁 🎫 😵 🔄 🛒 ✅ 😕 😱 📚 🎉 | coupon, receipt, gift, error/retry, cart, success, course | Use check/warning/book; ticket/cart require extension only if they remain interactive. |
| course-detail.html | 🎟 ▶ ✍ 🎯 🦉 🖥 🏷 📅 ♥ ✅ 🔒 📘 ⭐ 🧠 😵 ⚠ 😖 🎉 ❤ | coupon, play, edit, goal, course/avatar, device, tag, calendar, favorite, success, lock, book, knowledge, error | Use play/pencil/heart/check/book/star/warning. |
| courses.html | 🦉 🔥 ⭐ 🏆 💻 🖥 📊 🎮 📐 🎯 📈 🏢 🌱 ⚙ 🤖 🌐 🔧 🎨 🗄 🧩 📚 🔍 plus search/filter/caret SVG and course-cover img | course subjects/categories, ranking, settings, search/filter; content cover image | Use book/star/trophy/gear/search/caret; preserve content cover images and replace three hand-authored control SVGs. |
| dashboard.html | ✨ 👋 🧑 🎓 ⚙ 🔑 ⏱ ✍ 📚 🔥 📈 📊 🍩 🏆 🦊 💰 🎖 🔄 📺 📝 🧪 🎯 🥇 🥈 🥉 plus trend chart SVG | greeting/avatar, education, settings, time, notes, progress, achievements, course actions, chart | Use graduation/gear/book/trophy/certificate/play; preserve the labelled trend SVG as data visualization. |
| favorites.html | ⭐ 😵 🔄 🛒 📘 | favorite, error/retry, cart, book | `ic-star`, `ic-warning`, `ic-book-open`. |
| learning.html | 🦉 🎓 🎬 ⏳ 📒 📝 📐 📚 🔒 🧠 ✅ ▶ 📵 📎 🎉 ⚠ ❌ plus play/document/warning SVG tabs | learning/avatar, video, pending, notes, course, lock, knowledge, success, play, offline, attachment, warning/error | Use graduation/play/book/check/warning; replace the three hand-authored tab icons. |
| login-register.html | ⚠ 🍭 🌈 🍬 ✨ 🎈 👁 🚀 🎀 🏅 🙈 | warning plus decorative candy, password visibility, launch, medal | Use sign-in/warning; use a future eye icon only for the labelled password control; remove decoration glyphs. |
| me.html | 🐻 ✏ 📊 ⏱ ✅ 💎 🏅 🧭 📝 ⭐ 📚 🧾 🎟 ↩ 🎫 💾 😵 🔄 | avatar, edit, stats/time, success, achievements/navigation, notes/favorites/course, commerce, save, error/retry | Use user/pencil/check/certificate/star/book/arrow/warning. |
| my-cohorts.html | 🎓 🦉 ⏰ ▶ 🐰 🌱 🐧 🏆 🐻 💸 😵 🎒 | cohorts, avatars, time, play, ranking, refund, error, learning | Use graduation/play/trophy/users/warning. |
| practice.html | ✨ 🐣 🎯 📚 🔤 📈 🔥 📕 🗂 🛠 ⏹ 💡 ✅ ❌ 😵 🎉 | decoration/avatar, goal, practice/course, trend, collection/tools, stop, hint, success/failure/error | Use book/bookmark/check/warning; add a stop control only if still needed. |
| refund.html | 💸 plus external Baloo font import | refund | Keep a visible text label; add a receipt/refund icon only when the action is implemented. |

## Frozen Phosphor fill subset

Source: official `@phosphor-icons/core@2.1.1` fill SVG assets. License: MIT, copied beside the sprite as `LICENSE.phosphor.txt`.

| Semantic group | Sprite IDs |
|---|---|
| Navigation and account | `ic-house`, `ic-user`, `ic-users`, `ic-gear`, `ic-sign-in`, `ic-sign-out`, `ic-arrow-left`, `ic-arrow-right`, `ic-caret-down` |
| Learning and community | `ic-book-open`, `ic-graduation-cap`, `ic-chat-circle`, `ic-heart`, `ic-star`, `ic-bookmark-simple`, `ic-trophy`, `ic-certificate` |
| Actions | `ic-paper-plane-tilt`, `ic-copy`, `ic-magnifying-glass`, `ic-play`, `ic-pause`, `ic-plus`, `ic-trash`, `ic-pencil-simple`, `ic-upload-simple` |
| Feedback | `ic-x`, `ic-warning`, `ic-check-circle`, `ic-info` |

This is a 30-icon starter subset. Page rollout may extend it from the same Phosphor fill source when a real remaining action cannot be expressed by visible text. It must not mix icon families or reintroduce emoji as structural icons.
