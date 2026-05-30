/* =================================================================
   SNAKE ARENA — Unified GUI2
   Combines dashboard game management with gui canvas rendering
   ================================================================= */

/* ── Constants ────────────────────────────────────── */
const GAME_LIST_POLL_MS = 2000;
const ZOOM_MIN = 1.0;
const ZOOM_MAX = 5.0;
const ZOOM_SPEED = 1.15;
const MINIMAP_SIZE = 160;
const CLICK_THRESHOLD = 5;

/* ── Snake palette ────────────────────────────────────
 * Mirrors `SNAKE_COLOR_PALETTE` in server/src/game/snake_colors.rs so the web
 * UI matches the native debug window. Used as a fallback when the server does
 * not provide a per-snake color in the stream payload. */
const SNAKE_PALETTE_RGB = [
  [244, 67, 54], // Red
  [255, 152, 0], // Orange
  [255, 235, 59], // Yellow
  [139, 195, 74], // Light Green
  [76, 175, 80], // Green
  [0, 150, 136], // Teal
  [0, 188, 212], // Cyan
  [33, 150, 243], // Blue
  [63, 81, 181], // Indigo
  [156, 39, 176], // Purple
  [233, 30, 99], // Pink
  [121, 85, 72], // Brown
];

/* ── DOM refs ─────────────────────────────────────── */
const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");
const wrap = document.getElementById("canvas-wrap");
const minimapCanvas = document.getElementById("minimap");
const minimapCtx = minimapCanvas.getContext("2d");
const minimapWrap = document.getElementById("minimap-wrap");
const minimapVp = document.getElementById("minimap-viewport");
const $gameList = document.getElementById("game-list");
const $noGameMsg = document.getElementById("no-game-msg");
const $viewingGame = document.getElementById("viewing-game");
const $resetBtn = document.getElementById("reset-game-btn");
const $deleteBtn = document.getElementById("delete-game-btn");
const $scoreboardList = document.getElementById("scoreboard-list");
const $scoreboardTick = document.getElementById("scoreboard-tick");
const $connStatus = document.getElementById("connection-status");
const $createBtn = document.getElementById("create-game-btn");
const $modalOverlay = document.getElementById("modal-overlay");
const $modalCancel = document.getElementById("modal-cancel");
const $modalCreate = document.getElementById("modal-create");
const $modalName = document.getElementById("modal-game-name");
const $modalWidth = document.getElementById("modal-width");
const $modalHeight = document.getElementById("modal-height");
const $zoomIndicator = document.getElementById("zoom-indicator");
const $followIndicator = document.getElementById("follow-indicator");
const $followName = document.getElementById("follow-name");
const $themeToggle = document.getElementById("theme-toggle");
const $winnerBanner = document.getElementById("winner-banner");
const $winnerName = document.getElementById("winner-name");
const $globalEffects = document.getElementById("global-effects");

/* ── State ────────────────────────────────────────── */
let currentGame = null;
let eventSource = null;
let lastData = null;

const teamColorMap = new Map();
let previousSnakeNames = null;

/* ── Zoom / Pan state ─────────────────────────────── */
let zoom = 1.0;
let panX = 0,
  panY = 0;
let isPanning = false;
let panStartX = 0,
  panStartY = 0;
let panStartPanX = 0,
  panStartPanY = 0;

/* ── Follow state ─────────────────────────────────── */
let followedSnakeName = null;
let mouseDownPos = null;

/* ── Sand pattern & trails ────────────────────────── */
let sandPattern = null;
let trailGrid = new Map();
let prevSnakePositions = new Map();
const TRAIL_FADE_RATE = 0.09;
const TRAIL_MAX_INTENSITY = 0.9;

/* ================================================================
   SECTION: Color helpers
   ================================================================ */
function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r, g, b) {
  return (
    "#" +
    [r, g, b]
      .map((c) =>
        Math.max(0, Math.min(255, Math.round(c)))
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

function lerpColor(a, b, t) {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return rgbToHex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t);
}

function lightenColor(hex, amt) {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r + amt, g + amt, b + amt);
}

function toGrayscale(hex) {
  const [r, g, b] = hexToRgb(hex);
  const gray = Math.round(r * 0.299 + g * 0.587 + b * 0.114);
  return rgbToHex(gray, gray, gray);
}

function colorsFromRgb(rgb) {
  const [r, g, b] = rgb;
  const body = rgbToHex(r, g, b);
  const head = rgbToHex(r * 0.7, g * 0.7, b * 0.7);
  return { body, head, eye: "#fff" };
}

function getSnakeColors(name, serverRgb) {
  if (teamColorMap.has(name)) return teamColorMap.get(name);
  const rgb =
    serverRgb ||
    SNAKE_PALETTE_RGB[teamColorMap.size % SNAKE_PALETTE_RGB.length];
  const colors = colorsFromRgb(rgb);
  teamColorMap.set(name, colors);
  return colors;
}

/* ================================================================
   SECTION: Utilities
   ================================================================ */
function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function isDayMode() {
  return document.body.classList.contains("day-mode");
}

/* ================================================================
   SECTION: Layout & canvas sizing
   ================================================================ */
function getContainerSize() {
  const pad = parseFloat(getComputedStyle(wrap).padding) || 16;
  const w = wrap.clientWidth - pad * 2;
  const h = wrap.clientHeight - pad * 2;
  return { w: Math.max(w, 100), h: Math.max(h, 100) };
}

function layoutFromData(data) {
  const [fw, fh] = data.size;
  const container = getContainerSize();
  const fitSize = Math.min(container.w, container.h);
  const cell = fitSize / Math.max(fw, fh);
  return { fw, fh, cell };
}

function setCanvasSize(w, h) {
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
    sandPattern = null;
  }
}

/* ================================================================
   SECTION: Zoom helpers
   ================================================================ */
function clampPan() {
  if (zoom <= 1.0) {
    panX = 0;
    panY = 0;
    return;
  }
  const maxPanX = (canvas.width * (zoom - 1)) / 2;
  const maxPanY = (canvas.height * (zoom - 1)) / 2;
  panX = clamp(panX, -maxPanX, maxPanX);
  panY = clamp(panY, -maxPanY, maxPanY);
}

function updateZoomIndicator() {
  $zoomIndicator.textContent = zoom.toFixed(1) + "x";
}

function resetZoom() {
  zoom = 1.0;
  panX = 0;
  panY = 0;
  updateZoomIndicator();
  minimapWrap.classList.remove("visible");
  renderIfData();
}

function renderIfData() {
  if (lastData) render(lastData);
}

let _animRafPending = false;
function needsAnimation(data) {
  if (!data || !data.snakes) return false;
  for (const name in data.snakes) {
    if (data.snakes[name].starBuffed) return true;
  }
  return false;
}
function ensureAnimationLoop() {
  if (_animRafPending) return;
  if (!lastData || !needsAnimation(lastData)) return;
  _animRafPending = true;
  requestAnimationFrame(() => {
    _animRafPending = false;
    if (lastData && needsAnimation(lastData)) {
      render(lastData);
      ensureAnimationLoop();
    }
  });
}

/* ================================================================
   SECTION: Follow helpers
   ================================================================ */
function setFollowedSnake(name) {
  followedSnakeName = name;
  if (name !== null) {
    $followIndicator.classList.remove("hidden");
    $zoomIndicator.classList.add("follow-shift");
    $followName.textContent = name;
  } else {
    $followIndicator.classList.add("hidden");
    $zoomIndicator.classList.remove("follow-shift");
  }
  updateScoreboardFollowHighlight();
  renderIfData();
}

function updateScoreboardFollowHighlight() {
  const cards = $scoreboardList.querySelectorAll(".player-card");
  cards.forEach((card) => {
    card.classList.toggle(
      "following",
      card.dataset.snake === followedSnakeName,
    );
  });
}

function centerOnFollowedSnake(data) {
  if (followedSnakeName === null || !data) return;
  const snakeInfo = data.snakes[followedSnakeName];
  if (!snakeInfo || snakeInfo.body.length === 0) {
    setFollowedSnake(null);
    return;
  }
  const { fw, fh, cell } = layoutFromData(data);
  const fieldW = Math.round(fw * cell);
  const fieldH = Math.round(fh * cell);
  const container = getContainerSize();
  const offsetX = (container.w - fieldW) / 2;
  const offsetY = (container.h - fieldH) / 2;

  const headX = snakeInfo.body[0][0] * cell + cell / 2;
  const headY = snakeInfo.body[0][1] * cell + cell / 2;

  panX =
    container.w / 2 - (headX + offsetX) * zoom - (container.w * (1 - zoom)) / 2;
  panY =
    container.h / 2 - (headY + offsetY) * zoom - (container.h * (1 - zoom)) / 2;
}

function hitTestSnake(clientX, clientY, data) {
  if (!data) return null;
  const { fw, fh, cell } = layoutFromData(data);
  const fieldW = Math.round(fw * cell);
  const fieldH = Math.round(fh * cell);
  const container = getContainerSize();
  const offsetX = (container.w - fieldW) / 2;
  const offsetY = (container.h - fieldH) / 2;

  const rect = canvas.getBoundingClientRect();
  const mx = clientX - rect.left;
  const my = clientY - rect.top;

  const tx = offsetX * zoom + panX + (container.w * (1 - zoom)) / 2;
  const ty = offsetY * zoom + panY + (container.h * (1 - zoom)) / 2;
  const fieldX = (mx - tx) / zoom;
  const fieldY = (my - ty) / zoom;

  const cellX = Math.floor(fieldX / cell);
  const cellY = Math.floor(fieldY / cell);

  if (cellX < 0 || cellX >= fw || cellY < 0 || cellY >= fh) return null;

  for (const name in data.snakes) {
    const body = data.snakes[name].body;
    for (const seg of body) {
      if (seg[0] === cellX && seg[1] === cellY) return name;
    }
  }
  return null;
}

