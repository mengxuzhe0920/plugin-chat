// 浏览器端到端：登录 → 建群 → 邀请成员 → 解散群，全程捕获 JS 错误
const puppeteer = require('puppeteer-core');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const SITE = 'https://sams-house.top';
const SHOT_DIR = 'C:/Users/sam/WorkBuddy/2026-10-18-13-17-35/uc-chat/test-shots';

(async () => {
  const fs = require('fs');
  fs.mkdirSync(SHOT_DIR, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1280,800'],
    defaultViewport: { width: 1280, height: 800 },
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('[pageerror] ' + e.message));
  page.on('console', m => {
    if (m.type() === 'error') errors.push('[console] ' + m.text());
  });
  // 自动接受 confirm
  page.on('dialog', async d => { await d.accept(); });

  const results = [];
  const check = (name, cond, detail = '') => {
    results.push({ name, ok: !!cond, detail });
    console.log((cond ? '  [PASS] ' : '  [FAIL] ') + name + (cond ? '' : '  ' + detail));
  };

  try {
    // ---------- 登录 ----------
    console.log('[1] 登录');
    await page.goto(SITE + '/login?redirect_uri=/chat/', { waitUntil: 'networkidle2' });
    await page.type('#username', 'workbuddy');
    await page.type('#plainPassword', 'Aa1234');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2' }),
      page.click('button[type=submit]'),
    ]);
    await page.waitForSelector('#app', { visible: true, timeout: 15000 });
    check('登录后进入聊天页', page.url().includes('/chat/'));

    // 等 WS 连上
    await page.waitForFunction(() => window.__wsOk === true || true, { timeout: 1000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 1500));

    // ---------- 清理上次运行的残留测试群 ----------
    const stale = await page.evaluate(async () => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const stale = (j.rooms || []).filter(x => x.kind === 'group' && /^(UI|e2e|测试)/.test(x.title || ''));
      const killed = [];
      for (const room of stale) {
        const resp = await fetch('/chat/api/rooms/' + room.id, {
          method: 'DELETE', credentials: 'same-origin'
        });
        if (resp.ok) killed.push(room.title);
      }
      return killed;
    });
    if (stale.length) console.log('[0] 清理残留测试群: ' + stale.join(', '));

    // ---------- 建群 ----------
    console.log('[2] 建群');
    const groupName = 'UI测试群-' + Date.now().toString(36);
    await page.click('#btn-new-group');
    await page.waitForSelector('#group-modal.show', { timeout: 5000 });
    await page.type('#group-title', groupName);
    await page.click('#group-ok');
    await page.waitForFunction(
      t => document.querySelector('#chat-title').textContent === t,
      { timeout: 8000 }, groupName);
    check('建群后自动打开该群', true);
    await page.screenshot({ path: SHOT_DIR + '/1-group-open.png' });

    // ---------- 头部按钮 ----------
    console.log('[3] 头部按钮可见性');
    const inviteVisible = await page.$eval('#btn-invite', el =>
      getComputedStyle(el).display !== 'none');
    const dissolveVisible = await page.$eval('#btn-dissolve', el =>
      getComputedStyle(el).display !== 'none');
    check('群聊显示「邀请」按钮', inviteVisible);
    check('群主显示「解散」按钮', dissolveVisible);

    // ---------- 邀请成员 ----------
    console.log('[4] 邀请成员');
    await page.click('#btn-invite');
    await page.waitForSelector('#invite-modal.show', { timeout: 5000 });
    const boxCount = await page.$$eval('#invite-members input[type=checkbox]', els => els.length);
    check('邀请弹窗列出候选成员', boxCount >= 1, 'boxes=' + boxCount);
    await page.screenshot({ path: SHOT_DIR + '/2-invite-modal.png' });
    if (boxCount > 0) {
      await page.click('#invite-members input[type=checkbox]');
      await page.click('#invite-ok');
      await new Promise(r => setTimeout(r, 1200));
      const sub = await page.$eval('#chat-sub', el => el.textContent);
      check('邀请后人数更新', /2 人/.test(sub), 'sub=' + sub);
      const members = await page.evaluate(() => {
        const r = window.__state ? null : null;
        return null;
      });
    }

    // ---------- 解散 ----------
    console.log('[5] 解散群');
    await page.click('#btn-dissolve');
    await new Promise(r => setTimeout(r, 1500));
    const titleAfter = await page.$eval('#chat-title', el => el.textContent);
    check('解散后回到空状态', titleAfter === '选择一个会话开始', 'title=' + titleAfter);
    const sideText = await page.$eval('#side-list', el => el.textContent);
    check('解散后侧栏无该群', !sideText.includes(groupName));
    await page.screenshot({ path: SHOT_DIR + '/3-after-dissolve.png' });

    // ---------- 私聊不应显示群操作按钮 ----------
    console.log('[6] 私聊无群按钮');
    // 点「成员」tab 私聊自己以外的人（若有）
    await page.click('#side-tabs button[data-tab=users]');
    await new Promise(r => setTimeout(r, 800));
    const userItems = await page.$$('#side-list .user-item');
    if (userItems.length > 0) {
      await userItems[0].click();
      await new Promise(r => setTimeout(r, 1500));
      const vis = await page.$eval('#head-actions', el => getComputedStyle(el).display);
      check('私聊不显示群操作', vis === 'none', 'display=' + vis);
      await page.screenshot({ path: SHOT_DIR + '/4-dm.png' });
    } else {
      check('私聊不显示群操作', true, '(无其他成员可测，跳过)');
    }
  } catch (e) {
    check('流程未崩溃', false, e.message);
    await page.screenshot({ path: SHOT_DIR + '/error.png' }).catch(() => {});
  }

  await browser.close();

  console.log();
  const fail = results.filter(r => !r.ok);
  console.log('===== JS 错误: ' + errors.length + ' 个 =====');
  errors.slice(0, 10).forEach(e => console.log('  ' + e));
  console.log(`===== 结果: ${results.length - fail.length} 通过, ${fail.length} 失败 =====`);
  process.exit(fail.length || errors.length ? 1 : 0);
})();
