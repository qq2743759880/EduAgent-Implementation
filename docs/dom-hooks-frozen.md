# DOM Hooks Frozen Inventory

Generated: 2026-09-20T16:44:15.241Z

Source scope: `edu-frontend/public/*.html` (25 current pages, 1214 hook expressions).

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
| 475 | classList operations | - | `classList.add('open')` |
| 475 | classList operations | - | `classList.add('open')` |
| 475 | classList operations | - | `classList.remove('open')` |
| 475 | classList operations | - | `classList.remove('open')` |
| 475 | classList operations | - | `classList.contains('open')` |
| 475 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 475 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 475 | getElementById | gnav | `getElementById('gnav')` |
| 482 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 498 | getElementById | - | `getElementById(id)` |
| 504 | getElementById | - | `getElementById(id)` |
| 505 | getElementById | loginGate | `getElementById("loginGate")` |
| 507 | getElementById | loginGateBtn | `getElementById("loginGateBtn")` |
| 538 | querySelector | #secBadges .badge-grid | `querySelector("#secBadges .badge-grid")` |
| 540 | getElementById | badgeCount | `getElementById("badgeCount")` |
| 542 | getElementById | badgeNext | `getElementById("badgeNext")` |
| 571 | querySelector | #secPoints .total-pts | `querySelector("#secPoints .total-pts")` |
| 573 | querySelector | #secPoints .lv-pill | `querySelector("#secPoints .lv-pill")` |
| 577 | querySelector | #secPoints .lv-range | `querySelector("#secPoints .lv-range")` |
| 581 | querySelector | #secPoints .lv-prog | `querySelector("#secPoints .lv-prog")` |
| 582 | querySelector | i | `querySelector("i")` |
| 583 | querySelector | #secPoints .lv-note | `querySelector("#secPoints .lv-note")` |
| 587 | querySelector | #secPoints .log-list | `querySelector("#secPoints .log-list")` |
| 591 | getElementById | logHead | `getElementById("logHead")` |
| 599 | getElementById | logPager | `getElementById("logPager")` |
| 613 | querySelectorAll | .pager-btn[data-page] | `querySelectorAll(".pager-btn[data-page]")` |
| 616 | querySelector | [data-nav="prev"] | `querySelector('[data-nav="prev"]')` |
| 617 | querySelector | [data-nav="next"] | `querySelector('[data-nav="next"]')` |
| 624 | getElementById | logPager | `getElementById("logPager")` |
| 637 | getElementById | rankMeta | `getElementById("rankMeta")` |
| 639 | getElementById | rankLiveBadge | `getElementById("rankLiveBadge")` |
| 643 | querySelector | #secRank .rank-body | `querySelector("#secRank .rank-body")` |
| 653 | getElementById | myRankVal | `getElementById("myRankVal")` |
| 656 | getElementById | myRankMetric | `getElementById("myRankMetric")` |
| 665 | querySelector | #secRank .rank-span .tabgroup .tab.on | `querySelector("#secRank .rank-span .tabgroup .tab.on")` |
| 669 | querySelectorAll | #secRank .rank-dim .tabgroup .tab | `querySelectorAll("#secRank .rank-dim .tabgroup .tab")` |
| 670 | classList operations | - | `classList.contains("on")` |
| 682 | dynamic/template selectors | - | `querySelectorAll(groupSel)` |
| 682 | querySelectorAll | - | `querySelectorAll(groupSel)` |
| 685 | classList operations | - | `classList.remove("on")` |
| 686 | classList operations | - | `classList.add("on")` |
| 696 | getElementById | - | `getElementById(secId)` |
| 698 | querySelector | .show-err .retry | `querySelector(".show-err .retry")` |

## admin-course-detail.html

Total hooks: 42

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 2 |
| querySelectorAll | 14 |
| classList operations | 11 |
| closest | 3 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 5 |
| parentNode / nextSibling family | 2 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 524 | classList operations | - | `classList.add('open')` |
| 524 | classList operations | - | `classList.add('open')` |
| 524 | classList operations | - | `classList.remove('open')` |
| 524 | classList operations | - | `classList.remove('open')` |
| 524 | classList operations | - | `classList.contains('open')` |
| 524 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 524 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 524 | getElementById | gnav | `getElementById('gnav')` |
| 533 | getElementById | - | `getElementById(id)` |
| 595 | querySelectorAll | [data-cohort] | `querySelectorAll("[data-cohort]")` |
| 596 | closest | button | `closest("button")` |
| 597 | querySelectorAll | [data-coedit] | `querySelectorAll("[data-coedit]")` |
| 598 | querySelectorAll | [data-codel] | `querySelectorAll("[data-codel]")` |
| 677 | event delegation selectors | button | `addEventListener("click",function(ev){ if(ev.target.closest("button")` |
| 677 | querySelectorAll | .mp-h | `querySelectorAll(".mp-h")` |
| 678 | closest | button | `closest("button")` |
| 679 | parentNode / nextSibling family | - | `.parentNode` |
| 679 | querySelector | .mp-b | `querySelector(".mp-b")` |
| 680 | classList operations | - | `classList.toggle("open")` |
| 680 | querySelector | .chev | `querySelector(".chev")` |
| 681 | querySelectorAll | [data-ssadd] | `querySelectorAll("[data-ssadd]")` |
| 682 | querySelectorAll | [data-moedit] | `querySelectorAll("[data-moedit]")` |
| 683 | querySelectorAll | [data-model] | `querySelectorAll("[data-model]")` |
| 685 | querySelectorAll | [data-vid] | `querySelectorAll("[data-vid]")` |
| 686 | querySelectorAll | [data-ssedit] | `querySelectorAll("[data-ssedit]")` |
| 687 | querySelectorAll | [data-ssdel] | `querySelectorAll("[data-ssdel]")` |
| 771 | querySelectorAll | [data-chap] | `querySelectorAll("[data-chap]")` |
| 781 | classList operations | - | `classList.toggle("hover",ev==="dragover")` |
| 798 | form.elements / name / tagName | - | `.name` |
| 798 | form.elements / name / tagName | - | `.name` |
| 798 | form.elements / name / tagName | - | `.name` |
| 805 | form.elements / name / tagName | - | `.name` |
| 810 | form.elements / name / tagName | - | `.name` |
| 822 | parentNode / nextSibling family | - | `.firstElementChild` |
| 881 | querySelectorAll | [data-chdel] | `querySelectorAll("[data-chdel]")` |
| 896 | classList operations | - | `classList.add("show")` |
| 897 | classList operations | - | `classList.remove("show")` |
| 898 | classList operations | - | `classList.remove("show")` |
| 898 | closest | .scrim | `closest(".scrim")` |
| 898 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 899 | classList operations | - | `classList.remove("show")` |
| 899 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |

## admin-courses-recycle-proto.html

Total hooks: 63

