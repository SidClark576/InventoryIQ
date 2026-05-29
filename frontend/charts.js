/* ============================================================
   InventoryIQ — inline SVG chart helpers + toast utility.
   No external libraries. Returns SVG strings for embedding.
   ============================================================ */

/**
 * Render a sparkline as an inline SVG string (polyline + soft area fill).
 * @param {number[]} values
 * @param {{width?:number,height?:number,stroke?:string,fill?:string}} [opts]
 * @returns {string}
 */
function renderSparkline(values, opts) {
  const o = opts || {};
  const w = o.width || 120;
  const h = o.height || 36;
  const stroke = o.stroke || '#3b8df0';
  const fill = o.fill || 'rgba(59,141,240,0.18)';
  const pad = 2;

  const data = Array.isArray(values) ? values.filter(v => Number.isFinite(v)) : [];
  if (data.length < 2) {
    // Flat baseline when there isn't enough data to draw a trend.
    const midY = (h / 2).toFixed(1);
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="${midY}" x2="${w}" y2="${midY}" stroke="${stroke}" stroke-width="1.5" stroke-dasharray="3 4" opacity="0.5"/>
    </svg>`;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = (w - pad * 2) / (data.length - 1);

  const points = data.map((v, i) => {
    const x = pad + i * step;
    const y = pad + (1 - (v - min) / range) * (h - pad * 2);
    return [x, y];
  });

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${points[points.length - 1][0].toFixed(1)},${h} L${points[0][0].toFixed(1)},${h} Z`;
  const last = points[points.length - 1];

  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${area}" fill="${fill}" stroke="none"/>
    <path d="${line}" fill="none" stroke="${stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.4" fill="${stroke}"/>
  </svg>`;
}

/**
 * Render a radial gauge (0-100) as an inline SVG string.
 * @param {number} value 0..100
 * @param {{size?:number,label?:string,color?:string,track?:string}} [opts]
 * @returns {string}
 */
function renderRadialGauge(value, opts) {
  const o = opts || {};
  const size = o.size || 160;
  const stroke = 12;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const dash = (pct / 100) * circ;
  const color = o.color || (pct < 50 ? '#f87171' : pct < 80 ? '#fbbf24' : '#34d399');
  const track = o.track || '#243352';
  const label = o.label || 'Health';

  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${label} ${pct}">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${track}" stroke-width="${stroke}"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
      stroke-linecap="round" stroke-dasharray="${dash.toFixed(2)} ${(circ - dash).toFixed(2)}"
      transform="rotate(-90 ${cx} ${cy})"/>
    <text x="${cx}" y="${cy - 4}" text-anchor="middle" dominant-baseline="middle"
      fill="#eef2fb" font-size="${size * 0.26}" font-weight="900" font-family="Inter, sans-serif"
      style="font-variant-numeric:tabular-nums">${pct}</text>
    <text x="${cx}" y="${cy + size * 0.16}" text-anchor="middle" dominant-baseline="middle"
      fill="#5d6f96" font-size="${size * 0.085}" font-weight="700" letter-spacing="1.5"
      font-family="Inter, sans-serif">${label.toUpperCase()}</text>
  </svg>`;
}

/**
 * Render a horizontal stacked distribution bar (in / low / out).
 * @param {{inStock:number,low:number,out:number}} parts
 * @returns {string}
 */
function renderStackBar(parts) {
  const inS = Math.max(0, parts.inStock || 0);
  const low = Math.max(0, parts.low || 0);
  const out = Math.max(0, parts.out || 0);
  const total = inS + low + out;
  if (total === 0) {
    return `<div class="h-3 w-full rounded-full bg-[#1d2942]"></div>`;
  }
  const pInS = (inS / total) * 100;
  const pLow = (low / total) * 100;
  const pOut = (out / total) * 100;
  const seg = (w, color) => w > 0 ? `<div style="width:${w}%;background:${color}" class="h-full"></div>` : '';
  return `<div class="h-3 w-full rounded-full overflow-hidden flex bg-[#1d2942] border border-[#243352]">
    ${seg(pInS, '#34d399')}${seg(pLow, '#fbbf24')}${seg(pOut, '#f87171')}
  </div>`;
}

/* ---- Toast utility ---------------------------------------- */
function showToast(message, type) {
  let stack = document.getElementById('iq-toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'iq-toast-stack';
    document.body.appendChild(stack);
  }
  const kind = type || 'info';
  const icon = kind === 'ok' ? 'check_circle' : kind === 'err' ? 'error' : 'info';
  const el = document.createElement('div');
  el.className = `iq-toast ${kind}`;
  el.innerHTML = `<span class="material-symbols-outlined">${icon}</span><span>${String(message)}</span>`;
  stack.appendChild(el);
  const ttl = kind === 'err' ? 4200 : 2600;
  setTimeout(() => {
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 220);
  }, ttl);
}
