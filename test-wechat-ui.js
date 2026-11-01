// 微信风格 UI 端到端测试（真实 Chrome + 真实登录）
// 覆盖：三栏布局 / 系统通知视图 / 建群 / 文本消息（自己的蓝气泡）/ 他人消息（白气泡+昵称）/
//      红点+标题未读 / 叮咚提示音 / 图片消息（他人推送+自己上传）/ 灯箱 / 表情面板 /
//      通讯录 / 设置开关 / 搜索过滤 / 「…」菜单（权限） / 查看聊天记录（渲染+搜索+失败重试）/
//      发送文件（气泡+下载） / WS 断开发送保护 / 移动端布局 / 零 JS 错误
const puppeteer = require('puppeteer-core');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const SITE = 'https://sams-house.top';
const SHOT_DIR = 'C:/Users/sam/WorkBuddy/2026-10-18-13-17-35/uc-chat/test-shots';

(async () => {
  const fs = require('fs');
  fs.mkdirSync(SHOT_DIR, { recursive: true });

  // 本地测试图片（4x4 红色 PNG）
  const PNG_4x4 = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAFUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64');
  const UPLOAD_PNG = SHOT_DIR + '/tmp-upload-test.png';
  fs.writeFileSync(UPLOAD_PNG, PNG_4x4);

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1280,800'],
    defaultViewport: { width: 1280, height: 800 },
  });
  browser.defaultBrowserContext().overridePermissions(SITE, ['notifications']);

  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('[pageerror] ' + e.message));
  page.on('console', m => {
    if (m.type() === 'error') errors.push('[console] ' + m.text());
  });
  page.on('dialog', async d => { await d.accept(); });

  // ---------- 探针：通知 / 音频 / WebSocket ----------
  await page.evaluateOnNewDocument(() => {
    window.__notifs = [];
    window.__oscCount = 0;
    window.__wsInstances = [];
    window.__wsSent = [];
    window.Notification = class {
      static permission = 'granted';
      constructor(title, opts) {
        window.__notifs.push({ title, body: (opts && opts.body) || '', tag: (opts && opts.tag) || '' });
        this.onclick = null;
      }
      close() {}
      static requestPermission() { return Promise.resolve('granted'); }
    };
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
    // WebSocket 桩：模拟服务端——把发送方自己的 msg 也广播回来（真实服务端行为）
    window.__myName = null;
    window.WebSocket = class {
      constructor(url) {
        this.url = url; this.readyState = 0;
        window.__wsInstances.push(this);
        setTimeout(() => { this.readyState = 1; if (this.onopen) this.onopen(); }, 50);
      }
      send(raw) {
        let obj = {};
        try { obj = JSON.parse(raw); } catch (e) { return; }
        window.__wsSent.push(obj);
        if (obj.type === 'join') {
          setTimeout(() => this.onmessage({ data: JSON.stringify({ type: 'joined', room: obj.room, online: [] }) }), 10);
        } else if (obj.type === 'msg') {
          // 回显（服务端广播给房间内所有人，含发送者）
          setTimeout(() => this.onmessage({ data: JSON.stringify({
            type: 'msg', room: obj.room, id: Date.now() % 100000,
            sender: window.__myName || 'me',
            sender_display: window.__myName || 'me',
            sender_avatar: '',
            content: obj.content, kind: obj.kind || 'text',
            fname: obj.fname || '',
            created_at: Math.floor(Date.now() / 1000),
          }) }), 10);
        }
      }
      close() {}
    };
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
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // 清理遗留的测试群（之前异常退出可能没解散）与测试上传图
  const cleanupStale = async () => {
    try {
      await page.evaluate(async () => {
        const j = await (await fetch('/chat/api/rooms', { credentials: 'same-origin' })).json();
        const stale = (j.rooms || []).filter(r => /^(微信风测试群|提醒测试|e2e-)/.test(r.title || ''));
        for (const r of stale) {
          await fetch('/chat/api/rooms/' + r.id, { method: 'DELETE', credentials: 'same-origin' });
        }
      });
    } catch (e) { console.log('[cleanup] 房间清理跳过:', e.message); }
    try {
      const { execSync } = require('child_process');
      execSync('echo "rm -f /opt/uc-chat/uploads/e2e-push.png" | "C:/Users/sam/.workbuddy/binaries/python/envs/default/Scripts/python.exe" "C:/Users/sam/WorkBuddy/2026-10-13-21-16-59/tools/ssh-run.py" 191.40.37.234 root e4ZxNJnAdicbElo8',
        { stdio: 'ignore', timeout: 60000 });
    } catch (e) { console.log('[cleanup] 上传图清理跳过:', e.message); }
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
    await sleep(1800);
    await cleanupStale();
    await sleep(500);

    // 把真实用户名塞进桩（用于回显 sender）
    await page.evaluate(() => {
      window.__myName = JSON.parse(localStorage.getItem('uc_chat_me') || '{}').name || 'workbuddy';
    });

    // ---------- 三栏布局 ----------
    console.log('[2] 微信式三栏布局');
    const layout = await page.evaluate(() => {
      const nav = document.querySelector('#nav');
      const side = document.querySelector('#side');
      const main = document.querySelector('#main');
      const nb = nav.getBoundingClientRect(), sb = side.getBoundingClientRect(), mb = main.getBoundingClientRect();
      return {
        navW: Math.round(nb.width), sideW: Math.round(sb.width),
        order: nb.left < sb.left && sb.left < mb.left,
        mainVisible: mb.width > 300,
        searchPlaceholder: (document.querySelector('#search') || {}).placeholder || '',
      };
    });
    check('导航栏约 64px 且在左', layout.navW === 64 && layout.order, JSON.stringify(layout));
    check('会话列表 300px', layout.sideW === 300, String(layout.sideW));
    check('搜索框占位文案', layout.searchPlaceholder.includes('搜索'), layout.searchPlaceholder);
    await page.screenshot({ path: SHOT_DIR + '/wechat-1-main.png' });

    // ---------- 系统通知视图 ----------
    console.log('[3] 系统通知');
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('#side-list .item'));
      const el = items.find(x => x.textContent.includes('系统通知'));
      if (el) el.click();
    });
    await sleep(600);
    check('系统通知标题', (await page.$eval('#chat-title', el => el.textContent)) === '系统通知');
    check('通知列表渲染', await page.$eval('#notice-wrap', el =>
      el.style.display !== 'none' && el.querySelectorAll('.notice').length >= 3));
    check('通知含公告链接', await page.$eval('#notice-wrap', el =>
      !!el.querySelector('a[href*="uc-chat-launch"]')));
    check('通知视图隐藏撰写区', await page.$eval('#composer', el => el.style.display === 'none'));
    await page.screenshot({ path: SHOT_DIR + '/wechat-2-notice.png' });

    // ---------- 建群 ----------
    console.log('[4] 建群');
    const GNAME = '微信风测试群-' + Date.now().toString(36);
    await page.click('#btn-add');
    await page.waitForSelector('#add-pop.show', { timeout: 5000 });
    await page.click('#add-group');
    await page.waitForSelector('#group-modal.show', { timeout: 5000 });
    await page.type('#group-title', GNAME);
    await page.click('#group-ok');
    await page.waitForFunction(
      t => document.querySelector('#chat-title').textContent === t,
      { timeout: 8000 }, GNAME);
    check('建群后打开该群', true);
    const rid = await page.evaluate(async (name) => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      const g = (j.rooms || []).find(x => x.title === name);
      return g && g.id;
    }, GNAME);
    check('拿到群 id', !!rid, String(rid));
    check('群副标题显示人数与群主', /1 人 · 群主/.test(
      await page.$eval('#chat-sub', el => el.textContent)),
      await page.$eval('#chat-sub', el => el.textContent));

    // ---------- 自己发文本 ----------
    console.log('[5] 自己发文本消息');
    await page.click('#input');
    await page.type('#input', '大家好，这是新界面');
    check('发送按钮随输入启用', !(await page.$eval('#btn-send', el => el.disabled)));
    await page.click('#btn-send');
    await page.waitForSelector('.msg-row.me .bubble', { timeout: 5000 });
    const meBubble = await page.$eval('.msg-row.me .bubble', el => ({
      text: el.textContent, color: getComputedStyle(el).backgroundColor,
    }));
    check('自己的消息内容正确', meBubble.text === '大家好，这是新界面', meBubble.text);
    check('自己的气泡是蓝色', meBubble.color === 'rgb(76, 139, 245)', meBubble.color);
    const myPos = await page.evaluate(() => {
      const row = document.querySelector('.msg-row.me');
      const av = row.querySelector('.avatar').getBoundingClientRect();
      const bb = row.querySelector('.bubble').getBoundingClientRect();
      return { avLeft: av.left, bbLeft: bb.left, avRight: av.right, bbRight: bb.right };
    });
    check('自己的消息：头像在气泡右侧（靠右布局）', myPos.avLeft > myPos.bbLeft,
      JSON.stringify(myPos));
    check('输入框已清空', (await page.$eval('#input', el => el.value)) === '');
    await page.screenshot({ path: SHOT_DIR + '/wechat-3-group-chat.png' });

    // ---------- 别人发文本（当前会话、前台：不响不弹不计数） ----------
    console.log('[6] 他人消息（前台当前会话）');
    const osc0 = await page.evaluate(() => window.__oscCount);
    const notif0 = await page.evaluate(() => window.__notifs.length);
    await page.evaluate((r) => {
      window.__pushServer({
        type: 'msg', room: r, id: 90001, sender: 'samm',
        sender_display: 'Samm 大哥', sender_avatar: '',
        content: '你们好呀', kind: 'text', created_at: Math.floor(Date.now() / 1000),
      });
    }, rid);
    await page.waitForSelector('.msg-row.other .bubble', { timeout: 5000 });
    check('他人白气泡渲染', await page.$eval('.msg-row.other .bubble', el =>
      getComputedStyle(el).backgroundColor === 'rgb(255, 255, 255)'));
    check('群聊显示发送者昵称', (await page.$eval('.msg-row.other .msg-who', el => el.textContent)) === 'Samm 大哥');
    const otherPos = await page.evaluate(() => {
      const row = document.querySelector('.msg-row.other');
      const av = row.querySelector('.avatar').getBoundingClientRect();
      const bb = row.querySelector('.bubble').getBoundingClientRect();
      return { avLeft: av.left, bbLeft: bb.left };
    });
    check('他人消息：头像在气泡左侧（靠左布局）', otherPos.avLeft < otherPos.bbLeft,
      JSON.stringify(otherPos));
    check('前台当前会话不发音', (await page.evaluate(() => window.__oscCount)) === osc0);
    check('前台当前会话不弹通知', (await page.evaluate(() => window.__notifs.length)) === notif0);
    check('前台当前会话无红点', await page.evaluate(() =>
      !document.querySelector('.item.active .badge')));

    // ---------- 后台会话来消息：通知 + 叮咚 + 红点 + 标题 ----------
    console.log('[7] 后台消息提醒');
    // 先开启系统通知（设置弹层里）
    await page.click('#btn-settings');
    await page.waitForSelector('#settings-pop.show', { timeout: 3000 });
    await page.click('#row-notify');
    await sleep(600);
    check('开启通知时弹出测试通知', (await page.evaluate(() => window.__notifs)).length === 1,
      JSON.stringify(await page.evaluate(() => window.__notifs)));
    check('通知开关变为开启态', await page.$eval('#sw-notify', el => el.classList.contains('on')));
    await page.evaluate(() => { window.__notifs.length = 0; document.body.click(); });
    await sleep(200);

    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    });
    await page.evaluate((r) => {
      window.__notifs.length = 0;
      window.__pushServer({
        type: 'msg', room: r, id: 90002, sender: 'samm',
        sender_display: 'Samm 大哥', sender_avatar: '',
        content: '后台也提醒', kind: 'text', created_at: Math.floor(Date.now() / 1000),
      });
    }, rid);
    await sleep(700);
    const oscDelta = (await page.evaluate(() => window.__oscCount)) - osc0;
    check('后台消息播放叮咚（振荡器 +4）', oscDelta === 4, 'delta=' + oscDelta);
    check('后台消息弹系统通知', (await page.evaluate(() => window.__notifs)).length === 1,
      JSON.stringify(await page.evaluate(() => window.__notifs)));
    check('通知标题含发送者与会话', await page.evaluate(() => {
      const n = window.__notifs[0] || {};
      return n.title.includes('Samm 大哥') && n.title.includes('微信风测试群');
    }), JSON.stringify(await page.evaluate(() => window.__notifs)));
    check('当前会话后台也计红点', await page.evaluate(() => {
      const b = document.querySelector('.item.active .badge');
      return !!b && b.textContent === '1';
    }));
    check('标签页标题显示未读', (await page.title()) === '(1) 小窝聊天', await page.title());
    // 回前台清零
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await sleep(300);
    check('回前台红点清零', await page.evaluate(() =>
      !document.querySelector('.item.active .badge')));
    check('回前台标题恢复', (await page.title()) === '小窝聊天', await page.title());

    // ---------- 图片消息：他人推送 ----------
    console.log('[8] 他人发图片');
    const imgUrl = await page.evaluate(async () => {
      const b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAFUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
      const r = await fetch('/chat/api/upload', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'e2e-push.png', data: b64 }),
      });
      const j = await r.json();
      return j.url;
    });
    check('测试图片上传成功', !!imgUrl, String(imgUrl));
    await page.evaluate((u, r) => {
      window.__pushServer({
        type: 'msg', room: r, id: 90003, sender: 'samm',
        sender_display: 'Samm 大哥', sender_avatar: '',
        content: u, kind: 'image', created_at: Math.floor(Date.now() / 1000),
      });
    }, imgUrl, rid);
    await page.waitForSelector('img.msg-img', { timeout: 5000 });
    check('图片消息渲染 img.msg-img', await page.$eval('img.msg-img', (el, u) => el.src.endsWith(u), imgUrl));
    await sleep(400);
    check('图片加载完成（占位移除）', await page.evaluate(() =>
      !document.querySelector('.msg-row.other .img-ph')));
    // 灯箱
    await page.click('img.msg-img');
    await sleep(400);
    check('点击图片打开灯箱', await page.$eval('#lightbox', el => el.classList.contains('show')));
    await page.click('#lightbox');
    await sleep(300);
    check('再点关闭灯箱', !(await page.$eval('#lightbox', el => el.classList.contains('show'))));

    // ---------- 自己发图片（上传接口 + WS 发送） ----------
    console.log('[9] 自己发图片');
    await page.evaluate(() => { window.__wsSent.length = 0; });
    const fileInput = await page.$('#file-input');
    await fileInput.uploadFile(UPLOAD_PNG);
    await page.waitForFunction(() => {
      const chip = document.querySelector('#upload-chip');
      return chip.classList.contains('hidden');
    }, { timeout: 15000 });
    const sent = await page.evaluate(() => window.__wsSent.find(x => x.type === 'msg'));
    check('上传后通过 WS 发送图片消息', !!sent && sent.kind === 'image'
      && /^\/chat\/uploads\/[A-Za-z0-9]+\.png$/.test(sent.content || ''), JSON.stringify(sent));
    await page.waitForFunction(() =>
      document.querySelectorAll('.msg-row.me img.msg-img').length >= 1, { timeout: 5000 });
    check('自己的图片气泡渲染', true);
    check('自己的图片在右侧行', await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('.msg-row'));
      const last = rows[rows.length - 1];
      if (!last.classList.contains('me') || !last.querySelector('img.msg-img')) return false;
      const av = last.querySelector('.avatar').getBoundingClientRect();
      const im = last.querySelector('img.msg-img').getBoundingClientRect();
      return av.left > im.left; // 头像在图片右侧
    }));
    await page.screenshot({ path: SHOT_DIR + '/wechat-4-image-msg.png' });

    // ---------- 表情面板 ----------
    console.log('[10] 表情面板');
    await page.click('#btn-emoji');
    await page.waitForSelector('#emoji-panel.show', { timeout: 3000 });
    const emojiCount = await page.$$eval('#emoji-grid button', bs => bs.length);
    check('表情面板 64 个', emojiCount === 64, String(emojiCount));
    await page.evaluate(() => document.querySelectorAll('#emoji-grid button')[0].click());
    check('表情插入输入框', (await page.$eval('#input', el => el.value)).includes('😀'));
    await page.evaluate(() => { document.body.click(); });
    await sleep(200);
    check('点外面关闭表情面板', !(await page.$eval('#emoji-panel', el => el.classList.contains('show'))));

    // ---------- 通讯录 ----------
    console.log('[11] 通讯录');
    await page.click('#tab-contacts');
    await sleep(800);
    check('通讯录显示分区标题', await page.evaluate(() =>
      Array.from(document.querySelectorAll('.side-sec')).some(x => x.textContent === '群聊')));
    check('通讯录含本群', await page.evaluate((name) =>
      document.querySelector('#side-list').textContent.includes(name), GNAME));
    await page.screenshot({ path: SHOT_DIR + '/wechat-5-contacts.png' });

    // ---------- 设置开关 ----------
    console.log('[12] 设置');
    await page.click('#tab-chats');
    await page.click('#btn-settings');
    await page.waitForSelector('#settings-pop.show', { timeout: 3000 });
    check('设置弹层打开', true);
    check('提示音默认开启', await page.$eval('#sw-sound', el => el.classList.contains('on')));
    await page.click('#row-sound');
    check('提示音可关闭', !(await page.$eval('#sw-sound', el => el.classList.contains('on'))));
    await page.click('#row-sound');
    check('提示音可再开启', await page.$eval('#sw-sound', el => el.classList.contains('on')));
    await page.evaluate(() => document.body.click());

    // ---------- 「…」弹出菜单 ----------
    console.log('[13] 「…」菜单');
    await page.click('#btn-more');
    await page.waitForSelector('#more-pop.show', { timeout: 5000 });
    check('「…」菜单弹出', true);
    check('菜单含「查看聊天记录」', await page.evaluate(() =>
      document.querySelector('#more-history').textContent.includes('查看聊天记录')));
    check('群聊显示「群成员」', await page.evaluate(() =>
      getComputedStyle(document.querySelector('#more-members')).display !== 'none'));
    check('群主可见「解散群聊」', await page.evaluate(() =>
      getComputedStyle(document.querySelector('#more-dissolve')).display !== 'none'));
    await page.screenshot({ path: SHOT_DIR + '/wechat-6-more-menu.png' });
    // 点「群成员」打开成员弹窗
    await page.click('#more-members');
    await page.waitForSelector('#members-modal.show', { timeout: 5000 });
    check('菜单进入成员弹窗', true);
    check('群主徽章存在', await page.$eval('#members-list', el =>
      !!el.querySelector('.tag') && el.textContent.includes('群主')));
    check('邀请与解散按钮对群主可见', await page.evaluate(() =>
      document.querySelector('#btn-members-invite').style.display !== 'none' &&
      document.querySelector('#btn-members-dissolve').style.display !== 'none'));
    await page.screenshot({ path: SHOT_DIR + '/wechat-6-members.png' });
    await page.evaluate(() => document.querySelector('#members-modal .x').click());
    await sleep(200);
    check('成员弹窗可关闭', !(await page.$eval('#members-modal', el => el.classList.contains('show'))));

    // ---------- 查看聊天记录弹窗 ----------
    console.log('[13.5] 查看聊天记录');
    // 用 fetch 桩提供 3 条罐头消息（文本/图片/文件），验证渲染与搜索
    await page.evaluate(() => {
      window.__fetchOrig = window.fetch;
      window.__histMode = 'ok';       // ok | fail-once
      window.__histCalls = [];
      const CANNED = [
        { id: 101, sender: 'samm', sender_display: 'Samm 大哥', sender_avatar: '',
          content: '第一条文本消息', kind: 'text', fname: '', created_at: 1792321000 },
        { id: 102, sender: 'workbuddy', sender_display: 'WorkBuddy', sender_avatar: '',
          content: '/chat/uploads/e2ecanned.png', kind: 'image', fname: '', created_at: 1792321060 },
        { id: 103, sender: 'workbuddy', sender_display: 'WorkBuddy', sender_avatar: '',
          content: '/chat/uploads/e2ecanned.pdf', kind: 'file', fname: '测试文件.pdf',
          created_at: 1792321120 },
      ];
      window.__histCanned = CANNED;
      window.fetch = (url, opts) => {
        const u = String(url);
        if (u.includes('/messages')) {
          window.__histCalls.push(u);
          if (window.__histMode === 'fail-once') {
            window.__histMode = 'ok';
            return Promise.reject(new Error('网络异常'));
          }
          const isSearch = u.includes('q=');
          const list = isSearch ? CANNED.filter(m => m.content.includes('第一条')) : CANNED;
          return Promise.resolve(new Response(JSON.stringify({ ok: true, messages: list }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }));
        }
        return window.__fetchOrig(url, opts);
      };
    });
    await page.click('#btn-more');
    await page.waitForSelector('#more-pop.show', { timeout: 5000 });
    await page.click('#more-history');
    await page.waitForSelector('#history-modal.show', { timeout: 5000 });
    await page.waitForFunction(() =>
      document.querySelectorAll('#history-list .history-msg').length === 3, { timeout: 5000 });
    check('历史弹窗渲染 3 条消息', true);
    check('历史文本消息正确', await page.evaluate(() =>
      document.querySelector('#history-list .history-text').textContent === '第一条文本消息'));
    check('历史图片可放大（点击元素存在）', await page.evaluate(() =>
      !!document.querySelector('#history-list img.history-img')));
    const fileLink = await page.evaluate(() => {
      const a = document.querySelector('#history-list a.history-file');
      return a ? { href: a.getAttribute('href'), download: a.getAttribute('download'),
                   text: a.textContent } : null;
    });
    check('历史文件带下载链接', !!fileLink && fileLink.download === '测试文件.pdf'
      && fileLink.href === '/chat/uploads/e2ecanned.pdf', JSON.stringify(fileLink));
    check('历史文件显示文件名', !!fileLink && fileLink.text.includes('测试文件.pdf'));
    check('不足一页时「加载更多」隐藏', await page.evaluate(() =>
      document.querySelector('#history-more').style.display === 'none'));
    check('状态提示「已加载全部记录」', await page.$eval('#history-status', el =>
      el.textContent.includes('已加载全部记录'), ));
    // 关键词搜索
    await page.click('#history-q');
    await page.type('#history-q', '第一条');
    await page.click('#history-search-btn');
    await page.waitForFunction(() =>
      document.querySelectorAll('#history-list .history-msg').length === 1, { timeout: 5000 });
    check('搜索后只剩命中消息', true);
    check('搜索请求带 q 参数', await page.evaluate(() =>
      window.__histCalls.some(u => u.includes('q='))));
    check('「清除」按钮出现', await page.evaluate(() =>
      document.querySelector('#history-clear-btn').style.display !== 'none'));
    // 加载失败 + 重试
    await page.evaluate(() => { window.__histMode = 'fail-once'; });
    await page.click('#history-clear-btn');
    await page.waitForFunction(() =>
      !!document.querySelector('#history-list .history-error'), { timeout: 5000 });
    check('加载失败显示错误与重试按钮', true);
    await page.click('#history-list .history-retry');
    await page.waitForFunction(() =>
      document.querySelectorAll('#history-list .history-msg').length === 3, { timeout: 5000 });
    check('点重试后恢复渲染', true);
    await page.screenshot({ path: SHOT_DIR + '/wechat-8-history.png' });
    // 恢复真实 fetch，关闭弹窗
    await page.evaluate(() => { window.fetch = window.__fetchOrig; });
    await page.evaluate(() => document.querySelector('#history-modal .x').click());
    await sleep(200);
    check('历史弹窗可关闭', !(await page.$eval('#history-modal', el => el.classList.contains('show'))));

    // ---------- 发送文件 ----------
    console.log('[13.6] 发送文件');
    const UPLOAD_TXT = SHOT_DIR + '/tmp-upload-test.txt';
    fs.writeFileSync(UPLOAD_TXT, '小窝聊天文件消息测试内容');
    await page.evaluate(() => { window.__wsSent.length = 0; });
    const docInput = await page.$('#file-doc-input');
    await docInput.uploadFile(UPLOAD_TXT);
    // 直接等 WS 发送记录（上传完成 → 发送），避免与 chip 隐藏竞态
    await page.waitForFunction(() =>
      window.__wsSent.some(x => x.type === 'msg' && x.kind === 'file'), { timeout: 20000 });
    await page.waitForFunction(() => {
      const chip = document.querySelector('#upload-chip');
      return chip.classList.contains('hidden');
    }, { timeout: 5000 });
    const fileSent = await page.evaluate(() =>
      window.__wsSent.find(x => x.type === 'msg' && x.kind === 'file'));
    check('文件通过 WS 发送 kind=file', !!fileSent
      && fileSent.fname === 'tmp-upload-test.txt'
      && /^\/chat\/uploads\/[A-Za-z0-9]+\.txt$/.test(fileSent.content || ''),
      JSON.stringify(fileSent));
    await page.waitForFunction(() =>
      document.querySelectorAll('.msg-row.me a.file-bubble').length >= 1, { timeout: 5000 });
    const fileBubble = await page.evaluate(() => {
      const a = document.querySelector('.msg-row.me a.file-bubble');
      return a ? { download: a.getAttribute('download'), text: a.textContent,
                   href: a.getAttribute('href') } : null;
    });
    check('自己的文件气泡渲染', !!fileBubble, JSON.stringify(fileBubble));
    check('文件气泡带 download 原名', !!fileBubble
      && fileBubble.download === 'tmp-upload-test.txt', JSON.stringify(fileBubble));
    check('文件气泡显示文件名', !!fileBubble
      && fileBubble.text.includes('tmp-upload-test.txt'), JSON.stringify(fileBubble));
    // 文件气泡应在右侧行（自己的消息）
    check('文件气泡在右侧行', await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('.msg-row'));
      const last = rows[rows.length - 1];
      if (!last.classList.contains('me') || !last.querySelector('a.file-bubble')) return false;
      const av = last.querySelector('.avatar').getBoundingClientRect();
      const bb = last.querySelector('a.file-bubble').getBoundingClientRect();
      return av.left > bb.left;
    }));
    await page.screenshot({ path: SHOT_DIR + '/wechat-9-file-msg.png' });
    // 记录服务器上的测试文件名，供清理
    if (fileSent && fileSent.content) {
      await page.evaluate((u) => { window.__testUploadName = u.split('/').pop(); },
        fileSent.content);
    }

    // ---------- WS 断开时发送不丢 ----------
    console.log('[13.7] WS 断开发送保护');
    await page.evaluate(() => { window.__wsSent.length = 0; });
    // 先清空输入框（前面表情测试可能残留内容，type 是追加）
    await page.evaluate(() => { document.querySelector('#input').value = ''; });
    await page.click('#input');
    await page.type('#input', '断线测试消息');
    check('输入框内容就绪', (await page.$eval('#input', el => el.value)) === '断线测试消息');
    await page.evaluate(() => { window.__wsInstances[0].readyState = 3; }); // CLOSED
    await page.click('#btn-send');
    await sleep(400);
    check('断线时弹提示', await page.$eval('#toast', el =>
      el.classList.contains('show') && el.textContent.includes('连接已断开')));
    check('断线时输入内容保留', (await page.$eval('#input', el => el.value)) === '断线测试消息');
    await page.evaluate(() => { window.__wsInstances[0].readyState = 1; }); // OPEN
    await page.click('#btn-send');
    await sleep(400);
    check('恢复连接后重发成功', await page.evaluate(() =>
      window.__wsSent.some(x => x.type === 'msg' && x.content === '断线测试消息')));
    check('重发后输入框清空', (await page.$eval('#input', el => el.value)) === '');

    // ---------- 搜索过滤 ----------
    console.log('[14] 搜索');
    await page.click('#search');
    await page.type('#search', GNAME);
    await sleep(500);
    const searchDump = await page.evaluate(() => ({
      items: Array.from(document.querySelectorAll('#side-list .item .name')).map(x => x.textContent),
    }));
    check('搜索结果全部命中',
      searchDump.items.length >= 1 && searchDump.items.every(t => t.includes(GNAME)),
      JSON.stringify(searchDump));
    check('搜索命中测试群', searchDump.items.some(t => t === GNAME),
      JSON.stringify(searchDump));
    await page.evaluate(() => { const s = document.querySelector('#search'); s.value = ''; s.dispatchEvent(new Event('input')); });

    // ---------- 移动端 ----------
    console.log('[15] 移动端布局');
    // 模拟“刚打开页面”：先收起聊天区（桌面视口下 openRoom 也会加这个 class）
    await page.evaluate(() => document.querySelector('#app').classList.remove('show-chat'));
    await page.setViewport({ width: 390, height: 780 });
    await sleep(500);
    check('窄屏默认显示列表', await page.evaluate(() => {
      const app = document.querySelector('#app');
      return !app.classList.contains('show-chat') &&
        getComputedStyle(document.querySelector('#side')).display !== 'none';
    }));
    await page.evaluate((name) => {
      const el = Array.from(document.querySelectorAll('#side-list .item[data-room]'))
        .find(x => x.textContent.includes(name));
      if (el) el.click();
    }, GNAME);
    await sleep(600);
    check('窄屏点会话后显示聊天区', await page.evaluate(() =>
      document.querySelector('#app').classList.contains('show-chat') &&
      getComputedStyle(document.querySelector('#main')).display !== 'none'));
    check('窄屏返回按钮可见', await page.$eval('#btn-back', el =>
      getComputedStyle(el).display !== 'none'));
    await page.screenshot({ path: SHOT_DIR + '/wechat-7-mobile.png' });
    await page.click('#btn-back');
    await sleep(400);
    check('窄屏返回列表', await page.evaluate(() =>
      !document.querySelector('#app').classList.contains('show-chat')));
    await page.setViewport({ width: 1280, height: 800 });

    // ---------- 清理 ----------
    console.log('[16] 清理');
    await page.evaluate(async (r) => {
      await fetch('/chat/api/rooms/' + r, { method: 'DELETE', credentials: 'same-origin' });
      // 删掉测试上传的图片
      const rooms = await (await fetch('/chat/api/rooms', { credentials: 'same-origin' })).json();
      return rooms.rooms.length;
    }, rid);
    check('测试群已解散', await page.evaluate(async (name) => {
      const r = await fetch('/chat/api/rooms', { credentials: 'same-origin' });
      const j = await r.json();
      return !(j.rooms || []).some(x => x.title === name);
    }, GNAME));
    // uploads 里的测试文件清掉（图片 + txt，ssh 删除）
    const testUploadName = await page.evaluate(() => window.__testUploadName || '');
    if (testUploadName) {
      try {
        const { execSync } = require('child_process');
        execSync('echo "rm -f /opt/uc-chat/uploads/' + testUploadName + '" | "C:/Users/sam/.workbuddy/binaries/python/envs/default/Scripts/python.exe" "C:/Users/sam/WorkBuddy/2026-10-13-21-16-59/tools/ssh-run.py" 191.40.37.234 root e4ZxNJnAdicbElo8',
          { stdio: 'ignore', timeout: 60000 });
        check('测试上传文件已删除', true, testUploadName);
      } catch (e) {
        check('测试上传文件已删除', false, e.message);
      }
    } else {
      check('无测试上传文件需要清理', true);
    }

    // ---------- 零 JS 错误 ----------
    const realErrors = errors.filter(e =>
      !/favicon|Failed to load resource.*404/i.test(e));
    check('零 JS 错误', realErrors.length === 0, realErrors.slice(0, 5).join(' | '));

  } catch (e) {
    check('测试执行异常: ' + e.message, false);
  } finally {
    try { await cleanupStale(); } catch (e) {}
    try { fs.unlinkSync(UPLOAD_PNG); } catch (e) {}
    try { fs.unlinkSync(SHOT_DIR + '/tmp-upload-test.txt'); } catch (e) {}
    await browser.close();
  }

  const failed = results.filter(r => !r.ok);
  console.log(`\n===== 结果: ${results.length - failed.length} 通过, ${failed.length} 失败 =====`);
  if (failed.length) {
    failed.forEach(f => console.log('  [FAIL] ' + f.name + '  ' + f.detail));
    process.exit(1);
  }
})();