/* ================================================================
   SECTION: Background & sand
   ================================================================ */
function buildSandPattern() {
  const sz = 24;
  const off = document.createElement("canvas");
  off.width = sz;
  off.height = sz;
  const c = off.getContext("2d");

  const baseColor =
    getComputedStyle(document.body).getPropertyValue("--sand-base").trim() ||
    "#2a2418";
  c.fillStyle = baseColor;
  c.fillRect(0, 0, sz, sz);

  const day = isDayMode();
  const rng = mulberry32(77);

  // Sand grain noise — small speckles
  for (let i = 0; i < 18; i++) {
    const x = rng() * sz;
    const y = rng() * sz;
    const r = 0.5 + rng() * 1.8;
    if (day) {
      const v = Math.floor(180 + rng() * 50);
      c.fillStyle = `rgba(${v},${Math.floor(v * 0.85)},${Math.floor(v * 0.65)},${0.25 + rng() * 0.3})`;
    } else {
      const v = Math.floor(30 + rng() * 30);
      c.fillStyle = `rgba(${v + 10},${v},${Math.floor(v * 0.7)},${0.3 + rng() * 0.3})`;
    }
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fill();
  }

  // Subtle sand ripple lines
  for (let i = 0; i < 4; i++) {
    const y = rng() * sz;
    if (day) {
      c.strokeStyle = `rgba(190,170,130,${0.15 + rng() * 0.15})`;
    } else {
      c.strokeStyle = `rgba(60,50,35,${0.2 + rng() * 0.2})`;
    }
    c.lineWidth = 0.4 + rng() * 0.3;
    c.beginPath();
    c.moveTo(0, y);
    c.quadraticCurveTo(
      sz * 0.5 + (rng() - 0.5) * 6,
      y + (rng() - 0.5) * 3,
      sz,
      y + (rng() - 0.5) * 2,
    );
    c.stroke();
  }

  sandPattern = ctx.createPattern(off, "repeat");
}

function drawStraightTrail(cx, cy, cell, dx, dy, day) {
  const perpX = -dy;
  const perpY = dx;
  const grooveLen = cell * 0.42;
  const spacing = cell * 0.14;

  ctx.strokeStyle = day ? "rgba(100,80,40,0.6)" : "rgba(10,8,4,0.7)";
  ctx.lineWidth = cell * 0.06;
  ctx.lineCap = "round";
  for (let i = -1; i <= 1; i++) {
    const ox = perpX * spacing * i;
    const oy = perpY * spacing * i;
    ctx.beginPath();
    ctx.moveTo(cx + ox - dx * grooveLen, cy + oy - dy * grooveLen);
    ctx.lineTo(cx + ox + dx * grooveLen, cy + oy + dy * grooveLen);
    ctx.stroke();
  }

  ctx.strokeStyle = day ? "rgba(240,225,190,0.45)" : "rgba(65,55,35,0.55)";
  ctx.lineWidth = cell * 0.04;
  const shiftX = perpX * cell * 0.04;
  const shiftY = perpY * cell * 0.04;
  for (let i = -1; i <= 1; i++) {
    const ox = perpX * spacing * i + shiftX;
    const oy = perpY * spacing * i + shiftY;
    ctx.beginPath();
    ctx.moveTo(cx + ox - dx * grooveLen, cy + oy - dy * grooveLen);
    ctx.lineTo(cx + ox + dx * grooveLen, cy + oy + dy * grooveLen);
    ctx.stroke();
  }
}

function drawCornerTrail(cx, cy, cell, inDx, inDy, outDx, outDy, day) {
  // Corner: snake entered from (inDx,inDy) direction and left toward (outDx,outDy)
  // Draw L-shaped grooves: from the entry edge to center, then center to exit edge
  const halfLen = cell * 0.42;
  const spacing = cell * 0.14;

  // Entry point (where snake came from — opposite of inDir)
  const entryX = -inDx * halfLen;
  const entryY = -inDy * halfLen;
  // Exit point (where snake went)
  const exitX = outDx * halfLen;
  const exitY = outDy * halfLen;

  // Perpendicular to incoming direction
  const inPerpX = -inDy;
  const inPerpY = inDx;
  // Perpendicular to outgoing direction
  const outPerpX = -outDy;
  const outPerpY = outDx;

  const styles = [
    {
      color: day ? "rgba(100,80,40,0.6)" : "rgba(10,8,4,0.7)",
      width: cell * 0.06,
      shift: 0,
    },
    {
      color: day ? "rgba(240,225,190,0.45)" : "rgba(65,55,35,0.55)",
      width: cell * 0.04,
      shift: cell * 0.04,
    },
  ];

  for (const style of styles) {
    ctx.strokeStyle = style.color;
    ctx.lineWidth = style.width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (let i = -1; i <= 1; i++) {
      // Offset along perpendicular for each groove line
      const inOff = i * spacing;
      const outOff = i * spacing;

      const sx = cx + entryX + inPerpX * (inOff + style.shift);
      const sy = cy + entryY + inPerpY * (inOff + style.shift);
      const mx = cx + outPerpX * (outOff + style.shift);
      const my = cy + outPerpY * (outOff + style.shift);
      const ex = cx + exitX + outPerpX * (outOff + style.shift);
      const ey = cy + exitY + outPerpY * (outOff + style.shift);

      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.quadraticCurveTo(mx, my, ex, ey);
      ctx.stroke();
    }
  }
}

function drawTrails(cell, fw, fh) {
  if (trailGrid.size === 0) return;
  const day = isDayMode();

  trailGrid.forEach((trail, key) => {
    const [gx, gy] = key.split(",").map(Number);
    if (gx < 0 || gx >= fw || gy < 0 || gy >= fh) return;

    const cx = gx * cell + cell / 2;
    const cy = gy * cell + cell / 2;

    ctx.save();
    ctx.globalAlpha = trail.intensity;

    const inDx = trail.inDx !== undefined ? trail.inDx : trail.dx;
    const inDy = trail.inDy !== undefined ? trail.inDy : trail.dy;
    const isCorner = inDx !== trail.dx || inDy !== trail.dy;

    if (isCorner) {
      drawCornerTrail(cx, cy, cell, inDx, inDy, trail.dx, trail.dy, day);
    } else {
      drawStraightTrail(cx, cy, cell, trail.dx, trail.dy, day);
    }

    ctx.restore();
  });
}

function drawBackground(w, h, cell, fw, fh) {
  if (!sandPattern) buildSandPattern();

  ctx.fillStyle = sandPattern;
  ctx.fillRect(0, 0, w, h);

  // Draw snake trails on sand
  drawTrails(cell, fw, fh);

  ctx.strokeStyle = isDayMode() ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.04)";
  ctx.lineWidth = 0.5;
  for (let x = 0; x <= fw; x++) {
    ctx.beginPath();
    ctx.moveTo(x * cell, 0);
    ctx.lineTo(x * cell, h);
    ctx.stroke();
  }
  for (let y = 0; y <= fh; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * cell);
    ctx.lineTo(w, y * cell);
    ctx.stroke();
  }
}

/* ================================================================
   SECTION: Trail tracking
   ================================================================ */

/* Convert a raw axis delta between two adjacent body cells into a unit
   direction. Adjacent cells normally differ by 0 or 1; a delta with
   magnitude > 1 means the snake wrapped around the playfield, in which case
   the actual movement direction is the inverse of the delta's sign. */
function unitDeltaWithWrap(raw) {
  if (raw === 0) return 0;
  if (Math.abs(raw) === 1) return Math.sign(raw);
  return -Math.sign(raw); // wrap: head appears on the opposite side
}

function updateTrails(data) {
  // Build current snake positions with per-cell directions (in + out)
  const currentPositions = new Set();
  const newPrevPositions = new Map();

  for (const name in data.snakes) {
    const snakeInfo = data.snakes[name];
    if (snakeInfo.body.length === 0) continue;

    const bodyMap = new Map(); // key → {dx, dy, inDx, inDy}
    const body = snakeInfo.body;
    for (let i = 0; i < body.length; i++) {
      const key = body[i][0] + "," + body[i][1];
      currentPositions.add(key);

      // Outgoing direction (toward head)
      let dx = 0,
        dy = 0;
      if (i === 0 && body.length > 1) {
        dx = unitDeltaWithWrap(body[0][0] - body[1][0]);
        dy = unitDeltaWithWrap(body[0][1] - body[1][1]);
      } else if (i > 0) {
        dx = unitDeltaWithWrap(body[i - 1][0] - body[i][0]);
        dy = unitDeltaWithWrap(body[i - 1][1] - body[i][1]);
      }
      if (dx === 0 && dy === 0) {
        dx = 0;
        dy = 1;
      }

      // Incoming direction (from tail side)
      let inDx = dx,
        inDy = dy;
      if (i < body.length - 1) {
        inDx = unitDeltaWithWrap(body[i][0] - body[i + 1][0]);
        inDy = unitDeltaWithWrap(body[i][1] - body[i + 1][1]);
        if (inDx === 0 && inDy === 0) {
          inDx = dx;
          inDy = dy;
        }
      }

      // For tail: preserve corner data from previous tick
      if (i === body.length - 1) {
        const prevBodyMap = prevSnakePositions.get(name);
        if (prevBodyMap) {
          const prevDir = prevBodyMap.get(key);
          if (
            prevDir &&
            (prevDir.inDx !== prevDir.dx || prevDir.inDy !== prevDir.dy)
          ) {
            inDx = prevDir.inDx;
            inDy = prevDir.inDy;
          }
        }
      }

      bodyMap.set(key, { dx, dy, inDx, inDy });
    }
    newPrevPositions.set(name, bodyMap);

    // Mark trails where this snake previously was but no longer is
    const prev = prevSnakePositions.get(name);
    if (prev) {
      prev.forEach((dir, key) => {
        if (!currentPositions.has(key)) {
          trailGrid.set(key, {
            intensity: TRAIL_MAX_INTENSITY,
            dx: dir.dx,
            dy: dir.dy,
            inDx: dir.inDx,
            inDy: dir.inDy,
          });
        }
      });
    }
  }

  prevSnakePositions = newPrevPositions;

  // Fade all existing trails
  trailGrid.forEach((trail, key) => {
    if (currentPositions.has(key)) return;
    trail.intensity -= TRAIL_FADE_RATE;
    if (trail.intensity <= 0.01) {
      trailGrid.delete(key);
    }
  });
}

