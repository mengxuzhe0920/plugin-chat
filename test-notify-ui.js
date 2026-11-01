// 浏览器端到端：消息提醒四件套（提示音 / 系统通知 / 红点 / 标签页标题）+ 表情面板
// 用 WebSocket 探针模拟“别人发来的消息”，无需第二个账号
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
  // 授予通知权限（真实权限体系）
  browser.defaultBrowserContext().overridePermissions(SITE, ['notifications']);

  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('[pageerror] ' + e.message));
  page.on('console', m => {
    if (m.type() === 'error') errors.push('[console] ' + m.text());
  });
  page.on('dialog', async d => { await d.accept(); });

  // 探针：录制通知与音频振荡器；用假 WebSocket 接管实时通道
  await page.evaluateOnNewDocument(() => {
    window.__notifs = [];
    window.__oscCount = 0;
    window.__wsInstances = [];
    // --- Notification 录制桩 ---
    window.Notification = class {
      static permission = 'granted';
      constructor(title, opts) {
        window.__notifs.push({
          title: title,
          body: (opts && opts.body) || '',
          tag: (opts && opts.tag) || '',
        });
        this.onclick = null;
      }
      close() {}
      static requestPermission() { return Promise.resolve('granted'); }
    };
    // --- AudioContext 录制桩（只数振荡器，不真的放音）---
    window.AudioContext = class {
      constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; }
      createOscillator() {
        window.__oscCount++;
        return { type: '', frequency: { value: 0 }, connect() {}, start() {}, stop() {} };
      }
      createGain() {
        return { gain: { value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} };
      }
      resume() { return Promise.resolve(); }
    };
    // --- WebSocket 桩 ---
    window.WebSocket = class {
      constructor(url) {
        this.url = url; this.readyState = 0;
        window.__wsInstances.push(this);
        setTimeout(() => { this.readyState = 1; if (this.onopen) this.onopen(); }, 50);
      }
      send() {}
      close() {}
    };
    // 测试辅助：模拟服务端推来一条消息
    window.__pushServer = (obj) => {
      const ws = window.__wsInstances[0];
      if (!ws) throw new Error('no ws instance');
      ws.onmessage({ data: JSON.stringify(obj) });
    };
  });

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

    // ---------- 建两个群：G1 打开着，G2 在后台 ----------
    console.log('[2] 建群');
    const G1 = '提醒测试A-' + Date.now().toString(36);
    const G2 = '提醒测试B-' + Date.now().toString(36);
    for (const name of [G1, G2]) {
      await page.click('#btn-new-group');
      await page.waitForSelector('#group-modal.show', { timeout: 5000 });
      await page.type('#group-title', name);
      await page.click('#group-ok');
      await page.waitForFunction(
        t => document.querySelector('#chat-title').textContent === t,
        { timeout: 8000 }, name);
    }
    // 点开 G1（G2 退为后台）
    await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll('#side-list .room-item'));
      const el = items.find(x => x.textContent.includes(name));
      if (el) el.click();
    }, G1);
    await new Promise(r => setTimeout(r, 800));
    check('G1 为当前会话', /提醒测试A/.test(await page.$eval('#chat-title', el => el.textContent)));
    const roomIds = await page.evaluate(async () => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const g1 = (j.rooms || []).find(x => x.title.startsWith('提醒测试A-'));
      const g2 = (j.rooms || []).find(x => x.title.startsWith('提醒测试B-'));
      return { g1: g1 && g1.id, g2: g2 && g2.id };
    });
    check('拿到两个群 id', !!(roomIds.g1 && roomIds.g2), JSON.stringify(roomIds));

    // ---------- 声音开关 ----------
    console.log('[3] 提示音开关');
    const soundOnInit = await page.$eval('#btn-sound', el => el.classList.contains('on'));
    check('提示音默认开启', soundOnInit);
    const oscBefore = await page.evaluate(() => window.__oscCount);
    await page.click('#btn-sound'); // 关
    await new Promise(r => setTimeout(r, 300));
    check('关闭后按钮状态', !(await page.$eval('#btn-sound', el => el.classList.contains('on'))));
    check('关闭不发音（振荡器不增加）',
      (await page.evaluate(() => window.__oscCount)) === oscBefore);
    await page.click('#btn-sound'); // 开 → 立刻试听
    await new Promise(r => setTimeout(r, 300));
    const oscAfter = await page.evaluate(() => window.__oscCount);
    check('开启时试听叮咚（振荡器 4 个）', oscAfter - oscBefore === 4,
      'delta=' + (oscAfter - oscBefore));

    // ---------- 系统通知开关 ----------
    console.log('[4] 系统通知开关');
    await page.click('#btn-notify');
    await new Promise(r => setTimeout(r, 500));
    check('铃铛开启（已授权）',
      await page.$eval('#btn-notify', el => el.classList.contains('on')));
    check('开启时弹出测试通知',
      (await page.evaluate(() => window.__notifs)).length === 1,
      JSON.stringify(await page.evaluate(() => window.__notifs)));

    // ---------- 后台会话来消息：通知 + 红点 + 标题 ----------
    console.log('[5] 后台消息提醒');
    await page.evaluate(() => { window.__notifs.length = 0; });
    await page.evaluate((rid) => {
      window.__pushServer({
        type: 'msg', room: rid, id: 99001,
        sender: 'samm', sender_display: 'sam', sender_avatar: '',
        content: '在吗？看到消息回一下', created_at: Math.floor(Date.now() / 1000),
      });
    }, roomIds.g2);
    await new Promise(r => setTimeout(r, 600));

    const notifs = await page.evaluate(() => window.__notifs);
    check('收到系统通知', notifs.length === 1, JSON.stringify(notifs));
    check('通知标题含发送者', notifs.length === 1 && /sam/.test(notifs[0].title),
      JSON.stringify(notifs));
    check('通知正文含消息内容',
      notifs.length === 1 && notifs[0].body.includes('看到消息'), JSON.stringify(notifs));
    check('通知带房间 tag',
      notifs.length === 1 && notifs[0].tag === 'uc-chat-' + roomIds.g2, JSON.stringify(notifs));

    const oscMid = await page.evaluate(() => window.__oscCount);
    check('提示音响起（振荡器 +4）', oscMid - oscAfter === 4, 'delta=' + (oscMid - oscAfter));

    // 红点：G2 侧栏项
    const badge = await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll('#side-list .room-item'));
      const el = items.find(x => x.textContent.includes(name));
      const b = el && el.querySelector('.badge');
      return b ? b.textContent : '';
    }, G2);
    check('后台群显示红点 1', badge === '1', 'badge=' + badge);
    check('标签页标题显示未读 (1)',
      (await page.title()) === '(1) 小窝聊天', 'title=' + await page.title());
    await page.screenshot({ path: SHOT_DIR + '/12-unread-badge.png' });

    // 当前会话来消息：不弹通知（正在看），但后台标签页要计红点
    console.log('[6] 当前会话 + 模拟后台标签页');
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.evaluate((rid) => {
      window.__pushServer({
        type: 'msg', room: rid, id: 99002,
        sender: 'samm', sender_display: 'sam', sender_avatar: '',
        content: '当前会话的后台消息', created_at: Math.floor(Date.now() / 1000),
      });
    }, roomIds.g1);
    await new Promise(r => setTimeout(r, 500));
    const notifs2 = await page.evaluate(() => window.__notifs);
    check('后台标签页的当前会话也弹通知', notifs2.length === 2,
      JSON.stringify(notifs2));
    const badgeG1 = await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll('#side-list .room-item'));
      const el = items.find(x => x.textContent.includes(name));
      const b = el && el.querySelector('.badge');
      return b ? b.textContent : '';
    }, G1);
    check('当前会话在后台也计红点', badgeG1 === '1', 'badge=' + badgeG1);

    // 回到前台：红点清零
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await new Promise(r => setTimeout(r, 300));
    const badgeG1b = await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll('#side-list .room-item'));
      const el = items.find(x => x.textContent.includes(name));
      const b = el && el.querySelector('.badge');
      return b ? b.textContent : '';
    }, G1);
    check('回前台后当前会话红点清零', !badgeG1b, 'badge=' + badgeG1b);
    check('标题仍有未读 1（G2 未读）',
      (await page.title()) === '(1) 小窝聊天', 'title=' + await page.title());

    // 点开 G2：红点清零、标题恢复
    await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll('#side-list .room-item'));
      const el = items.find(x => x.textContent.includes(name));
      if (el) el.click();
    }, G2);
    await new Promise(r => setTimeout(r, 600));
    check('打开 G2 后标题恢复', (await page.title()) === '小窝聊天',
      'title=' + await page.title());

    // ---------- 表情 ----------
    console.log('[7] 表情面板');
    await page.click('#btn-emoji');
    await page.waitForSelector('#emoji-panel.show', { timeout: 5000 });
    check('表情面板打开', true);
    const emojiCount = await page.$$eval('#emoji-grid button', els => els.length);
    check('表情数量 64', emojiCount === 64, 'count=' + emojiCount);
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('#emoji-grid button'));
      const b = btns.find(x => x.textContent === '😀');
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 300));
    const inputVal = await page.$eval('#input', el => el.value);
    check('点击表情插入输入框', inputVal.includes('😀'), 'value=' + inputVal);
    await page.screenshot({ path: SHOT_DIR + '/13-emoji-panel.png' });
    // 点外面关闭
    await page.click('#msg-wrap');
    await new Promise(r => setTimeout(r, 200));
    check('点外面关闭表情面板',
      !(await page.$('#emoji-panel.show')));
    // 清空输入框（不真的发出去）
    await page.evaluate(() => {
      const inp = document.querySelector('#input');
      inp.value = '';
      inp.dispatchEvent(new Event('input'));
    });

    // ---------- 清理：解散两个测试群 ----------
    console.log('[8] 清理');
    const cleaned = await page.evaluate(async () => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const stale = (j.rooms || []).filter(x => x.kind === 'group');
      for (const room of stale) {
        await fetch('/chat/api/rooms/' + room.id, { method: 'DELETE', credentials: 'same-origin' });
      }
      return stale.map(x => x.title);
    });
    check('测试群已解散', cleaned.length === 2, JSON.stringify(cleaned));
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