| Category | Count |
|---|---:|
| getElementById | 38 |
| querySelector | 0 |
| querySelectorAll | 5 |
| classList operations | 18 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 2 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 370 | classList operations | - | `classList.add('open')` |
| 370 | classList operations | - | `classList.add('open')` |
| 370 | classList operations | - | `classList.remove('open')` |
| 370 | classList operations | - | `classList.remove('open')` |
| 370 | classList operations | - | `classList.contains('open')` |
| 370 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 370 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 370 | getElementById | gnav | `getElementById('gnav')` |
| 403 | getElementById | emToast | `getElementById("emToast")` |
| 415 | getElementById | f-kw | `getElementById("f-kw")` |
| 416 | getElementById | f-dm | `getElementById("f-dm")` |
| 424 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 443 | getElementById | f-kw | `getElementById("f-kw")` |
| 444 | getElementById | f-dm | `getElementById("f-dm")` |
| 447 | form.elements / name / tagName | - | `.name` |
| 449 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 453 | form.elements / name / tagName | - | `.name` |
| 460 | getElementById | pager | `getElementById("pager")` |
| 463 | getElementById | pager | `getElementById("pager")` |
| 467 | classList operations | - | `classList.toggle("hidden",!b)` |
| 467 | getElementById | state-empty | `getElementById("state-empty")` |
| 468 | classList operations | - | `classList.toggle("hidden",b)` |
| 468 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 469 | classList operations | - | `classList.toggle("hidden",b)` |
| 469 | getElementById | pager | `getElementById("pager")` |
| 473 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 474 | classList operations | - | `classList.add("hidden")` |
| 474 | getElementById | state-empty | `getElementById("state-empty")` |
| 475 | classList operations | - | `classList.add("hidden")` |
| 475 | getElementById | state-error | `getElementById("state-error")` |
| 476 | classList operations | - | `classList.add("hidden")` |
| 476 | getElementById | pager | `getElementById("pager")` |
| 480 | classList operations | - | `classList.toggle("on",b.dataset.v===state)` |
| 480 | querySelectorAll | [data-v] | `querySelectorAll("[data-v]")` |
| 483 | classList operations | - | `classList.toggle("hidden",state!=="error")` |
| 483 | getElementById | state-error | `getElementById("state-error")` |
| 484 | classList operations | - | `classList.add("hidden")` |
| 484 | classList operations | - | `classList.add("hidden")` |
| 484 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 484 | getElementById | pager | `getElementById("pager")` |
| 484 | getElementById | state-empty | `getElementById("state-empty")` |
| 488 | getElementById | - | `getElementById(id)` |
| 491 | classList operations | - | `classList.toggle("active",b.dataset.view===activeView)` |
| 491 | querySelectorAll | #viewTabs .vtab | `querySelectorAll("#viewTabs .vtab")` |
| 493 | getElementById | btn-create | `getElementById("btn-create")` |
| 494 | getElementById | f-ss | `getElementById("f-ss")` |
| 495 | getElementById | f-sort | `getElementById("f-sort")` |
| 496 | getElementById | meta-count | `getElementById("meta-count")` |
| 499 | getElementById | head-sub | `getElementById("head-sub")` |
| 506 | classList operations | - | `classList.add("show")` |
| 506 | getElementById | - | `getElementById(id)` |
| 507 | classList operations | - | `classList.remove("show")` |
| 507 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 508 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 509 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 518 | getElementById | restore-name | `getElementById("restore-name")` |
| 519 | getElementById | restore-id | `getElementById("restore-id")` |
| 539 | getElementById | purge-name | `getElementById("purge-name")` |
| 540 | getElementById | purge-id | `getElementById("purge-id")` |
| 545 | getElementById | purge-code-echo | `getElementById("purge-code-echo")` |
| 546 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 553 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 554 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |

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
| 459 | classList operations | - | `classList.add('open')` |
| 459 | classList operations | - | `classList.add('open')` |
| 459 | classList operations | - | `classList.remove('open')` |
| 459 | classList operations | - | `classList.remove('open')` |
| 459 | classList operations | - | `classList.contains('open')` |
| 459 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 459 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 459 | getElementById | gnav | `getElementById('gnav')` |
| 490 | getElementById | emToast | `getElementById("emToast")` |
| 516 | getElementById | thead-row | `getElementById("thead-row")` |
| 525 | classList operations | - | `classList.toggle("active", b.dataset.view === activeView)` |
| 525 | querySelectorAll | #viewTabs .vtab | `querySelectorAll("#viewTabs .vtab")` |
| 526 | getElementById | btn-create | `getElementById("btn-create")` |
| 527 | getElementById | f-ss | `getElementById("f-ss")` |
| 527 | getElementById | f-sort | `getElementById("f-sort")` |
| 530 | getElementById | head-sub | `getElementById("head-sub")` |
| 534 | getElementById | empty-ico | `getElementById("empty-ico")` |
| 535 | getElementById | empty-title | `getElementById("empty-title")` |
| 536 | getElementById | empty-desc | `getElementById("empty-desc")` |
| 542 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 543 | classList operations | - | `classList.remove("hidden")` |
| 543 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 544 | classList operations | - | `classList.add("hidden")` |
| 544 | getElementById | state-empty | `getElementById("state-empty")` |
| 545 | classList operations | - | `classList.add("hidden")` |
| 545 | getElementById | state-error | `getElementById("state-error")` |
| 546 | classList operations | - | `classList.add("hidden")` |
| 546 | getElementById | pager | `getElementById("pager")` |
| 553 | getElementById | f-kw | `getElementById("f-kw")` |
| 555 | getElementById | f-dm | `getElementById("f-dm")` |
| 563 | getElementById | f-ss | `getElementById("f-ss")` |
| 565 | getElementById | f-sort | `getElementById("f-sort")` |
| 572 | getElementById | - | `getElementById(id)` |
| 584 | getElementById | pager | `getElementById("pager")` |
| 590 | classList operations | - | `classList.add("hidden")` |
| 595 | classList operations | - | `classList.remove("hidden")` |
| 604 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 606 | classList operations | - | `classList.toggle("hidden", !items.length)` |
| 609 | getElementById | total-count | `getElementById("total-count")` |
| 611 | getElementById | meta-suffix | `getElementById("meta-suffix")` |
| 615 | classList operations | - | `classList.add("hidden")` |
| 615 | getElementById | tbl-body | `getElementById("tbl-body")` |
| 616 | classList operations | - | `classList.add("hidden")` |
| 616 | getElementById | pager | `getElementById("pager")` |
| 617 | getElementById | err-msg | `getElementById("err-msg")` |
| 619 | classList operations | - | `classList.remove("hidden")` |
| 619 | getElementById | state-error | `getElementById("state-error")` |
| 623 | classList operations | - | `classList.toggle("hidden", !b)` |
| 623 | getElementById | state-empty | `getElementById("state-empty")` |
| 656 | classList operations | - | `classList.contains("open")` |
| 656 | dynamic/template selectors | - | `querySelector('.dd[data-row="'+id+'"]')` |
| 656 | querySelector | - | `querySelector('.dd[data-row="'+id+'"]')` |
| 657 | classList operations | - | `classList.remove("open")` |
| 657 | classList operations | - | `classList.add("open")` |
| 657 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 658 | classList operations | - | `classList.remove("open")` |
| 658 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 659 | classList operations | - | `classList.remove("open")` |
| 659 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 662 | classList operations | - | `classList.add("show")` |
| 662 | getElementById | - | `getElementById(id)` |
| 663 | classList operations | - | `classList.remove("show")` |
| 663 | classList operations | - | `classList.remove("open")` |
| 663 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 663 | querySelectorAll | .dd | `querySelectorAll(".dd")` |
| 664 | querySelectorAll | [data-close] | `querySelectorAll("[data-close]")` |
| 665 | querySelectorAll | .scrim | `querySelectorAll(".scrim")` |
| 670 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 672 | getElementById | form-title | `getElementById("form-title")` |
| 675 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 688 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 692 | getElementById | form-title | `getElementById("form-title")` |
| 699 | getElementById | series-form-fields | `getElementById("series-form-fields")` |
| 703 | getElementById | series-save-btn | `getElementById("series-save-btn")` |
| 724 | getElementById | del-name | `getElementById("del-name")` |
| 729 | getElementById | off-name | `getElementById("off-name")` |
| 738 | getElementById | off-confirm-btn | `getElementById("off-confirm-btn")` |
| 744 | getElementById | del-confirm-btn | `getElementById("del-confirm-btn")` |
| 754 | getElementById | restore-name | `getElementById("restore-name")` |
| 755 | getElementById | restore-id | `getElementById("restore-id")` |
| 760 | getElementById | restore-confirm-btn | `getElementById("restore-confirm-btn")` |
| 773 | getElementById | purge-name | `getElementById("purge-name")` |
| 774 | getElementById | purge-id | `getElementById("purge-id")` |
| 779 | getElementById | purge-code-echo | `getElementById("purge-code-echo")` |
| 780 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 787 | getElementById | purge-code-input | `getElementById("purge-code-input")` |
| 788 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |
| 792 | getElementById | purge-confirm-btn | `getElementById("purge-confirm-btn")` |
| 802 | getElementById | btn-create | `getElementById("btn-create")` |
| 811 | querySelector | .toolbar-meta,.page-head .sub | `querySelector(".toolbar-meta,.page-head .sub")` |

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
| 438 | classList operations | - | `classList.add('open')` |
| 438 | classList operations | - | `classList.add('open')` |
| 438 | classList operations | - | `classList.remove('open')` |
| 438 | classList operations | - | `classList.remove('open')` |
| 438 | classList operations | - | `classList.contains('open')` |
| 438 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 438 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 438 | getElementById | gnav | `getElementById('gnav')` |
| 446 | getElementById | view-loading | `getElementById('view-loading')` |
| 447 | getElementById | view-success | `getElementById('view-success')` |
| 466 | querySelector | .page-head .sub, .demo-note | `querySelector(".page-head .sub, .demo-note")` |
| 475 | getElementById | - | `getElementById(v)` |
| 483 | getElementById | kpi-total | `getElementById("kpi-total")` |
| 484 | getElementById | kpi-active7d | `getElementById("kpi-active7d")` |
| 485 | getElementById | kpi-newreg7d | `getElementById("kpi-newreg7d")` |
| 486 | getElementById | kpi-disabled | `getElementById("kpi-disabled")` |
| 488 | getElementById | rb-admin | `getElementById("rb-admin")` |
| 489 | getElementById | rb-manager | `getElementById("rb-manager")` |
| 490 | getElementById | rb-teacher | `getElementById("rb-teacher")` |
| 491 | getElementById | rb-student | `getElementById("rb-student")` |
| 493 | getElementById | kpi-avglogin | `getElementById("kpi-avglogin")` |
| 497 | getElementById | bars-real | `getElementById("bars-real")` |
| 512 | getElementById | donut-real | `getElementById("donut-real")` |
| 518 | getElementById | donut-total | `getElementById("donut-total")` |
| 519 | getElementById | donut-sub | `getElementById("donut-sub")` |
| 521 | getElementById | lg-admin | `getElementById("lg-admin")` |
| 522 | getElementById | lg-student | `getElementById("lg-student")` |
| 523 | getElementById | lg-teacher | `getElementById("lg-teacher")` |
| 524 | getElementById | lg-manager | `getElementById("lg-manager")` |
| 526 | getElementById | updated-at | `getElementById("updated-at")` |
| 530 | getElementById | err-msg | `getElementById("err-msg")` |

## admin-mcp.html

Total hooks: 18

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 4 |
| querySelectorAll | 5 |
| classList operations | 5 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 410 | classList operations | - | `classList.add('open')` |
| 410 | classList operations | - | `classList.add('open')` |
| 410 | classList operations | - | `classList.remove('open')` |
| 410 | classList operations | - | `classList.remove('open')` |
| 410 | classList operations | - | `classList.contains('open')` |
| 410 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 410 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 410 | getElementById | gnav | `getElementById('gnav')` |
| 420 | getElementById | - | `getElementById(id)` |
| 431 | querySelector | #srvTable tbody | `querySelector("#srvTable tbody")` |
| 445 | querySelectorAll | [data-srv-hl] | `querySelectorAll("[data-srv-hl]")` |
| 446 | querySelectorAll | [data-srv-dc] | `querySelectorAll("[data-srv-dc]")` |
| 447 | querySelectorAll | [data-srv-en] | `querySelectorAll("[data-srv-en]")` |
| 448 | querySelectorAll | [data-srv-del] | `querySelectorAll("[data-srv-del]")` |
| 451 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 522 | querySelector | #toolTable tbody | `querySelector("#toolTable tbody")` |
| 530 | querySelectorAll | [data-tt] | `querySelectorAll("[data-tt]")` |
| 532 | querySelector | #toolTable tbody | `querySelector("#toolTable tbody")` |

## admin-question-detail.html

Total hooks: 74

