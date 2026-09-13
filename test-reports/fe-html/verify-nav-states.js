const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;
const byPath = p => `file://${path.join(root, p).replace(/\\/g, "/")}`;
const wait = () => new Promise(r => setTimeout(r, 140));

(async () => {
  const b = await chromium.launch({ headless: true });
  const out = {};
  // community-post
  {
    const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
    await p.goto(byPath("community-post.html"));
    const r = {};
    const c = s => p.click('.respbar ' + s).then(wait);
    await c('[data-st="ok"]');      r.successComments = await p.locator('#page .c-item').count();
    await c('[data-st="loading"]'); r.loadingSkeleton = await p.locator('#page .sk-card').count();
    await c('[data-st="error"]');   r.errorRetry = await p.locator('#page .state .retry').count(); r.errorState = await p.locator('#page .state').count();
    await c('[data-st="empty"]');   r.emptyState = await p.locator('#page .state').count(); r.emptyComments = await p.locator('#page .c-item').count();
    out.communityPost = r; await p.close();
  }
  // practice (await properly)
  {
    const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
    await p.goto(byPath("practice.html"));
    const c = s => p.click('.statebar ' + s).then(wait);
    await c('button[data-state="success"]'); const sv = await p.locator('#panel-success').isVisible();
    await c('button[data-state="loading"]'); const sk = await p.locator('#panel-loading .skel-card').count();
    await c('button[data-state="error"]');   const er = await p.locator('#panel-error .btn-retry').count();
    await c('button[data-state="empty"]');   const em = await p.locator('#panel-empty .btn-go').count();
    out.practice = { successPanelVisible: sv, loadingSkeleton: sk, errorPanelRetry: er, emptyPanelCTA: em };
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(out, null, 2));
})();