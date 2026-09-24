# DOM Hooks Frozen Inventory

Generated: 2026-09-24T02:35:49.269Z

Source scope: `edu-frontend/public/*.html` (27 current pages, 1283 hook expressions).

> The dispatch document says 19 pages, while the current directory contains 25. The inventory intentionally follows the live filesystem so new pages cannot escape G3.

Regenerate: `node scripts/gates/dom-hook-inventory.mjs --all`

Verify: `node scripts/gates/dom-hook-inventory.mjs --all --check`

A changed line number is allowed. A removed or newly introduced normalized hook expression is drift and makes `--check` fail until this inventory is deliberately regenerated.

## achievements.html

Total hooks: 43

| Category | Count |
|---|---:|
| getElementById | 18 |
| querySelector | 13 |
| querySelectorAll | 3 |
| classList operations | 8 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 1 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 503 | classList operations | - | `classList.add('open')` |
| 503 | classList operations | - | `classList.add('open')` |
| 503 | classList operations | - | `classList.remove('open')` |
| 503 | classList operations | - | `classList.remove('open')` |
| 503 | classList operations | - | `classList.contains('open')` |
| 503 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 503 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 503 | getElementById | gnav | `getElementById('gnav')` |
| 510 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 526 | getElementById | - | `getElementById(id)` |
| 532 | getElementById | - | `getElementById(id)` |
| 533 | getElementById | loginGate | `getElementById("loginGate")` |
| 535 | getElementById | loginGateBtn | `getElementById("loginGateBtn")` |
| 566 | querySelector | #secBadges .badge-grid | `querySelector("#secBadges .badge-grid")` |
| 568 | getElementById | badgeCount | `getElementById("badgeCount")` |
| 570 | getElementById | badgeNext | `getElementById("badgeNext")` |
| 599 | querySelector | #secPoints .total-pts | `querySelector("#secPoints .total-pts")` |
| 601 | querySelector | #secPoints .lv-pill | `querySelector("#secPoints .lv-pill")` |
| 605 | querySelector | #secPoints .lv-range | `querySelector("#secPoints .lv-range")` |
| 609 | querySelector | #secPoints .lv-prog | `querySelector("#secPoints .lv-prog")` |
| 610 | querySelector | i | `querySelector("i")` |
| 611 | querySelector | #secPoints .lv-note | `querySelector("#secPoints .lv-note")` |
| 615 | querySelector | #secPoints .log-list | `querySelector("#secPoints .log-list")` |
| 619 | getElementById | logHead | `getElementById("logHead")` |
| 627 | getElementById | logPager | `getElementById("logPager")` |
| 641 | querySelectorAll | .pager-btn[data-page] | `querySelectorAll(".pager-btn[data-page]")` |
| 644 | querySelector | [data-nav="prev"] | `querySelector('[data-nav="prev"]')` |
| 645 | querySelector | [data-nav="next"] | `querySelector('[data-nav="next"]')` |
| 652 | getElementById | logPager | `getElementById("logPager")` |
| 665 | getElementById | rankMeta | `getElementById("rankMeta")` |
| 667 | getElementById | rankLiveBadge | `getElementById("rankLiveBadge")` |
| 671 | querySelector | #secRank .rank-body | `querySelector("#secRank .rank-body")` |
| 681 | getElementById | myRankVal | `getElementById("myRankVal")` |
| 684 | getElementById | myRankMetric | `getElementById("myRankMetric")` |
| 693 | querySelector | #secRank .rank-span .tabgroup .tab.on | `querySelector("#secRank .rank-span .tabgroup .tab.on")` |
| 697 | querySelectorAll | #secRank .rank-dim .tabgroup .tab | `querySelectorAll("#secRank .rank-dim .tabgroup .tab")` |
| 698 | classList operations | - | `classList.contains("on")` |
| 710 | dynamic/template selectors | - | `querySelectorAll(groupSel)` |
| 710 | querySelectorAll | - | `querySelectorAll(groupSel)` |
| 713 | classList operations | - | `classList.remove("on")` |
| 714 | classList operations | - | `classList.add("on")` |
| 724 | getElementById | - | `getElementById(secId)` |
| 726 | querySelector | .show-err .retry | `querySelector(".show-err .retry")` |

## admin-chat-audit.html

Total hooks: 17

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 0 |
| querySelectorAll | 2 |
| classList operations | 9 |
| closest | 1 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 457 | classList operations | - | `classList.add('open')` |
| 457 | classList operations | - | `classList.add('open')` |
| 457 | classList operations | - | `classList.remove('open')` |
| 457 | classList operations | - | `classList.remove('open')` |
| 457 | classList operations | - | `classList.contains('open')` |
| 457 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 457 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 457 | getElementById | gnav | `getElementById('gnav')` |
| 467 | getElementById | - | `getElementById(id)` |
| 493 | querySelectorAll | tr[data-sid] | `querySelectorAll("tr[data-sid]")` |
| 494 | event delegation selectors | [data-hist] | `addEventListener("click",function(ev){ if(ev.target.closest("[data-hist]")` |
| 495 | closest | [data-hist] | `closest("[data-hist]")` |
| 499 | querySelectorAll | [data-hist] | `querySelectorAll("[data-hist]")` |
| 510 | classList operations | - | `classList.add("show")` |
| 527 | classList operations | - | `classList.remove("show")` |
| 528 | classList operations | - | `classList.remove("show")` |
| 529 | classList operations | - | `classList.remove("show")` |

## admin-course-detail.html

Total hooks: 46

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 2 |
| querySelectorAll | 15 |
| classList operations | 11 |
| closest | 3 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 6 |
| parentNode / nextSibling family | 4 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 640 | classList operations | - | `classList.add('open')` |
| 640 | classList operations | - | `classList.add('open')` |
| 640 | classList operations | - | `classList.remove('open')` |
| 640 | classList operations | - | `classList.remove('open')` |
| 640 | classList operations | - | `classList.contains('open')` |
| 640 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 640 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 640 | getElementById | gnav | `getElementById('gnav')` |
| 649 | getElementById | - | `getElementById(id)` |
| 711 | querySelectorAll | [data-cohort] | `querySelectorAll("[data-cohort]")` |
| 712 | closest | button | `closest("button")` |
| 713 | querySelectorAll | [data-coedit] | `querySelectorAll("[data-coedit]")` |
| 714 | querySelectorAll | [data-codel] | `querySelectorAll("[data-codel]")` |
| 793 | event delegation selectors | button | `addEventListener("click",function(ev){ if(ev.target.closest("button")` |
| 793 | querySelectorAll | .mp-h | `querySelectorAll(".mp-h")` |
| 794 | closest | button | `closest("button")` |
| 795 | parentNode / nextSibling family | - | `.parentNode` |
| 795 | querySelector | .mp-b | `querySelector(".mp-b")` |
| 796 | classList operations | - | `classList.toggle("open")` |
| 796 | querySelector | .chev | `querySelector(".chev")` |
| 797 | querySelectorAll | [data-ssadd] | `querySelectorAll("[data-ssadd]")` |
| 798 | querySelectorAll | [data-moedit] | `querySelectorAll("[data-moedit]")` |
| 799 | querySelectorAll | [data-model] | `querySelectorAll("[data-model]")` |
| 801 | querySelectorAll | [data-vid] | `querySelectorAll("[data-vid]")` |
| 802 | querySelectorAll | [data-upl] | `querySelectorAll("[data-upl]")` |
| 811 | querySelectorAll | [data-ssedit] | `querySelectorAll("[data-ssedit]")` |
| 812 | querySelectorAll | [data-ssdel] | `querySelectorAll("[data-ssdel]")` |
| 896 | querySelectorAll | [data-chap] | `querySelectorAll("[data-chap]")` |
| 906 | classList operations | - | `classList.toggle("hover",ev==="dragover")` |
| 926 | form.elements / name / tagName | - | `.name` |
| 928 | parentNode / nextSibling family | - | `.parentNode` |
| 928 | parentNode / nextSibling family | - | `.nextSibling` |
| 935 | form.elements / name / tagName | - | `.name` |
| 935 | form.elements / name / tagName | - | `.name` |
| 935 | form.elements / name / tagName | - | `.name` |
| 943 | form.elements / name / tagName | - | `.name` |
| 948 | form.elements / name / tagName | - | `.name` |
| 960 | parentNode / nextSibling family | - | `.firstElementChild` |
| 1026 | querySelectorAll | [data-chdel] | `querySelectorAll("[data-chdel]")` |
| 1041 | classList operations | - | `classList.add("show")` |
| 1042 | classList operations | - | `classList.remove("show")` |
| 1043 | classList operations | - | `classList.remove("show")` |
| 1043 | closest | .scrim | `closest(".scrim")` |
| 1043 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 1044 | classList operations | - | `classList.remove("show")` |
| 1044 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |

## admin-courses-recycle-proto.html

Total hooks: 56

| Category | Count |
|---|---:|
| getElementById | 35 |
| querySelector | 0 |
| querySelectorAll | 4 |
| classList operations | 15 |
| closest | 1 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 448 | classList operations | - | `classList.add('open')` |
| 448 | classList operations | - | `classList.add('open')` |
| 448 | classList operations | - | `classList.remove('open')` |
| 448 | classList operations | - | `classList.remove('open')` |
| 448 | classList operations | - | `classList.contains('open')` |
| 448 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 448 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 448 | getElementById | gnav | `getElementById('gnav')` |
| 469 | getElementById | emToast | `getElementById("emToast")` |
| 488 | classList operations | - | `classList.add("hidden")` |
| 488 | getElementById | state-error | `getElementById("state-error")` |
| 489 | classList operations | - | `classList.add("hidden")` |
| 489 | getElementById | state-empty | `getElementById("state-empty")` |
| 490 | classList operations | - | `classList.add("hidden")` |
| 490 | getElementById | pager | `getElementById("pager")` |
| 491 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 495 | getElementById | f-kw | `getElementById("f-kw")` |
| 497 | getElementById | f-dm | `getElementById("f-dm")` |
| 499 | getElementById | f-ss | `getElementById("f-ss")` |
| 505 | classList operations | - | `classList.remove("hidden")` |
| 505 | getElementById | state-empty | `getElementById("state-empty")` |
| 509 | classList operations | - | `classList.add("hidden")` |
| 509 | getElementById | state-empty | `getElementById("state-empty")` |
| 514 | getElementById | err-msg | `getElementById("err-msg")` |
| 516 | classList operations | - | `classList.remove("hidden")` |
| 516 | getElementById | state-error | `getElementById("state-error")` |
| 535 | getElementById | meta-count | `getElementById("meta-count")` |
| 539 | classList operations | - | `classList.remove("hidden")` |
| 539 | getElementById | pager | `getElementById("pager")` |
| 550 | event delegation selectors | [data-pg] | `addEventListener("click",function(e){ var b=e.target.closest("[data-pg]")` |
| 550 | getElementById | pager | `getElementById("pager")` |
| 551 | closest | [data-pg] | `closest("[data-pg]")` |
| 555 | getElementById | f-kw | `getElementById("f-kw")` |
| 560 | getElementById | - | `getElementById(id)` |
| 561 | getElementById | - | `getElementById(id)` |
| 564 | classList operations | - | `classList.toggle("active",b.dataset.view===state.view)` |
| 564 | querySelectorAll | #viewTabs .vtab | `querySelectorAll("#viewTabs .vtab")` |
| 566 | getElementById | btn-create | `getElementById("btn-create")` |
| 567 | getElementById | f-ss | `getElementById("f-ss")` |
| 568 | getElementById | f-sort | `getElementById("f-sort")` |
| 569 | getElementById | head-sub | `getElementById("head-sub")` |
| 576 | classList operations | - | `classList.add("show")` |
| 576 | getElementById | - | `getElementById(id)` |
| 577 | classList operations | - | `classList.remove("show")` |
| 577 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 578 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 579 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 587 | getElementById | restore-name | `getElementById("restore-name")` |
| 588 | getElementById | restore-id | `getElementById("restore-id")` |
| 609 | getElementById | purge-name | `getElementById("purge-name")` |
| 610 | getElementById | purge-id | `getElementById("purge-id")` |
| 615 | getElementById | purge-code-echo | `getElementById("purge-code-echo")` |
| 616 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 623 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 624 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |
| 629 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |

