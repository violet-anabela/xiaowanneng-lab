/*
 * 小完能桌宠引擎（XwnPet）
 * 纯原生 JS 单文件，无依赖。本站页面与 desktop-pet Skill 模板共用同一份。
 *
 * 用法：
 *   XwnPet.mount({ image: <url|dataURL>, name: '球球', size: 96 })
 *   XwnPet.unmount()
 *
 * 行为：
 *   - 沿视口底部来回溜达（走动 + 转身），随机停下待机
 *   - 待机时呼吸浮动
 *   - 鼠标拖拽，松手后抛物线落回地面
 *   - 点击：冒爪印 + 爱心
 *   - 随机打盹（趴下 + Zzz 气泡）
 *   - 超过 5 分钟无交互：气泡"喵？"
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
    '@media (prefers-reduced-motion: reduce){.xwn-pet{display:none;}}',
  ].join('\n');

  var pet = null; // 单例状态

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function rand(min, max) { return min + Math.random() * (max - min); }

  function mount(opts) {
    if (!opts || !opts.image) return null;
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
    img.src = opts.image;
    img.alt = '';
    flip.appendChild(img);
    el.appendChild(flip);

    var bubble = document.createElement('div');
    bubble.className = 'xwn-pet-bubble';
    el.appendChild(bubble);

    document.body.appendChild(el);

    var state = {
      el: el, bubble: bubble, size: size, name: name,
      x: rand(40, Math.max(60, innerWidth - size - 60)),
      y: 0,             // 相对地面的高度（向上为正）
      vx: 0, vy: 0,
      dir: 1,           // 1 右 -1 左
      mode: 'walk',     // walk | idle | drag | fall | sleep
      modeUntil: now() + rand(2000, 6000),
      lastInteract: now(),
      meowed: false,
      raf: 0, phase: rand(0, 6.28),
      bubbleTimer: 0,
    };
    pet = state;

    // ---- 交互 ----
    var drag = null;
    el.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      drag = { dx: e.clientX - state.x, y0: e.clientY, lastX: e.clientX, lastY: e.clientY, lastT: now(), moved: false };
      state.mode = 'drag';
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
        state.mode = 'idle';
        state.modeUntil = now() + rand(1500, 3000);
      } else {
        state.mode = 'fall';
      }
      touch(state);
    });

    // ---- 主循环 ----
    var GROUND_FRICTION = 0.86, GRAVITY = 1.4;
    function tick() {
      var t = now();

      if (state.mode === 'walk') {
        state.x += state.dir * 0.7;
        state.y = Math.abs(Math.sin(t / 140)) * 4; // 小碎步起伏
        if (state.x < 8) { state.x = 8; state.dir = 1; }
        if (state.x > innerWidth - state.size - 8) { state.x = innerWidth - state.size - 8; state.dir = -1; }
        if (t > state.modeUntil) {
          if (Math.random() < 0.25) enterSleep(state);
          else { state.mode = 'idle'; state.modeUntil = t + rand(2000, 5000); }
        }
      } else if (state.mode === 'idle') {
        state.y = Math.sin(t / 500 + state.phase) * 2.5; // 呼吸
        if (t > state.modeUntil) {
          state.mode = 'walk';
          state.dir = Math.random() < 0.5 ? -1 : 1;
          state.modeUntil = t + rand(3000, 8000);
        }
      } else if (state.mode === 'sleep') {
        state.y = Math.sin(t / 900 + state.phase) * 1.2; // 慢呼吸
        if (t > state.modeUntil) {
          say(state, '哈——欠', 1000);
          state.el.classList.remove('sleeping');
          state.el.style.rotate = '';
          state.mode = 'idle';
          state.modeUntil = t + 1500;
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
          state.y = 0;
          state.vy = 0;
          state.vx *= GROUND_FRICTION;
          if (Math.abs(state.vx) < 0.5) {
            say(state, pick(['咚！', '还行，四脚着地', '喵!?']), 1100);
            state.mode = 'idle';
            state.modeUntil = t + rand(1500, 3000);
          }
        }
      }

      // 5 分钟没人理：喊一声（每次交互后只喊一次）
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
    state.raf = requestAnimationFrame(tick);

    addEventListener('resize', clampX);
    function clampX() {
      state.x = Math.min(state.x, Math.max(0, innerWidth - state.size));
    }
    state.cleanupResize = function () { removeEventListener('resize', clampX); };

    return state;
  }

  function enterSleep(state) {
    state.mode = 'sleep';
    state.modeUntil = now() + rand(9000, 18000);
    state.el.classList.add('sleeping');
    state.el.style.rotate = (state.dir === 1 ? '' : '-') + '8deg';
  }

  function touch(state) {
    state.lastInteract = now();
    state.meowed = false;
    if (state.mode === 'sleep') {
      state.el.classList.remove('sleeping');
      state.el.style.rotate = '';
    }
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

  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function now() { return performance.now ? performance.now() : Date.now(); }

  function unmount() {
    if (!pet) return;
    cancelAnimationFrame(pet.raf);
    clearTimeout(pet.bubbleTimer);
    if (pet.cleanupResize) pet.cleanupResize();
    pet.el.remove();
    pet = null;
  }

  window.XwnPet = { mount: mount, unmount: unmount };
})();