function clearTrails() {
  trailGrid.clear();
  prevSnakePositions.clear();
}

/* ================================================================
   SECTION: Item rendering
   ================================================================ */
const ITEM_REGISTRY = {
  Apple: { draw: drawApple, minimapColor: "#e63946" },
  BadApple: { draw: drawBadApple, minimapColor: "#8e44ad" },
  Star: { draw: drawStar, minimapColor: "#f1c40f" },
  Sword: { draw: drawSword, minimapColor: "#b0bec5" },
  InstantStack: { draw: drawInstantStack, minimapColor: "#00bcd4" },
  SpeedBoost: { draw: drawSpeedBoost, minimapColor: "#ff9800" },
};

function hashColor(name) {
  let h = 5381;
  for (let i = 0; i < name.length; i++)
    h = (h * 33 + name.charCodeAt(i)) & 0xffffffff;
  return "hsl(" + (h % 360) + ", 70%, 55%)";
}

function getItemRenderer(type) {
  if (ITEM_REGISTRY[type]) return ITEM_REGISTRY[type];
  const color = hashColor(type);
  return {
    draw: (x, y, cell) => drawUnknownItem(x, y, cell, color),
    minimapColor: color,
  };
}

function drawItems(items, cell) {
  items.forEach((i) => getItemRenderer(i[1]).draw(i[0][0], i[0][1], cell));
}