## admin-courses.html

Total hooks: 90

| Category | Count |
|---|---:|
| getElementById | 54 |
| querySelector | 2 |
| querySelectorAll | 8 |
| classList operations | 25 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 1 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 569 | classList operations | - | `classList.add('open')` |
| 569 | classList operations | - | `classList.add('open')` |
| 569 | classList operations | - | `classList.remove('open')` |
| 569 | classList operations | - | `classList.remove('open')` |
| 569 | classList operations | - | `classList.contains('open')` |
| 569 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 569 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 569 | getElementById | gnav | `getElementById('gnav')` |
| 600 | getElementById | emToast | `getElementById("emToast")` |
| 626 | getElementById | thead-row | `getElementById("thead-row")` |
| 635 | classList operations | - | `classList.toggle("active", b.dataset.view === activeView)` |
| 635 | querySelectorAll | #viewTabs .vtab | `querySelectorAll("#viewTabs .vtab")` |
| 636 | getElementById | btn-create | `getElementById("btn-create")` |
| 637 | getElementById | f-ss | `getElementById("f-ss")` |
| 637 | getElementById | f-sort | `getElementById("f-sort")` |
| 640 | getElementById | head-sub | `getElementById("head-sub")` |
| 644 | getElementById | empty-ico | `getElementById("empty-ico")` |
| 645 | getElementById | empty-title | `getElementById("empty-title")` |
| 646 | getElementById | empty-desc | `getElementById("empty-desc")` |
| 652 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 653 | classList operations | - | `classList.remove("hidden")` |
| 653 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 654 | classList operations | - | `classList.add("hidden")` |
| 654 | getElementById | state-empty | `getElementById("state-empty")` |
| 655 | classList operations | - | `classList.add("hidden")` |
| 655 | getElementById | state-error | `getElementById("state-error")` |
| 656 | classList operations | - | `classList.add("hidden")` |
| 656 | getElementById | pager | `getElementById("pager")` |
| 663 | getElementById | f-kw | `getElementById("f-kw")` |
| 665 | getElementById | f-dm | `getElementById("f-dm")` |
| 673 | getElementById | f-ss | `getElementById("f-ss")` |
| 675 | getElementById | f-sort | `getElementById("f-sort")` |
| 682 | getElementById | - | `getElementById(id)` |
| 694 | getElementById | pager | `getElementById("pager")` |
| 700 | classList operations | - | `classList.add("hidden")` |
| 705 | classList operations | - | `classList.remove("hidden")` |
| 714 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 716 | classList operations | - | `classList.toggle("hidden", !items.length)` |
| 719 | getElementById | total-count | `getElementById("total-count")` |
| 721 | getElementById | meta-suffix | `getElementById("meta-suffix")` |
| 725 | classList operations | - | `classList.add("hidden")` |
| 725 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 726 | classList operations | - | `classList.add("hidden")` |
| 726 | getElementById | pager | `getElementById("pager")` |
| 727 | getElementById | err-msg | `getElementById("err-msg")` |
| 729 | classList operations | - | `classList.remove("hidden")` |
| 729 | getElementById | state-error | `getElementById("state-error")` |
| 733 | classList operations | - | `classList.toggle("hidden", !b)` |
| 733 | getElementById | state-empty | `getElementById("state-empty")` |
| 766 | classList operations | - | `classList.contains("open")` |
| 766 | dynamic/template selectors | - | `querySelector('.dd[data-row="'+id+'"]')` |
| 766 | querySelector | - | `querySelector('.dd[data-row="'+id+'"]')` |
| 767 | classList operations | - | `classList.remove("open")` |
| 767 | classList operations | - | `classList.add("open")` |
| 767 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 768 | classList operations | - | `classList.remove("open")` |
| 768 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 769 | classList operations | - | `classList.remove("open")` |
| 769 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 772 | classList operations | - | `classList.add("show")` |
| 772 | getElementById | - | `getElementById(id)` |
| 773 | classList operations | - | `classList.remove("show")` |
| 773 | classList operations | - | `classList.remove("open")` |
| 773 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 773 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 774 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 775 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 780 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 782 | getElementById | form-title | `getElementById("form-title")` |
| 785 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 798 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 802 | getElementById | form-title | `getElementById("form-title")` |
| 809 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 813 | getElementById | series-save-btn | `getElementById("series-save-btn")` |
| 834 | getElementById | del-name | `getElementById("del-name")` |
| 839 | getElementById | off-name | `getElementById("off-name")` |
| 848 | getElementById | off-confirm-btn | `getElementById("off-confirm-btn")` |
| 854 | getElementById | del-confirm-btn | `getElementById("del-confirm-btn")` |
| 864 | getElementById | restore-name | `getElementById("restore-name")` |
| 865 | getElementById | restore-id | `getElementById("restore-id")` |
| 870 | getElementById | restore-confirm-btn | `getElementById("restore-confirm-btn")` |
| 883 | getElementById | purge-name | `getElementById("purge-name")` |
| 884 | getElementById | purge-id | `getElementById("purge-id")` |
| 889 | getElementById | purge-code-echo | `getElementById("purge-code-echo")` |
| 890 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 897 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 898 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |
| 902 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |
| 912 | getElementById | btn-create | `getElementById("btn-create")` |
| 921 | querySelector | .toolbar-meta,.page-head .sub | `querySelector(".toolbar-meta,.page-head .sub")` |

## admin-dashboard.html

Total hooks: 31

| Category | Count |
|---|---:|
| getElementById | 25 |
| querySelector | 1 |
| querySelectorAll | 0 |
| classList operations | 5 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 529 | classList operations | - | `classList.add('open')` |
| 529 | classList operations | - | `classList.add('open')` |
| 529 | classList operations | - | `classList.remove('open')` |
| 529 | classList operations | - | `classList.remove('open')` |
| 529 | classList operations | - | `classList.contains('open')` |
| 529 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 529 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 529 | getElementById | gnav | `getElementById('gnav')` |
| 537 | getElementById | view-loading | `getElementById('view-loading')` |
| 538 | getElementById | view-success | `getElementById('view-success')` |
| 557 | querySelector | .page-head .sub, .demo-note | `querySelector(".page-head .sub, .demo-note")` |
| 566 | getElementById | - | `getElementById(v)` |
| 574 | getElementById | kpi-total | `getElementById("kpi-total")` |
| 575 | getElementById | kpi-active7d | `getElementById("kpi-active7d")` |
| 576 | getElementById | kpi-newreg7d | `getElementById("kpi-newreg7d")` |
| 577 | getElementById | kpi-disabled | `getElementById("kpi-disabled")` |
| 579 | getElementById | rb-admin | `getElementById("rb-admin")` |
| 580 | getElementById | rb-manager | `getElementById("rb-manager")` |
| 581 | getElementById | rb-teacher | `getElementById("rb-teacher")` |
| 582 | getElementById | rb-student | `getElementById("rb-student")` |
| 584 | getElementById | kpi-avglogin | `getElementById("kpi-avglogin")` |
| 588 | getElementById | bars-real | `getElementById("bars-real")` |
| 603 | getElementById | donut-real | `getElementById("donut-real")` |
| 609 | getElementById | donut-total | `getElementById("donut-total")` |
| 610 | getElementById | donut-sub | `getElementById("donut-sub")` |
| 612 | getElementById | lg-admin | `getElementById("lg-admin")` |
| 613 | getElementById | lg-student | `getElementById("lg-student")` |
| 614 | getElementById | lg-teacher | `getElementById("lg-teacher")` |
| 615 | getElementById | lg-manager | `getElementById("lg-manager")` |
| 617 | getElementById | updated-at | `getElementById("updated-at")` |
| 621 | getElementById | err-msg | `getElementById("err-msg")` |

## admin-infra.html

Total hooks: 33

| Category | Count |
|---|---:|
| getElementById | 32 |
| querySelector | 0 |
| querySelectorAll | 0 |
| classList operations | 0 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 1 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 397 | getElementById | - | `getElementById(v)` |
| 403 | getElementById | runDemo | `getElementById("runDemo")` |
| 411 | getElementById | err-msg | `getElementById("err-msg")` |
| 434 | getElementById | deps | `getElementById("deps")` |
| 441 | getElementById | viewer-chip | `getElementById("viewer-chip")` |
| 445 | getElementById | raw-line | `getElementById("raw-line")` |
| 456 | getElementById | k-rl-hits | `getElementById("k-rl-hits")` |
| 457 | getElementById | k-rl-keys | `getElementById("k-rl-keys")` |
| 458 | getElementById | k-rl-rej | `getElementById("k-rl-rej")` |
| 460 | getElementById | rl-rows | `getElementById("rl-rows")` |
| 467 | getElementById | rl-bypass | `getElementById("rl-bypass")` |
| 478 | getElementById | k-cache-keys | `getElementById("k-cache-keys")` |
| 479 | getElementById | k-cache-mutex | `getElementById("k-cache-mutex")` |
| 480 | getElementById | k-cache-sample | `getElementById("k-cache-sample")` |
| 481 | getElementById | cmp-box | `getElementById("cmp-box")` |
| 498 | getElementById | cmp-verdict | `getElementById("cmp-verdict")` |
| 511 | getElementById | k-lock-impl | `getElementById("k-lock-impl")` |
| 512 | getElementById | k-lock-count | `getElementById("k-lock-count")` |
| 514 | getElementById | lock-rows | `getElementById("lock-rows")` |
| 523 | getElementById | k-queue-impl | `getElementById("k-queue-impl")` |
| 524 | getElementById | k-queue-count | `getElementById("k-queue-count")` |
| 525 | getElementById | k-queue-depth | `getElementById("k-queue-depth")` |
| 527 | getElementById | queue-rows | `getElementById("queue-rows")` |
| 535 | getElementById | k-mongo-db | `getElementById("k-mongo-db")` |
| 537 | getElementById | mongo-rows | `getElementById("mongo-rows")` |
| 538 | form.elements / name / tagName | - | `.name` |
| 541 | getElementById | mongo-bad | `getElementById("mongo-bad")` |
| 549 | getElementById | k-ev-total | `getElementById("k-ev-total")` |
| 550 | getElementById | k-ev-worker | `getElementById("k-ev-worker")` |
| 551 | getElementById | k-ev-q | `getElementById("k-ev-q")` |
| 553 | getElementById | ev-rows | `getElementById("ev-rows")` |
| 560 | getElementById | ev-mask-note | `getElementById("ev-mask-note")` |
| 573 | getElementById | runDemo | `getElementById("runDemo")` |

## admin-mcp.html

Total hooks: 23

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 5 |
| querySelectorAll | 8 |
| classList operations | 6 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 644 | classList operations | - | `classList.add('open')` |
| 644 | classList operations | - | `classList.add('open')` |
| 644 | classList operations | - | `classList.remove('open')` |
| 644 | classList operations | - | `classList.remove('open')` |
| 644 | classList operations | - | `classList.contains('open')` |
| 644 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 644 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 644 | getElementById | gnav | `getElementById('gnav')` |
| 654 | getElementById | - | `getElementById(id)` |
| 693 | querySelector | #srvTable tbody | `querySelector("#srvTable tbody")` |
| 713 | querySelectorAll | [data-srv-hl] | `querySelectorAll("[data-srv-hl]")` |
| 714 | querySelectorAll | [data-srv-dc] | `querySelectorAll("[data-srv-dc]")` |
| 715 | querySelectorAll | [data-srv-en] | `querySelectorAll("[data-srv-en]")` |
| 716 | querySelectorAll | [data-srv-del] | `querySelectorAll("[data-srv-del]")` |
| 719 | querySelector | #srvTable tbody | `querySelector("#srvTable tbody")` |
| 725 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 773 | querySelectorAll | #srvSteps li | `querySelectorAll("#srvSteps li")` |
| 779 | querySelectorAll | #mdl-server .step-pane | `querySelectorAll("#mdl-server .step-pane")` |
| 780 | classList operations | - | `classList.toggle("on",+panes[j].getAttribute("data-pane")` |
| 834 | querySelectorAll | #srvSteps li | `querySelectorAll("#srvSteps li")` |
| 916 | querySelector | #toolTable tbody | `querySelector("#toolTable tbody")` |
| 932 | querySelectorAll | [data-tt] | `querySelectorAll("[data-tt]")` |
| 935 | querySelector | #toolTable tbody | `querySelector("#toolTable tbody")` |

