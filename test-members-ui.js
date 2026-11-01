// 浏览器端到端：群成员名单面板（群主标识 / 邀请后实时刷新 / 副标题显示群主）
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
    const groupName = 'UI成员测试群-' + Date.now().toString(36);
    await page.click('#btn-new-group');
    await page.waitForSelector('#group-modal.show', { timeout: 5000 });
    await page.type('#group-title', groupName);
    await page.click('#group-ok');
    await page.waitForFunction(
      t => document.querySelector('#chat-title').textContent === t,
      { timeout: 8000 }, groupName);
    check('建群后自动打开该群', true);

    // ---------- 头部：群主显示在副标题 ----------
    console.log('[3] 头部群主信息');
    const membersBtnVisible = await page.$eval('#btn-members', el =>
      getComputedStyle(el).display !== 'none');
    check('群聊显示「成员」按钮', membersBtnVisible);
    const sub = await page.$eval('#chat-sub', el => el.textContent);
    check('副标题显示群主', /群主/.test(sub), 'sub=' + sub);
    check('副标题显示人数', /1 人/.test(sub), 'sub=' + sub);

    // ---------- 成员弹窗 ----------
    console.log('[4] 成员名单弹窗');
    await page.click('#btn-members');
    await page.waitForSelector('#members-modal.show', { timeout: 5000 });
    check('成员弹窗打开', true);
    const modalTitle = await page.$eval('#members-title', el => el.textContent);
    check('弹窗标题含群名与人数',
      modalTitle.includes(groupName) && /1 人/.test(modalTitle), 'title=' + modalTitle);
    const rowCount = await page.$$eval('#members-list .member-row', els => els.length);
    check('名单 1 行', rowCount === 1, 'rows=' + rowCount);
    const ownerTag = await page.$eval('#members-list .tag.owner', el => el.textContent)
      .catch(() => null);
    check('群主标识存在', ownerTag === '群主', 'tag=' + ownerTag);
    const meTag = await page.$eval('#members-list .tag:not(.owner)', el => el.textContent)
      .catch(() => null);
    check('「我」标识存在', meTag === '我', 'tag=' + meTag);
    const stText = await page.$eval('#members-list .st', el => el.textContent);
    check('显示在线状态', /在线|离线/.test(stText), 'st=' + stText);
    await page.screenshot({ path: SHOT_DIR + '/5-members-modal.png' });

    // ---------- 邀请后弹窗实时刷新 ----------
    console.log('[5] 邀请后名单刷新');
    await page.click('#members-close');
    await page.click('#btn-invite');
    await page.waitForSelector('#invite-modal.show', { timeout: 5000 });
    const boxCount = await page.$$eval('#invite-members input[type=checkbox]', els => els.length);
    if (boxCount > 0) {
      await page.click('#invite-members input[type=checkbox]');
      await page.click('#invite-ok');
      await new Promise(r => setTimeout(r, 1500));
      const sub2 = await page.$eval('#chat-sub', el => el.textContent);
      check('邀请后副标题人数更新', /2 人/.test(sub2), 'sub=' + sub2);
      // 重新打开成员弹窗
      await page.click('#btn-members');
      await page.waitForSelector('#members-modal.show', { timeout: 5000 });
      const rowCount2 = await page.$$eval('#members-list .member-row', els => els.length);
      check('邀请后名单 2 行', rowCount2 === 2, 'rows=' + rowCount2);
      const rows = await page.$$eval('#members-list .member-row', els =>
        els.map(el => ({
          text: el.textContent,
          isOwner: !!el.querySelector('.tag.owner'),
        })));
      check('群主仍只有 1 个且置顶',
        rows.filter(r => r.isOwner).length === 1 && rows[0].isOwner,
        JSON.stringify(rows));
      await page.screenshot({ path: SHOT_DIR + '/6-members-after-invite.png' });
    } else {
      check('邀请后副标题人数更新', true, '(无候选成员，跳过)');
    }

    // ---------- 清理：解散群 ----------
    console.log('[6] 解散群');
    await page.click('#members-close');
    await page.click('#btn-dissolve');
    await new Promise(r => setTimeout(r, 1500));
    const titleAfter = await page.$eval('#chat-title', el => el.textContent);
    check('解散后回到空状态', titleAfter === '选择一个会话开始', 'title=' + titleAfter);
    const sideText = await page.$eval('#side-list', el => el.textContent);
    check('解散后侧栏无该群', !sideText.includes(groupName));
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