function drawApple(x, y, cell) {
  const ox = x * cell;
  const oy = y * cell;
  const u = cell / 48;
  const X = (px) => ox + px * u;
  const Y = (py) => oy + py * u;

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(X(24), Y(43.5), 11 * u, 2.6 * u, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fill();

  // apple silhouette (two lobes + top dimple)
  const body = new Path2D();
  body.moveTo(X(24), Y(15));
  body.bezierCurveTo(X(16), Y(12), X(10), Y(18), X(10), Y(26));
  body.bezierCurveTo(X(10), Y(35), X(16), Y(41), X(24), Y(41));
  body.bezierCurveTo(X(32), Y(41), X(38), Y(35), X(38), Y(26));
  body.bezierCurveTo(X(38), Y(18), X(32), Y(12), X(24), Y(15));
  body.closePath();

  // body fill: offset radial gradient (light from top-left)
  const grad = ctx.createRadialGradient(X(19), Y(18), 1 * u, X(24), Y(26), 17 * u);
  grad.addColorStop(0, "#ffbcbc");
  grad.addColorStop(0.3, "#f25566");
  grad.addColorStop(0.72, "#c21f2e");
  grad.addColorStop(1, "#7d1019");
  ctx.fillStyle = grad;
  ctx.fill(body);

  // core shadow + specular, clipped to the body
  ctx.save();
  ctx.clip(body);
  ctx.beginPath();
  ctx.ellipse(X(30), Y(33), 6.5 * u, 8.5 * u, (20 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.globalAlpha = 0.3;
  ctx.fillStyle = "#5e0d14";
  ctx.fill();
  ctx.globalAlpha = 0.45;
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.ellipse(X(17), Y(22), 3.2 * u, 5.2 * u, (-18 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 0.9;
  ctx.beginPath();
  ctx.ellipse(X(15.6), Y(20), 1.5 * u, 2.4 * u, (-18 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.restore();

  // stem
  ctx.beginPath();
  ctx.moveTo(X(24), Y(15));
  ctx.quadraticCurveTo(X(25), Y(8), X(23), Y(5));
  ctx.lineWidth = 2.4 * u;
  ctx.strokeStyle = "#6b4423";
  ctx.lineCap = "round";
  ctx.stroke();

  // leaf + vein
  ctx.beginPath();
  ctx.moveTo(X(24), Y(9));
  ctx.quadraticCurveTo(X(31), Y(4.5), X(33.5), Y(9));
  ctx.quadraticCurveTo(X(28), Y(13), X(24), Y(9));
  ctx.closePath();
  ctx.fillStyle = "#4caf50";
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(X(24.5), Y(9));
  ctx.quadraticCurveTo(X(30), Y(7), X(32.5), Y(9));
  ctx.lineWidth = 0.7 * u;
  ctx.strokeStyle = "#2e7d32";
  ctx.stroke();
}

function drawBadApple(x, y, cell) {
  const ox = x * cell;
  const oy = y * cell;
  const u = cell / 48;
  const X = (px) => ox + px * u;
  const Y = (py) => oy + py * u;

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(X(24), Y(43.5), 11 * u, 2.6 * u, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fill();

  // apple silhouette (same shape as Apple)
  const body = new Path2D();
  body.moveTo(X(24), Y(15));
  body.bezierCurveTo(X(16), Y(12), X(10), Y(18), X(10), Y(26));
  body.bezierCurveTo(X(10), Y(35), X(16), Y(41), X(24), Y(41));
  body.bezierCurveTo(X(32), Y(41), X(38), Y(35), X(38), Y(26));
  body.bezierCurveTo(X(38), Y(18), X(32), Y(12), X(24), Y(15));
  body.closePath();

  // body fill: purple offset radial gradient
  const grad = ctx.createRadialGradient(X(19), Y(18), 1 * u, X(24), Y(26), 17 * u);
  grad.addColorStop(0, "#e4baf6");
  grad.addColorStop(0.32, "#a45fc8");
  grad.addColorStop(0.72, "#723a93");
  grad.addColorStop(1, "#43205c");
  ctx.fillStyle = grad;
  ctx.fill(body);

  // core shadow + specular, clipped to body
  ctx.save();
  ctx.clip(body);
  ctx.beginPath();
  ctx.ellipse(X(30), Y(33), 6.5 * u, 8.5 * u, (20 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.globalAlpha = 0.32;
  ctx.fillStyle = "#2e1340";
  ctx.fill();
  ctx.globalAlpha = 0.38;
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.ellipse(X(17), Y(22), 3 * u, 5 * u, (-18 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 0.85;
  ctx.beginPath();
  ctx.ellipse(X(15.8), Y(20.4), 1.4 * u, 2.2 * u, (-18 * Math.PI) / 180, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.restore();

  // skull mark
  ctx.fillStyle = "#f3ecfa";
  ctx.beginPath();
  ctx.arc(X(24), Y(28), 5.2 * u, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  roundRect(ctx, X(21.3), Y(31.6), 5.4 * u, 3.2 * u, 1 * u);
  ctx.fill();
  ctx.fillStyle = "#43205c";
  ctx.beginPath();
  ctx.ellipse(X(21.8), Y(27.6), 1.4 * u, 1.6 * u, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(X(26.2), Y(27.6), 1.4 * u, 1.6 * u, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(X(23.2), Y(30));
  ctx.lineTo(X(24), Y(31.5));
  ctx.lineTo(X(24.8), Y(30));
  ctx.closePath();
  ctx.fill();

  // stem
  ctx.beginPath();
  ctx.moveTo(X(24), Y(15));
  ctx.quadraticCurveTo(X(23), Y(8), X(25), Y(5));
  ctx.lineWidth = 2.4 * u;
  ctx.strokeStyle = "#3d2b0f";
  ctx.lineCap = "round";
  ctx.stroke();

  // leaf
  ctx.beginPath();
  ctx.moveTo(X(24), Y(10));
  ctx.quadraticCurveTo(X(30), Y(6), X(32), Y(10));
  ctx.quadraticCurveTo(X(27), Y(13), X(24), Y(10));
  ctx.closePath();
  ctx.fillStyle = "#7e57c2";
  ctx.fill();
}

function drawStar(x, y, cell) {
  const ox = x * cell;
  const oy = y * cell;
  const u = cell / 48;
  const X = (px) => ox + px * u;
  const Y = (py) => oy + py * u;

  // 10 vertices of the 5-point star (design units)
  const pts = [
    [24, 6], [28.4, 17.9], [41.1, 18.4], [31.1, 26.3], [34.6, 38.6],
    [24, 31.5], [13.4, 38.6], [16.9, 26.3], [6.9, 18.4], [19.6, 17.9],
  ];

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(X(24), Y(43), 10 * u, 2.5 * u, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.32)";
  ctx.fill();

  // star body path
  const star = new Path2D();
  star.moveTo(X(pts[0][0]), Y(pts[0][1]));
  for (let i = 1; i < pts.length; i++) star.lineTo(X(pts[i][0]), Y(pts[i][1]));
  star.closePath();

  // body fill: vertical gold gradient
  const grad = ctx.createLinearGradient(0, Y(6), 0, Y(38.6));
  grad.addColorStop(0, "#fff0a8");
  grad.addColorStop(0.5, "#f2c40f");
  grad.addColorStop(1, "#b8860b");
  ctx.fillStyle = grad;
  ctx.fill(star);
  ctx.lineWidth = 1 * u;
  ctx.strokeStyle = "#9a7400";
  ctx.lineJoin = "round";
  ctx.stroke(star);

  // folded facets: tip -> next inner vertex -> center, darker
  const facets = [
    [[24, 6], [28.4, 17.9]],
    [[41.1, 18.4], [31.1, 26.3]],
    [[34.6, 38.6], [24, 31.5]],
    [[13.4, 38.6], [16.9, 26.3]],
    [[6.9, 18.4], [19.6, 17.9]],
  ];
  ctx.globalAlpha = 0.5;
  ctx.fillStyle = "#8a6800";
  for (const [tip, inner] of facets) {
    ctx.beginPath();
    ctx.moveTo(X(tip[0]), Y(tip[1]));
    ctx.lineTo(X(inner[0]), Y(inner[1]));
    ctx.lineTo(X(24), Y(24));
    ctx.closePath();
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // Mario eyes (white ovals, tilted outward, dark pupils, highlight)
  ctx.save();
  ctx.translate(X(20.8), Y(23.2));
  ctx.rotate((-8 * Math.PI) / 180);
  ctx.beginPath();
  ctx.ellipse(0, 0, 2.3 * u, 4.4 * u, 0, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();
  ctx.restore();

  ctx.save();
  ctx.translate(X(27.2), Y(23.2));
  ctx.rotate((8 * Math.PI) / 180);
  ctx.beginPath();
  ctx.ellipse(0, 0, 2.3 * u, 4.4 * u, 0, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();
  ctx.restore();

  ctx.fillStyle = "#2b1d00";
  ctx.beginPath();
  ctx.ellipse(X(21.2), Y(24.7), 1.25 * u, 2.6 * u, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(X(26.8), Y(24.7), 1.25 * u, 2.6 * u, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(X(20.8), Y(23.1), 0.55 * u, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(X(26.4), Y(23.1), 0.55 * u, 0, Math.PI * 2);
  ctx.fill();
}

function drawSword(x, y, cell) {
  const cx = x * cell + cell / 2;
  const cy = y * cell + cell / 2;
  const s = cell;

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(cx, cy + s * 0.4, s * 0.18, s * 0.05, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fill();

  const bladeTop = cy - s * 0.4;
  const bladeBottom = cy + s * 0.08;
  const halfW = s * 0.07;

  // blade with steel gradient (tip pointing up)
  const grad = ctx.createLinearGradient(cx - halfW, 0, cx + halfW, 0);
  grad.addColorStop(0, "#ffffff");
  grad.addColorStop(0.5, "#cfd8dc");
  grad.addColorStop(1, "#90a4ae");
  ctx.beginPath();
  ctx.moveTo(cx, bladeTop);
  ctx.lineTo(cx + halfW, bladeTop + s * 0.12);
  ctx.lineTo(cx + halfW, bladeBottom);
  ctx.lineTo(cx - halfW, bladeBottom);
  ctx.lineTo(cx - halfW, bladeTop + s * 0.12);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.lineWidth = s * 0.02;
  ctx.strokeStyle = "#607d8b";
  ctx.stroke();

  // fuller / center highlight
  ctx.beginPath();
  ctx.moveTo(cx, bladeTop + s * 0.12);
  ctx.lineTo(cx, bladeBottom);
  ctx.lineWidth = s * 0.02;
  ctx.strokeStyle = "rgba(255,255,255,0.7)";
  ctx.stroke();

  // crossguard (gold)
  ctx.fillStyle = "#e0a106";
  ctx.fillRect(cx - s * 0.2, bladeBottom, s * 0.4, s * 0.07);
  ctx.fillStyle = "#ffd54f";
  ctx.fillRect(cx - s * 0.2, bladeBottom, s * 0.4, s * 0.025);

  // handle (brown)
  ctx.fillStyle = "#8a5a2b";
  ctx.fillRect(cx - s * 0.035, bladeBottom + s * 0.07, s * 0.07, s * 0.16);

  // pommel (gold)
  ctx.beginPath();
  ctx.arc(cx, bladeBottom + s * 0.24, s * 0.055, 0, Math.PI * 2);
  ctx.fillStyle = "#f1c40f";
  ctx.fill();
  ctx.lineWidth = s * 0.015;
  ctx.strokeStyle = "#b8860b";
  ctx.stroke();
}

function drawInstantStack(x, y, cell) {
  const cx = x * cell + cell / 2;
  const cy = y * cell + cell / 2;
  const s = cell;

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(cx, cy + s * 0.34, s * 0.27, s * 0.055, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fill();

  // three stacked cyan layers (bottom -> top)
  const layers = [
    { w: 0.58, oy: 0.1, fill: "#00bcd4", gloss: "#5cf0ff" },
    { w: 0.46, oy: -0.08, fill: "#26c6da", gloss: "#7df3ff" },
    { w: 0.34, oy: -0.26, fill: "#4dd0e1", gloss: "#9af7ff" },
  ];
  const h = s * 0.17;
  for (const L of layers) {
    const w = s * L.w;
    const lx = cx - w / 2;
    const ly = cy + s * L.oy;

    ctx.beginPath();
    roundRect(ctx, lx, ly, w, h, h * 0.4);
    ctx.fillStyle = L.fill;
    ctx.fill();

    // gloss strip along the top edge
    ctx.beginPath();
    roundRect(ctx, lx, ly, w, h * 0.4, h * 0.3);
    ctx.globalAlpha = 0.7;
    ctx.fillStyle = L.gloss;
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

function drawChevron(tipX, cy, half, reach) {
  ctx.beginPath();
  ctx.moveTo(tipX - reach, cy - half);
  ctx.lineTo(tipX, cy);
  ctx.lineTo(tipX - reach, cy + half);
  ctx.stroke();
}

function drawSpeedBoost(x, y, cell) {
  const cx = x * cell + cell / 2;
  const cy = y * cell + cell / 2;
  const s = cell;

  // ground shadow
  ctx.beginPath();
  ctx.ellipse(cx, cy + s * 0.3, s * 0.25, s * 0.055, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.fill();

  const half = s * 0.22;
  const reach = s * 0.16;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // three chevrons, light -> dark orange (back to front)
  ctx.strokeStyle = "#ffcc80";
  ctx.lineWidth = s * 0.1;
  drawChevron(cx - s * 0.1, cy, half, reach);

  ctx.strokeStyle = "#ffb74d";
  ctx.lineWidth = s * 0.1;
  drawChevron(cx + s * 0.08, cy, half, reach);

  ctx.strokeStyle = "#ff8f00";
  ctx.lineWidth = s * 0.1;
  drawChevron(cx + s * 0.26, cy, half, reach);
}

function starPath(ctx, cx, cy, rOuter, rInner) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const r = i % 2 === 0 ? rOuter : rInner;
    const px = cx + r * Math.cos(angle);
    const py = cy + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

function drawStarSparkle(cx, cy, r, alpha) {
  const a = alpha == null ? 1 : alpha;
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  ctx.shadowColor = "rgba(255, 230, 120, 0.95)";
  ctx.shadowBlur = r * 4;

  ctx.fillStyle = "rgba(255, 248, 210, " + 0.9 * a + ")";
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.strokeStyle = "rgba(255, 245, 200, " + 0.85 * a + ")";
  ctx.lineCap = "round";
  ctx.lineWidth = r * 0.28;
  ctx.beginPath();
  ctx.moveTo(cx - r * 1.6, cy);
  ctx.lineTo(cx + r * 1.6, cy);
  ctx.moveTo(cx, cy - r * 1.6);
  ctx.lineTo(cx, cy + r * 1.6);
  ctx.stroke();

  ctx.lineWidth = r * 0.16;
  ctx.strokeStyle = "rgba(255, 245, 200, " + 0.55 * a + ")";
  ctx.beginPath();
  const d = r * 1.05;
  ctx.moveTo(cx - d, cy - d);
  ctx.lineTo(cx + d, cy + d);
  ctx.moveTo(cx - d, cy + d);
  ctx.lineTo(cx + d, cy - d);
  ctx.stroke();

  ctx.restore();
}

function drawSnakeStarBuff(snakeBody, cell, snakeIdx) {
  if (!snakeBody || snakeBody.length === 0) return;
  const head = snakeBody[0];
  const cx = head[0] * cell + cell / 2;
  const cy = head[1] * cell + cell / 2;
  const orbit = cell * 0.78;
  const r = cell * 0.13;
  const t = Date.now() * 0.0018;

  for (let i = 0; i < 3; i++) {
    const angle = t + snakeIdx * 0.7 + (i * (Math.PI * 2)) / 3;
    const wobble = 1 + 0.18 * Math.sin(t * 1.7 + i * 2.1);
    const sx = cx + orbit * wobble * Math.cos(angle);
    const sy = cy + orbit * wobble * Math.sin(angle);
    const alpha = 0.7 + 0.3 * Math.sin(t * 3 + i * 1.9);
    drawStarSparkle(sx, sy, r, alpha);
  }
}

function drawStarBuffs(snakes, cell) {
  let idx = 0;
  for (const name in snakes) {
    if (snakes[name].starBuffed)
      drawSnakeStarBuff(snakes[name].body, cell, idx);
    idx++;
  }
}

function drawUnknownItem(x, y, cell, color) {
  const cx = x * cell + cell / 2;
  const cy = y * cell + cell / 2;
  const r = cell * 0.35;

  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.3)";
  ctx.lineWidth = 1;
  ctx.stroke();
}

/* ================================================================
   SECTION: Snake drawing
   ================================================================ */
function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* Mario-style star buff: cycles a rainbow hue over time, offset per body
   segment so the colors march along the snake like a chase marquee. */
const STAR_HUE_SPEED = 0.4; // degrees per millisecond (~1.1s full cycle)
const STAR_HUE_PER_SEG = 32; // hue offset between adjacent segments

function hslToHex(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const sN = s / 100;
  const lN = l / 100;
  const c = (1 - Math.abs(2 * lN - 1)) * sN;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = lN - c / 2;
  let r1, g1, b1;
  if (h < 60) [r1, g1, b1] = [c, x, 0];
  else if (h < 120) [r1, g1, b1] = [x, c, 0];
  else if (h < 180) [r1, g1, b1] = [0, c, x];
  else if (h < 240) [r1, g1, b1] = [0, x, c];
  else if (h < 300) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  return rgbToHex((r1 + m) * 255, (g1 + m) * 255, (b1 + m) * 255);
}

function starHue(segmentIdx, timeMs, lightness) {
  const h = timeMs * STAR_HUE_SPEED + segmentIdx * STAR_HUE_PER_SEG;
  return hslToHex(h, 100, lightness == null ? 58 : lightness);
}

function drawSnakes(snakes, cell, fw, fh) {
  for (const name in snakes) {
    const snakeInfo = snakes[name];
    const body = snakeInfo.body;
    if (body.length === 0) continue;

    const alive = snakeInfo.alive;
    const rawColors = getSnakeColors(name, snakeInfo.color);

    // For dead snakes: grayscale + transparency
    let colors;
    if (!alive) {
      colors = {
        body: toGrayscale(rawColors.body),
        head: toGrayscale(rawColors.head),
        eye: "#ccc",
      };
      ctx.globalAlpha = 0.4;
    } else {
      colors = rawColors;
    }

    const pad = cell * 0.1;
    const seg = cell - pad * 2;
    const rad = seg * 0.35;
    const buffed = !!snakeInfo.starBuffed && alive;

    // Pass 0 (buffed only): rainbow outline behind the body. A single
    // continuous thicker stroke + a wider rounded-rect at the head, so
    // the chase reads as one frame around the whole snake silhouette
    // rather than separate boxes per segment.
    if (buffed) {
      const outline = cell * 0.14;
      const tNow = Date.now();

      ctx.save();
      ctx.lineWidth = seg + outline * 2;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (let i = 1; i < body.length; i++) {
        const dx = Math.abs(body[i][0] - body[i - 1][0]);
        const dy = Math.abs(body[i][1] - body[i - 1][1]);
        if (dx > 1 || dy > 1) continue;
        ctx.strokeStyle = starHue(i, tNow);
        ctx.beginPath();
        ctx.moveTo(
          body[i - 1][0] * cell + cell / 2,
          body[i - 1][1] * cell + cell / 2,
        );
        ctx.lineTo(body[i][0] * cell + cell / 2, body[i][1] * cell + cell / 2);
        ctx.stroke();
      }
      // Cap the head — Pass 2 draws a slightly bigger head than the
      // backbone (`seg * 1.1`), so we need a matching outline rect.
      const headSize = seg * 1.1 + outline * 2;
      const headCx = body[0][0] * cell + cell / 2;
      const headCy = body[0][1] * cell + cell / 2;
      ctx.fillStyle = starHue(0, tNow);
      ctx.beginPath();
      roundRect(
        ctx,
        headCx - headSize / 2,
        headCy - headSize / 2,
        headSize,
        headSize,
        headSize * 0.38,
      );
      ctx.fill();
      ctx.restore();
    }

    // Pass 1: thick continuous path as snake backbone (identity color)
    ctx.save();
    ctx.lineWidth = seg;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = colors.body;
    ctx.beginPath();
    ctx.moveTo(body[0][0] * cell + cell / 2, body[0][1] * cell + cell / 2);
    for (let i = 1; i < body.length; i++) {
      const dx = Math.abs(body[i][0] - body[i - 1][0]);
      const dy = Math.abs(body[i][1] - body[i - 1][1]);
      const px = body[i][0] * cell + cell / 2;
      const py = body[i][1] * cell + cell / 2;
      if (dx > 1 || dy > 1) {
        ctx.moveTo(px, py);
      } else {
        ctx.lineTo(px, py);
      }
    }
    ctx.stroke();
    ctx.restore();

    // Pass 2: draw detailed segments (rounded rects + textures)
    for (let i = body.length - 1; i >= 0; i--) {
      const [bx, by] = body[i];
      const cx = bx * cell + cell / 2;
      const cy = by * cell + cell / 2;

      if (i === 0) {
        drawSnakeHead(cx, cy, cell, seg, rad, colors, body);
      } else {
        drawBodySegment(cx, cy, seg, rad, colors, i, body.length);
      }
    }

    // Restore alpha for dead snakes
    if (!alive) {
      ctx.globalAlpha = 1.0;
    }
  }
}

function drawBodySegment(cx, cy, seg, rad, colors, idx, total) {
  const t = idx / Math.max(total - 1, 1);
  const shade = lerpColor(colors.body, colors.head, t * 0.4);

  ctx.beginPath();
  roundRect(ctx, cx - seg / 2 + 1, cy - seg / 2 + 2, seg, seg, rad);
  ctx.fillStyle = "rgba(0,0,0,0.2)";
  ctx.fill();

  ctx.beginPath();
  roundRect(ctx, cx - seg / 2, cy - seg / 2, seg, seg, rad);
  ctx.fillStyle = shade;
  ctx.fill();

  ctx.beginPath();
  roundRect(ctx, cx - seg / 2, cy - seg / 2, seg, seg, rad);
  ctx.save();
  ctx.clip();
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.beginPath();
  ctx.moveTo(cx, cy - seg * 0.3);
  ctx.lineTo(cx + seg * 0.3, cy);
  ctx.lineTo(cx, cy + seg * 0.3);
  ctx.lineTo(cx - seg * 0.3, cy);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawSnakeHead(cx, cy, cell, seg, rad, colors, body) {
  const headSize = seg * 1.1;
  const headRad = headSize * 0.38;

  ctx.beginPath();
  roundRect(
    ctx,
    cx - headSize / 2 + 1,
    cy - headSize / 2 + 2,
    headSize,
    headSize,
    headRad,
  );
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fill();

  const hg = ctx.createRadialGradient(
    cx - headSize * 0.15,
    cy - headSize * 0.15,
    0,
    cx,
    cy,
    headSize * 0.7,
  );
  hg.addColorStop(0, lightenColor(colors.body, 20));
  hg.addColorStop(1, colors.head);
  ctx.beginPath();
  roundRect(
    ctx,
    cx - headSize / 2,
    cy - headSize / 2,
    headSize,
    headSize,
    headRad,
  );
  ctx.fillStyle = hg;
  ctx.fill();

  let dir = { x: 0, y: -1 };
  if (body.length > 1) {
    const [hx, hy] = body[0];
    const [nx, ny] = body[1];
    dir = { x: Math.sign(hx - nx), y: Math.sign(hy - ny) };
    if (dir.x === 0 && dir.y === 0) dir = { x: 0, y: -1 };
  }

  const eyeOff = headSize * 0.22;
  const eyeR = headSize * 0.14;
  const pupilR = headSize * 0.07;
  const eyeShift = headSize * 0.08;

  let e1, e2;
  if (dir.x !== 0) {
    e1 = { x: cx + dir.x * eyeShift, y: cy - eyeOff };
    e2 = { x: cx + dir.x * eyeShift, y: cy + eyeOff };
  } else {
    e1 = { x: cx - eyeOff, y: cy + dir.y * eyeShift };
    e2 = { x: cx + eyeOff, y: cy + dir.y * eyeShift };
  }

  [e1, e2].forEach((e) => {
    ctx.beginPath();
    ctx.arc(e.x, e.y, eyeR, 0, Math.PI * 2);
    ctx.fillStyle = colors.eye;
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.3)";
    ctx.lineWidth = 0.5;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(
      e.x + dir.x * pupilR * 0.4,
      e.y + dir.y * pupilR * 0.4,
      pupilR,
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = "#1a1a2e";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(
      e.x - pupilR * 0.3,
      e.y - pupilR * 0.3,
      pupilR * 0.35,
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.fill();
  });
}

/* ================================================================
   SECTION: Full render
   ================================================================ */
function render(data) {
  centerOnFollowedSnake(data);

  const { fw, fh, cell } = layoutFromData(data);
  const fieldW = Math.round(fw * cell);
  const fieldH = Math.round(fh * cell);

  const container = getContainerSize();
  setCanvasSize(container.w, container.h);

  const canvasBg =
    getComputedStyle(document.body).getPropertyValue("--canvas-bg").trim() ||
    "#0f1117";
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const offsetX = (container.w - fieldW) / 2;
  const offsetY = (container.h - fieldH) / 2;

  ctx.setTransform(
    zoom,
    0,
    0,
    zoom,
    offsetX * zoom + panX + (container.w * (1 - zoom)) / 2,
    offsetY * zoom + panY + (container.h * (1 - zoom)) / 2,
  );

  drawBackground(fieldW, fieldH, cell, fw, fh);
  drawItems(data.items, cell);
  drawSnakes(data.snakes, cell, fw, fh);
  drawStarBuffs(data.snakes, cell, data.tick);

  ctx.setTransform(1, 0, 0, 1, 0, 0);

  renderMinimap(data);
}

/* ================================================================
   SECTION: Minimap
   ================================================================ */
function renderMinimap(data) {
  if (zoom <= 1.0) {
    minimapWrap.classList.remove("visible");
    return;
  }
  minimapWrap.classList.add("visible");

  const { fw, fh, cell } = layoutFromData(data);
  const fieldW = Math.round(fw * cell);
  const fieldH = Math.round(fh * cell);

  const mmScale = Math.min(MINIMAP_SIZE / fieldW, MINIMAP_SIZE / fieldH);
  const mmW = Math.round(fieldW * mmScale);
  const mmH = Math.round(fieldH * mmScale);

  minimapCanvas.width = MINIMAP_SIZE;
  minimapCanvas.height = MINIMAP_SIZE;

  const canvasBg =
    getComputedStyle(document.body).getPropertyValue("--canvas-bg").trim() ||
    "#0f1117";
  minimapCtx.fillStyle = canvasBg;
  minimapCtx.fillRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE);

  const mmOffX = (MINIMAP_SIZE - mmW) / 2;
  const mmOffY = (MINIMAP_SIZE - mmH) / 2;

  minimapCtx.save();
  minimapCtx.setTransform(mmScale, 0, 0, mmScale, mmOffX, mmOffY);

  const sandBase =
    getComputedStyle(document.body).getPropertyValue("--sand-base").trim() ||
    "#2a2418";
  minimapCtx.fillStyle = sandBase;
  minimapCtx.fillRect(0, 0, fieldW, fieldH);

  if (data.items) {
    data.items.forEach((i) => {
      const ax = i[0][0] * cell + cell / 2;
      const ay = i[0][1] * cell + cell / 2;
      minimapCtx.fillStyle = getItemRenderer(i[1]).minimapColor;
      minimapCtx.beginPath();
      minimapCtx.arc(ax, ay, cell * 0.3, 0, Math.PI * 2);
      minimapCtx.fill();
    });
  }

  for (const name in data.snakes) {
    const snakeInfo = data.snakes[name];
    const body = snakeInfo.body;
    if (body.length === 0) continue;
    const colors = getSnakeColors(name, snakeInfo.color);
    minimapCtx.strokeStyle = snakeInfo.alive ? colors.body : "#666";
    minimapCtx.globalAlpha = snakeInfo.alive ? 1.0 : 0.4;
    minimapCtx.lineWidth = cell * 0.7;
    minimapCtx.lineCap = "round";
    minimapCtx.lineJoin = "round";
    minimapCtx.beginPath();
    minimapCtx.moveTo(
      body[0][0] * cell + cell / 2,
      body[0][1] * cell + cell / 2,
    );
    for (let i = 1; i < body.length; i++) {
      const dx = Math.abs(body[i][0] - body[i - 1][0]);
      const dy = Math.abs(body[i][1] - body[i - 1][1]);
      const px = body[i][0] * cell + cell / 2;
      const py = body[i][1] * cell + cell / 2;
      if (dx > 1 || dy > 1) {
        minimapCtx.moveTo(px, py);
      } else {
        minimapCtx.lineTo(px, py);
      }
    }
    minimapCtx.stroke();
    minimapCtx.globalAlpha = 1.0;
  }

  minimapCtx.restore();

  // Compute viewport rectangle
  const container = getContainerSize();
  const offsetX = (container.w - fieldW) / 2;
  const offsetY = (container.h - fieldH) / 2;
  const tx = offsetX * zoom + panX + (container.w * (1 - zoom)) / 2;
  const ty = offsetY * zoom + panY + (container.h * (1 - zoom)) / 2;

  const visX = -tx / zoom;
  const visY = -ty / zoom;
  const visW = container.w / zoom;
  const visH = container.h / zoom;

  const vpLeft = mmOffX + visX * mmScale;
  const vpTop = mmOffY + visY * mmScale;
  const vpWidth = visW * mmScale;
  const vpHeight = visH * mmScale;

  minimapVp.style.left = Math.max(0, vpLeft) + "px";
  minimapVp.style.top = Math.max(0, vpTop) + "px";
  minimapVp.style.width =
    Math.min(vpWidth, MINIMAP_SIZE - Math.max(0, vpLeft)) + "px";
  minimapVp.style.height =
    Math.min(vpHeight, MINIMAP_SIZE - Math.max(0, vpTop)) + "px";
}

/* ================================================================
   SECTION: Timer
   ================================================================ */
// Derived from the server-authoritative tick counter, so it is reload-proof
// and resets automatically when a new game starts (tick returns to 0).
function updateTimerDisplay(data) {
  const tps = data.ticks_per_second || 0;
  const elapsed = tps > 0 ? Math.floor((data.tick || 0) / tps) : 0;
  const m = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  document.getElementById("game-timer").textContent = `${m}:${s}`;
}

/* ================================================================
   SECTION: Game reset detection
   ================================================================ */
function detectGameReset(data) {
  const names = Object.keys(data.snakes).sort().join(",");
  if (previousSnakeNames !== null && names !== previousSnakeNames) {
    teamColorMap.clear();
    clearTrails();
  }
  previousSnakeNames = names;
}

/* ================================================================
   SECTION: Winner banner
   ================================================================ */
function updateWinnerBanner(data) {
  const entries = Object.entries(data.snakes);
  const alive = entries.filter(
    ([_, info]) => info.alive && info.body.length > 0,
  );
  if (alive.length === 1 && entries.length > 1) {
    $winnerBanner.classList.remove("hidden");
    $winnerName.textContent = alive[0][0];
  } else {
    $winnerBanner.classList.add("hidden");
  }
}

/* ================================================================
   SECTION: Game list polling (from dashboard)
   ================================================================ */
async function fetchGameList() {
  try {
    const res = await fetch("/games", { cache: "no-store" });
    if (!res.ok) return;
    const games = await res.json();
    renderGameList(games);
  } catch (_) {
    /* silent */
  }
}

function renderGameList(games) {
  $gameList.innerHTML = "";
  games.forEach((g) => {
    const li = document.createElement("li");
    if (g.name === currentGame) li.classList.add("active");
    li.innerHTML =
      '<span class="game-name">' +
      escHtml(g.name) +
      "</span>" +
      '<span class="game-meta">' +
      g.player_count +
      "P " +
      g.size[0] +
      "x" +
      g.size[1] +
      "</span>";
    li.addEventListener("click", () => selectGame(g.name));
    $gameList.appendChild(li);
  });
}

/* ================================================================
   SECTION: Game selection & SSE connection
   ================================================================ */
function selectGame(gameName) {
  if (currentGame === gameName) return;
  currentGame = gameName;
  setFollowedSnake(null);
  document.getElementById("game-timer").textContent = "00:00";
  previousSnakeNames = null;
  teamColorMap.clear();
  clearTrails();

  $viewingGame.textContent = "WATCHING: " + gameName;
  $resetBtn.style.display = "inline-block";
  $deleteBtn.style.display = "inline-block";
  $noGameMsg.classList.add("hidden");

  document.querySelectorAll("#game-list li").forEach((li) => {
    li.classList.toggle(
      "active",
      li.querySelector(".game-name").textContent === gameName,
    );
  });

  connectSSE(gameName);
}

function adaptServerMessage(msg) {
  const state = msg.state || {};
  const snakes = {};
  for (const [name, s] of Object.entries(state.snake || {})) {
    const inventory = {};
    for (const item of s.inventory || [])
      inventory[item] = (inventory[item] || 0) + 1;
    const effects = {};
    for (const e of s.active_effects || [])
      effects[e.effect] = e.remaining_ticks;
    snakes[name] = {
      body: s.body,
      alive: s.alive,
      inventory,
      active_effects: effects,
      color: s.color,
      starBuffed: s.alive && !!effects.Invincible && !!effects.TouchOfDeath,
    };
  }
  return {
    size: state.size,
    items: state.items || [],
    snakes,
    scoreboard: msg.scoreboard,
    tick: msg.tick,
    ticks_per_second: msg.ticks_per_second,
  };
}

function connectSSE(gameName) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  setConnectionStatus(false);
  eventSource = new EventSource(
    "/games/" + encodeURIComponent(gameName) + "/json-stream",
  );

  eventSource.addEventListener("gamestate", (e) => {
    setConnectionStatus(true);
    try {
      const msg = JSON.parse(e.data);
      const data = adaptServerMessage(msg);
      lastData = data;
      detectGameReset(data);
      updateTrails(data);
      render(data);
      updateTimerDisplay(data);
      renderScoreboard(data.scoreboard, data.tick);
      renderGlobalEffects(data.global_effects);
      updateWinnerBanner(data);
      ensureAnimationLoop();
    } catch (err) {
      console.error("Parse error:", err);
    }
  });

  eventSource.addEventListener("open", () => setConnectionStatus(true));
  eventSource.addEventListener("error", () => setConnectionStatus(false));
}

/* ================================================================
   SECTION: Connection status
   ================================================================ */
function setConnectionStatus(connected) {
  if (connected) {
    $connStatus.textContent = "CONNECTED";
    $connStatus.className = "status-connected";
  } else {
    $connStatus.textContent = "DISCONNECTED";
    $connStatus.className = "status-disconnected";
  }
}

/* ================================================================
   SECTION: Scoreboard rendering
   ================================================================ */

/* Item & effect accent colors used by inventory slots and effect pills.
   Item colors mirror ITEM_REGISTRY.minimapColor; effects each have a
   semantic color matching the existing cyan/danger/yellow vocabulary. */
const ITEM_ACCENT = {
  Apple: "#e63946",
  BadApple: "#8e44ad",
  Star: "#f1c40f",
  Sword: "#b0bec5",
  InstantStack: "#00bcd4",
  SpeedBoost: "#ff9800",
};
const EFFECT_ACCENT = {
  Invincible: {
    color: "var(--cyan)",
    bg: "rgba(0, 229, 255, 0.12)",
    glow: "rgba(0, 229, 255, 0.55)",
  },
  TouchOfDeath: {
    color: "var(--danger)",
    bg: "rgba(231, 76, 60, 0.12)",
    glow: "rgba(231, 76, 60, 0.55)",
  },
  SpeedBoost: {
    color: "var(--yellow)",
    bg: "rgba(255, 230, 0, 0.12)",
    glow: "rgba(255, 230, 0, 0.55)",
  },
};

/* Short, evocative arcade-style display labels for active effects. */
const EFFECT_LABELS = {
  Invincible: "SHIELD",
  TouchOfDeath: "REAPER",
  SpeedBoost: "RUSH",
};

function humanizeEffectName(name) {
  if (EFFECT_LABELS[name]) return EFFECT_LABELS[name];
  return name.replace(/([a-z])([A-Z])/g, "$1 $2").toUpperCase();
}

/* Inline pixel-art SVG icons. Effect icons use currentColor so they tint to
   the pill's accent color; item icons carry their own intrinsic palette. */
const SVG_NS = 'xmlns="http://www.w3.org/2000/svg"';
const FX_ICONS = {
  Invincible: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 1 L2 3 L2 8 C2 11 5 14 8 15 C11 14 14 11 14 8 L14 3 Z"
                  fill="currentColor" fill-opacity="0.22"
                  stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
            <path d="M8 5.2 L9 7.2 L11.1 7.5 L9.6 9 L10 11.1 L8 10.1 L6 11.1 L6.4 9 L4.9 7.5 L7 7.2 Z"
                  fill="currentColor"/>
        </svg>`,
  TouchOfDeath: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 3 L12 3 L13 4 L13 9 L11 9 L11 11 L10 12 L10 13 L6 13 L6 12 L5 11 L5 9 L3 9 L3 4 Z"
                  fill="currentColor" fill-opacity="0.22"
                  stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
            <rect x="5" y="6" width="2.2" height="2.2" fill="currentColor"/>
            <rect x="8.8" y="6" width="2.2" height="2.2" fill="currentColor"/>
            <rect x="7.4" y="9" width="1.2" height="1.6" fill="currentColor"/>
        </svg>`,
  SpeedBoost: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <path d="M9.5 1 L3 9 L7 9 L6 15 L13 6.5 L9 6.5 Z"
                  fill="currentColor" stroke="currentColor"
                  stroke-width="0.8" stroke-linejoin="round"/>
        </svg>`,
};

const ITEM_ICONS = {
  Apple: `<svg ${SVG_NS} viewBox="0 0 48 48" aria-hidden="true">
            <path d="M24 15 C16 12 10 18 10 26 C10 35 16 41 24 41 C32 41 38 35 38 26 C38 18 32 12 24 15 Z" fill="#cf2233"/>
            <ellipse cx="30" cy="33" rx="6.5" ry="8.5" fill="#5e0d14" fill-opacity="0.3" transform="rotate(20 30 33)"/>
            <ellipse cx="17" cy="22" rx="3.2" ry="5.2" fill="#ffffff" fill-opacity="0.4" transform="rotate(-18 17 22)"/>
            <ellipse cx="15.6" cy="20" rx="1.5" ry="2.4" fill="#ffffff" fill-opacity="0.9" transform="rotate(-18 15.6 20)"/>
            <path d="M24 15 Q25 8 23 5" stroke="#6b4423" stroke-width="2.4" fill="none" stroke-linecap="round"/>
            <path d="M24 9 Q31 4.5 33.5 9 Q28 13 24 9 Z" fill="#4caf50"/>
        </svg>`,
  BadApple: `<svg ${SVG_NS} viewBox="0 0 48 48" aria-hidden="true">
            <path d="M24 15 C16 12 10 18 10 26 C10 35 16 41 24 41 C32 41 38 35 38 26 C38 18 32 12 24 15 Z" fill="#8e44ad"/>
            <ellipse cx="30" cy="33" rx="6.5" ry="8.5" fill="#2e1340" fill-opacity="0.32" transform="rotate(20 30 33)"/>
            <ellipse cx="15.8" cy="20.4" rx="1.4" ry="2.2" fill="#ffffff" fill-opacity="0.85" transform="rotate(-18 15.8 20.4)"/>
            <g fill="#f3ecfa"><circle cx="24" cy="28" r="5.2"/><rect x="21.3" y="31.6" width="5.4" height="3.2" rx="1"/></g>
            <ellipse cx="21.8" cy="27.6" rx="1.4" ry="1.6" fill="#43205c"/>
            <ellipse cx="26.2" cy="27.6" rx="1.4" ry="1.6" fill="#43205c"/>
            <path d="M23.2 30 L24 31.5 L24.8 30 Z" fill="#43205c"/>
            <path d="M24 15 Q23 8 25 5" stroke="#3d2b0f" stroke-width="2.4" fill="none" stroke-linecap="round"/>
            <path d="M24 10 Q30 6 32 10 Q27 13 24 10 Z" fill="#7e57c2"/>
        </svg>`,
  Star: `<svg ${SVG_NS} viewBox="0 0 48 48" aria-hidden="true">
            <path d="M24,6 L28.4,17.9 L41.1,18.4 L31.1,26.3 L34.6,38.6 L24,31.5 L13.4,38.6 L16.9,26.3 L6.9,18.4 L19.6,17.9 Z" fill="#f2c40f" stroke="#9a7400" stroke-width="1" stroke-linejoin="round"/>
            <g fill="#8a6800" fill-opacity="0.5">
              <polygon points="24,6 28.4,17.9 24,24"/><polygon points="41.1,18.4 31.1,26.3 24,24"/>
              <polygon points="34.6,38.6 24,31.5 24,24"/><polygon points="13.4,38.6 16.9,26.3 24,24"/>
              <polygon points="6.9,18.4 19.6,17.9 24,24"/>
            </g>
            <ellipse cx="20.8" cy="23.2" rx="2.3" ry="4.4" fill="#ffffff" transform="rotate(-8 20.8 23.2)"/>
            <ellipse cx="27.2" cy="23.2" rx="2.3" ry="4.4" fill="#ffffff" transform="rotate(8 27.2 23.2)"/>
            <ellipse cx="21.2" cy="24.7" rx="1.25" ry="2.6" fill="#2b1d00"/>
            <ellipse cx="26.8" cy="24.7" rx="1.25" ry="2.6" fill="#2b1d00"/>
            <circle cx="20.8" cy="23.1" r="0.55" fill="#ffffff"/>
            <circle cx="26.4" cy="23.1" r="0.55" fill="#ffffff"/>
        </svg>`,
  Sword: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <polygon points="8,1.5 9.3,4 9.3,9.7 6.7,9.7 6.7,4" fill="#cfd8dc" stroke="#607d8b" stroke-width="0.6" stroke-linejoin="round"/>
            <line x1="8" y1="4" x2="8" y2="9.2" stroke="#ffffff" stroke-width="0.5" opacity="0.7"/>
            <rect x="4.4" y="9.7" width="7.2" height="1.5" rx="0.7" fill="#e0a106"/>
            <rect x="7.3" y="11.2" width="1.4" height="2.6" fill="#8a5a2b"/>
            <circle cx="8" cy="14.2" r="1.1" fill="#f1c40f" stroke="#b8860b" stroke-width="0.3"/>
        </svg>`,
  InstantStack: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <rect x="2.5" y="9.5" width="11" height="2.8" rx="1.2" fill="#00bcd4"/>
            <rect x="2.5" y="9.5" width="11" height="1" rx="0.5" fill="#5cf0ff" fill-opacity="0.7"/>
            <rect x="4" y="6.3" width="8" height="2.8" rx="1.2" fill="#26c6da"/>
            <rect x="4" y="6.3" width="8" height="1" rx="0.5" fill="#7df3ff" fill-opacity="0.7"/>
            <rect x="5.5" y="3.1" width="5" height="2.8" rx="1.2" fill="#4dd0e1"/>
            <rect x="5.5" y="3.1" width="5" height="1" rx="0.5" fill="#9af7ff" fill-opacity="0.7"/>
        </svg>`,
  SpeedBoost: `<svg ${SVG_NS} viewBox="0 0 16 16" aria-hidden="true">
            <path d="M2.5 3.5 L7 8 L2.5 12.5" fill="none" stroke="#ffcc80" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M6.5 3.5 L11 8 L6.5 12.5" fill="none" stroke="#ffb74d" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M10.5 3.5 L15 8 L10.5 12.5" fill="none" stroke="#ff8f00" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`,
};

function getItemAccent(itemName) {
  return ITEM_ACCENT[itemName] || hashColor(itemName);
}

function getEffectAccent(effectName) {
  return EFFECT_ACCENT[effectName] || EFFECT_ACCENT.Invincible;
}

function rgbCss(rgb) {
  return rgb ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : "var(--accent)";
}

function buildInvSlot(itemName, count) {
  const accent = getItemAccent(itemName);
  const slot = document.createElement("div");
  slot.className = "inv-slot";
  slot.dataset.item = itemName;
  slot.title = `${itemName} ×${count}`;
  slot.style.borderColor = accent;
  slot.style.setProperty("--slot-tint", accent);
  slot.innerHTML =
    `<span class="inv-glyph">${getItemBadgeIcon(itemName)}</span>` +
    `<span class="inv-count">×${count}</span>`;
  return slot;
}

function buildFxSlot(effectName, ticks) {
  const accent = getEffectAccent(effectName);
  const label = humanizeEffectName(effectName);
  const slot = document.createElement("div");
  slot.className = "fx-slot";
  slot.title = `${effectName} (${ticks} ticks remaining)`;
  slot.style.setProperty("--fx-color", accent.color);
  slot.style.setProperty("--fx-bg", accent.bg);
  slot.style.setProperty("--fx-glow", accent.glow);
  slot.innerHTML =
    `<span class="fx-icon">${getEffectBadgeIcon(effectName)}</span>` +
    `<span class="fx-name">${escHtml(label)}</span>` +
    `<span class="fx-ticks">${ticks}<span class="fx-ticks-unit">T</span></span>`;
  return slot;
}

function buildPlayerCard(player, rank) {
  const card = document.createElement("li");
  card.className = "player-card";
  card.dataset.snake = player.name;

  const snakeInfo = lastData && lastData.snakes && lastData.snakes[player.name];
  const snakeColor = snakeInfo && snakeInfo.color;
  card.style.setProperty("--snake-color", rgbCss(snakeColor));
  if (!player.alive) card.classList.add("dead");
  if (followedSnakeName === player.name) card.classList.add("following");

  const stripe = document.createElement("span");
  stripe.className = "color-stripe";

  const medal = document.createElement("span");
  medal.className = "rank-medal" + (rank <= 3 ? " rank-" + rank : "");
  medal.textContent = rank;

  const body = document.createElement("div");
  body.className = "card-body";

  const header = document.createElement("div");
  header.className = "card-header";

  const name = document.createElement("span");
  name.className = "player-name" + (player.alive ? "" : " dead");
  name.textContent = player.name;

  const lengthPill = document.createElement("span");
  lengthPill.className = "length-pill";
  lengthPill.innerHTML = `<span class="len-num">${player.length}</span>SEG`;

  header.append(name, lengthPill);
  body.appendChild(header);

  if (snakeInfo && player.alive) {
    const inv = snakeInfo.inventory || {};
    const invEntries = Object.entries(inv).filter(([, c]) => c > 0);
    if (invEntries.length > 0) {
      const invRow = document.createElement("div");
      invRow.className = "inv-row";
      invEntries.forEach(([itemName, count]) => {
        invRow.appendChild(buildInvSlot(itemName, count));
      });
      body.appendChild(invRow);
    }

    const effects = snakeInfo.active_effects || {};
    const fxEntries = Object.entries(effects).filter(([, t]) => t > 0);
    if (fxEntries.length > 0) {
      const fxRow = document.createElement("div");
      fxRow.className = "fx-row";
      fxEntries.forEach(([effectName, ticks]) => {
        fxRow.appendChild(buildFxSlot(effectName, ticks));
      });
      body.appendChild(fxRow);
    }
  }

  card.append(stripe, medal, body);
  card.addEventListener("click", () => {
    setFollowedSnake(followedSnakeName === player.name ? null : player.name);
  });
  return card;
}

function renderScoreboard(scoreboard, tick) {
  $scoreboardTick.textContent = "TICK: " + tick;
  $scoreboardList.innerHTML = "";

  if (!scoreboard || !scoreboard.players) return;

  scoreboard.players.forEach((p, i) => {
    $scoreboardList.appendChild(buildPlayerCard(p, i + 1));
  });
}

function renderGlobalEffects(globalEffects) {
  if (!globalEffects || Object.keys(globalEffects).length === 0) {
    $globalEffects.innerHTML = "";
    return;
  }
  let html = "";
  for (const [name, ticks] of Object.entries(globalEffects)) {
    html +=
      '<span class="global-effect-badge">' +
      '<span class="fx-icon">' +
      getEffectBadgeIcon(name) +
      "</span> " +
      escHtml(humanizeEffectName(name)) +
      ' <span class="effect-ticks">' +
      ticks +
      "t</span></span>";
  }
  $globalEffects.innerHTML = html;
}

function getItemBadgeIcon(itemName) {
  return ITEM_ICONS[itemName] || '<span class="badge-fallback">&#9679;</span>';
}

function getEffectBadgeIcon(effectName) {
  return FX_ICONS[effectName] || '<span class="badge-fallback">&#9733;</span>';
}

/* ================================================================
   SECTION: Create game modal (from dashboard)
   ================================================================ */
$createBtn.addEventListener("click", () => {
  $modalOverlay.classList.remove("hidden");
  $modalName.value = "";
  $modalName.focus();
});

// Strip whitespace as it is typed/pasted — game names are used as REST path
// segments and must not contain spaces.
$modalName.addEventListener("input", () => {
  const stripped = $modalName.value.replace(/\s/g, "");
  if (stripped !== $modalName.value) $modalName.value = stripped;
});

$modalCancel.addEventListener("click", () => {
  $modalOverlay.classList.add("hidden");
});

$modalOverlay.addEventListener("click", (e) => {
  if (e.target === $modalOverlay) $modalOverlay.classList.add("hidden");
});

$modalCreate.addEventListener("click", async () => {
  const name = $modalName.value.trim();
  if (!name) return;

  const width = parseInt($modalWidth.value) || 10;
  const height = parseInt($modalHeight.value) || 10;

  const snakePositions = [
    { x: Math.floor(width * 0.2), y: Math.floor(height / 2) },
    { x: Math.floor(width * 0.8), y: Math.floor(height / 2) },
    { x: Math.floor(width / 2), y: Math.floor(height * 0.2) },
    { x: Math.floor(width / 2), y: Math.floor(height * 0.8) },
  ];

  const snakes = snakePositions.map((pos) => ({
    alive: true,
    body: Array(6).fill([pos.x, pos.y]),
  }));

  try {
    const res = await fetch("/games", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        config: {
          size: [width, height],
          snakes: snakes,
          apple_every_ticks: 2,
          auto_start_on_player_join: true,
        },
      }),
    });
    if (res.ok) {
      $modalOverlay.classList.add("hidden");
      await fetchGameList();
      selectGame(name);
    }
  } catch (err) {
    console.error("Failed to create game:", err);
  }
});

/* ================================================================
   SECTION: Delete game (from dashboard)
   ================================================================ */
$deleteBtn.addEventListener("click", async () => {
  if (!currentGame) return;
  const name = currentGame;
  try {
    await fetch("/games/" + encodeURIComponent(name), { method: "DELETE" });
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    currentGame = null;
    lastData = null;
    $viewingGame.textContent = "Select a game...";
    $resetBtn.style.display = "none";
    $deleteBtn.style.display = "none";
    $noGameMsg.classList.remove("hidden");
    $scoreboardList.innerHTML = "";
    $scoreboardTick.textContent = "TICK: --";
    setConnectionStatus(false);
    document.getElementById("game-timer").textContent = "00:00";
    // Clear canvas
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    fetchGameList();
  } catch (err) {
    console.error("Failed to delete game:", err);
  }
});

/* ================================================================
   SECTION: Reset game (from dashboard)
   ================================================================ */
$resetBtn.addEventListener("click", async () => {
  if (!currentGame) return;
  try {
    const res = await fetch("/games/" + encodeURIComponent(currentGame) + "/reset", {
      method: "POST",
    });
    if (!res.ok) console.error("Failed to reset game:", res.status);
  } catch (err) {
    console.error("Failed to reset game:", err);
  }
});

/* ================================================================
   SECTION: Day/Night toggle
   ================================================================ */
function initTheme() {
  const saved = localStorage.getItem("snake-theme");
  if (saved === "day") {
    document.body.classList.add("day-mode");
  }
  updateThemeButton();
}

function toggleTheme() {
  document.body.classList.toggle("day-mode");
  const isDay = isDayMode();
  localStorage.setItem("snake-theme", isDay ? "day" : "night");
  updateThemeButton();
  sandPattern = null;
  renderIfData();
}

function updateThemeButton() {
  $themeToggle.textContent = isDayMode() ? "DAY" : "NIGHT";
}

$themeToggle.addEventListener("click", toggleTheme);

/* ================================================================
   SECTION: Zoom & Pan event handlers
   ================================================================ */
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const oldZoom = zoom;
    zoom = clamp(
      zoom * (e.deltaY < 0 ? ZOOM_SPEED : 1 / ZOOM_SPEED),
      ZOOM_MIN,
      ZOOM_MAX,
    );

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    panX = mx - (mx - panX) * (zoom / oldZoom);
    panY = my - (my - panY) * (zoom / oldZoom);

    if (zoom <= 1.0 + 0.001) {
      zoom = 1.0;
      panX = 0;
      panY = 0;
    }

    clampPan();
    updateZoomIndicator();
    renderIfData();
  },
  { passive: false },
);

canvas.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  mouseDownPos = { x: e.clientX, y: e.clientY };
  if (followedSnakeName !== null) return;
  if (zoom <= 1.0) return;
  isPanning = true;
  panStartX = e.clientX;
  panStartY = e.clientY;
  panStartPanX = panX;
  panStartPanY = panY;
  wrap.classList.add("panning");
});

window.addEventListener("mousemove", (e) => {
  if (!isPanning) return;
  panX = panStartPanX + (e.clientX - panStartX);
  panY = panStartPanY + (e.clientY - panStartY);
  clampPan();
  renderIfData();
});

window.addEventListener("mouseup", (e) => {
  if (isPanning) {
    isPanning = false;
    wrap.classList.remove("panning");
  }
  if (mouseDownPos) {
    const dx = e.clientX - mouseDownPos.x;
    const dy = e.clientY - mouseDownPos.y;
    if (Math.abs(dx) < CLICK_THRESHOLD && Math.abs(dy) < CLICK_THRESHOLD) {
      const hit = hitTestSnake(e.clientX, e.clientY, lastData);
      if (hit) {
        setFollowedSnake(followedSnakeName === hit ? null : hit);
      } else {
        setFollowedSnake(null);
      }
    }
    mouseDownPos = null;
  }
});

canvas.addEventListener("dblclick", () => {
  setFollowedSnake(null);
  resetZoom();
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && followedSnakeName !== null) {
    setFollowedSnake(null);
  }
});

window.addEventListener("resize", () => {
  sandPattern = null;
  renderIfData();
});

/* ================================================================
   SECTION: Sidebar resizer
   ================================================================ */
const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 500;
const SIDEBAR_DEFAULT = 320;
const $sidebarResizer = document.getElementById("sidebar-resizer");
let sidebarResizing = false;

function setSidebarWidth(px) {
  const w = clamp(px, SIDEBAR_MIN, SIDEBAR_MAX);
  document.documentElement.style.setProperty("--sidebar-w", w + "px");
  sandPattern = null;
  renderIfData();
  return w;
}

function initSidebarWidth() {
  const saved = parseInt(localStorage.getItem("snake-sidebar-w"), 10);
  setSidebarWidth(Number.isFinite(saved) ? saved : SIDEBAR_DEFAULT);
}

$sidebarResizer.addEventListener("mousedown", (e) => {
  sidebarResizing = true;
  $sidebarResizer.classList.add("resizing");
  document.body.classList.add("resizing-sidebar");
  e.preventDefault();
});

window.addEventListener("mousemove", (e) => {
  if (!sidebarResizing) return;
  setSidebarWidth(e.clientX);
});

window.addEventListener("mouseup", () => {
  if (!sidebarResizing) return;
  sidebarResizing = false;
  $sidebarResizer.classList.remove("resizing");
  document.body.classList.remove("resizing-sidebar");
  const current = getComputedStyle(document.documentElement)
    .getPropertyValue("--sidebar-w")
    .trim();
  const px = parseInt(current, 10);
  if (Number.isFinite(px)) {
    localStorage.setItem("snake-sidebar-w", String(px));
  }
});

/* ================================================================
   SECTION: Boot
   ================================================================ */
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initSidebarWidth();
  fetchGameList();
  setInterval(fetchGameList, GAME_LIST_POLL_MS);
});