| Category | Count |
|---|---:|
| getElementById | 51 |
| querySelector | 1 |
| querySelectorAll | 3 |
| classList operations | 15 |
| closest | 2 |
| matches | 0 |
| event delegation selectors | 1 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 508 | getElementById | view-loading | `getElementById('view-loading')` |
| 508 | getElementById | view-error | `getElementById('view-error')` |
| 509 | getElementById | tabhead | `getElementById('tabhead')` |
| 509 | querySelectorAll | .qd-pane | `querySelectorAll('.qd-pane')` |
| 520 | classList operations | - | `classList.add('open')` |
| 520 | classList operations | - | `classList.add('open')` |
| 520 | classList operations | - | `classList.remove('open')` |
| 520 | classList operations | - | `classList.remove('open')` |
| 520 | classList operations | - | `classList.contains('open')` |
| 520 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 520 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 520 | getElementById | gnav | `getElementById('gnav')` |
| 536 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 552 | getElementById | f-type | `getElementById("f-type")` |
| 567 | getElementById | - | `getElementById(kind+"-body")` |
| 590 | querySelectorAll | .opt-input[data-ol] | `querySelectorAll(".opt-input[data-ol]")` |
| 602 | getElementById | cr-type | `getElementById("cr-type")` |
| 605 | getElementById | - | `getElementById(id)` |
| 607 | getElementById | ro-obj-label | `getElementById("ro-obj-label")` |
| 609 | classList operations | - | `classList.add("hidden")` |
| 609 | getElementById | - | `getElementById(id)` |
| 610 | classList operations | - | `classList.remove("hidden")` |
| 610 | getElementById | opt-single | `getElementById("opt-single")` |
| 611 | classList operations | - | `classList.remove("hidden")` |
| 611 | getElementById | opt-multi | `getElementById("opt-multi")` |
| 612 | classList operations | - | `classList.remove("hidden")` |
| 612 | getElementById | opt-tf | `getElementById("opt-tf")` |
| 613 | classList operations | - | `classList.remove("hidden")` |
| 613 | getElementById | opt-none | `getElementById("opt-none")` |
| 614 | getElementById | answer-hint | `getElementById("answer-hint")` |
| 617 | getElementById | f-type | `getElementById("f-type")` |
| 620 | event delegation selectors | input[type=radio] | `addEventListener("change", function(e){ var r=e.target.closest("input[type=radio]")` |
| 620 | getElementById | opt-tf | `getElementById("opt-tf")` |
| 621 | closest | input[type=radio] | `closest("input[type=radio]")` |
| 622 | parentNode / nextSibling family | - | `.parentElement` |
| 623 | getElementById | f-answer | `getElementById("f-answer")` |
| 644 | getElementById | analysis-preview | `getElementById("analysis-preview")` |
| 644 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 645 | getElementById | prev-stem | `getElementById("prev-stem")` |
| 645 | getElementById | f-stem | `getElementById("f-stem")` |
| 646 | getElementById | prev-analysis | `getElementById("prev-analysis")` |
| 646 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 649 | getElementById | prev-options | `getElementById("prev-options")` |
| 662 | classList operations | - | `classList.toggle("hidden",pi!=="edit")` |
| 662 | getElementById | pane-edit | `getElementById("pane-edit")` |
| 663 | classList operations | - | `classList.toggle("hidden",pi!=="preview")` |
| 663 | getElementById | pane-preview | `getElementById("pane-preview")` |
| 664 | classList operations | - | `classList.toggle("on",pi==="edit")` |
| 664 | getElementById | tab-edit | `getElementById("tab-edit")` |
| 665 | classList operations | - | `classList.toggle("on",pi==="preview")` |
| 665 | getElementById | tab-preview | `getElementById("tab-preview")` |
| 670 | getElementById | - | `getElementById(id)` |
| 675 | getElementById | - | `getElementById(id)` |
| 675 | getElementById | - | `getElementById(errId)` |
| 676 | closest | .fld | `closest(".fld")` |
| 677 | classList operations | - | `classList.toggle("err",bad)` |
| 683 | getElementById | f-stem | `getElementById("f-stem")` |
| 684 | getElementById | f-answer | `getElementById("f-answer")` |
| 685 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 688 | getElementById | - | `getElementById(id)` |
| 716 | getElementById | qd-err-msg | `getElementById("qd-err-msg")` |
| 728 | getElementById | cr-code | `getElementById("cr-code")` |
| 729 | getElementById | cr-bank | `getElementById("cr-bank")` |
| 730 | getElementById | ro-bank-id | `getElementById("ro-bank-id")` |
| 731 | getElementById | ro-code | `getElementById("ro-code")` |
| 732 | getElementById | ro-qid | `getElementById("ro-qid")` |
| 733 | getElementById | ro-bank-full | `getElementById("ro-bank-full")` |
| 734 | getElementById | ro-code-full | `getElementById("ro-code-full")` |
| 736 | getElementById | f-type | `getElementById("f-type")` |
| 738 | getElementById | f-stem | `getElementById("f-stem")` |
| 739 | getElementById | f-answer | `getElementById("f-answer")` |
| 740 | getElementById | f-analysis | `getElementById("f-analysis")` |
| 744 | querySelectorAll | #opt-tf input[type=radio] | `querySelectorAll("#opt-tf input[type=radio]")` |
| 750 | getElementById | qd-err-msg | `getElementById("qd-err-msg")` |

## admin-questions.html

Total hooks: 41

| Category | Count |
|---|---:|
| getElementById | 5 |
| querySelector | 1 |
| querySelectorAll | 5 |
| classList operations | 20 |
| closest | 8 |
| matches | 0 |
| event delegation selectors | 2 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 0 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 623 | getElementById | - | `getElementById(id)` |
| 638 | classList operations | - | `classList.add('open')` |
| 638 | classList operations | - | `classList.add('open')` |
| 638 | classList operations | - | `classList.remove('open')` |
| 638 | classList operations | - | `classList.remove('open')` |
| 638 | classList operations | - | `classList.contains('open')` |
| 638 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 638 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 638 | getElementById | gnav | `getElementById('gnav')` |
| 651 | getElementById | - | `getElementById(id)` |
| 658 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |
| 666 | classList operations | - | `classList.remove("show")` |
| 666 | querySelectorAll | .scrim.show | `querySelectorAll(".scrim.show")` |
| 667 | classList operations | - | `classList.toggle("hidden",!a1)` |
| 667 | classList operations | - | `classList.toggle("hidden",!a2)` |
| 667 | classList operations | - | `classList.toggle("hidden",!a3)` |
| 697 | closest | button[data-bkpg] | `closest("button[data-bkpg]")` |
| 709 | classList operations | - | `classList.toggle("on", x.getAttribute("data-tab")` |
| 709 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 710 | classList operations | - | `classList.toggle("hidden", t!=="banks")` |
| 711 | classList operations | - | `classList.toggle("hidden", t!=="questions")` |
| 732 | closest | button[data-qpg] | `closest("button[data-qpg]")` |
| 746 | event delegation selectors | [data-del-q] | `addEventListener("click", function(e){ var db=e.target.closest("[data-del-q]")` |
| 747 | closest | [data-del-q] | `closest("[data-del-q]")` |
| 749 | closest | [data-edit-q] | `closest("[data-edit-q]")` |
| 751 | closest | [data-qrow] | `closest("[data-qrow]")` |
| 754 | event delegation selectors | [data-bank-del] | `addEventListener("click", function(e){ var bd=e.target.closest("[data-bank-del]")` |
| 755 | closest | [data-bank-del] | `closest("[data-bank-del]")` |
| 757 | closest | [data-bank-edit] | `closest("[data-bank-edit]")` |
| 759 | closest | [data-manage-bank] | `closest("[data-manage-bank]")` |
| 793 | classList operations | - | `classList.add("show")` |
| 818 | classList operations | - | `classList.add("show")` |
| 833 | classList operations | - | `classList.add("show")` |
| 856 | classList operations | - | `classList.add("show")` |
| 872 | querySelectorAll | #qf-options-body input[data-opt-label] | `querySelectorAll("#qf-options-body input[data-opt-label]")` |
| 891 | classList operations | - | `classList.add("show")` |
| 894 | classList operations | - | `classList.toggle("hidden", Number(x.getAttribute("data-idx")` |
| 894 | querySelectorAll | .imp-step | `querySelectorAll(".imp-step")` |
| 896 | classList operations | - | `classList.toggle("done", !!i&&i<n)` |
| 896 | classList operations | - | `classList.toggle("cur", i===n)` |
| 896 | querySelectorAll | .stp,.stp-conn | `querySelectorAll(".stp,.stp-conn")` |

## admin-rag-upload.html

Total hooks: 32

| Category | Count |
|---|---:|
| getElementById | 4 |
| querySelector | 2 |
| querySelectorAll | 2 |
| classList operations | 11 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 9 |
| parentNode / nextSibling family | 4 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 429 | classList operations | - | `classList.add('open')` |
| 429 | classList operations | - | `classList.add('open')` |
| 429 | classList operations | - | `classList.remove('open')` |
| 429 | classList operations | - | `classList.remove('open')` |
| 429 | classList operations | - | `classList.contains('open')` |
| 429 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 429 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 429 | getElementById | gnav | `getElementById('gnav')` |
| 442 | getElementById | - | `getElementById(id)` |
| 460 | form.elements / name / tagName | - | `.name` |
| 476 | form.elements / name / tagName | - | `.name` |
| 481 | form.elements / name / tagName | - | `.name` |
| 484 | querySelectorAll | [data-rm] | `querySelectorAll("[data-rm]")` |
| 517 | classList operations | - | `classList.add("hover")` |
| 518 | classList operations | - | `classList.remove("hover")` |
| 520 | classList operations | - | `classList.remove("hover")` |
| 533 | classList operations | - | `classList.add("show")` |
| 542 | classList operations | - | `classList.remove("show")` |
| 545 | classList operations | - | `classList.add("show")` |
| 558 | form.elements / name / tagName | - | `.name` |
| 561 | form.elements / name / tagName | - | `.name` |
| 565 | form.elements / name / tagName | - | `.name` |
| 582 | querySelector | #taskTable tbody | `querySelector("#taskTable tbody")` |
| 618 | parentNode / nextSibling family | - | `.parentNode` |
| 618 | parentNode / nextSibling family | - | `.parentNode` |
| 634 | form.elements / name / tagName | - | `.name` |
| 634 | form.elements / name / tagName | - | `.name` |
| 641 | form.elements / name / tagName | - | `.name` |
| 642 | querySelectorAll | [data-del] | `querySelectorAll("[data-del]")` |
| 648 | parentNode / nextSibling family | - | `.parentNode` |
| 648 | parentNode / nextSibling family | - | `.parentNode` |
| 665 | querySelector | [data-collection-count] | `querySelector("[data-collection-count]")` |

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

Total hooks: 74