## admin-question-detail.html

Total hooks: 75

| Category | Count |
|---|---:|
| getElementById | 51 |
| querySelector | 1 |
| querySelectorAll | 4 |
| classList operations | 15 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 606 | getElementById | view-loading | `getElementById('view-loading')` |
| 606 | getElementById | view-error | `getElementById('view-error')` |
| 607 | getElementById | tabhead | `getElementById('tabhead')` |
| 607 | querySelectorAll | .qd-pane | `querySelectorAll('.qd-pane')` |
| 618 | classList operations | - | `classList.add('open')` |
| 618 | classList operations | - | `classList.add('open')` |
| 618 | classList operations | - | `classList.remove('open')` |
| 618 | classList operations | - | `classList.remove('open')` |
| 618 | classList operations | - | `classList.contains('open')` |
| 618 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 618 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 618 | getElementById | gnav | `getElementById('gnav')` |
| 634 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 650 | getElementById | f-type | `getElementById("f-type")` |
| 665 | getElementById | - | `getElementById(kind+"-body")` |
| 675 | querySelectorAll | [data-optdel] | `querySelectorAll("[data-optdel]")` |
| 693 | querySelectorAll | .opt-input[data-ol] | `querySelectorAll(".opt-input[data-ol]")` |
| 705 | getElementById | cr-type | `getElementById("cr-type")` |
| 708 | getElementById | - | `getElementById(id)` |
| 710 | getElementById | ro-obj-label | `getElementById("ro-obj-label")` |
| 712 | classList operations | - | `classList.add("hidden")` |
| 712 | getElementById | - | `getElementById(id)` |
| 713 | classList operations | - | `classList.remove("hidden")` |
| 713 | getElementById | opt-single | `getElementById("opt-single")` |
| 714 | classList operations | - | `classList.remove("hidden")` |
| 714 | getElementById | opt-multi | `getElementById("opt-multi")` |
| 715 | classList operations | - | `classList.remove("hidden")` |
| 715 | getElementById | opt-tf | `getElementById("opt-tf")` |
| 716 | classList operations | - | `classList.remove("hidden")` |
| 716 | getElementById | opt-none | `getElementById("opt-none")` |
| 717 | getElementById | answer-hint | `getElementById("answer-hint")` |
| 720 | getElementById | f-type | `getElementById("f-type")` |
| 723 | event delegation selectors | input[type=radio] | `addEventListener("change", function(e){ var r=e.target.closest("input[type=radio]")` |
| 723 | getElementById | opt-tf | `getElementById("opt-tf")` |
| 724 | closest | input[type=radio] | `closest("input[type=radio]")` |
| 725 | parentNode / nextSibling family | - | `.parentElement` |
| 726 | getElementById | f-answer | `getElementById("f-answer")` |
| 747 | getElementById | analysis-preview | `getElementById("analysis-preview")` |
| 747 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 748 | getElementById | prev-stem | `getElementById("prev-stem")` |
| 748 | getElementById | f-stem | `getElementById("f-stem")` |
| 749 | getElementById | prev-analysis | `getElementById("prev-analysis")` |
| 749 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 752 | getElementById | prev-options | `getElementById("prev-options")` |
| 765 | classList operations | - | `classList.toggle("hidden",pi!=="edit")` |
| 765 | getElementById | pane-edit | `getElementById("pane-edit")` |
| 766 | classList operations | - | `classList.toggle("hidden",pi!=="preview")` |
| 766 | getElementById | pane-preview | `getElementById("pane-preview")` |
| 767 | classList operations | - | `classList.toggle("on",pi==="edit")` |
| 767 | getElementById | tab-edit | `getElementById("tab-edit")` |
| 768 | classList operations | - | `classList.toggle("on",pi==="preview")` |
| 768 | getElementById | tab-preview | `getElementById("tab-preview")` |
| 773 | getElementById | - | `getElementById(id)` |
| 778 | getElementById | - | `getElementById(id)` |
| 778 | getElementById | - | `getElementById(errId)` |
| 779 | closest | .fld | `closest(".fld")` |
| 780 | classList operations | - | `classList.toggle("err",bad)` |
| 786 | getElementById | f-stem | `getElementById("f-stem")` |
| 787 | getElementById | f-answer | `getElementById("f-answer")` |
| 788 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 791 | getElementById | - | `getElementById(id)` |
| 819 | getElementById | qd-err-msg | `getElementById("qd-err-msg")` |
| 831 | getElementById | cr-code | `getElementById("cr-code")` |
| 832 | getElementById | cr-bank | `getElementById("cr-bank")` |
| 833 | getElementById | ro-bank-id | `getElementById("ro-bank-id")` |
| 834 | getElementById | ro-code | `getElementById("ro-code")` |
| 835 | getElementById | ro-qid | `getElementById("ro-qid")` |
| 836 | getElementById | ro-bank-full | `getElementById("ro-bank-full")` |
| 837 | getElementById | ro-code-full | `getElementById("ro-code-full")` |
| 839 | getElementById | f-type | `getElementById("f-type")` |
| 841 | getElementById | f-stem | `getElementById("f-stem")` |
| 842 | getElementById | f-answer | `getElementById("f-answer")` |
| 843 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 847 | querySelectorAll | #opt-tf input[type=radio] | `querySelectorAll("#opt-tf input[type=radio]")` |
| 853 | getElementById | qd-err-msg | `getElementById("qd-err-msg")` |

## admin-questions.html

Total hooks: 45

| Category | Count |
|---|---:|
| getElementById | 5 |
| querySelector | 1 |
| querySelectorAll | 5 |
| classList operations | 22 |
| closest | 9 |
| matches | 0 |
| event delegation selectors | 3 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 735 | getElementById | - | `getElementById(id)` |
| 750 | classList operations | - | `classList.add('open')` |
| 750 | classList operations | - | `classList.add('open')` |
| 750 | classList operations | - | `classList.remove('open')` |
| 750 | classList operations | - | `classList.remove('open')` |
| 750 | classList operations | - | `classList.contains('open')` |
| 750 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 750 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 750 | getElementById | gnav | `getElementById('gnav')` |
| 763 | getElementById | - | `getElementById(id)` |
| 770 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 778 | classList operations | - | `classList.remove("show")` |
| 778 | querySelectorAll | .scrim.show | `querySelectorAll(".scrim.show")` |
| 782 | event delegation selectors | [data-close] | `addEventListener("click",function(e){ var c=e.target.closest("[data-close]")` |
| 783 | closest | [data-close] | `closest("[data-close]")` |
| 784 | classList operations | - | `classList.contains("scrim")` |
| 784 | classList operations | - | `classList.contains("show")` |
| 787 | classList operations | - | `classList.toggle("hidden",!a1)` |
| 787 | classList operations | - | `classList.toggle("hidden",!a2)` |
| 787 | classList operations | - | `classList.toggle("hidden",!a3)` |
| 817 | closest | button[data-bkpg] | `closest("button[data-bkpg]")` |
| 829 | classList operations | - | `classList.toggle("on", x.getAttribute("data-tab")` |
| 829 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 830 | classList operations | - | `classList.toggle("hidden", t!=="banks")` |
| 831 | classList operations | - | `classList.toggle("hidden", t!=="questions")` |
| 852 | closest | button[data-qpg] | `closest("button[data-qpg]")` |
| 866 | event delegation selectors | [data-del-q] | `addEventListener("click", function(e){ var db=e.target.closest("[data-del-q]")` |
| 867 | closest | [data-del-q] | `closest("[data-del-q]")` |
| 869 | closest | [data-edit-q] | `closest("[data-edit-q]")` |
| 871 | closest | [data-qrow] | `closest("[data-qrow]")` |
| 874 | event delegation selectors | [data-bank-del] | `addEventListener("click", function(e){ var bd=e.target.closest("[data-bank-del]")` |
| 875 | closest | [data-bank-del] | `closest("[data-bank-del]")` |
| 877 | closest | [data-bank-edit] | `closest("[data-bank-edit]")` |
| 879 | closest | [data-manage-bank] | `closest("[data-manage-bank]")` |
| 913 | classList operations | - | `classList.add("show")` |
| 938 | classList operations | - | `classList.add("show")` |
| 953 | classList operations | - | `classList.add("show")` |
| 976 | classList operations | - | `classList.add("show")` |
| 992 | querySelectorAll | #qf-options-body input[data-opt-label] | `querySelectorAll("#qf-options-body input[data-opt-label]")` |
| 1011 | classList operations | - | `classList.add("show")` |
| 1014 | classList operations | - | `classList.toggle("hidden", Number(x.getAttribute("data-idx")` |
| 1014 | querySelectorAll | .imp-step | `querySelectorAll(".imp-step")` |
| 1016 | classList operations | - | `classList.toggle("done", !!i&&i<n)` |
| 1016 | classList operations | - | `classList.toggle("cur", i===n)` |
| 1016 | querySelectorAll | .stp,.stp-conn | `querySelectorAll(".stp,.stp-conn")` |

## admin-rag-upload.html

Total hooks: 37

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 2 |
| querySelectorAll | 5 |
| classList operations | 13 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 9 |
| parentNode / nextSibling family | 4 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 776 | classList operations | - | `classList.add('open')` |
| 776 | classList operations | - | `classList.add('open')` |
| 776 | classList operations | - | `classList.remove('open')` |
| 776 | classList operations | - | `classList.remove('open')` |
| 776 | classList operations | - | `classList.contains('open')` |
| 776 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 776 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 776 | getElementById | gnav | `getElementById('gnav')` |
| 789 | getElementById | - | `getElementById(id)` |
| 823 | form.elements / name / tagName | - | `.name` |
| 842 | form.elements / name / tagName | - | `.name` |
| 847 | form.elements / name / tagName | - | `.name` |
| 850 | querySelectorAll | [data-rm] | `querySelectorAll("[data-rm]")` |
| 889 | classList operations | - | `classList.add("hover")` |
| 890 | classList operations | - | `classList.remove("hover")` |
| 892 | classList operations | - | `classList.remove("hover")` |
| 905 | classList operations | - | `classList.add("show")` |
| 915 | classList operations | - | `classList.remove("show")` |
| 921 | classList operations | - | `classList.add("show")` |
| 934 | form.elements / name / tagName | - | `.name` |
| 938 | form.elements / name / tagName | - | `.name` |
| 944 | form.elements / name / tagName | - | `.name` |
| 961 | querySelector | #taskTable tbody | `querySelector("#taskTable tbody")` |
| 1001 | parentNode / nextSibling family | - | `.parentNode` |
| 1001 | parentNode / nextSibling family | - | `.parentNode` |
| 1019 | form.elements / name / tagName | - | `.name` |
| 1019 | form.elements / name / tagName | - | `.name` |
| 1026 | form.elements / name / tagName | - | `.name` |
| 1027 | querySelectorAll | [data-del] | `querySelectorAll("[data-del]")` |
| 1033 | parentNode / nextSibling family | - | `.parentNode` |
| 1033 | parentNode / nextSibling family | - | `.parentNode` |
| 1052 | querySelector | [data-collection-count] | `querySelector("[data-collection-count]")` |
| 1073 | querySelectorAll | .tabs .tab[data-tab] | `querySelectorAll(".tabs .tab[data-tab]")` |
| 1074 | classList operations | - | `classList.toggle("on", btns[i].getAttribute("data-tab")` |
| 1076 | classList operations | - | `classList.toggle("hidden", RAG_TABS[j] !== name)` |
| 1083 | querySelectorAll | .tabs .tab[data-tab] | `querySelectorAll(".tabs .tab[data-tab]")` |
| 1112 | querySelectorAll | [data-ragrb] | `querySelectorAll("[data-ragrb]")` |

