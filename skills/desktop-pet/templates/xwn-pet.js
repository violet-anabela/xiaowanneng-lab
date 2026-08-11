/*
 * 小完能桌宠引擎（XwnPet）v2 —— 五状态多图版
 * 纯原生 JS 单文件，无依赖。本站页面与 desktop-pet Skill 模板共用同一份
 *（skills/desktop-pet/templates/xwn-pet.js 是它的副本，改动需同步）。
 *
 * 用法：
 *   XwnPet.mount({
 *     name: '球球', size: 96,
 *     images: {
 *       idle:  <url|dataURL>,   // 必填：站立/溜达
 *       eat:   <url|dataURL>,   // 选填：吃饭（缺省用 idle）
 *       sleep: <url|dataURL>,   // 选填：睡觉
 *       drag:  <url|dataURL>,   // 选填：被拎起来
 *       click: <url|dataURL>,   // 选填：被点击
 *     },
 *   })
 *   // 兼容 v1：XwnPet.mount({ image: <url>, name, size })
 *   XwnPet.unmount()
 *
 * 行为：底部溜达/转身、呼吸待机、随机干饭、随机打盹（Zzz）、
 *       拖拽抛掷（抛物线落地）、点击冒爪印换表情、5 分钟没人理会喊人。
 */
(function () {
  'use strict';

  var STYLE_ID = 'xwn-pet-style';
  var CSS = [
    '.xwn-pet{position:fixed;z-index:9999;left:0;bottom:0;cursor:grab;user-select:none;-webkit-user-select:none;touch-action:none;will-change:transform;filter:drop-shadow(0 6px 8px rgba(0,0,0,.22));}',
    '.xwn-pet.dragging{cursor:grabbing;}',
    '.xwn-pet img{display:block;width:100%;height:100%;object-fit:contain;pointer-events:none;-webkit-user-drag:none;}',
    '.xwn-pet .xwn-pet-flip{width:100%;height:100%;}',
    '.xwn-pet.face-left .xwn-pet-flip{transform:scaleX(-1);}',
    '.xwn-pet-bubble{position:absolute;left:50%;bottom:calc(100% + 10px);transform:translateX(-50%);padding:6px 10px;border:2px solid #23324d;border-radius:10px;background:#fffdf7;color:#23324d;font:700 13px/1.2 -apple-system,"PingFang SC",sans-serif;white-space:nowrap;opacity:0;transition:opacity .25s ease;pointer-events:none;}',
    '.xwn-pet-bubble::after{content:"";position:absolute;top:100%;left:50%;margin-left:-5px;border:5px solid transparent;border-top-color:#23324d;}',
    '.xwn-pet-bubble.show{opacity:1;}',
    '.xwn-pet-fx{position:fixed;z-index:9998;pointer-events:none;font-size:18px;opacity:0;animation:xwn-fx 1s ease-out forwards;}',
    '@keyframes xwn-fx{0%{opacity:0;transform:translateY(4px) scale(.6);}25%{opacity:1;}100%{opacity:0;transform:translateY(-36px) scale(1.15) rotate(12deg);}}',
    '.xwn-pet.sleeping{filter:drop-shadow(0 6px 8px rgba(0,0,0,.22)) brightness(.96);}',
    '.xwn-pet-menu{position:fixed;z-index:10000;min-width:120px;padding:6px;border:2px solid #23324d;border-radius:8px;background:#fffdf7;box-shadow:4px 4px 0 rgba(35,50,77,.16);font:700 13px/1.4 -apple-system,"PingFang SC",sans-serif;color:#23324d;}',
    '.xwn-pet-menu button{display:flex;align-items:center;gap:8px;width:100%;padding:7px 10px;border:0;border-radius:5px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer;}',
    '.xwn-pet-menu button:hover{background:rgba(217,79,48,.09);color:#d94f30;}',
    '.xwn-pet-menu .xwn-menu-title{padding:4px 10px 7px;margin-bottom:4px;border-bottom:2px dashed rgba(35,50,77,.18);color:#8b94a8;font-size:11px;letter-spacing:.08em;}',
    '@media (prefers-reduced-motion: reduce){.xwn-pet{display:none;}}',
  ].join('\n');

  var pet = null; // 单例

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function rand(min, max) { return min + Math.random() * (max - min); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function now() { return performance.now ? performance.now() : Date.now(); }

  function normalizeImages(opts) {
    var raw = opts.images || {};
    var idle = raw.idle || opts.image;
    if (!idle) return null;
    return {
      idle: idle,
      eat: raw.eat || null,
      sleep: raw.sleep || null,
      drag: raw.drag || null,
      click: raw.click || null,
    };
  }

  function mount(opts) {
    if (!opts) return null;
    var images = normalizeImages(opts);
    if (!images) return null;
    unmount();
    injectStyle();

    var size = Math.max(48, Math.min(200, opts.size || 96));
    var name = opts.name || '小伙伴';

    var el = document.createElement('div');
    el.className = 'xwn-pet';
    el.setAttribute('role', 'img');
    el.setAttribute('aria-label', '桌宠 ' + name);
    el.style.width = size + 'px';
    el.style.height = size + 'px';

    var flip = document.createElement('div');
    flip.className = 'xwn-pet-flip';
    var img = document.createElement('img');
    img.src = images.idle;
    img.alt = '';
    flip.appendChild(img);
    el.appendChild(flip);

    var bubble = document.createElement('div');
    bubble.className = 'xwn-pet-bubble';
    el.appendChild(bubble);

    document.body.appendChild(el);

    var state = {
      el: el, img: img, bubble: bubble, images: images, size: size, name: name,
      x: rand(40, Math.max(60, innerWidth - size - 60)),
      y: 0, vx: 0, vy: 0, dir: 1,
      mode: 'walk', modeUntil: now() + rand(2000, 6000),
      lastInteract: now(), meowed: false,
      raf: 0, phase: rand(0, 6.28),
      bubbleTimer: 0, faceTimer: 0,
    };
    pet = state;

    function setFace(key) {
      var src = state.images[key] || state.images.idle;
      if (state.img.getAttribute('src') !== src) state.img.src = src;
    }

    // 临时换表情（点击时用），结束后回到当前模式的表情
    function flashFace(key, ms) {
      if (!state.images[key]) return;
      setFace(key);
      clearTimeout(state.faceTimer);
      state.faceTimer = setTimeout(function () { faceForMode(); }, ms);
    }

    function faceForMode() {
      if (state.mode === 'sleep') setFace('sleep');
      else if (state.mode === 'eat') setFace('eat');
      else if (state.mode === 'drag' || state.mode === 'fall') setFace('drag');
      else setFace('idle');
    }

    // ---- 交互 ----
    var drag = null;
    el.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return; // 拖拽/点击只认左键和触摸，右键留给点单菜单
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      drag = { dx: e.clientX - state.x, y0: e.clientY, lastX: e.clientX, lastY: e.clientY, lastT: now(), moved: false };
      setMode('drag', Infinity);
      el.classList.add('dragging');
      touch(state);
    });
    el.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var t = now();
      state.vx = (e.clientX - drag.lastX) / Math.max(1, t - drag.lastT) * 16;
      state.vy = -(e.clientY - drag.lastY) / Math.max(1, t - drag.lastT) * 16;
      drag.lastX = e.clientX; drag.lastY = e.clientY; drag.lastT = t;
      if (Math.abs(e.clientX - (drag.dx + state.x)) > 3 || Math.abs(e.clientY - drag.y0) > 3) drag.moved = true;
      state.x = e.clientX - drag.dx;
      state.y = Math.max(0, innerHeight - e.clientY - state.size / 2);
    });
    el.addEventListener('pointerup', function (e) {
      if (!drag) return;
      var wasTap = !drag.moved;
      drag = null;
      el.classList.remove('dragging');
      if (wasTap) {
        burst(e.clientX, e.clientY);
        say(state, pick(['喵～', '❤', '干嘛！', name + '在此']), 1200);
        setMode('idle', rand(1500, 3000));
        flashFace('click', 1400); // 必须在 setMode 之后，否则表情会被 faceForMode 立刻盖掉
      } else {
        setMode('fall', Infinity);
      }
      touch(state);
    });

    function setMode(mode, duration) {
      state.mode = mode;
      state.modeUntil = duration === Infinity ? Infinity : now() + duration;
      state.el.classList.toggle('sleeping', mode === 'sleep');
      if (mode !== 'sleep') state.el.style.rotate = '';
      faceForMode();
    }

    // ---- 右键点单菜单 ----
    var menu = null;
    function closeMenu() {
      if (menu) { menu.remove(); menu = null; }
      removeEventListener('pointerdown', onOutside, true);
      removeEventListener('keydown', onEsc, true);
    }
    function onOutside(e) { if (menu && !menu.contains(e.target)) closeMenu(); }
    function onEsc(e) { if (e.key === 'Escape') closeMenu(); }

    el.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      closeMenu();
      touch(state);

      var items = [
        { label: '🚶 出去溜达', run: function () { state.dir = Math.random() < 0.5 ? -1 : 1; setMode('walk', rand(6000, 12000)); } },
        { label: '🍚 开饭', run: function () { say(state, '开饭！', 900); setMode('eat', rand(7000, 12000)); } },
        { label: '😴 睡一会', run: function () { enterSleep(); } },
        { label: '🧍 站好别动', run: function () { setMode('idle', rand(6000, 10000)); } },
      ];

      menu = document.createElement('div');
      menu.className = 'xwn-pet-menu';
      menu.setAttribute('role', 'menu');
      var title = document.createElement('div');
      title.className = 'xwn-menu-title';
      title.textContent = '给' + name + '点单';
      menu.appendChild(title);
      items.forEach(function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = item.label;
        btn.addEventListener('click', function () { item.run(); closeMenu(); });
        menu.appendChild(btn);
      });
      document.body.appendChild(menu);

      // 贴着鼠标弹出，防止溢出视口
      var mw = menu.offsetWidth, mh = menu.offsetHeight;
      menu.style.left = Math.min(e.clientX, innerWidth - mw - 8) + 'px';
      menu.style.top = Math.min(e.clientY, innerHeight - mh - 8) + 'px';

      setTimeout(function () {
        addEventListener('pointerdown', onOutside, true);
        addEventListener('keydown', onEsc, true);
      }, 0);
    });
    state.cleanupMenu = closeMenu;

    // ---- 主循环 ----
    var GROUND_FRICTION = 0.86, GRAVITY = 1.4;
    function tick() {
      var t = now();

      if (state.mode === 'walk') {
        state.x += state.dir * 0.7;
        state.y = Math.abs(Math.sin(t / 140)) * 4;
        if (state.x < 8) { state.x = 8; state.dir = 1; }
        if (state.x > innerWidth - state.size - 8) { state.x = innerWidth - state.size - 8; state.dir = -1; }
        if (t > state.modeUntil) decideNext(t);
      } else if (state.mode === 'idle') {
        state.y = Math.sin(t / 500 + state.phase) * 2.5;
        if (t > state.modeUntil) {
          state.dir = Math.random() < 0.5 ? -1 : 1;
          setMode('walk', rand(3000, 8000));
        }
      } else if (state.mode === 'eat') {
        state.y = Math.abs(Math.sin(t / 220)) * 2; // 小口小口
        if (!state.bubbleTimer && Math.random() < 0.015) {
          say(state, pick(['干饭中…', '咔嚓咔嚓', '真香']), 1400);
        }
        if (t > state.modeUntil) {
          say(state, pick(['饱了', '舔舔嘴']), 1100);
          setMode('idle', rand(1800, 3500));
        }
      } else if (state.mode === 'sleep') {
        state.y = Math.sin(t / 900 + state.phase) * 1.2;
        if (t > state.modeUntil) {
          say(state, '哈——欠', 1000);
          setMode('idle', 1500);
        } else if (!state.bubbleTimer && Math.random() < 0.02) {
          say(state, 'Zzz…', 1600);
        }
      } else if (state.mode === 'fall') {
        state.x += state.vx;
        state.y += state.vy;
        state.vy -= GRAVITY;
        if (state.x < 0) { state.x = 0; state.vx = Math.abs(state.vx) * 0.5; }
        if (state.x > innerWidth - state.size) { state.x = innerWidth - state.size; state.vx = -Math.abs(state.vx) * 0.5; }
        if (state.y <= 0) {
          state.y = 0; state.vy = 0;
          state.vx *= GROUND_FRICTION;
          if (Math.abs(state.vx) < 0.5) {
            say(state, pick(['咚！', '还行，四脚着地', '喵!?']), 1100);
            setMode('idle', rand(1500, 3000));
          }
        }
      }

      if (!state.meowed && state.mode !== 'sleep' && t - state.lastInteract > 5 * 60 * 1000) {
        state.meowed = true;
        say(state, '喵？', 2500);
      }

      if (state.mode !== 'drag') {
        if (state.vx > 0.2) state.dir = 1;
        else if (state.vx < -0.2) state.dir = -1;
      }
      el.classList.toggle('face-left', state.dir === -1);
      el.style.transform = 'translate(' + state.x + 'px, ' + (-state.y) + 'px)';
      state.raf = requestAnimationFrame(tick);
    }

    function decideNext(t) {
      var r = Math.random();
      if (r < 0.2 && state.images.sleep) enterSleep();
      else if (r < 0.4 && state.images.eat) {
        say(state, '开饭！', 900);
        setMode('eat', rand(5000, 10000));
      } else if (r < 0.55) enterSleep();
      else setMode('idle', rand(2000, 5000));
    }

    function enterSleep() {
      setMode('sleep', rand(9000, 18000));
      // 没有专门的睡觉图时，用歪头角度表现打盹
      if (!state.images.sleep) state.el.style.rotate = (state.dir === 1 ? '' : '-') + '8deg';
    }

    state.raf = requestAnimationFrame(tick);

    addEventListener('resize', clampX);
    function clampX() { state.x = Math.min(state.x, Math.max(0, innerWidth - state.size)); }
    state.cleanupResize = function () { removeEventListener('resize', clampX); };

    return state;
  }

  function touch(state) {
    state.lastInteract = now();
    state.meowed = false;
  }

  function say(state, text, ms) {
    state.bubble.textContent = text;
    state.bubble.classList.add('show');
    clearTimeout(state.bubbleTimer);
    state.bubbleTimer = setTimeout(function () {
      state.bubble.classList.remove('show');
      state.bubbleTimer = 0;
    }, ms || 1500);
  }

  function burst(cx, cy) {
    var icons = ['🐾', '❤️', '🐾', '✨'];
    for (var i = 0; i < 4; i++) {
      var fx = document.createElement('span');
      fx.className = 'xwn-pet-fx';
      fx.textContent = icons[i % icons.length];
      fx.style.left = cx + rand(-22, 22) + 'px';
      fx.style.top = cy + rand(-26, 2) + 'px';
      fx.style.animationDelay = (i * 70) + 'ms';
      document.body.appendChild(fx);
      setTimeout(function (n) { return function () { n.remove(); }; }(fx), 1400 + i * 70);
    }
  }

  function unmount() {
    if (!pet) return;
    cancelAnimationFrame(pet.raf);
    clearTimeout(pet.bubbleTimer);
    clearTimeout(pet.faceTimer);
    if (pet.cleanupResize) pet.cleanupResize();
    if (pet.cleanupMenu) pet.cleanupMenu();
    pet.el.remove();
    pet = null;
  }

  window.XwnPet = { mount: mount, unmount: unmount };
})();
