// 浏览器端到端：退出群聊（群主禁退提示 → 转让后退群 → 界面收尾）
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

    // ---------- 建群 + 邀请 ----------
    console.log('[2] 建群并邀请');
    const groupName = 'UI退群测试群-' + Date.now().toString(36);
    await page.click('#btn-new-group');
    await page.waitForSelector('#group-modal.show', { timeout: 5000 });
    await page.type('#group-title', groupName);
    await page.click('#group-ok');
    await page.waitForFunction(
      t => document.querySelector('#chat-title').textContent === t,
      { timeout: 8000 }, groupName);
    await page.click('#btn-invite');
    await page.waitForSelector('#invite-modal.show', { timeout: 5000 });
    const boxCount = await page.$$eval('#invite-members input[type=checkbox]', els => els.length);
    if (boxCount === 0) throw new Error('没有可邀请的成员');
    await page.click('#invite-members input[type=checkbox]');
    await page.click('#invite-ok');
    await new Promise(r => setTimeout(r, 1500));
    check('邀请后 2 人', /2 人/.test(await page.$eval('#chat-sub', el => el.textContent)));

    // ---------- 群主视角：无退群按钮 + 提示 ----------
    console.log('[3] 群主视角');
    await page.click('#btn-members');
    await page.waitForSelector('#members-modal.show', { timeout: 5000 });
    const leaveBtnsOwner = await page.$$('#members-list button.leave');
    check('群主看不到退群按钮', leaveBtnsOwner.length === 0, 'count=' + leaveBtnsOwner.length);
    const hintVisible = await page.$eval('#members-hint', el =>
      getComputedStyle(el).display !== 'none' && el.textContent.length > 0);
    check('群主看到禁退提示', hintVisible);
    await page.screenshot({ path: SHOT_DIR + '/9-owner-hint.png' });

    // ---------- 转让给 samm，变成普通成员 ----------
    console.log('[4] 转让群主给 sam');
    await page.click('#members-list button.transfer');
    await new Promise(r => setTimeout(r, 2000));
    const sub = await page.$eval('#chat-sub', el => el.textContent);
    check('已成为普通成员（群主是 sam）', /群主 sam/.test(sub), 'sub=' + sub);

    // ---------- 普通成员视角：我的行有退群按钮 ----------
    console.log('[5] 普通成员视角');
    // 转让后弹窗已自动刷新；若意外关闭则重开
    if (!(await page.$('#members-modal.show'))) {
      await page.click('#btn-members');
      await page.waitForSelector('#members-modal.show', { timeout: 5000 });
    }
    const leaveBtns = await page.$$('#members-list button.leave');
    check('自己行上出现退群按钮', leaveBtns.length === 1, 'count=' + leaveBtns.length);
    const transferBtns = await page.$$('#members-list button.transfer');
    check('普通成员看不到转让按钮', transferBtns.length === 0, 'count=' + transferBtns.length);
    const hintHidden = await page.$eval('#members-hint', el =>
      getComputedStyle(el).display === 'none');
    check('普通成员无禁退提示', hintHidden);
    await page.screenshot({ path: SHOT_DIR + '/10-leave-button.png' });

    // ---------- 执行退群 ----------
    console.log('[6] 执行退群');
    await page.click('#members-list button.leave');
    await new Promise(r => setTimeout(r, 2000)); // confirm 已自动接受
    const modalGone = !(await page.$('#members-modal.show'));
    check('退群后弹窗关闭', modalGone);
    const titleAfter = await page.$eval('#chat-title', el => el.textContent);
    check('退群后回到空状态', titleAfter === '选择一个会话开始', 'title=' + titleAfter);
    const sideText = await page.$eval('#side-list', el => el.textContent);
    check('退群后侧栏无该群', !sideText.includes(groupName));
    await page.screenshot({ path: SHOT_DIR + '/11-after-leave.png' });

    // ---------- 清理：找出测试群 id 交给 SSH ----------
    const rid = await page.evaluate(async () => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const room = (j.rooms || []).find(x => x.kind === 'group');
      return room ? room.id : null;
    });
    console.log('  (残留群 id: ' + rid + '，普通成员视角已不该看到任何群)');
    check('退群后列表无任何群', !rid, 'rid=' + rid);
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