## admin-users-refine-proto.html

Total hooks: 0

| Category | Count |
|---|---:|
| getElementById | 0 |
| querySelector | 0 |
| querySelectorAll | 0 |
| classList operations | 0 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| - | - | - | No matching hook expressions |

## admin-users.html

Total hooks: 76

| Category | Count |
|---|---:|
| getElementById | 41 |
| querySelector | 3 |
| querySelectorAll | 4 |
| classList operations | 17 |
| closest | 6 |
| matches | 0 |
| event delegation selectors | 4 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 574 | getElementById | f-kw | `getElementById("f-kw")` |
| 575 | getElementById | deb-pulse | `getElementById("deb-pulse")` |
| 576 | classList operations | - | `classList.add("show")` |
| 579 | classList operations | - | `classList.remove("show")` |
| 582 | getElementById | f-kw | `getElementById("f-kw")` |
| 582 | getElementById | f-role | `getElementById("f-role")` |
| 583 | getElementById | f-status | `getElementById("f-status")` |
| 585 | getElementById | f-role | `getElementById("f-role")` |
| 586 | getElementById | f-status | `getElementById("f-status")` |
| 621 | getElementById | u-body | `getElementById("u-body")` |
| 622 | classList operations | - | `classList.toggle("hidden",view!=="empty")` |
| 622 | getElementById | u-empty | `getElementById("u-empty")` |
| 623 | getElementById | u-error | `getElementById("u-error")` |
| 624 | classList operations | - | `classList.toggle("hidden",view!=="error")` |
| 642 | getElementById | u-count | `getElementById("u-count")` |
| 643 | getElementById | u-pager | `getElementById("u-pager")` |
| 663 | getElementById | u-body | `getElementById("u-body")` |
| 665 | getElementById | head-total | `getElementById("head-total")` |
| 673 | event delegation selectors | [data-upg] | `addEventListener("click",function(e){ var b=e.target.closest("[data-upg]")` |
| 673 | getElementById | u-pager | `getElementById("u-pager")` |
| 674 | closest | [data-upg] | `closest("[data-upg]")` |
| 680 | getElementById | learn-sub | `getElementById("learn-sub")` |
| 684 | getElementById | learn-fields | `getElementById("learn-fields")` |
| 696 | getElementById | st-title | `getElementById("st-title")` |
| 697 | getElementById | st-sub | `getElementById("st-sub")` |
| 698 | getElementById | st-msg | `getElementById("st-msg")` |
| 700 | getElementById | st-reason | `getElementById("st-reason")` |
| 701 | getElementById | st-confirm | `getElementById("st-confirm")` |
| 704 | getElementById | st-confirm | `getElementById("st-confirm")` |
| 709 | getElementById | st-reason | `getElementById("st-reason")` |
| 725 | getElementById | edit-sub | `getElementById("edit-sub")` |
| 726 | getElementById | e-role | `getElementById("e-role")` |
| 728 | getElementById | e-reason | `getElementById("e-reason")` |
| 729 | getElementById | e-status-seg | `getElementById("e-status-seg")` |
| 730 | classList operations | - | `classList.toggle("on",+b.getAttribute("data-st")` |
| 730 | querySelectorAll | button | `querySelectorAll("button")` |
| 733 | classList operations | - | `classList.toggle("hidden",!redline)` |
| 733 | getElementById | e-redline | `getElementById("e-redline")` |
| 735 | querySelector | button[data-st="0"] | `querySelector('button[data-st="0"]')` |
| 736 | getElementById | e-save | `getElementById("e-save")` |
| 739 | event delegation selectors | button | `addEventListener("click",function(e){ const b=e.target.closest("button")` |
| 739 | getElementById | e-status-seg | `getElementById("e-status-seg")` |
| 740 | closest | button | `closest("button")` |
| 741 | classList operations | - | `classList.toggle("on",x===b)` |
| 741 | parentNode / nextSibling family | - | `.parentElement` |
| 741 | querySelectorAll | button | `querySelectorAll("button")` |
| 746 | getElementById | e-role | `getElementById("e-role")` |
| 747 | querySelector | #e-status-seg button.on | `querySelector("#e-status-seg button.on")` |
| 749 | getElementById | e-reason | `getElementById("e-reason")` |
| 752 | getElementById | e-save | `getElementById("e-save")` |
| 758 | getElementById | e-save | `getElementById("e-save")` |
| 762 | getElementById | - | `getElementById(id)` |
| 764 | getElementById | - | `getElementById(id+"-mask")` |
| 764 | getElementById | - | `getElementById(id+"-dlg")` |
| 765 | classList operations | - | `classList.add("show")` |
| 766 | classList operations | - | `classList.add("show")` |
| 769 | classList operations | - | `classList.remove("show")` |
| 769 | querySelectorAll | .mask.show | `querySelectorAll(".mask.show")` |
| 770 | classList operations | - | `classList.remove("show")` |
| 770 | querySelectorAll | .dialog.show | `querySelectorAll(".dialog.show")` |
| 772 | event delegation selectors | [data-close] | `addEventListener("keydown",function(e){ if(e.key==="Escape") closeAll(); }); document.addEventListener("click",function(e){ if(e.target.classList && e.target.classList.contains("mask")) closeAll(); const c=e.target.closest("[data-close]")` |
| 773 | event delegation selectors | [data-close] | `addEventListener("click",function(e){ if(e.target.classList && e.target.classList.contains("mask")) closeAll(); const c=e.target.closest("[data-close]")` |
| 774 | classList operations | - | `classList.contains("mask")` |
| 775 | closest | [data-close] | `closest("[data-close]")` |
| 776 | closest | [data-view] | `closest("[data-view]")` |
| 777 | closest | [data-edit] | `closest("[data-edit]")` |
| 778 | closest | [data-toggle] | `closest("[data-toggle]")` |
| 786 | classList operations | - | `classList.add('open')` |
| 786 | classList operations | - | `classList.add('open')` |
| 786 | classList operations | - | `classList.remove('open')` |
| 786 | classList operations | - | `classList.remove('open')` |
| 786 | classList operations | - | `classList.contains('open')` |
| 786 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 786 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 786 | getElementById | gnav | `getElementById('gnav')` |
| 795 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |

## chat.html

Total hooks: 34

| Category | Count |
|---|---:|
| getElementById | 8 |
| querySelector | 4 |
| querySelectorAll | 3 |
| classList operations | 14 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 1 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 513 | dynamic/template selectors | - | `querySelectorAll(s)` |
| 513 | querySelectorAll | - | `querySelectorAll(s)` |
| 618 | classList operations | - | `classList.toggle("stop", isStream)` |
| 629 | getElementById | degradeBanner | `getElementById("degradeBanner")` |
| 655 | event delegation selectors | [data-del] | `addEventListener("click", (e)=>{ const del = e.target.closest("[data-del]")` |
| 656 | closest | [data-del] | `closest("[data-del]")` |
| 658 | closest | .sess | `closest(".sess")` |
| 665 | getElementById | toast | `getElementById("toast")` |
| 669 | classList operations | - | `classList.toggle("open", open)` |
| 670 | classList operations | - | `classList.toggle("open", open)` |
| 678 | getElementById | composerInput | `getElementById("composerInput")` |
| 747 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 773 | getElementById | - | `getElementById(id)` |
| 828 | querySelectorAll | .sess | `querySelectorAll(".sess")` |
| 831 | querySelectorAll | .del | `querySelectorAll(".del")` |
| 899 | classList operations | - | `classList.toggle("stop", on)` |
| 916 | parentNode / nextSibling family | - | `.parentNode` |
| 916 | querySelector | .empty,.error-st | `querySelector(".empty,.error-st")` |
| 947 | querySelector | .hitl-confirm | `querySelector(".hitl-confirm")` |
| 948 | querySelector | .hitl-reject | `querySelector(".hitl-reject")` |
| 962 | classList operations | - | `classList.add("hitl-busy")` |
| 963 | querySelector | .hitl-note | `querySelector(".hitl-note")` |
| 975 | classList operations | - | `classList.add("hitl-busy")` |
| 985 | classList operations | - | `classList.remove("hitl-busy")` |
| 1221 | classList operations | - | `classList.add("open")` |
| 1222 | classList operations | - | `classList.add("open")` |
| 1233 | classList operations | - | `classList.add('open')` |
| 1233 | classList operations | - | `classList.add('open')` |
| 1233 | classList operations | - | `classList.remove('open')` |
| 1233 | classList operations | - | `classList.remove('open')` |
| 1233 | classList operations | - | `classList.contains('open')` |
| 1233 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 1233 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 1233 | getElementById | gnav | `getElementById('gnav')` |

## community-post.html

Total hooks: 109