| Category | Count |
|---|---:|
| getElementById | 40 |
| querySelector | 3 |
| querySelectorAll | 4 |
| classList operations | 17 |
| closest | 6 |
| matches | 0 |
| event delegation selectors | 3 |
| dynamic/template selectors | 0 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 477 | getElementById | f-kw | `getElementById("f-kw")` |
| 478 | getElementById | deb-pulse | `getElementById("deb-pulse")` |
| 479 | classList operations | - | `classList.add("show")` |
| 482 | classList operations | - | `classList.remove("show")` |
| 485 | getElementById | f-kw | `getElementById("f-kw")` |
| 485 | getElementById | f-role | `getElementById("f-role")` |
| 486 | getElementById | f-status | `getElementById("f-status")` |
| 488 | getElementById | f-role | `getElementById("f-role")` |
| 489 | getElementById | f-status | `getElementById("f-status")` |
| 524 | getElementById | u-body | `getElementById("u-body")` |
| 525 | classList operations | - | `classList.toggle("hidden",view!=="empty")` |
| 525 | getElementById | u-empty | `getElementById("u-empty")` |
| 526 | getElementById | u-error | `getElementById("u-error")` |
| 527 | classList operations | - | `classList.toggle("hidden",view!=="error")` |
| 545 | getElementById | u-count | `getElementById("u-count")` |
| 546 | getElementById | u-pager | `getElementById("u-pager")` |
| 566 | getElementById | u-body | `getElementById("u-body")` |
| 568 | getElementById | head-total | `getElementById("head-total")` |
| 576 | event delegation selectors | [data-upg] | `addEventListener("click",function(e){ var b=e.target.closest("[data-upg]")` |
| 576 | getElementById | u-pager | `getElementById("u-pager")` |
| 577 | closest | [data-upg] | `closest("[data-upg]")` |
| 583 | getElementById | learn-sub | `getElementById("learn-sub")` |
| 587 | getElementById | learn-fields | `getElementById("learn-fields")` |
| 599 | getElementById | st-title | `getElementById("st-title")` |
| 600 | getElementById | st-sub | `getElementById("st-sub")` |
| 601 | getElementById | st-msg | `getElementById("st-msg")` |
| 603 | getElementById | st-reason | `getElementById("st-reason")` |
| 604 | getElementById | st-confirm | `getElementById("st-confirm")` |
| 607 | getElementById | st-confirm | `getElementById("st-confirm")` |
| 612 | getElementById | st-reason | `getElementById("st-reason")` |
| 628 | getElementById | edit-sub | `getElementById("edit-sub")` |
| 629 | getElementById | e-role | `getElementById("e-role")` |
| 631 | getElementById | e-reason | `getElementById("e-reason")` |
| 632 | getElementById | e-status-seg | `getElementById("e-status-seg")` |
| 633 | classList operations | - | `classList.toggle("on",+b.getAttribute("data-st")` |
| 633 | querySelectorAll | button | `querySelectorAll("button")` |
| 636 | classList operations | - | `classList.toggle("hidden",!redline)` |
| 636 | getElementById | e-redline | `getElementById("e-redline")` |
| 638 | querySelector | button[data-st="0"] | `querySelector('button[data-st="0"]')` |
| 639 | getElementById | e-save | `getElementById("e-save")` |
| 642 | event delegation selectors | button | `addEventListener("click",function(e){ const b=e.target.closest("button")` |
| 642 | getElementById | e-status-seg | `getElementById("e-status-seg")` |
| 643 | closest | button | `closest("button")` |
| 644 | classList operations | - | `classList.toggle("on",x===b)` |
| 644 | parentNode / nextSibling family | - | `.parentElement` |
| 644 | querySelectorAll | button | `querySelectorAll("button")` |
| 649 | getElementById | e-role | `getElementById("e-role")` |
| 650 | querySelector | #e-status-seg button.on | `querySelector("#e-status-seg button.on")` |
| 652 | getElementById | e-reason | `getElementById("e-reason")` |
| 655 | getElementById | e-save | `getElementById("e-save")` |
| 661 | getElementById | e-save | `getElementById("e-save")` |
| 665 | classList operations | - | `classList.add("show")` |
| 665 | classList operations | - | `classList.add("show")` |
| 665 | getElementById | - | `getElementById(id+"-mask")` |
| 665 | getElementById | - | `getElementById(id)` |
| 667 | classList operations | - | `classList.remove("show")` |
| 667 | querySelectorAll | .mask.show | `querySelectorAll(".mask.show")` |
| 668 | classList operations | - | `classList.remove("show")` |
| 668 | querySelectorAll | .dialog.show | `querySelectorAll(".dialog.show")` |
| 670 | event delegation selectors | [data-close] | `addEventListener("click",function(e){ if(e.target.classList && e.target.classList.contains("mask")) closeAll(); const c=e.target.closest("[data-close]")` |
| 671 | classList operations | - | `classList.contains("mask")` |
| 672 | closest | [data-close] | `closest("[data-close]")` |
| 673 | closest | [data-view] | `closest("[data-view]")` |
| 674 | closest | [data-edit] | `closest("[data-edit]")` |
| 675 | closest | [data-toggle] | `closest("[data-toggle]")` |
| 683 | classList operations | - | `classList.add('open')` |
| 683 | classList operations | - | `classList.add('open')` |
| 683 | classList operations | - | `classList.remove('open')` |
| 683 | classList operations | - | `classList.remove('open')` |
| 683 | classList operations | - | `classList.contains('open')` |
| 683 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 683 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 683 | getElementById | gnav | `getElementById('gnav')` |
| 692 | querySelector | .page-head .sub | `querySelector(".page-head .sub")` |

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
| 463 | dynamic/template selectors | - | `querySelectorAll(s)` |
| 463 | querySelectorAll | - | `querySelectorAll(s)` |
| 568 | classList operations | - | `classList.toggle("stop", isStream)` |
| 579 | getElementById | degradeBanner | `getElementById("degradeBanner")` |
| 605 | event delegation selectors | [data-del] | `addEventListener("click", (e)=>{ const del = e.target.closest("[data-del]")` |
| 606 | closest | [data-del] | `closest("[data-del]")` |
| 608 | closest | .sess | `closest(".sess")` |
| 615 | getElementById | toast | `getElementById("toast")` |
| 619 | classList operations | - | `classList.toggle("open", open)` |
| 620 | classList operations | - | `classList.toggle("open", open)` |
| 628 | getElementById | composerInput | `getElementById("composerInput")` |
| 697 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 723 | getElementById | - | `getElementById(id)` |
| 778 | querySelectorAll | .sess | `querySelectorAll(".sess")` |
| 781 | querySelectorAll | .del | `querySelectorAll(".del")` |
| 849 | classList operations | - | `classList.toggle("stop", on)` |
| 866 | parentNode / nextSibling family | - | `.parentNode` |
| 866 | querySelector | .empty,.error-st | `querySelector(".empty,.error-st")` |
| 897 | querySelector | .hitl-confirm | `querySelector(".hitl-confirm")` |
| 898 | querySelector | .hitl-reject | `querySelector(".hitl-reject")` |
| 912 | classList operations | - | `classList.add("hitl-busy")` |
| 913 | querySelector | .hitl-note | `querySelector(".hitl-note")` |
| 925 | classList operations | - | `classList.add("hitl-busy")` |
| 935 | classList operations | - | `classList.remove("hitl-busy")` |
| 1073 | classList operations | - | `classList.add("open")` |
| 1074 | classList operations | - | `classList.add("open")` |
| 1085 | classList operations | - | `classList.add('open')` |
| 1085 | classList operations | - | `classList.add('open')` |
| 1085 | classList operations | - | `classList.remove('open')` |
| 1085 | classList operations | - | `classList.remove('open')` |
| 1085 | classList operations | - | `classList.contains('open')` |
| 1085 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 1085 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 1085 | getElementById | gnav | `getElementById('gnav')` |

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
| 356 | getElementById | likeBtn | `getElementById('likeBtn')` |
| 357 | getElementById | favBtn | `getElementById('favBtn')` |
| 358 | getElementById | likeCnt | `getElementById('likeCnt')` |
| 359 | getElementById | favCnt | `getElementById('favCnt')` |
| 360 | getElementById | metaLike | `getElementById('metaLike')` |
| 361 | getElementById | metaFav | `getElementById('metaFav')` |
| 362 | getElementById | pointsHint | `getElementById('pointsHint')` |
| 366 | classList operations | - | `classList.toggle('on')` |
| 373 | classList operations | - | `classList.toggle('on')` |
| 379 | getElementById | cList | `getElementById('cList')` |
| 380 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 381 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 382 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 383 | getElementById | metaCmt | `getElementById('metaCmt')` |
| 395 | event delegation selectors | .c-like | `addEventListener('click',function(){ if(window.__REAL_COMMUNITY__) return; var t=cmtInput.value.trim(); if(!t){cmtInput.focus();return;} addComment(t); pointsHint.style.display='inline-flex';setTimeout(function(){pointsHint.style.display='none'},1800); }); /* 评论点赞（事件委托） */ cList.addEventListener('click',function(e){ if(window.__REAL_COMMUNITY__) return; var b=e.target.closest('.c-like')` |
| 403 | event delegation selectors | .c-like | `addEventListener('click',function(e){ if(window.__REAL_COMMUNITY__) return; var b=e.target.closest('.c-like')` |
| 404 | closest | .c-like | `closest('.c-like')` |
| 406 | classList operations | - | `classList.toggle('on')` |
| 407 | querySelector | b | `querySelector('b')` |
| 412 | getElementById | page | `getElementById('page')` |
| 413 | getElementById | comments | `getElementById('comments')` |
| 430 | querySelector | .back-row | `querySelector('.back-row')` |
| 431 | querySelector | .badges | `querySelector('.badges')` |
| 432 | querySelector | .post-title | `querySelector('.post-title')` |
| 433 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 434 | querySelector | .actions | `querySelector('.actions')` |
| 435 | querySelector | .body-card | `querySelector('.body-card')` |
| 447 | getElementById | pager | `getElementById('pager')` |
| 451 | getElementById | actions | `getElementById('actions')` |
| 456 | querySelector | .body-card | `querySelector('.body-card')` |
| 457 | querySelector | .badges | `querySelector('.badges')` |
| 459 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 461 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 462 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 465 | getElementById | pager | `getElementById('pager')` |
| 468 | querySelector | .back-row | `querySelector('.back-row')` |
| 469 | querySelector | .badges | `querySelector('.badges')` |
| 470 | querySelector | .post-title | `querySelector('.post-title')` |
| 471 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 472 | querySelector | .actions | `querySelector('.actions')` |
| 473 | querySelector | .body-card | `querySelector('.body-card')` |
| 484 | querySelector | [data-sk] | `querySelector('[data-sk]')` |
| 485 | querySelector | [data-st] | `querySelector('[data-st]')` |
| 486 | querySelector | [data-lock] | `querySelector('[data-lock]')` |
| 487 | querySelector | .back-row | `querySelector('.back-row')` |
| 488 | querySelector | .badges | `querySelector('.badges')` |
| 489 | querySelector | .post-title | `querySelector('.post-title')` |
| 490 | querySelector | .post-meta | `querySelector('.post-meta')` |
| 491 | querySelector | .actions | `querySelector('.actions')` |
| 492 | querySelector | .actions | `querySelector('.actions')` |
| 493 | querySelector | .body-card | `querySelector('.body-card')` |
| 494 | querySelector | .badges | `querySelector('.badges')` |
| 495 | getElementById | cmtInput | `getElementById('cmtInput')` |
| 497 | getElementById | cmtSubmit | `getElementById('cmtSubmit')` |
| 498 | getElementById | cmtTotal | `getElementById('cmtTotal')` |
| 501 | getElementById | pager | `getElementById('pager')` |
| 513 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 547 | getElementById | likeBtn | `getElementById("likeBtn")` |
| 547 | getElementById | likeCnt | `getElementById("likeCnt")` |
| 547 | getElementById | metaLike | `getElementById("metaLike")` |
| 548 | getElementById | favBtn | `getElementById("favBtn")` |
| 548 | getElementById | favCnt | `getElementById("favCnt")` |
| 548 | getElementById | metaFav | `getElementById("metaFav")` |
| 549 | getElementById | cList | `getElementById("cList")` |
| 549 | getElementById | cmtInput | `getElementById("cmtInput")` |
| 549 | getElementById | cmtSubmit | `getElementById("cmtSubmit")` |
| 550 | getElementById | cmtTotal | `getElementById("cmtTotal")` |
| 550 | getElementById | metaCmt | `getElementById("metaCmt")` |
| 550 | getElementById | pointsHint | `getElementById("pointsHint")` |
| 551 | getElementById | bodyCard | `getElementById("bodyCard")` |
| 551 | getElementById | mdBody | `getElementById("mdBody")` |
| 552 | getElementById | badges | `getElementById("badges")` |
| 552 | getElementById | actions | `getElementById("actions")` |
| 552 | getElementById | postTitle | `getElementById("postTitle")` |
| 552 | getElementById | postMeta | `getElementById("postMeta")` |
| 553 | getElementById | page | `getElementById("page")` |
| 556 | classList operations | - | `classList.toggle("on", !!on)` |
| 558 | querySelector | #pager .total | `querySelector("#pager .total")` |
| 561 | getElementById | cmtErr | `getElementById("cmtErr")` |
| 565 | getElementById | composer | `getElementById("composer")` |
| 580 | parentNode / nextSibling family | - | `.parentNode` |
| 580 | parentNode / nextSibling family | - | `.parentNode` |
| 581 | parentNode / nextSibling family | - | `.parentNode` |
| 581 | querySelectorAll | [data-st] | `querySelectorAll("[data-st]")` |
| 589 | getElementById | backListBtn | `getElementById("backListBtn")` |
| 591 | getElementById | retryLoadBtn | `getElementById("retryLoadBtn")` |
| 604 | querySelector | .who | `querySelector(".who")` |
| 605 | parentNode / nextSibling family | - | `.children` |
| 605 | parentNode / nextSibling family | - | `.children` |
| 606 | parentNode / nextSibling family | - | `.children` |
| 606 | parentNode / nextSibling family | - | `.children` |
| 613 | getElementById | comments | `getElementById("comments")` |
| 633 | getElementById | pager | `getElementById("pager")` |
| 647 | querySelectorAll | .pager-btn | `querySelectorAll(".pager-btn")` |
| 666 | getElementById | cRetryBtn | `getElementById("cRetryBtn")` |
| 681 | classList operations | - | `classList.contains("on")` |
| 697 | event delegation selectors | .c-like | `addEventListener("click", function () { var t = (cmtInput.value \|\| "").trim(); if (!t) { cmtInput.focus(); flash("评论不能为空"); return; } if (cmtSubmit.disabled) return; // 防抖 cmtSubmit.disabled = true; flash(""); EAPI.post("/api/community/posts/" + pid + "/comments", { content_md: t }).then(function (resp) { cmtInput.value = ""; var lastPage = Math.max(1, Math.ceil((lastCmtTotal + 1) / PAGE_SIZE)); return loadComments(lastPage).then(function () { hint(); if (resp && resp.points) flash("评论成功（+" + resp.points + " 积分）"); }); }).catch(function (e) { flash("发布失败：" + ((e && e.message) \|\| "网络错误")); }) .` |
| 711 | event delegation selectors | .c-like | `addEventListener("click", function (e) { var b = e.target.closest(".c-like")` |
| 712 | closest | .c-like | `closest(".c-like")` |
| 714 | classList operations | - | `classList.contains("on")` |
| 715 | querySelector | b | `querySelector("b")` |
| 729 | classList operations | - | `classList.add('open')` |
| 729 | classList operations | - | `classList.add('open')` |
| 729 | classList operations | - | `classList.remove('open')` |
| 729 | classList operations | - | `classList.remove('open')` |
| 729 | classList operations | - | `classList.contains('open')` |
| 729 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 729 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 729 | getElementById | gnav | `getElementById('gnav')` |

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
| 350 | classList operations | - | `classList.add('open')` |
| 350 | classList operations | - | `classList.add('open')` |
| 350 | classList operations | - | `classList.remove('open')` |
| 350 | classList operations | - | `classList.remove('open')` |
| 350 | classList operations | - | `classList.contains('open')` |
| 350 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 350 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 350 | getElementById | gnav | `getElementById('gnav')` |
| 357 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 380 | getElementById | boards | `getElementById("boards")` |
| 381 | getElementById | total | `getElementById("total")` |
| 397 | classList operations | - | `classList.toggle("on", !!liked)` |
| 428 | event delegation selectors | .like-btn | `addEventListener("click", function (e) { var lb = e.target.closest(".like-btn")` |
| 429 | closest | .like-btn | `closest(".like-btn")` |
| 431 | closest | .post | `closest(".post")` |
| 440 | classList operations | - | `classList.contains("on")` |
| 441 | querySelector | i | `querySelector("i")` |
| 462 | getElementById | kw | `getElementById("kw")` |
| 463 | getElementById | sort | `getElementById("sort")` |
| 474 | querySelector | .mine b | `querySelector(".mine b")` |
| 481 | getElementById | retryLoad | `getElementById("retryLoad")` |
| 490 | getElementById | pager | `getElementById("pager")` |
| 503 | getElementById | total | `getElementById("total")` |
| 504 | querySelectorAll | .pager-btn | `querySelectorAll(".pager-btn")` |
| 516 | querySelectorAll | #chips .chip | `querySelectorAll("#chips .chip")` |
| 517 | classList operations | - | `classList.remove("on")` |
| 517 | classList operations | - | `classList.add("on")` |
| 545 | getElementById | pmTitle | `getElementById("pmTitle")` |
| 545 | getElementById | pmContent | `getElementById("pmContent")` |
| 546 | getElementById | pmTags | `getElementById("pmTags")` |
| 546 | getElementById | pmErr | `getElementById("pmErr")` |
| 546 | querySelector | .pm-submit | `querySelector(".pm-submit")` |
| 547 | classList operations | - | `classList.remove("open")` |
| 548 | querySelector | .pm-mask | `querySelector(".pm-mask")` |
| 549 | querySelector | .pm-cancel | `querySelector(".pm-cancel")` |
| 550 | querySelector | .pm-x | `querySelector(".pm-x")` |
| 551 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 553 | classList operations | - | `classList.remove("on")` |
| 553 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 554 | classList operations | - | `classList.add("on")` |
| 564 | classList operations | - | `classList.remove("open")` |
| 577 | classList operations | - | `classList.toggle("on", c.dataset.bc === def)` |
| 577 | querySelectorAll | .pm-chip | `querySelectorAll(".pm-chip")` |
| 579 | classList operations | - | `classList.add("open")` |
| 581 | getElementById | - | `getElementById(id)` |
| 582 | getElementById | go | `getElementById("go")` |
| 583 | getElementById | sort | `getElementById("sort")` |
| 584 | getElementById | kw | `getElementById("kw")` |

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
| 248 | classList operations | - | `classList.add('open')` |
| 248 | classList operations | - | `classList.add('open')` |
| 248 | classList operations | - | `classList.remove('open')` |
| 248 | classList operations | - | `classList.remove('open')` |
| 248 | classList operations | - | `classList.contains('open')` |
| 248 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 248 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 248 | getElementById | gnav | `getElementById('gnav')` |
| 258 | getElementById | cpStage | `getElementById("cpStage")` |
| 259 | getElementById | cpPager | `getElementById("cpPager")` |
| 260 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 261 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 262 | getElementById | pgNext | `getElementById("pgNext")` |
| 387 | dynamic/template selectors | - | `querySelector('.tab[data-status="' + status + '"]')` |
| 387 | querySelector | - | `querySelector('.tab[data-status="' + status + '"]')` |
| 389 | querySelector | .cnt | `querySelector(".cnt")` |
| 410 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 412 | querySelectorAll | .tab | `querySelectorAll(".tab")` |
| 413 | classList operations | - | `classList.remove("on")` |
| 416 | classList operations | - | `classList.add("on")` |
| 478 | classList operations | - | `classList.add("show")` |
| 480 | classList operations | - | `classList.remove("show")` |
| 484 | getElementById | tplStage | `getElementById("tplStage")` |
| 621 | getElementById | omOverlay | `getElementById("omOverlay")` |
| 622 | getElementById | omBody | `getElementById("omBody")` |
| 623 | getElementById | omTitle | `getElementById("omTitle")` |
| 624 | getElementById | omClose | `getElementById("omClose")` |
| 696 | classList operations | - | `classList.add("open")` |
| 701 | classList operations | - | `classList.remove("open")` |
| 952 | classList operations | - | `classList.contains("open")` |
| 964 | getElementById | adminEntry | `getElementById("adminEntry")` |

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
| 446 | getElementById | couponList | `getElementById("couponList")` |
| 458 | querySelectorAll | button[data-get] | `querySelectorAll("button[data-get]")` |
| 461 | getElementById | summary | `getElementById("summary")` |
| 464 | classList operations | - | `classList.toggle("open",open)` |
| 464 | getElementById | couponOverlay | `getElementById("couponOverlay")` |
| 465 | getElementById | couponClose | `getElementById("couponClose")` |
| 466 | getElementById | couponDone | `getElementById("couponDone")` |
| 467 | getElementById | couponOverlay | `getElementById("couponOverlay")` |
| 630 | getElementById | enrollBtn | `getElementById("enrollBtn")` |
| 639 | getElementById | favBtn | `getElementById("favBtn")` |
| 640 | event delegation selectors | .cohort | `addEventListener("click",function(){ if(!authed){ alert("未登录：收藏 → /login?redirect=/courses/1001（J5）"); return; } favorited=!favorited; this.setAttribute("aria-pressed",String(favorited)); this.innerHTML=favorited?"♥":"♡"; alert(favorited?"POST /api/favorites/1001（favorite_source=series_detail）":"已取消收藏（J2）"); }); } function bindCohorts(){ const list=document.getElementById("cohortList"); if(!list) return; list.addEventListener("click",e=>{ const b=e.target.closest(".cohort")` |
| 649 | getElementById | cohortList | `getElementById("cohortList")` |
| 650 | event delegation selectors | .cohort | `addEventListener("click",e=>{ const b=e.target.closest(".cohort")` |
| 651 | classList operations | - | `classList.contains("disabled")` |
| 651 | closest | .cohort | `closest(".cohort")` |
| 657 | querySelectorAll | #tablist .tab | `querySelectorAll("#tablist .tab")` |
| 658 | classList operations | - | `classList.toggle("on",x===t)` |
| 658 | querySelectorAll | #tablist .tab | `querySelectorAll("#tablist .tab")` |
| 659 | classList operations | - | `classList.toggle("active",p.dataset.panel===t.dataset.tab)` |
| 659 | querySelectorAll | [data-panel] | `querySelectorAll("[data-panel]")` |
| 661 | querySelectorAll | [data-panel=outline] .lvl[data-lvl=module] | `querySelectorAll("[data-panel=outline] .lvl[data-lvl=module]")` |
| 662 | classList operations | - | `classList.toggle("open")` |
| 663 | classList operations | - | `classList.toggle("open",open)` |
| 663 | parentNode / nextSibling family | - | `.nextElementSibling` |
| 663 | parentNode / nextSibling family | - | `.nextElementSibling` |
| 667 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 673 | querySelectorAll | #cohortList .go-learn | `querySelectorAll("#cohortList .go-learn")` |
| 707 | getElementById | mainArea | `getElementById("mainArea")` |
| 723 | classList operations | - | `classList.toggle("on",b.dataset[k]===val)` |
| 723 | dynamic/template selectors | - | `querySelectorAll(\`.toolbar button[data-${k}]\`)` |
| 723 | querySelectorAll | - | `querySelectorAll(\`.toolbar button[data-${k}]\`)` |
| 724 | querySelectorAll | .toolbar button[data-s] | `querySelectorAll(".toolbar button[data-s]")` |
| 725 | querySelectorAll | .toolbar button[data-auth] | `querySelectorAll(".toolbar button[data-auth]")` |
| 726 | classList operations | - | `classList.toggle("on",x===b)` |
| 726 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 726 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 727 | classList operations | - | `classList.remove("on")` |
| 727 | getElementById | resetVp | `getElementById("resetVp")` |
| 727 | querySelectorAll | .toolbar button[data-w] | `querySelectorAll(".toolbar button[data-w]")` |
| 734 | classList operations | - | `classList.add('open')` |
| 734 | classList operations | - | `classList.add('open')` |
| 734 | classList operations | - | `classList.remove('open')` |
| 734 | classList operations | - | `classList.remove('open')` |
| 734 | classList operations | - | `classList.contains('open')` |
| 734 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 734 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 734 | getElementById | gnav | `getElementById('gnav')` |
| 741 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 765 | getElementById | mainArea | `getElementById("mainArea")` |
| 805 | parentNode / nextSibling family | - | `.parentNode` |
| 817 | querySelector | .dialog-x | `querySelector(".dialog-x")` |
| 823 | querySelector | #realDlgTitle | `querySelector("#realDlgTitle")` |
| 824 | querySelector | #realDlgBody | `querySelector("#realDlgBody")` |
| 825 | querySelector | #realDlgFoot | `querySelector("#realDlgFoot")` |
| 826 | classList operations | - | `classList.add("open")` |
| 829 | classList operations | - | `classList.remove("open")` |
| 844 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 845 | parentNode / nextSibling family | - | `.parentNode` |
| 847 | getElementById | myCouponEntry | `getElementById("myCouponEntry")` |
| 852 | parentNode / nextSibling family | - | `.nextSibling` |
| 868 | getElementById | couponList | `getElementById("couponList")` |
| 885 | getElementById | couponList | `getElementById("couponList")` |
| 905 | querySelectorAll | button[data-tpl] | `querySelectorAll("button[data-tpl]")` |
| 926 | getElementById | couponList | `getElementById("couponList")` |
| 928 | getElementById | couponDlgErr | `getElementById("couponDlgErr")` |
| 938 | getElementById | couponOpen | `getElementById("couponOpen")` |
| 942 | getElementById | couponList | `getElementById("couponList")` |
| 945 | getElementById | couponLoginBtn | `getElementById("couponLoginBtn")` |
| 984 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 999 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1003 | getElementById | enrollBtn | `getElementById("enrollBtn")` |
| 1035 | getElementById | writeReviewBtn | `getElementById("writeReviewBtn")` |
| 1039 | querySelector | [data-panel=review] | `querySelector("[data-panel=review]")` |
| 1058 | querySelector | #tablist .tab[data-tab="review"] | `querySelector('#tablist .tab[data-tab="review"]')` |
| 1062 | querySelector | [data-panel=review] | `querySelector("[data-panel=review]")` |
| 1072 | getElementById | rvLoginBtn | `getElementById("rvLoginBtn")` |
| 1098 | getElementById | starPick | `getElementById("starPick")` |
| 1108 | querySelectorAll | button[data-star] | `querySelectorAll("button[data-star]")` |
| 1128 | getElementById | reviewSubmit | `getElementById("reviewSubmit")` |
| 1134 | getElementById | reviewSubmit | `getElementById("reviewSubmit")` |
| 1135 | getElementById | reviewContent | `getElementById("reviewContent")` |
| 1136 | getElementById | reviewErr | `getElementById("reviewErr")` |
| 1153 | event delegation selectors | #tablist .tab[data-tab="review"] | `addEventListener("click", function (e) { if (!e.target \|\| !e.target.closest) return; if (e.target.closest('#tablist .tab[data-tab="review"]')` |
| 1155 | closest | #tablist .tab[data-tab="review"] | `closest('#tablist .tab[data-tab="review"]')` |
| 1165 | getElementById | favBtn | `getElementById("favBtn")` |
| 1174 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1188 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1196 | querySelector | #realDlgFoot button | `querySelector("#realDlgFoot button")` |
| 1208 | getElementById | favBtn | `getElementById("favBtn")` |
| 1226 | form.elements / name / tagName | - | `.name` |
| 1230 | form.elements / name / tagName | - | `.name` |
| 1239 | querySelector | h1.title,.title | `querySelector("h1.title,.title")` |
| 1240 | form.elements / name / tagName | - | `.name` |
| 1243 | querySelector | .breadcrumb .cur | `querySelector(".breadcrumb .cur")` |
| 1244 | form.elements / name / tagName | - | `.name` |
| 1245 | getElementById | crumbCat | `getElementById("crumbCat")` |

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
| 519 | getElementById | categoryRow | `getElementById("categoryRow")` |
| 525 | getElementById | subGroup | `getElementById("subGroup")` |
| 525 | getElementById | subRow | `getElementById("subRow")` |
| 541 | getElementById | fbSummary | `getElementById("fbSummary")` |
| 544 | classList operations | - | `classList.toggle("active",c===el)` |
| 544 | getElementById | - | `getElementById(rowId)` |
| 544 | querySelectorAll | .chip | `querySelectorAll(".chip")` |
| 628 | getElementById | resText | `getElementById("resText")` |
| 637 | getElementById | contentArea | `getElementById("contentArea")` |
| 651 | getElementById | contentArea | `getElementById("contentArea")` |
| 652 | getElementById | pgPages | `getElementById("pgPages")` |
| 653 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 657 | getElementById | contentArea | `getElementById("contentArea")` |
| 658 | getElementById | pgPages | `getElementById("pgPages")` |
| 659 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 666 | getElementById | contentArea | `getElementById("contentArea")` |
| 667 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 667 | getElementById | pgPages | `getElementById("pgPages")` |
| 673 | getElementById | pgPages | `getElementById("pgPages")` |
| 680 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 681 | getElementById | pgNext | `getElementById("pgNext")` |
| 682 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 685 | event delegation selectors | .chip | `addEventListener("click",()=>{ if(page>1){page--; refresh();} }); document.getElementById("pgNext").addEventListener("click",()=>{ if(page<totalPages){page++; refresh();} }); /* ---- 事件绑定 ---- */ document.getElementById("fbToggle").addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 685 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 686 | event delegation selectors | .chip | `addEventListener("click",()=>{ if(page<totalPages){page++; refresh();} }); /* ---- 事件绑定 ---- */ document.getElementById("fbToggle").addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 686 | getElementById | pgNext | `getElementById("pgNext")` |
| 689 | event delegation selectors | .chip | `addEventListener("click",e=>{ const open=document.getElementById("filterBar").classList.toggle("open"); document.getElementById("fbToggle").setAttribute("aria-expanded", open ? "true":"false"); }); document.getElementById("categoryRow").addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 689 | getElementById | fbToggle | `getElementById("fbToggle")` |
| 690 | classList operations | - | `classList.toggle("open")` |
| 690 | getElementById | filterBar | `getElementById("filterBar")` |
| 691 | getElementById | fbToggle | `getElementById("fbToggle")` |
| 693 | closest | .chip | `closest(".chip")` |
| 693 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 693 | getElementById | categoryRow | `getElementById("categoryRow")` |
| 694 | closest | .chip | `closest(".chip")` |
| 694 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 694 | getElementById | subRow | `getElementById("subRow")` |
| 695 | closest | .chip | `closest(".chip")` |
| 695 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 695 | getElementById | deliveryRow | `getElementById("deliveryRow")` |
| 696 | closest | .chip | `closest(".chip")` |
| 696 | event delegation selectors | .chip | `addEventListener("click",e=>{ const t=e.target.closest(".chip")` |
| 696 | getElementById | sortRow | `getElementById("sortRow")` |
| 697 | getElementById | priceSelect | `getElementById("priceSelect")` |
| 699 | getElementById | searchInput | `getElementById("searchInput")` |
| 701 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 705 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 705 | getElementById | searchInput | `getElementById("searchInput")` |
| 705 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 708 | classList operations | - | `classList.toggle("active",c.dataset.v==="全部")` |
| 708 | querySelectorAll | #categoryRow .chip | `querySelectorAll("#categoryRow .chip")` |
| 709 | classList operations | - | `classList.toggle("active",c.dataset.v==="")` |
| 709 | querySelectorAll | #deliveryRow .chip | `querySelectorAll("#deliveryRow .chip")` |
| 710 | classList operations | - | `classList.toggle("active",c.dataset.v==="default")` |
| 710 | querySelectorAll | #sortRow .chip | `querySelectorAll("#sortRow .chip")` |
| 711 | getElementById | priceSelect | `getElementById("priceSelect")` |
| 711 | getElementById | searchInput | `getElementById("searchInput")` |
| 711 | getElementById | clearBtn | `getElementById("clearBtn")` |
| 715 | getElementById | resetBtn | `getElementById("resetBtn")` |
| 726 | getElementById | - | `getElementById(id)` |
| 735 | getElementById | xpFill | `getElementById("xpFill")` |
| 747 | classList operations | - | `classList.add('open')` |
| 747 | classList operations | - | `classList.add('open')` |
| 747 | classList operations | - | `classList.remove('open')` |
| 747 | classList operations | - | `classList.remove('open')` |
| 747 | classList operations | - | `classList.contains('open')` |
| 747 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 747 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 747 | getElementById | gnav | `getElementById('gnav')` |
| 753 | getElementById | adminEntry | `getElementById("adminEntry")` |

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
| 485 | getElementById | - | `getElementById(id)` |
| 489 | querySelectorAll | .v-loading | `querySelectorAll(".v-loading")` |
| 490 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 495 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 669 | querySelector | p | `querySelector("p")` |
| 680 | querySelectorAll | .v-success | `querySelectorAll(".v-success")` |
| 681 | querySelector | .v-error | `querySelector(".v-error")` |
| 690 | classList operations | - | `classList.add('open')` |
| 690 | classList operations | - | `classList.add('open')` |
| 690 | classList operations | - | `classList.remove('open')` |
| 690 | classList operations | - | `classList.remove('open')` |
| 690 | classList operations | - | `classList.contains('open')` |
| 690 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 690 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 690 | getElementById | gnav | `getElementById('gnav')` |

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
| 145 | classList operations | - | `classList.add('open')` |
| 145 | classList operations | - | `classList.add('open')` |
| 145 | classList operations | - | `classList.remove('open')` |
| 145 | classList operations | - | `classList.remove('open')` |
| 145 | classList operations | - | `classList.contains('open')` |
| 145 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 145 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 145 | getElementById | gnav | `getElementById('gnav')` |
| 155 | getElementById | favStage | `getElementById("favStage")` |
| 156 | getElementById | favPager | `getElementById("favPager")` |
| 157 | getElementById | pgInfo | `getElementById("pgInfo")` |
| 158 | getElementById | pgPrev | `getElementById("pgPrev")` |
| 159 | getElementById | pgNext | `getElementById("pgNext")` |
| 274 | getElementById | adminEntry | `getElementById("adminEntry")` |

## learning.html

Total hooks: 13

| Category | Count |
|---|---:|
| getElementById | 1 |
| querySelector | 4 |
| querySelectorAll | 3 |
| classList operations | 2 |
| closest | 0 |
| matches | 0 |
| event delegation selectors | 0 |
| dynamic/template selectors | 2 |
| form.elements / name / tagName | 0 |
| parentNode / nextSibling family | 1 |

| Line | Category | Selector | Expression |
|---:|---|---|---|
| 458 | querySelectorAll | .tab | `querySelectorAll('.tab')` |
| 459 | querySelectorAll | .tab-panel | `querySelectorAll('.tab-panel')` |
| 461 | classList operations | - | `classList.toggle('on',idx===i)` |
| 462 | classList operations | - | `classList.toggle('active',idx===i)` |
| 484 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 503 | querySelector | h1,.title,[class*=title] | `querySelector("h1,.title,[class*=title]")` |
| 527 | dynamic/template selectors | - | `querySelector(s)` |
| 527 | querySelector | - | `querySelector(s)` |
| 528 | dynamic/template selectors | - | `querySelectorAll(s)` |
| 528 | querySelectorAll | - | `querySelectorAll(s)` |
| 554 | querySelector | .spinner | `querySelector(".spinner")` |
| 658 | querySelector | video.real-video | `querySelector("video.real-video")` |
| 730 | parentNode / nextSibling family | - | `.parentNode` |

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
| 2886 | classList operations | - | `classList.toggle("on", b.dataset.page===p)` |
| 2886 | querySelectorAll | #page-seg button | `querySelectorAll("#page-seg button")` |
| 2887 | classList operations | - | `classList.toggle("hidden", p!=="login")` |
| 2887 | getElementById | login-form | `getElementById("login-form")` |
| 2888 | classList operations | - | `classList.toggle("hidden", p!=="register")` |
| 2888 | getElementById | reg-form | `getElementById("reg-form")` |
| 2889 | getElementById | card-title | `getElementById("card-title")` |
| 2890 | getElementById | card-sub | `getElementById("card-sub")` |
| 2891 | getElementById | card-foot | `getElementById("card-foot")` |
| 2898 | classList operations | - | `classList.remove("show")` |
| 2898 | querySelectorAll | .banner | `querySelectorAll(".banner")` |
| 2899 | classList operations | - | `classList.remove("show")` |
| 2899 | querySelectorAll | .ferr | `querySelectorAll(".ferr")` |
| 2900 | classList operations | - | `classList.remove("err")` |
| 2900 | querySelectorAll | .ctl input | `querySelectorAll(".ctl input")` |
| 2914 | getElementById | li-banner-t | `getElementById("li-banner-t")` |
| 2915 | classList operations | - | `classList.add("show")` |
| 2915 | getElementById | li-banner | `getElementById("li-banner")` |
| 2918 | getElementById | rg-conflict-t | `getElementById("rg-conflict-t")` |
| 2919 | classList operations | - | `classList.add("show")` |
| 2919 | getElementById | rg-conflict | `getElementById("rg-conflict")` |
| 2948 | getElementById | - | `getElementById(hit.ferr)` |
| 2949 | getElementById | - | `getElementById(hit.input)` |
| 2950 | classList operations | - | `classList.add("show")` |
| 2951 | classList operations | - | `classList.add("err")` |
| 2967 | classList operations | - | `classList.toggle("busy", !!on)` |
| 2976 | getElementById | login-btn | `getElementById("login-btn")` |
| 2977 | getElementById | li-id | `getElementById("li-id")` |
| 2978 | getElementById | li-pwd | `getElementById("li-pwd")` |
| 3003 | getElementById | reg-btn | `getElementById("reg-btn")` |
| 3004 | getElementById | rg-u | `getElementById("rg-u")` |
| 3005 | getElementById | rg-n | `getElementById("rg-n")` |
| 3006 | getElementById | rg-e | `getElementById("rg-e")` |
| 3007 | getElementById | rg-p | `getElementById("rg-p")` |
| 3008 | getElementById | rg-c | `getElementById("rg-c")` |
| 3039 | getElementById | li-id | `getElementById("li-id")` |
| 3051 | event delegation selectors | [data-page] | `addEventListener("click",function(e){ var b=e.target.closest("[data-page]")` |
| 3051 | getElementById | page-seg | `getElementById("page-seg")` |
| 3052 | closest | [data-page] | `closest("[data-page]")` |
| 3054 | querySelectorAll | [data-eye] | `querySelectorAll("[data-eye]")` |
| 3055 | getElementById | - | `getElementById(this.dataset.eye)` |

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
| 4351 | classList operations | - | `classList.add('open')` |
| 4351 | classList operations | - | `classList.add('open')` |
| 4351 | classList operations | - | `classList.remove('open')` |
| 4351 | classList operations | - | `classList.remove('open')` |
| 4351 | classList operations | - | `classList.contains('open')` |
| 4351 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 4351 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 4351 | getElementById | gnav | `getElementById('gnav')` |
| 4360 | getElementById | - | `getElementById(id)` |
| 4368 | getElementById | me-prefs | `getElementById("me-prefs")` |
| 4371 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 4401 | getElementById | pfForm | `getElementById("pfForm")` |
| 4403 | getElementById | pfErr | `getElementById("pfErr")` |
| 4404 | getElementById | emToast | `getElementById("emToast")` |
| 4405 | getElementById | pfSave | `getElementById("pfSave")` |
| 4419 | classList operations | - | `classList.add("show")` |
| 4420 | classList operations | - | `classList.remove("show")` |
| 4422 | classList operations | - | `classList.add("show")` |
| 4423 | classList operations | - | `classList.remove("show")` |
| 4426 | getElementById | pf-grade_code | `getElementById("pf-grade_code")` |
| 4443 | getElementById | pf-goals | `getElementById("pf-goals")` |
| 4454 | classList operations | - | `classList.toggle("on")` |
| 4461 | getElementById | pf-nickname | `getElementById("pf-nickname")` |
| 4463 | getElementById | pf-school_name | `getElementById("pf-school_name")` |
| 4464 | getElementById | pf-study_style | `getElementById("pf-study_style")` |
| 4465 | getElementById | pf-weekly | `getElementById("pf-weekly")` |
| 4475 | getElementById | pf-nickname | `getElementById("pf-nickname")` |
| 4478 | getElementById | pf-grade_code | `getElementById("pf-grade_code")` |
| 4480 | getElementById | pf-school_name | `getElementById("pf-school_name")` |
| 4482 | getElementById | pf-study_style | `getElementById("pf-study_style")` |
| 4484 | getElementById | pf-weekly | `getElementById("pf-weekly")` |
| 4489 | querySelectorAll | #pf-goals .pf-goal.on | `querySelectorAll("#pf-goals .pf-goal.on")` |
| 4501 | getElementById | me-goal | `getElementById("me-goal")` |
| 4559 | getElementById | emOverlay | `getElementById("emOverlay")` |
| 4560 | getElementById | emForm | `getElementById("emForm")` |
| 4561 | getElementById | emErr | `getElementById("emErr")` |
| 4562 | getElementById | emToast | `getElementById("emToast")` |
| 4566 | getElementById | - | `getElementById(id)` |
| 4567 | getElementById | - | `getElementById(id)` |
| 4585 | classList operations | - | `classList.remove("show")` |
| 4599 | classList operations | - | `classList.add("open")` |
| 4604 | classList operations | - | `classList.remove("open")` |
| 4606 | classList operations | - | `classList.add("show")` |
| 4608 | classList operations | - | `classList.add("show")` |
| 4609 | classList operations | - | `classList.remove("show")` |
| 4612 | getElementById | me-name | `getElementById("me-name")` |
| 4613 | querySelector | .me-head .avatar | `querySelector(".me-head .avatar")` |
| 4615 | getElementById | me-prefs | `getElementById("me-prefs")` |
| 4624 | classList operations | - | `classList.remove("show")` |
| 4627 | getElementById | em-nickname | `getElementById("em-nickname")` |
| 4629 | getElementById | em-gender | `getElementById("em-gender")` |
| 4631 | getElementById | em-birthday | `getElementById("em-birthday")` |
| 4636 | getElementById | em-grade_code | `getElementById("em-grade_code")` |
| 4643 | getElementById | em-avatar_url | `getElementById("em-avatar_url")` |
| 4645 | getElementById | em-learning_goals | `getElementById("em-learning_goals")` |
| 4647 | getElementById | em-subject_preferences | `getElementById("em-subject_preferences")` |
| 4649 | getElementById | em-interest_tags | `getElementById("em-interest_tags")` |
| 4658 | classList operations | - | `classList.remove("open")` |
| 4667 | querySelector | .edit-btn | `querySelector(".edit-btn")` |
| 4669 | getElementById | emClose | `getElementById("emClose")` |
| 4670 | getElementById | emCancel | `getElementById("emCancel")` |
| 4701 | querySelector | .t10-retry | `querySelector(".t10-retry")` |
| 4711 | getElementById | odList | `getElementById("odList")` |
| 4711 | getElementById | odMeta | `getElementById("odMeta")` |
| 4712 | getElementById | odPrev | `getElementById("odPrev")` |
| 4712 | getElementById | odNext | `getElementById("odNext")` |
| 4713 | getElementById | odStatus | `getElementById("odStatus")` |
| 4756 | getElementById | cpList | `getElementById("cpList")` |
| 4756 | getElementById | cpMeta | `getElementById("cpMeta")` |
| 4757 | getElementById | cpPrev | `getElementById("cpPrev")` |
| 4757 | getElementById | cpNext | `getElementById("cpNext")` |
| 4796 | getElementById | fvList | `getElementById("fvList")` |
| 4796 | getElementById | fvMeta | `getElementById("fvMeta")` |
| 4826 | querySelector | .me-head .avatar | `querySelector(".me-head .avatar")` |

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
| 548 | querySelectorAll | .tab | `querySelectorAll('.tab')` |
| 549 | getElementById | tab-active | `getElementById('tab-active')` |
| 549 | getElementById | tab-completed | `getElementById('tab-completed')` |
| 549 | getElementById | tab-refunded | `getElementById('tab-refunded')` |
| 551 | classList operations | - | `classList.remove('on')` |
| 552 | classList operations | - | `classList.add('on')` |
| 553 | classList operations | - | `classList.toggle('active', k === t.dataset.tab)` |
| 567 | classList operations | - | `classList.add('open')` |
| 567 | classList operations | - | `classList.add('open')` |
| 567 | classList operations | - | `classList.remove('open')` |
| 567 | classList operations | - | `classList.remove('open')` |
| 567 | classList operations | - | `classList.contains('open')` |
| 567 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 567 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 567 | getElementById | gnav | `getElementById('gnav')` |
| 574 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 619 | getElementById | - | `getElementById("panel-" + p)` |
| 624 | querySelector | #panel-empty .btn | `querySelector("#panel-empty .btn")` |
| 626 | querySelector | #panel-error .btn | `querySelector("#panel-error .btn")` |
| 632 | getElementById | - | `getElementById("tabbtn-" + kk)` |
| 632 | getElementById | - | `getElementById("tab-" + kk)` |
| 635 | classList operations | - | `classList.toggle("on", on)` |
| 638 | classList operations | - | `classList.toggle("active", on)` |
| 653 | getElementById | - | `getElementById("tab-" + k)` |
| 653 | querySelector | .grid | `querySelector(".grid")` |
| 655 | getElementById | - | `getElementById("tabbtn-" + k)` |
| 655 | querySelector | .cnt | `querySelector(".cnt")` |
| 657 | getElementById | - | `getElementById("tab-empty-" + k)` |

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
| 814 | getElementById | stage | `getElementById('stage')` |
| 815 | querySelectorAll | .statebar button | `querySelectorAll('.statebar button')` |
| 818 | classList operations | - | `classList.remove('on')` |
| 819 | classList operations | - | `classList.add('on')` |
| 820 | getElementById | - | `getElementById(id)` |
| 824 | querySelectorAll | .q-typebar button | `querySelectorAll('.q-typebar button')` |
| 826 | classList operations | - | `classList.remove('on')` |
| 827 | classList operations | - | `classList.add('on')` |
| 828 | classList operations | - | `classList.add('hid')` |
| 828 | querySelectorAll | .quiz-item | `querySelectorAll('.quiz-item')` |
| 829 | classList operations | - | `classList.remove('hid')` |
| 829 | getElementById | - | `getElementById('qi-' + b.dataset.type)` |
| 833 | getElementById | qi-blank-submit | `getElementById('qi-blank-submit')` |
| 834 | getElementById | qi-blank-input | `getElementById('qi-blank-input')` |
| 835 | getElementById | qi-blank-result | `getElementById('qi-blank-result')` |
| 836 | getElementById | qi-blank-analysis | `getElementById('qi-blank-analysis')` |
| 840 | classList operations | - | `classList.remove('hid')` |
| 841 | classList operations | - | `classList.toggle('ok', ok)` |
| 842 | classList operations | - | `classList.toggle('error', !ok)` |
| 843 | querySelector | .t | `querySelector('.t')` |
| 844 | querySelector | .d | `querySelector('.d')` |
| 845 | querySelector | .big | `querySelector('.big')` |
| 846 | classList operations | - | `classList.remove('hid')` |
| 847 | classList operations | - | `classList.add('gray')` |
| 847 | classList operations | - | `classList.add('hid')` |
| 852 | querySelectorAll | .judge-opt | `querySelectorAll('.judge-opt')` |
| 854 | getElementById | qi-judge-result | `getElementById('qi-judge-result')` |
| 855 | getElementById | qi-judge-analysis | `getElementById('qi-judge-analysis')` |
| 856 | classList operations | - | `classList.remove('hid')` |
| 857 | classList operations | - | `classList.toggle('ok', correct)` |
| 858 | classList operations | - | `classList.toggle('error', !correct)` |
| 859 | querySelector | .t | `querySelector('.t')` |
| 860 | querySelector | .big | `querySelector('.big')` |
| 861 | classList operations | - | `classList.remove('hid')` |
| 862 | querySelectorAll | .judge-opt | `querySelectorAll('.judge-opt')` |
| 867 | classList operations | - | `classList.add('open')` |
| 867 | classList operations | - | `classList.add('open')` |
| 867 | classList operations | - | `classList.remove('open')` |
| 867 | classList operations | - | `classList.remove('open')` |
| 867 | classList operations | - | `classList.contains('open')` |
| 867 | getElementById | gnavToggle | `getElementById('gnavToggle')` |
| 867 | getElementById | gnavOverlay | `getElementById('gnavOverlay')` |
| 867 | getElementById | gnav | `getElementById('gnav')` |
| 874 | getElementById | adminEntry | `getElementById("adminEntry")` |
| 886 | getElementById | - | `getElementById(id)` |
| 953 | dynamic/template selectors | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 953 | querySelector | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 957 | dynamic/template selectors | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 957 | querySelector | - | `querySelector('td[data-wcode="' + row.custom_code + '"]')` |
| 969 | querySelectorAll | #wb-real .pill | `querySelectorAll('#wb-real .pill')` |
| 970 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { document.querySelectorAll('#wb-real .pill').forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); WB.status = b.dataset.wstatus; WB.page = 1; loadWrong(); }); }); $$('wbPrev').addEventListener('click', function () { if (WB.page > 1) { WB.page--; loadWrong(); } }); $$('wbNext').addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 971 | classList operations | - | `classList.remove('on')` |
| 971 | querySelectorAll | #wb-real .pill | `querySelectorAll('#wb-real .pill')` |
| 972 | classList operations | - | `classList.add('on')` |
| 977 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { if (WB.page > 1) { WB.page--; loadWrong(); } }); $$('wbNext').addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 978 | event delegation selectors | [data-wredo] | `addEventListener('click', function () { WB.page++; loadWrong(); }); document.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 979 | event delegation selectors | [data-wredo] | `addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-wredo]')` |
| 980 | closest | [data-wredo] | `closest('[data-wredo]')` |
| 982 | closest | tr | `closest('tr')` |
| 982 | querySelector | .type-chip | `querySelector('.type-chip')` |
| 992 | parentNode / nextSibling family | - | `.children` |
| 995 | classList operations | - | `classList.remove('hid')` |
| 1115 | querySelectorAll | #rvBody .rv-opt | `querySelectorAll('#rvBody .rv-opt')` |
| 1119 | classList operations | - | `classList.remove('correct')` |
| 1119 | querySelectorAll | #rvBody .rv-opt | `querySelectorAll('#rvBody .rv-opt')` |
| 1120 | classList operations | - | `classList.add('correct')` |
| 1124 | querySelectorAll | #rvBody .rv-judge | `querySelectorAll('#rvBody .rv-judge')` |
| 1128 | classList operations | - | `classList.remove('correct')` |
| 1128 | querySelectorAll | #rvBody .rv-judge | `querySelectorAll('#rvBody .rv-judge')` |
| 1129 | classList operations | - | `classList.add('correct')` |
| 1133 | querySelectorAll | #rvBody .rv-multi | `querySelectorAll('#rvBody .rv-multi')` |
| 1136 | classList operations | - | `classList.toggle('correct')` |
| 1141 | querySelector | #rvBody .drag-list | `querySelector('#rvBody .drag-list')` |
| 1144 | parentNode / nextSibling family | - | `.children` |
| 1144 | querySelector | .idx | `querySelector('.idx')` |
| 1146 | querySelectorAll | .drag-item .mv | `querySelectorAll('.drag-item .mv')` |
| 1149 | closest | .drag-item | `closest('.drag-item')` |
| 1150 | parentNode / nextSibling family | - | `.children` |
| 1159 | querySelector | #rvBody .rv-submit | `querySelector('#rvBody .rv-submit')` |
| 1161 | querySelectorAll | #rvBody .rv-next | `querySelectorAll('#rvBody .rv-next')` |
| 1169 | querySelectorAll | #rvBody .rv-multi.correct | `querySelectorAll('#rvBody .rv-multi.correct')` |
| 1174 | querySelectorAll | #rvBody .fill-blanks input[data-fill] | `querySelectorAll('#rvBody .fill-blanks input[data-fill]')` |
| 1178 | querySelectorAll | #rvBody .drag-item | `querySelectorAll('#rvBody .drag-item')` |
| 1181 | querySelectorAll | #rvBody .match-item select[data-match] | `querySelectorAll('#rvBody .match-item select[data-match]')` |
| 1205 | querySelector | #rvBody .rv-submit | `querySelector('#rvBody .rv-submit')` |
| 1206 | classList operations | - | `classList.add('gray')` |
| 1222 | classList operations | - | `classList.remove('gray')` |
| 1223 | querySelector | #rvBody .rv-result | `querySelector('#rvBody .rv-result')` |
| 1225 | classList operations | - | `classList.remove('hid')` |
| 1225 | classList operations | - | `classList.remove('ok')` |
| 1225 | classList operations | - | `classList.add('error')` |
| 1226 | querySelector | .big | `querySelector('.big')` |
| 1227 | querySelector | .t | `querySelector('.t')` |
| 1228 | querySelector | .d | `querySelector('.d')` |
| 1233 | querySelector | #rvBody .rv-result | `querySelector('#rvBody .rv-result')` |
| 1234 | querySelector | #rvBody .rv-expl | `querySelector('#rvBody .rv-expl')` |
| 1235 | querySelector | #rvBody .rv-mast | `querySelector('#rvBody .rv-mast')` |
| 1236 | querySelector | #rvBody .rv-next | `querySelector('#rvBody .rv-next')` |
| 1238 | classList operations | - | `classList.remove('hid')` |
| 1239 | classList operations | - | `classList.toggle('ok', !!r.is_correct)` |
| 1240 | classList operations | - | `classList.toggle('error', !r.is_correct)` |
| 1241 | querySelector | .big | `querySelector('.big')` |
| 1242 | querySelector | .t | `querySelector('.t')` |
| 1245 | querySelector | .d | `querySelector('.d')` |
| 1249 | classList operations | - | `classList.remove('hid')` |
| 1251 | classList operations | - | `classList.toggle('hid', !r.explain_text)` |
| 1258 | classList operations | - | `classList.remove('hid')` |
| 1265 | classList operations | - | `classList.add('hid')` |
| 1270 | querySelectorAll | #rvBody .rv-next | `querySelectorAll('#rvBody .rv-next')` |
| 1312 | querySelectorAll | #vocabCards .word-acts button | `querySelectorAll('#vocabCards .word-acts button')` |
| 1315 | closest | .word-card | `closest('.word-card')` |
| 1319 | querySelectorAll | .word-acts button | `querySelectorAll('.word-acts button')` |
| 1322 | querySelector | .word-fb | `querySelector('.word-fb')` |
| 1331 | querySelectorAll | .word-acts button | `querySelectorAll('.word-acts button')` |
| 1332 | querySelector | .word-fb | `querySelector('.word-fb')` |
| 1373 | querySelectorAll | #topic-real .pill[data-ttype] | `querySelectorAll('#topic-real .pill[data-ttype]')` |
| 1375 | classList operations | - | `classList.remove('on')` |
| 1375 | querySelectorAll | #topic-real .pill[data-ttype] | `querySelectorAll('#topic-real .pill[data-ttype]')` |
| 1376 | classList operations | - | `classList.add('on')` |
| 1391 | classList operations | - | `classList.remove('hid')` |
| 1392 | classList operations | - | `classList.remove('hid')` |
| 1393 | classList operations | - | `classList.remove('hid')` |
| 1403 | querySelector | .entry.green .go | `querySelector('.entry.green .go')` |
| 1405 | querySelector | .entry.blue .go | `querySelector('.entry.blue .go')` |
| 1407 | querySelector | .entry.purple .go | `querySelector('.entry.purple .go')` |

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
| 211 | getElementById | flash | `getElementById("flash")` |
| 248 | getElementById | - | `getElementById(id)` |
| 418 | event delegation selectors | [data-cancel] | `addEventListener("submit", applyRefund); $("ticketForm").addEventListener("submit", submitTicket); $("pgPrev").addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 419 | event delegation selectors | [data-cancel] | `addEventListener("submit", submitTicket); $("pgPrev").addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 420 | event delegation selectors | [data-cancel] | `addEventListener("click", function(){ if(state.page>1){ state.page--; loadRefunds(); } }); $("pgNext").addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 421 | event delegation selectors | [data-cancel] | `addEventListener("click", function(){ state.page++; loadRefunds(); }); $("refundList").addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 422 | event delegation selectors | [data-cancel] | `addEventListener("click", function(ev){ var b = ev.target.closest && ev.target.closest("[data-cancel]")` |
| 423 | closest | [data-cancel] | `closest("[data-cancel]")` |
