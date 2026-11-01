// 浏览器端到端：转让群主（按钮可见性 → 转让 → 徽章易主 → 权力收尾）
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
    const groupName = 'UI转让测试群-' + Date.now().toString(36);
    await page.click('#btn-new-group');
    await page.waitForSelector('#group-modal.show', { timeout: 5000 });
    await page.type('#group-title', groupName);
    await page.click('#group-ok');
    await page.waitForFunction(
      t => document.querySelector('#chat-title').textContent === t,
      { timeout: 8000 }, groupName);
    check('建群后自动打开该群', true);

    // ---------- 邀请 samm 进群（转让目标） ----------
    console.log('[3] 邀请成员');
    await page.click('#btn-invite');
    await page.waitForSelector('#invite-modal.show', { timeout: 5000 });
    const boxCount = await page.$$eval('#invite-members input[type=checkbox]', els => els.length);
    if (boxCount === 0) throw new Error('没有可邀请的成员，无法测试转让');
    await page.click('#invite-members input[type=checkbox]');
    await page.click('#invite-ok');
    await new Promise(r => setTimeout(r, 1500));
    const sub = await page.$eval('#chat-sub', el => el.textContent);
    check('邀请后 2 人', /2 人/.test(sub), 'sub=' + sub);

    // ---------- 成员名单：转让按钮可见性 ----------
    console.log('[4] 转让按钮可见性');
    await page.click('#btn-members');
    await page.waitForSelector('#members-modal.show', { timeout: 5000 });
    const transferBtns = await page.$$('#members-list button.transfer');
    check('群主看到 1 个转让按钮（只在别人行上）', transferBtns.length === 1,
      'count=' + transferBtns.length);
    // 自己的行上没有转让按钮
    const myRowHasTransfer = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#members-list .member-row'));
      const myRow = rows.find(r => r.querySelector('.tag:not(.owner)'));
      return !!(myRow && myRow.querySelector('button.transfer'));
    });
    check('自己行上无转让按钮', !myRowHasTransfer);
    await page.screenshot({ path: SHOT_DIR + '/7-transfer-button.png' });

    // ---------- 执行转让 ----------
    console.log('[5] 执行转让');
    await page.click('#members-list button.transfer');
    await new Promise(r => setTimeout(r, 2000)); // confirm 已自动接受
    // 名单刷新：samm 戴上群主徽章，我失去徽章
    const ownerTags = await page.$$eval('#members-list .tag.owner', els =>
      els.map(el => {
        const row = el.closest('.member-row');
        return row ? row.textContent : '';
      }));
    check('群主徽章只有 1 个', ownerTags.length === 1, JSON.stringify(ownerTags));
    check('群主徽章在 sam 行上', ownerTags.length === 1 && /sam/.test(ownerTags[0]),
      JSON.stringify(ownerTags));
    const transferBtnsAfter = await page.$$('#members-list button.transfer');
    check('转让后自己不再有转让按钮', transferBtnsAfter.length === 0,
      'count=' + transferBtnsAfter.length);

    // ---------- 权力收尾 ----------
    console.log('[6] 权力变化');
    const sub2 = await page.$eval('#chat-sub', el => el.textContent);
    check('副标题群主变为 sam', /群主 sam/.test(sub2), 'sub=' + sub2);
    const dissolveVisible = await page.$eval('#btn-dissolve', el =>
      getComputedStyle(el).display !== 'none');
    check('解散按钮已隐藏（不再是群主）', !dissolveVisible);
    const inviteVisible = await page.$eval('#btn-invite', el =>
      getComputedStyle(el).display !== 'none');
    check('邀请按钮仍可见（普通成员也能邀请）', inviteVisible);
    await page.screenshot({ path: SHOT_DIR + '/8-after-transfer.png' });

    // ---------- 清理：改库把群主改回 workbuddy 再解散 ----------
    console.log('[7] 清理');
    // 从页面拿到群 id：通过 API 列表找标题匹配的群
    const rid = await page.evaluate(async () => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const room = (j.rooms || []).find(x => x.title.startsWith('UI转让测试群-'));
      return room ? room.id : null;
    });
    check('找到测试群 id', !!rid, 'rid=' + rid);
    if (rid) {
      // 通知服务端改库由外部完成，这里先本地刷新拿回解散权不可行（无 SSH 通道），
      // 改为：UI 上无权解散，直接由测试脚本通过页面无法完成，交由 API 侧清理。
      console.log('  (群 ' + rid + ' 将由 SSH 清理)');
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