| Category | Count |
|---|---:|
| getElementById | 54 |
| querySelector | 29 |
| querySelectorAll | 2 |
| classList operations | 11 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 4 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 7 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 383 | getElementById | likeBtn | `getElementById('likeBtn')` |
| 384 | getElementById | favBtn | `getElementById('favBtn')` |
| 385 | getElementById | likeCnt | `getElementById('likeCnt')` |
| 386 | getElementById | favCnt | `getElementById('favCnt')` |
| 387 | getElementById | metaLike | `getElementById('metaLike')` |
| 388 | getElementById | metaFav | `getElementById('metaFav')` |
| 389 | getElementById | pointsHint | `getElementById('pointsHint')` |
| 393 | classList operations | - | `classList.toggle('on')` |
| 400 | classList operations | - | `classList.toggle('on')` |
| 406 | getElementById | cList | `getElementById('cList')` |
| 407 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 408 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 409 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 410 | getElementById | metaCmt | `getElementById('metaCmt')` |
| 422 | event delegation selectors | .c-like | `addEventListener('click',function(){ if(window.__REAL_COMMUNITY__) return; var t=cmtInput.value.trim(); if(!t){cmtInput.focus();return;} addComment(t); pointsHint.style.display='inline-flex';setTimeout(function(){pointsHint.style.display='none'},1800); }); /* 评论点赞（事件委托） */ cList.addEventListener('click',function(e){ if(window.__REAL_COMMUNITY__) return; var b=e.target.closest('.c-like')` |
| 430 | event delegation selectors | .c-like | `addEventListener('click',function(e){ if(window.__REAL_COMMUNITY__) return; var b=e.target.closest('.c-like')` |
| 431 | closest | .c-like | `closest('.c-like')` |
| 433 | classList operations | - | `classList.toggle('on')` |
| 434 | querySelector | b | `querySelector('b')` |
| 439 | getElementById | page | `getElementById('page')` |
| 440 | getElementById | comments | `getElementById('comments')` |
| 457 | querySelector | .back-row | `querySelector('.back-row')` |
| 458 | querySelector | .badges | `querySelector('.badges')` |
| 459 | querySelector | .post-title | `querySelector('.post-title')` |
| 460 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 461 | querySelector | .actions | `querySelector('.actions')` |
| 462 | querySelector | .body-card | `querySelector('.body-card')` |
| 474 | getElementById | pager | `getElementById('pager')` |
| 478 | getElementById | actions | `getElementById('actions')` |
| 483 | querySelector | .body-card | `querySelector('.body-card')` |
| 484 | querySelector | .badges | `querySelector('.badges')` |
| 486 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 488 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 489 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 492 | getElementById | pager | `getElementById('pager')` |
| 495 | querySelector | .back-row | `querySelector('.back-row')` |
| 496 | querySelector | .badges | `querySelector('.badges')` |
| 497 | querySelector | .post-title | `querySelector('.post-title')` |
| 498 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 499 | querySelector | .actions | `querySelector('.actions')` |
| 500 | querySelector | .body-card | `querySelector('.body-card')` |
| 511 | querySelector | [data-sk] | `querySelector('[data-sk]')` |
| 512 | querySelector | [data-st] | `querySelector('[data-st]')` |
| 513 | querySelector | [data-lock] | `querySelector('[data-lock]')` |
| 514 | querySelector | .back-row | `querySelector('.back-row')` |
| 515 | querySelector | .badges | `querySelector('.badges')` |
| 516 | querySelector | .post-title | `querySelector('.post-title')` |
| 517 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 518 | querySelector | .actions | `querySelector('.actions')` |
| 519 | querySelector | .actions | `querySelector('.actions')` |
| 520 | querySelector | .body-card | `querySelector('.body-card')` |
| 521 | querySelector | .badges | `querySelector('.badges')` |
| 522 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 524 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 525 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 528 | getElementById | pager | `getElementById('pager')` |
| 540 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 574 | getElementById | likeBtn | `getElementById("likeBtn")` |
| 574 | getElementById | likeCnt | `getElementById("likeCnt")` |
| 574 | getElementById | metaLike | `getElementById("metaLike")` |
| 575 | getElementById | favBtn | `getElementById("favBtn")` |
| 575 | getElementById | favCnt | `getElementById("favCnt")` |
| 575 | getElementById | metaFav | `getElementById("metaFav")` |
| 576 | getElementById | cList | `getElementById("cList")` |
| 576 | getElementById | cmtInput | `getElementById("cmtInput")` |
| 576 | getElementById | cmtSubmit | `getElementById("cmtSubmit")` |
| 577 | getElementById | cmtTotal | `getElementById("cmtTotal")` |
| 577 | getElementById | metaCmt | `getElementById("metaCmt")` |
| 577 | getElementById | pointsHint | `getElementById("pointsHint")` |
| 578 | getElementById | bodyCard | `getElementById("bodyCard")` |
| 578 | getElementById | mdBody | `getElementById("mdBody")` |
| 579 | getElementById | badges | `getElementById("badges")` |
| 579 | getElementById | actions | `getElementById("actions")` |
| 579 | getElementById | postTitle | `getElementById("postTitle")` |
| 579 | getElementById | postMeta | `getElementById("postMeta")` |
| 580 | getElementById | page | `getElementById("page")` |
| 583 | classList operations | - | `classList.toggle("on", !!on)` |
| 585 | querySelector | #pager .total | `querySelector("#pager .total")` |
| 588 | getElementById | cmtErr | `getElementById("cmtErr")` |
| 592 | getElementById | composer | `getElementById("composer")` |
| 607 | parentNode / nextSibling family | - | `.parentNode` |
| 607 | parentNode / nextSibling family | - | `.parentNode` |
| 608 | parentNode / nextSibling family | - | `.parentNode` |
| 608 | querySelectorAll | [data-st] | `querySelectorAll("[data-st]")` |
| 616 | getElementById | backListBtn | `getElementById("backListBtn")` |
| 618 | getElementById | retryLoadBtn | `getElementById("retryLoadBtn")` |
| 631 | querySelector | .who | `querySelector(".who")` |
| 632 | parentNode / nextSibling family | - | `.children` |
| 632 | parentNode / nextSibling family | - | `.children` |
| 633 | parentNode / nextSibling family | - | `.children` |
| 633 | parentNode / nextSibling family | - | `.children` |
| 640 | getElementById | comments | `getElementById("comments")` |
| 660 | getElementById | pager | `getElementById("pager")` |
| 674 | querySelectorAll | .pager-btn | `querySelectorAll(".pager-btn")` |
| 693 | getElementById | cRetryBtn | `getElementById("cRetryBtn")` |
| 708 | classList operations | - | `classList.contains("on")` |
| 724 | event delegation selectors | .c-like | `addEventListener("click", function () { var t = (cmtInput.value \|\| "").trim(); if (!t) { cmtInput.focus(); flash("评论不能为空"); return; } if (cmtSubmit.disabled) return; // 防抖 cmtSubmit.disabled = true; flash(""); EAPI.post("/api/community/posts/" + pid + "/comments", { content_md: t }).then(function (resp) { cmtInput.value = ""; var lastPage = Math.max(1, Math.ceil((lastCmtTotal + 1) / PAGE_SIZE)); return loadComments(lastPage).then(function () { hint(); if (resp && resp.points) flash("评论成功（+" + resp.points + " 积分）"); }); }).catch(function (e) { flash("发布失败：" + ((e && e.message) \|\| "网络错误")); }) .` |
| 738 | event delegation selectors | .c-like | `addEventListener("click", function (e) { var b = e.target.closest(".c-like")` |
| 739 | closest | .c-like | `closest(".c-like")` |
| 741 | classList operations | - | `classList.contains("on")` |
| 742 | querySelector | b | `querySelector("b")` |
| 756 | classList operations | - | `classList.add('open')` |
| 756 | classList operations | - | `classList.add('open')` |
| 756 | classList operations | - | `classList.remove('open')` |
| 756 | classList operations | - | `classList.remove('open')` |
| 756 | classList operations | - | `classList.contains('open')` |
| 756 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 756 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 756 | getElementById | gnav | `getElementById('gnav')` |

## community.html

Total hooks: 48

| Category | Count |
|---|---:|
| getElementById | 19 |
| querySelector | 6 |
| querySelectorAll | 5 |
| classList operations | 15 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 372 | classList operations | - | `classList.add('open')` |
| 372 | classList operations | - | `classList.add('open')` |
| 372 | classList operations | - | `classList.remove('open')` |
| 372 | classList operations | - | `classList.remove('open')` |
| 372 | classList operations | - | `classList.contains('open')` |
| 372 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 372 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 372 | getElementById | gnav | `getElementById('gnav')` |
| 379 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 402 | getElementById | boards | `getElementById("boards")` |
| 403 | getElementById | total | `getElementById("total")` |
| 419 | classList operations | - | `classList.toggle("on", !!liked)` |
| 450 | event delegation selectors | .like-btn | `addEventListener("click", function (e) { var lb = e.target.closest(".like-btn")` |
| 451 | closest | .like-btn | `closest(".like-btn")` |
| 453 | closest | .post | `closest(".post")` |
| 462 | classList operations | - | `classList.contains("on")` |
| 463 | querySelector | i | `querySelector("i")` |
| 484 | getElementById | kw | `getElementById("kw")` |
| 485 | getElementById | sort | `getElementById("sort")` |
| 496 | querySelector | .mine b | `querySelector(".mine b")` |
| 503 | getElementById | retryLoad | `getElementById("retryLoad")` |
| 512 | getElementById | pager | `getElementById("pager")` |
| 525 | getElementById | total | `getElementById("total")` |
| 526 | querySelectorAll | .pager-btn | `querySelectorAll(".pager-btn")` |
| 538 | querySelectorAll | #chips .chip | `querySelectorAll("#chips .chip")` |
| 539 | classList operations | - | `classList.remove("on")` |
| 539 | classList operations | - | `classList.add("on")` |
| 567 | getElementById | pmTitle | `getElementById("pmTitle")` |
| 567 | getElementById | pmContent | `getElementById("pmContent")` |
| 568 | getElementById | pmTags | `getElementById("pmTags")` |
| 568 | getElementById | pmErr | `getElementById("pmErr")` |
| 568 | querySelector | .pm-submit | `querySelector(".pm-submit")` |
| 569 | classList operations | - | `classList.remove("open")` |
| 570 | querySelector | .pm-mask | `querySelector(".pm-mask")` |
| 571 | querySelector | .pm-cancel | `querySelector(".pm-cancel")` |
| 572 | querySelector | .pm-x | `querySelector(".pm-x")` |
| 573 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 575 | classList operations | - | `classList.remove("on")` |
| 575 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 576 | classList operations | - | `classList.add("on")` |
| 586 | classList operations | - | `classList.remove("open")` |
| 599 | classList operations | - | `classList.toggle("on", c.dataset.bc === def)` |
| 599 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 601 | classList operations | - | `classList.add("open")` |
| 603 | getElementById | - | `getElementById(id)` |
| 604 | getElementById | go | `getElementById("go")` |
| 605 | getElementById | sort | `getElementById("sort")` |
| 606 | getElementById | kw | `getElementById("kw")` |

## coupons.html

Total hooks: 31

| Category | Count |
|---|---:|
| getElementById | 14 |
| querySelector | 2 |
| querySelectorAll | 2 |
| classList operations | 12 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 1 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 263 | classList operations | - | `classList.add('open')` |
| 263 | classList operations | - | `classList.add('open')` |
| 263 | classList operations | - | `classList.remove('open')` |
| 263 | classList operations | - | `classList.remove('open')` |
| 263 | classList operations | - | `classList.contains('open')` |
| 263 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 263 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 263 | getElementById | gnav | `getElementById('gnav')` |
| 273 | getElementById | cpStage | `getElementById("cpStage")` |
| 274 | getElementById | cpPager | `getElementById("cpPager")` |
| 275 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 276 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 277 | getElementById | pgNext | `getElementById("pgNext")` |
| 404 | dynamic/template selectors | - | `querySelector('.tab[data-status="' + status + '"]')` |
| 404 | querySelector | - | `querySelector('.tab[data-status="' + status + '"]')` |
| 406 | querySelector | .cnt | `querySelector(".cnt")` |
| 427 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 429 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 430 | classList operations | - | `classList.remove("on")` |
| 433 | classList operations | - | `classList.add("on")` |
| 495 | classList operations | - | `classList.add("show")` |
| 497 | classList operations | - | `classList.remove("show")` |
| 501 | getElementById | tplStage | `getElementById("tplStage")` |
| 640 | getElementById | omOverlay | `getElementById("omOverlay")` |
| 641 | getElementById | omBody | `getElementById("omBody")` |
| 642 | getElementById | omTitle | `getElementById("omTitle")` |
| 643 | getElementById | omClose | `getElementById("omClose")` |
| 717 | classList operations | - | `classList.add("open")` |
| 722 | classList operations | - | `classList.remove("open")` |
| 975 | classList operations | - | `classList.contains("open")` |
| 987 | getElementById | adminEntry | `getElementById("adminEntry")` |

## course-detail.html

Total hooks: 96

| Category | Count |
|---|---:|
| getElementById | 37 |
| querySelector | 14 |
| querySelectorAll | 14 |
| classList operations | 16 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 3 |
| dynamic/template selectors | 1 |
| form.elements / name / tagName | 4 |
| parentNode / nextSibling family | 5 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 518 | getElementById | couponList | `getElementById("couponList")` |
| 530 | querySelectorAll | button[data-get] | `querySelectorAll("button[data-get]")` |
| 533 | getElementById | summary | `getElementById("summary")` |
| 536 | classList operations | - | `classList.toggle("open",open)` |
| 536 | getElementById | couponOverlay | `getElementById("couponOverlay")` |
| 537 | getElementById | couponClose | `getElementById("couponClose")` |
| 538 | getElementById | couponDone | `getElementById("couponDone")` |
| 539 | getElementById | couponOverlay | `getElementById("couponOverlay")` |
| 702 | getElementById | enrollBtn | `getElementById("enrollBtn")` |
| 711 | getElementById | favBtn | `getElementById("favBtn")` |
| 712 | event delegation selectors | .cohort | `addEventListener("click",function(){ if(!authed){ alert("未登录：收藏 → /login?redirect=/courses/1001（J5）"); return; } favorited=!favorited; this.setAttribute("aria-pressed",String(favorited)); this.innerHTML=favorited?"♥":"♡"; alert(favorited?"POST /api/favorites/1001（favorite_source=series_detail）":"已取消收藏（J2）"); }); } function bindCohorts(){ const list=document.getElementById("cohortList"); if(!list) return; list.addEventListener("click",e=>{ const b=e.target.closest(".cohort")` |
| 721 | getElementById | cohortList | `getElementById("cohortList")` |
| 722 | event delegation selectors | .cohort | `addEventListener("click",e=>{ const b=e.target.closest(".cohort")` |
| 723 | classList operations | - | `classList.contains("disabled")` |
| 723 | closest | .cohort | `closest(".cohort")` |
| 729 | querySelectorAll | #tablist .tab | `querySelectorAll("#tablist .tab")` |
| 730 | classList operations | - | `classList.toggle("on",x===t)` |
| 730 | querySelectorAll | #tablist .tab | `querySelectorAll("#tablist .tab")` |
| 731 | classList operations | - | `classList.toggle("active",p.dataset.panel===t.dataset.tab)` |
| 731 | querySelectorAll | [data-panel] | `querySelectorAll("[data-panel]")` |
| 733 | querySelectorAll | [data-panel=outline] .lvl[data-lvl=module] | `querySelectorAll("[data-panel=outline] .lvl[data-lvl=module]")` |
| 734 | classList operations | - | `classList.toggle("open")` |
| 735 | classList operations | - | `classList.toggle("open",open)` |
| 735 | parentNode / nextSibling family | - | `.nextElementSibling` |
| 735 | parentNode / nextSibling family | - | `.nextElementSibling` |
| 739 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 745 | querySelectorAll | #cohortList .go-learn | `querySelectorAll("#cohortList .go-learn")` |
| 779 | getElementById | mainArea | `getElementById("mainArea")` |
| 795 | classList operations | - | `classList.toggle("on",b.dataset[k]===val)` |
| 795 | dynamic/template selectors | - | `querySelectorAll(\`.toolbar button[data-${k}]\`)` |
| 795 | querySelectorAll | - | `querySelectorAll(\`.toolbar button[data-${k}]\`)` |
| 796 | querySelectorAll | .toolbar button[data-s] | `querySelectorAll(".toolbar button[data-s]")` |
| 797 | querySelectorAll | .toolbar button[data-auth] | `querySelectorAll(".toolbar button[data-auth]")` |
| 798 | classList operations | - | `classList.toggle("on",x===b)` |
| 798 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 798 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 799 | classList operations | - | `classList.remove("on")` |
| 799 | getElementById | resetVp | `getElementById("resetVp")` |
| 799 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 806 | classList operations | - | `classList.add('open')` |
| 806 | classList operations | - | `classList.add('open')` |
| 806 | classList operations | - | `classList.remove('open')` |
| 806 | classList operations | - | `classList.remove('open')` |
| 806 | classList operations | - | `classList.contains('open')` |
| 806 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 806 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 806 | getElementById | gnav | `getElementById('gnav')` |
| 813 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 837 | getElementById | mainArea | `getElementById("mainArea")` |
| 877 | parentNode / nextSibling family | - | `.parentNode` |
| 889 | querySelector | .dialog-x | `querySelector(".dialog-x")` |
| 895 | querySelector | #realDlgTitle | `querySelector("#realDlgTitle")` |
| 896 | querySelector | #realDlgBody | `querySelector("#realDlgBody")` |
| 897 | querySelector | #realDlgFoot | `querySelector("#realDlgFoot")` |
| 898 | classList operations | - | `classList.add("open")` |
| 901 | classList operations | - | `classList.remove("open")` |
| 916 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 917 | parentNode / nextSibling family | - | `.parentNode` |
| 919 | getElementById | myCouponEntry | `getElementById("myCouponEntry")` |
| 924 | parentNode / nextSibling family | - | `.nextSibling` |
| 940 | getElementById | couponList | `getElementById("couponList")` |
| 957 | getElementById | couponList | `getElementById("couponList")` |
| 977 | querySelectorAll | button[data-tpl] | `querySelectorAll("button[data-tpl]")` |
| 998 | getElementById | couponList | `getElementById("couponList")` |
| 1000 | getElementById | couponDlgErr | `getElementById("couponDlgErr")` |
| 1010 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 1014 | getElementById | couponList | `getElementById("couponList")` |
| 1017 | getElementById | couponLoginBtn | `getElementById("couponLoginBtn")` |
| 1056 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1071 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1075 | getElementById | enrollBtn | `getElementById("enrollBtn")` |
| 1107 | getElementById | writeReviewBtn | `getElementById("writeReviewBtn")` |
| 1111 | querySelector | [data-panel=review] | `querySelector("[data-panel=review]")` |
| 1130 | querySelector | #tablist .tab[data-tab="review"] | `querySelector('#tablist .tab[data-tab="review"]')` |
| 1134 | querySelector | [data-panel=review] | `querySelector("[data-panel=review]")` |
| 1144 | getElementById | rvLoginBtn | `getElementById("rvLoginBtn")` |
| 1170 | getElementById | starPick | `getElementById("starPick")` |
| 1180 | querySelectorAll | button[data-star] | `querySelectorAll("button[data-star]")` |
| 1200 | getElementById | reviewSubmit | `getElementById("reviewSubmit")` |
| 1206 | getElementById | reviewSubmit | `getElementById("reviewSubmit")` |
| 1207 | getElementById | reviewContent | `getElementById("reviewContent")` |
| 1208 | getElementById | reviewErr | `getElementById("reviewErr")` |
| 1225 | event delegation selectors | #tablist .tab[data-tab="review"] | `addEventListener("click", function (e) { if (!e.target \|\| !e.target.closest) return; if (e.target.closest('#tablist .tab[data-tab="review"]')` |
| 1227 | closest | #tablist .tab[data-tab="review"] | `closest('#tablist .tab[data-tab="review"]')` |
| 1237 | getElementById | favBtn | `getElementById("favBtn")` |
| 1246 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1260 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1268 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1280 | getElementById | favBtn | `getElementById("favBtn")` |
| 1298 | form.elements / name / tagName | - | `.name` |
| 1302 | form.elements / name / tagName | - | `.name` |
| 1311 | querySelector | h1.title,.title | `querySelector("h1.title,.title")` |
| 1312 | form.elements / name / tagName | - | `.name` |
| 1315 | querySelector | .breadcrumb .cur | `querySelector(".breadcrumb .cur")` |
| 1316 | form.elements / name / tagName | - | `.name` |
| 1317 | getElementById | crumbCat | `getElementById("crumbCat")` |

## courses.html

Total hooks: 70

| Category | Count |
|---|---:|
| getElementById | 45 |
| querySelector | 0 |
| querySelectorAll | 4 |
| classList operations | 10 |
| closest | 4 |
| matches | 0 |
| event delegation selectors | 7 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 598 | getElementById | categoryRow | `getElementById("categoryRow")` |
| 604 | getElementById | subGroup | `getElementById("subGroup")` |
| 604 | getElementById | subRow | `getElementById("subRow")` |
| 620 | getElementById | fbSummary | `getElementById("fbSummary")` |
| 623 | classList operations | - | `classList.toggle("active",c===el)` |
| 623 | getElementById | - | `getElementById(rowId)` |
| 623 | querySelectorAll | .chip | `querySelectorAll(".chip")` |
| 707 | getElementById | resText | `getElementById("resText")` |
| 716 | getElementById | contentArea | `getElementById("contentArea")` |
| 730 | getElementById | contentArea | `getElementById("contentArea")` |
| 731 | getElementById | pgPages | `getElementById("pgPages")` |
| 732 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 736 | getElementById | contentArea | `getElementById("contentArea")` |
| 737 | getElementById | pgPages | `getElementById("pgPages")` |
| 738 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 745 | getElementById | contentArea | `getElementById("contentArea")` |
| 746 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 746 | getElementById | pgPages | `getElementById("pgPages")` |
| 752 | getElementById | pgPages | `getElementById("pgPages")` |
| 759 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 760 | getElementById | pgNext | `getElementById("pgNext")` |
| 761 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 764 | event delegation selectors | .chip | `addEventListener("click",()=>{ if(page>1){page--; refresh();} }); document.getElementById("pgNext").addEventListener("click",()=>{ if(page<totalPages){page++; refresh();} }); /* ---- 事件绑定 ---- */ document.getElementById("fbToggle").addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 764 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 765 | event delegation selectors | .chip | `addEventListener("click",()=>{ if(page<totalPages){page++; refresh();} }); /* ---- 事件绑定 ---- */ document.getElementById("fbToggle").addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 765 | getElementById | pgNext | `getElementById("pgNext")` |
| 768 | event delegation selectors | .chip | `addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 768 | getElementById | fbToggle | `getElementById("fbToggle")` |
| 769 | classList operations | - | `classList.toggle("open")` |
| 769 | getElementById | filterBar | `getElementById("filterBar")` |
| 770 | getElementById | fbToggle | `getElementById("fbToggle")` |
| 772 | closest | .chip | `closest(".chip")` |
| 772 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 772 | getElementById | categoryRow | `getElementById("categoryRow")` |
| 773 | closest | .chip | `closest(".chip")` |
| 773 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 773 | getElementById | subRow | `getElementById("subRow")` |
| 774 | closest | .chip | `closest(".chip")` |
| 774 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 774 | getElementById | deliveryRow | `getElementById("deliveryRow")` |
| 775 | closest | .chip | `closest(".chip")` |
| 775 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 775 | getElementById | sortRow | `getElementById("sortRow")` |
| 776 | getElementById | priceSelect | `getElementById("priceSelect")` |
| 778 | getElementById | searchInput | `getElementById("searchInput")` |
| 780 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 784 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 784 | getElementById | searchInput | `getElementById("searchInput")` |
| 784 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 787 | classList operations | - | `classList.toggle("active",c.dataset.v==="全部")` |
| 787 | querySelectorAll | #categoryRow .chip | `querySelectorAll("#categoryRow .chip")` |
| 788 | classList operations | - | `classList.toggle("active",c.dataset.v==="")` |
| 788 | querySelectorAll | #deliveryRow .chip | `querySelectorAll("#deliveryRow .chip")` |
| 789 | classList operations | - | `classList.toggle("active",c.dataset.v==="default")` |
| 789 | querySelectorAll | #sortRow .chip | `querySelectorAll("#sortRow .chip")` |
| 790 | getElementById | priceSelect | `getElementById("priceSelect")` |
| 790 | getElementById | searchInput | `getElementById("searchInput")` |
| 790 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 794 | getElementById | resetBtn | `getElementById("resetBtn")` |
| 805 | getElementById | - | `getElementById(id)` |
| 814 | getElementById | xpFill | `getElementById("xpFill")` |
| 826 | classList operations | - | `classList.add('open')` |
| 826 | classList operations | - | `classList.add('open')` |
| 826 | classList operations | - | `classList.remove('open')` |
| 826 | classList operations | - | `classList.remove('open')` |
| 826 | classList operations | - | `classList.contains('open')` |
| 826 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 826 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 826 | getElementById | gnav | `getElementById('gnav')` |
| 832 | getElementById | adminEntry | `getElementById("adminEntry")` |

## dashboard.html

Total hooks: 15

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 2 |
| querySelectorAll | 4 |
| classList operations | 5 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 533 | getElementById | - | `getElementById(id)` |
| 537 | querySelectorAll | .v-loading | `querySelectorAll(".v-loading")` |
| 538 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 543 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 717 | querySelector | p | `querySelector("p")` |
| 728 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 729 | querySelector | .v-error | `querySelector(".v-error")` |
| 738 | classList operations | - | `classList.add('open')` |
| 738 | classList operations | - | `classList.add('open')` |
| 738 | classList operations | - | `classList.remove('open')` |
| 738 | classList operations | - | `classList.remove('open')` |
| 738 | classList operations | - | `classList.contains('open')` |
| 738 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 738 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 738 | getElementById | gnav | `getElementById('gnav')` |

## favorites.html

Total hooks: 14

| Category | Count |
|---|---:|
| getElementById | 9 |
| querySelector | 0 |
| querySelectorAll | 0 |
| classList operations | 5 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 140 | classList operations | - | `classList.add('open')` |
| 140 | classList operations | - | `classList.add('open')` |
| 140 | classList operations | - | `classList.remove('open')` |
| 140 | classList operations | - | `classList.remove('open')` |
| 140 | classList operations | - | `classList.contains('open')` |
| 140 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 140 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 140 | getElementById | gnav | `getElementById('gnav')` |
| 150 | getElementById | favStage | `getElementById("favStage")` |
| 151 | getElementById | favPager | `getElementById("favPager")` |
| 152 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 153 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 154 | getElementById | pgNext | `getElementById("pgNext")` |
| 269 | getElementById | adminEntry | `getElementById("adminEntry")` |

## learning.html

Total hooks: 18

| Category | Count |
|---|---:|
| getElementById | 1 |
| querySelector | 5 |
| querySelectorAll | 4 |
| classList operations | 4 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 2 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 2 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 533 | querySelectorAll | .tab | `querySelectorAll('.tab')` |
| 534 | querySelectorAll | .tab-panel | `querySelectorAll('.tab-panel')` |
| 536 | classList operations | - | `classList.toggle('on',idx===i)` |
| 537 | classList operations | - | `classList.toggle('active',idx===i)` |
| 559 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 578 | querySelector | h1,.title,[class*=title] | `querySelector("h1,.title,[class*=title]")` |
| 602 | dynamic/template selectors | - | `querySelector(s)` |
| 602 | querySelector | - | `querySelector(s)` |
| 603 | dynamic/template selectors | - | `querySelectorAll(s)` |
| 603 | querySelectorAll | - | `querySelectorAll(s)` |
| 629 | querySelector | .spinner | `querySelector(".spinner")` |
| 705 | querySelectorAll | .acc-head | `querySelectorAll(".acc-head")` |
| 707 | parentNode / nextSibling family | - | `.parentNode` |
| 708 | classList operations | - | `classList.contains("open")` |
| 709 | classList operations | - | `classList.toggle("open", open)` |
| 711 | querySelector | .acc-ind | `querySelector(".acc-ind")` |
| 747 | querySelector | video.real-video | `querySelector("video.real-video")` |
| 819 | parentNode / nextSibling family | - | `.parentNode` |

## login-register.html

Total hooks: 41

| Category | Count |
|---|---:|
| getElementById | 23 |
| querySelector | 0 |
| querySelectorAll | 5 |
| classList operations | 11 |
| closest | 1 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 2915 | classList operations | - | `classList.toggle("on", b.dataset.page===p)` |
| 2915 | querySelectorAll | #page-seg button | `querySelectorAll("#page-seg button")` |
| 2916 | classList operations | - | `classList.toggle("hidden", p!=="login")` |
| 2916 | getElementById | login-form | `getElementById("login-form")` |
| 2917 | classList operations | - | `classList.toggle("hidden", p!=="register")` |
| 2917 | getElementById | reg-form | `getElementById("reg-form")` |
| 2918 | getElementById | card-title | `getElementById("card-title")` |
| 2919 | getElementById | card-sub | `getElementById("card-sub")` |
| 2920 | getElementById | card-foot | `getElementById("card-foot")` |
| 2927 | classList operations | - | `classList.remove("show")` |
| 2927 | querySelectorAll | .banner | `querySelectorAll(".banner")` |
| 2928 | classList operations | - | `classList.remove("show")` |
| 2928 | querySelectorAll | .ferr | `querySelectorAll(".ferr")` |
| 2929 | classList operations | - | `classList.remove("err")` |
| 2929 | querySelectorAll | .ctl input | `querySelectorAll(".ctl input")` |
| 2943 | getElementById | li-banner-t | `getElementById("li-banner-t")` |
| 2944 | classList operations | - | `classList.add("show")` |
| 2944 | getElementById | li-banner | `getElementById("li-banner")` |
| 2947 | getElementById | rg-conflict-t | `getElementById("rg-conflict-t")` |
| 2948 | classList operations | - | `classList.add("show")` |
| 2948 | getElementById | rg-conflict | `getElementById("rg-conflict")` |
| 2977 | getElementById | - | `getElementById(hit.ferr)` |
| 2978 | getElementById | - | `getElementById(hit.input)` |
| 2979 | classList operations | - | `classList.add("show")` |
| 2980 | classList operations | - | `classList.add("err")` |
| 2996 | classList operations | - | `classList.toggle("busy", !!on)` |
| 3005 | getElementById | login-btn | `getElementById("login-btn")` |
| 3006 | getElementById | li-id | `getElementById("li-id")` |
| 3007 | getElementById | li-pwd | `getElementById("li-pwd")` |
| 3032 | getElementById | reg-btn | `getElementById("reg-btn")` |
| 3033 | getElementById | rg-u | `getElementById("rg-u")` |
| 3034 | getElementById | rg-n | `getElementById("rg-n")` |
| 3035 | getElementById | rg-e | `getElementById("rg-e")` |
| 3036 | getElementById | rg-p | `getElementById("rg-p")` |
| 3037 | getElementById | rg-c | `getElementById("rg-c")` |
| 3068 | getElementById | li-id | `getElementById("li-id")` |
| 3080 | event delegation selectors | [data-page] | `addEventListener("click",function(e){ var b=e.target.closest("[data-page]")` |
| 3080 | getElementById | page-seg | `getElementById("page-seg")` |
| 3081 | closest | [data-page] | `closest("[data-page]")` |
| 3083 | querySelectorAll | [data-eye] | `querySelectorAll("[data-eye]")` |
| 3084 | getElementById | - | `getElementById(this.dataset.eye)` |

## me.html

Total hooks: 74

| Category | Count |
|---|---:|
| getElementById | 51 |
| querySelector | 4 |
| querySelectorAll | 1 |
| classList operations | 18 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 4390 | classList operations | - | `classList.add('open')` |
| 4390 | classList operations | - | `classList.add('open')` |
| 4390 | classList operations | - | `classList.remove('open')` |
| 4390 | classList operations | - | `classList.remove('open')` |
| 4390 | classList operations | - | `classList.contains('open')` |
| 4390 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 4390 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 4390 | getElementById | gnav | `getElementById('gnav')` |
| 4399 | getElementById | - | `getElementById(id)` |
| 4407 | getElementById | me-prefs | `getElementById("me-prefs")` |
| 4410 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 4440 | getElementById | pfForm | `getElementById("pfForm")` |
| 4442 | getElementById | pfErr | `getElementById("pfErr")` |
| 4443 | getElementById | emToast | `getElementById("emToast")` |
| 4444 | getElementById | pfSave | `getElementById("pfSave")` |
| 4458 | classList operations | - | `classList.add("show")` |
| 4459 | classList operations | - | `classList.remove("show")` |
| 4461 | classList operations | - | `classList.add("show")` |
| 4462 | classList operations | - | `classList.remove("show")` |
| 4465 | getElementById | pf-grade_code | `getElementById("pf-grade_code")` |
| 4482 | getElementById | pf-goals | `getElementById("pf-goals")` |
| 4493 | classList operations | - | `classList.toggle("on")` |
| 4500 | getElementById | pf-nickname | `getElementById("pf-nickname")` |
| 4502 | getElementById | pf-school_name | `getElementById("pf-school_name")` |
| 4503 | getElementById | pf-study_style | `getElementById("pf-study_style")` |
| 4504 | getElementById | pf-weekly | `getElementById("pf-weekly")` |
| 4514 | getElementById | pf-nickname | `getElementById("pf-nickname")` |
| 4517 | getElementById | pf-grade_code | `getElementById("pf-grade_code")` |
| 4519 | getElementById | pf-school_name | `getElementById("pf-school_name")` |
| 4521 | getElementById | pf-study_style | `getElementById("pf-study_style")` |
| 4523 | getElementById | pf-weekly | `getElementById("pf-weekly")` |
| 4528 | querySelectorAll | #pf-goals .pf-goal.on | `querySelectorAll("#pf-goals .pf-goal.on")` |
| 4540 | getElementById | me-goal | `getElementById("me-goal")` |
| 4598 | getElementById | emOverlay | `getElementById("emOverlay")` |
| 4599 | getElementById | emForm | `getElementById("emForm")` |
| 4600 | getElementById | emErr | `getElementById("emErr")` |
| 4601 | getElementById | emToast | `getElementById("emToast")` |
| 4605 | getElementById | - | `getElementById(id)` |
| 4606 | getElementById | - | `getElementById(id)` |
| 4624 | classList operations | - | `classList.remove("show")` |
| 4638 | classList operations | - | `classList.add("open")` |
| 4643 | classList operations | - | `classList.remove("open")` |
| 4645 | classList operations | - | `classList.add("show")` |
| 4647 | classList operations | - | `classList.add("show")` |
| 4648 | classList operations | - | `classList.remove("show")` |
| 4651 | getElementById | me-name | `getElementById("me-name")` |
| 4652 | querySelector | .me-head .avatar | `querySelector(".me-head .avatar")` |
| 4654 | getElementById | me-prefs | `getElementById("me-prefs")` |
| 4663 | classList operations | - | `classList.remove("show")` |
| 4666 | getElementById | em-nickname | `getElementById("em-nickname")` |
| 4668 | getElementById | em-gender | `getElementById("em-gender")` |
| 4670 | getElementById | em-birthday | `getElementById("em-birthday")` |
| 4675 | getElementById | em-grade_code | `getElementById("em-grade_code")` |
| 4682 | getElementById | em-avatar_url | `getElementById("em-avatar_url")` |
| 4684 | getElementById | em-learning_goals | `getElementById("em-learning_goals")` |
| 4686 | getElementById | em-subject_preferences | `getElementById("em-subject_preferences")` |
| 4688 | getElementById | em-interest_tags | `getElementById("em-interest_tags")` |
| 4697 | classList operations | - | `classList.remove("open")` |
| 4706 | querySelector | .edit-btn | `querySelector(".edit-btn")` |
| 4708 | getElementById | emClose | `getElementById("emClose")` |
| 4709 | getElementById | emCancel | `getElementById("emCancel")` |
| 4740 | querySelector | .t10-retry | `querySelector(".t10-retry")` |
| 4750 | getElementById | odList | `getElementById("odList")` |
| 4750 | getElementById | odMeta | `getElementById("odMeta")` |
| 4751 | getElementById | odPrev | `getElementById("odPrev")` |
| 4751 | getElementById | odNext | `getElementById("odNext")` |
| 4752 | getElementById | odStatus | `getElementById("odStatus")` |
| 4795 | getElementById | cpList | `getElementById("cpList")` |
| 4795 | getElementById | cpMeta | `getElementById("cpMeta")` |
| 4796 | getElementById | cpPrev | `getElementById("cpPrev")` |
| 4796 | getElementById | cpNext | `getElementById("cpNext")` |
| 4835 | getElementById | fvList | `getElementById("fvList")` |
| 4835 | getElementById | fvMeta | `getElementById("fvMeta")` |
| 4865 | querySelector | .me-head .avatar | `querySelector(".me-head .avatar")` |

## my-cohorts.html

Total hooks: 28

| Category | Count |
|---|---:|
| getElementById | 13 |
| querySelector | 4 |
| querySelectorAll | 1 |
| classList operations | 10 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 567 | querySelectorAll | .tab | `querySelectorAll('.tab')` |
| 568 | getElementById | tab-active | `getElementById('tab-active')` |
| 568 | getElementById | tab-completed | `getElementById('tab-completed')` |
| 568 | getElementById | tab-refunded | `getElementById('tab-refunded')` |
| 570 | classList operations | - | `classList.remove('on')` |
| 571 | classList operations | - | `classList.add('on')` |
| 572 | classList operations | - | `classList.toggle('active', k === t.dataset.tab)` |
| 586 | classList operations | - | `classList.add('open')` |
| 586 | classList operations | - | `classList.add('open')` |
| 586 | classList operations | - | `classList.remove('open')` |
| 586 | classList operations | - | `classList.remove('open')` |
| 586 | classList operations | - | `classList.contains('open')` |
| 586 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 586 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 586 | getElementById | gnav | `getElementById('gnav')` |
| 593 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 638 | getElementById | - | `getElementById("panel-" + p)` |
| 643 | querySelector | #panel-empty .btn | `querySelector("#panel-empty .btn")` |
| 645 | querySelector | #panel-error .btn | `querySelector("#panel-error .btn")` |
| 651 | getElementById | - | `getElementById("tabbtn-" + kk)` |
| 651 | getElementById | - | `getElementById("tab-" + kk)` |
| 654 | classList operations | - | `classList.toggle("on", on)` |
| 657 | classList operations | - | `classList.toggle("active", on)` |
| 672 | getElementById | - | `getElementById("tab-" + k)` |
| 672 | querySelector | .grid | `querySelector(".grid")` |
| 674 | getElementById | - | `getElementById("tabbtn-" + k)` |
| 674 | querySelector | .cnt | `querySelector(".cnt")` |
| 676 | getElementById | - | `getElementById("tab-empty-" + k)` |

## practice.html

Total hooks: 125

| Category | Count |
|---|---:|
| getElementById | 14 |
| querySelector | 28 |
| querySelectorAll | 24 |
| classList operations | 46 |
| closest | 4 |
| matches | 0 |
| event delegation selectors | 4 |
| dynamic/template selectors | 2 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 3 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 907 | getElementById | stage | `getElementById('stage')` |
| 908 | querySelectorAll | .statebar button | `querySelectorAll('.statebar button')` |
| 911 | classList operations | - | `classList.remove('on')` |
| 912 | classList operations | - | `classList.add('on')` |
| 913 | getElementById | - | `getElementById(id)` |
| 917 | querySelectorAll | .q-typebar button | `querySelectorAll('.q-typebar button')` |
| 919 | classList operations | - | `classList.remove('on')` |
| 920 | classList operations | - | `classList.add('on')` |
| 921 | classList operations | - | `classList.add('hid')` |
| 921 | querySelectorAll | .quiz-item | `querySelectorAll('.quiz-item')` |
| 922 | classList operations | - | `classList.remove('hid')` |
| 922 | getElementById | - | `getElementById('qi-' + b.dataset.type)` |
| 926 | getElementById | qi-blank-submit | `getElementById('qi-blank-submit')` |
| 927 | getElementById | qi-blank-input | `getElementById('qi-blank-input')` |
| 928 | getElementById | qi-blank-result | `getElementById('qi-blank-result')` |
| 929 | getElementById | qi-blank-analysis | `getElementById('qi-blank-analysis')` |
| 933 | classList operations | - | `classList.remove('hid')` |
| 934 | classList operations | - | `classList.toggle('ok', ok)` |
| 935 | classList operations | - | `classList.toggle('error', !ok)` |
| 936 | querySelector | .t | `querySelector('.t')` |
| 937 | querySelector | .d | `querySelector('.d')` |
| 938 | querySelector | .big | `querySelector('.big')` |
| 939 | classList operations | - | `classList.remove('hid')` |
| 940 | classList operations | - | `classList.add('gray')` |
| 940 | classList operations | - | `classList.add('hid')` |
| 945 | querySelectorAll | .judge-opt | `querySelectorAll('.judge-opt')` |
| 947 | getElementById | qi-judge-result | `getElementById('qi-judge-result')` |
| 948 | getElementById | qi-judge-analysis | `getElementById('qi-judge-analysis')` |
| 949 | classList operations | - | `classList.remove('hid')` |
| 950 | classList operations | - | `classList.toggle('ok', correct)` |
| 951 | classList operations | - | `classList.toggle('error', !correct)` |
| 952 | querySelector | .t | `querySelector('.t')` |
| 953 | querySelector | .big | `querySelector('.big')` |
| 954 | classList operations | - | `classList.remove('hid')` |
| 955 | querySelectorAll | .judge-opt | `querySelectorAll('.judge-opt')` |
| 960 | classList operations | - | `classList.add('open')` |
| 960 | classList operations | - | `classList.add('open')` |
| 960 | classList operations | - | `classList.remove('open')` |
| 960 | classList operations | - | `classList.remove('open')` |
| 960 | classList operations | - | `classList.contains('open')` |
| 960 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 960 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 960 | getElementById | gnav | `getElementById('gnav')` |
| 967 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 979 | getElementById | - | `getElementById(id)` |
| 1046 | dynamic/template selectors | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 1046 | querySelector | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 1050 | dynamic/template selectors | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 1050 | querySelector | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 1062 | querySelectorAll | #wb-real .pill | `querySelectorAll('#wb-real .pill')` |
| 1063 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { document.querySelectorAll('#wb-real .pill').forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); WB.status = b.dataset.wstatus; WB.page = 1; loadWrong(); }); }); $$('wbPrev').addEventListener('click', function () { if (WB.page > 1) { WB.page--; loadWrong(); } }); $$('wbNext').addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 1064 | classList operations | - | `classList.remove('on')` |
| 1064 | querySelectorAll | #wb-real .pill | `querySelectorAll('#wb-real .pill')` |
| 1065 | classList operations | - | `classList.add('on')` |
| 1070 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { if (WB.page > 1) { WB.page--; loadWrong(); } }); $$('wbNext').addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 1071 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 1072 | event delegation selectors | [data-wredo] | `addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 1073 | closest | [data-wredo] | `closest('[data-wredo]')` |
| 1075 | closest | tr | `closest('tr')` |
| 1075 | querySelector | .type-chip | `querySelector('.type-chip')` |
| 1085 | parentNode / nextSibling family | - | `.children` |
| 1088 | classList operations | - | `classList.remove('hid')` |
| 1211 | querySelectorAll | #rvBody .rv-opt | `querySelectorAll('#rvBody .rv-opt')` |
| 1215 | classList operations | - | `classList.remove('correct')` |
| 1215 | querySelectorAll | #rvBody .rv-opt | `querySelectorAll('#rvBody .rv-opt')` |
| 1216 | classList operations | - | `classList.add('correct')` |
| 1220 | querySelectorAll | #rvBody .rv-judge | `querySelectorAll('#rvBody .rv-judge')` |
| 1224 | classList operations | - | `classList.remove('correct')` |
| 1224 | querySelectorAll | #rvBody .rv-judge | `querySelectorAll('#rvBody .rv-judge')` |
| 1225 | classList operations | - | `classList.add('correct')` |
| 1229 | querySelectorAll | #rvBody .rv-multi | `querySelectorAll('#rvBody .rv-multi')` |
| 1232 | classList operations | - | `classList.toggle('correct')` |
| 1237 | querySelector | #rvBody .drag-list | `querySelector('#rvBody .drag-list')` |
| 1240 | parentNode / nextSibling family | - | `.children` |
| 1240 | querySelector | .idx | `querySelector('.idx')` |
| 1242 | querySelectorAll | .drag-item .mv | `querySelectorAll('.drag-item .mv')` |
| 1245 | closest | .drag-item | `closest('.drag-item')` |
| 1246 | parentNode / nextSibling family | - | `.children` |
| 1255 | querySelector | #rvBody .rv-submit | `querySelector('#rvBody .rv-submit')` |
| 1257 | querySelectorAll | #rvBody .rv-next | `querySelectorAll('#rvBody .rv-next')` |
| 1265 | querySelectorAll | #rvBody .rv-multi.correct | `querySelectorAll('#rvBody .rv-multi.correct')` |
| 1270 | querySelectorAll | #rvBody .fill-blanks input[data-fill] | `querySelectorAll('#rvBody .fill-blanks input[data-fill]')` |
| 1274 | querySelectorAll | #rvBody .drag-item | `querySelectorAll('#rvBody .drag-item')` |
| 1277 | querySelectorAll | #rvBody .match-item select[data-match] | `querySelectorAll('#rvBody .match-item select[data-match]')` |
| 1301 | querySelector | #rvBody .rv-submit | `querySelector('#rvBody .rv-submit')` |
| 1302 | classList operations | - | `classList.add('gray')` |
| 1318 | classList operations | - | `classList.remove('gray')` |
| 1319 | querySelector | #rvBody .rv-result | `querySelector('#rvBody .rv-result')` |
| 1321 | classList operations | - | `classList.remove('hid')` |
| 1321 | classList operations | - | `classList.remove('ok')` |
| 1321 | classList operations | - | `classList.add('error')` |
| 1322 | querySelector | .big | `querySelector('.big')` |
| 1323 | querySelector | .t | `querySelector('.t')` |
| 1324 | querySelector | .d | `querySelector('.d')` |
| 1329 | querySelector | #rvBody .rv-result | `querySelector('#rvBody .rv-result')` |
| 1330 | querySelector | #rvBody .rv-expl | `querySelector('#rvBody .rv-expl')` |
| 1331 | querySelector | #rvBody .rv-mast | `querySelector('#rvBody .rv-mast')` |
| 1332 | querySelector | #rvBody .rv-next | `querySelector('#rvBody .rv-next')` |
| 1334 | classList operations | - | `classList.remove('hid')` |
| 1335 | classList operations | - | `classList.toggle('ok', !!r.is_correct)` |
| 1336 | classList operations | - | `classList.toggle('error', !r.is_correct)` |
| 1337 | querySelector | .big | `querySelector('.big')` |
| 1338 | querySelector | .t | `querySelector('.t')` |
| 1341 | querySelector | .d | `querySelector('.d')` |
| 1345 | classList operations | - | `classList.remove('hid')` |
| 1347 | classList operations | - | `classList.toggle('hid', !r.explain_text)` |
| 1354 | classList operations | - | `classList.remove('hid')` |
| 1361 | classList operations | - | `classList.add('hid')` |
| 1366 | querySelectorAll | #rvBody .rv-next | `querySelectorAll('#rvBody .rv-next')` |
| 1408 | querySelectorAll | #vocabCards .word-acts button | `querySelectorAll('#vocabCards .word-acts button')` |
| 1411 | closest | .word-card | `closest('.word-card')` |
| 1415 | querySelectorAll | .word-acts button | `querySelectorAll('.word-acts button')` |
| 1418 | querySelector | .word-fb | `querySelector('.word-fb')` |
| 1427 | querySelectorAll | .word-acts button | `querySelectorAll('.word-acts button')` |
| 1428 | querySelector | .word-fb | `querySelector('.word-fb')` |
| 1469 | querySelectorAll | #topic-real .pill[data-ttype] | `querySelectorAll('#topic-real .pill[data-ttype]')` |
| 1471 | classList operations | - | `classList.remove('on')` |
| 1471 | querySelectorAll | #topic-real .pill[data-ttype] | `querySelectorAll('#topic-real .pill[data-ttype]')` |
| 1472 | classList operations | - | `classList.add('on')` |
| 1487 | classList operations | - | `classList.remove('hid')` |
| 1488 | classList operations | - | `classList.remove('hid')` |
| 1489 | classList operations | - | `classList.remove('hid')` |
| 1499 | querySelector | .entry.green .go | `querySelector('.entry.green .go')` |
| 1501 | querySelector | .entry.blue .go | `querySelector('.entry.blue .go')` |
| 1503 | querySelector | .entry.purple .go | `querySelector('.entry.purple .go')` |

## refund.html

Total hooks: 8

| Category | Count |
|---|---:|
| getElementById | 2 |
| querySelector | 0 |
| querySelectorAll | 0 |
| classList operations | 0 |
| closest | 1 |
| matches | 0 |
| event delegation selectors | 5 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 224 | getElementById | flash | `getElementById("flash")` |
| 261 | getElementById | - | `getElementById(id)` |
| 431 | event delegation selectors | [data-cancel] | `addEventListener("submit", applyRefund); $("ticketForm").addEventListener("submit", submitTicket); $("pgPrev").addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 432 | event delegation selectors | [data-cancel] | `addEventListener("submit", submitTicket); $("pgPrev").addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 433 | event delegation selectors | [data-cancel] | `addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 434 | event delegation selectors | [data-cancel] | `addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 435 | event delegation selectors | [data-cancel] | `addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 436 | closest | [data-cancel] | `closest("[data-cancel]")` |
