import React, { useEffect, useRef, useState } from 'react';
import { gapSummary, filename, layout, number, states, label } from './data';

export function Treemap({ files, onSelect }) {
  const ref = useRef(null);
  const [size, setSize] = useState([900, 600]);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setSize([Math.max(1, entry.contentRect.width), Math.max(1, entry.contentRect.height)]));
    observer.observe(ref.current); return () => observer.disconnect();
  }, []);
  const root = layout(files, ...size);
  return <div className="treemap" ref={ref} aria-label="Files grouped by directory; area is line count">
    {root.descendants().filter(n => n.children && n.depth > 0).map(n => <span className="directory-label" key={n.ancestors().map(x => x.data.name).join('/')}
      style={{ left: n.x0, top: n.y0, width: n.x1 - n.x0, height: 22 }}>{n.data.name}/</span>)}
    {root.leaves().filter(n => n.data.file).map(n => {
      const f = n.data.file, width = n.x1 - n.x0, height = n.y1 - n.y0;
      // Small cells keep exact area. The file index below supplies 44px controls.
      const roomy = width >= 44 && height >= 44;
      const props = { className: `map-cell state-${f.state} ${!f.review.tested ? 'untested' : ''}`,
        style: { left: n.x0, top: n.y0, width, height },
        title: `${f.path} · ${number(f.line_count)} lines · ${label(f.state)} · ${f.review.tested ? 'Tested' : 'Never tested'}` };
      const content = width > 75 && height > 55 ? <><strong>{filename(f.path)}</strong><span>{label(f.state)}</span><small>{number(f.line_count)} lines</small></> : null;
      return roomy ? <button {...props} key={f.path} onClick={() => onSelect(f)} aria-label={`Inspect ${f.path}`}>{content}</button>
        : <span {...props} key={f.path} aria-hidden="true" />;
    })}
  </div>;
}

export function Weekly({ axis, ticks }) {
  if (!axis || !axis.columns.some(w => w.files_touched > 0)) return null;
  const shown = axis.columns;
  const max = Math.max(...shown.map(w => w.files_touched || 0));
  const step = 42, width = shown.length * step, height = 190, plotHeight = 145;
  return <><div className="chart-legend mono"><span className="event-key visibility">Files touched</span><span>│ Quiz completed</span></div>
    <div className="weekly-plot"><svg className="weekly-chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Files touched per week">
      <line x1="0" x2={width} y1={plotHeight} y2={plotHeight} className="axis" />
      {shown.map((w, i) => {
        const h = (w.files_touched || 0) / max * (plotHeight - 12);
        return <g key={w.week}>
          {w.files_touched > 0 && <rect className="event-fill visibility weekly-bar" x={i * step} y={plotHeight - h} width="36" height={h}><title>{`${w.week}: ${number(w.files_touched)} files · ${number(w.event_count)} events`}</title></rect>}
          {(i % 2 === 0 || shown.length === 1) && <text x={i * step} y="175">{w.week.slice(5)}</text>}
        </g>;
      })}
      {ticks.filter(t => +new Date(t.at) >= axis.start && +new Date(t.at) < axis.end).map(t => {
        const x = (+new Date(t.at) - axis.start) / (axis.end - axis.start) * width;
        return <line key={t.attempt_id} x1={x} x2={x} y1="0" y2={plotHeight} className="review-tick"><title>Quiz completed · {t.at}</title></line>;
      })}
    </svg></div><p className="mono dim">Busiest week: {number(max)} {max === 1 ? 'file' : 'files'}.</p></>;
}

export function Lanes({ files, events, ticks, onSelect, axis }) {
  if (!axis) return null;
  const { start, end } = axis, span = end - start;
  const within = date => +new Date(date) >= start && +new Date(date) < end;
  const relevant = events.filter(e => e.payload.path && ['visibility', 'interaction', 'file_event'].includes(e.kind) && within(e.observed_at));
  ticks = ticks.filter(t => within(t.at));
  if (!files.some(f => relevant.some(e => e.payload.path === f.path) || ticks.some(t => t.path === f.path))) return null;
  const width = axis.columns.length * 42;
  return <div className="lanes" style={{ '--timeline-width': `${width}px` }}><div className="lane-dates mono dim"><span>{new Date(start).toISOString().slice(0, 10)}</span><span>— {new Date(end).toISOString().slice(0, 10)} UTC</span></div>
    {files.filter(f => relevant.some(e => e.payload.path === f.path) || ticks.some(t => t.path === f.path)).map(f => <div className="lane" key={f.path}>
      <button className="lane-name" onClick={() => onSelect(f)}>{f.path}</button>
      <svg width={width} height="44" viewBox={`0 0 ${width} 44`} role="img" aria-label={`Recent activity for ${f.path}`}>
        <line x1="0" x2={width} y1="22" y2="22" className="axis" />
        {relevant.filter(e => e.payload.path === f.path).map(e => <line key={`${e.session_id}:${e.sequence}`} x1={(+new Date(e.observed_at) - start) / span * width}
          x2={(+new Date(e.observed_at) - start) / span * width} y1="13" y2="31" className={`event-stroke ${e.kind}`}><title>{`${e.kind} · ${e.observed_at} · ${e.session_id}:${e.sequence}`}</title></line>)}
        {ticks.filter(t => t.path === f.path).map(t => <circle key={t.attempt_id} cx={(+new Date(t.at) - start) / span * width} cy="22" r="4" className="review-dot"><title>Completed review · {t.at}</title></circle>)}
      </svg>
    </div>)}
  </div>;
}

export async function drawShare(canvas, data) {
  await Promise.all([document.fonts.load('400 108px "IBM Plex Mono"'), document.fonts.load('400 26px "EB Garamond"'), document.fonts.load('400 66px "Cormorant Garamond"')]);
  await document.fonts.ready;
  const css = getComputedStyle(document.documentElement);
  const color = token => css.getPropertyValue(`--${token}`).trim();
  const ctx = canvas.getContext('2d'); canvas.width = 1200; canvas.height = 630;
  ctx.fillStyle = color('ground'); ctx.fillRect(0, 0, 1200, 630);
  const text = (value, x, y, size, family = 'IBM Plex Mono', token = 'text') => {
    ctx.font = `${size}px "${family}"`; ctx.fillStyle = color(token); ctx.fillText(value, x, y);
  };
  text('blindspot', 40, 48, 28, 'Cormorant Garamond'); text(data.workspace.split('/').at(-1), 760, 48, 14, 'IBM Plex Mono', 'text-dim');
  ctx.strokeStyle = color('border'); ctx.beginPath(); ctx.moveTo(40, 75); ctx.lineTo(1160, 75); ctx.stroke();
  const gap = gapSummary(data);
  text('Seen', 40, 155, 26, 'EB Garamond');
  text(gap.headline, 36, 275, gap.known && gap.gap ? 84 : 44, 'Cormorant Garamond');
  text(gap.detail, 40, 337, 17, 'IBM Plex Mono', 'text-dim');
  if (gap.context) text(gap.context, 40, 385, 13);
  if (gap.percentage) text(gap.percentage, 40, 416, 14, 'IBM Plex Mono', 'text-dim');
  if (data.totals.uncertain_files > 0) text(`${number(data.totals.uncertain_files)} files unknown`, 40, 447, 14, 'IBM Plex Mono', 'text-dim');
  const root = layout(data.files, 560, 350);
  for (const n of root.leaves().filter(n => n.data.file)) {
    const f = n.data.file, x = 600 + n.x0, y = 114 + n.y0, w = n.x1 - n.x0, h = n.y1 - n.y0;
    ctx.fillStyle = color(`state-${f.state}`); ctx.fillRect(x, y, w, h);
    if (!f.review.tested) {
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); ctx.globalAlpha = 0.08; ctx.strokeStyle = color('hatch');
      for (let d = -h; d < w + h; d += 8) { ctx.beginPath(); ctx.moveTo(x + d, y); ctx.lineTo(x + d + h, y + h); ctx.stroke(); }
      ctx.restore();
    }
  }
  let x = 40;
  for (const state of states) {
    ctx.fillStyle = color(`state-${state.id}`); ctx.fillRect(x, 506, 10, 10);
    text(state.label, x + 17, 516, 12, 'IBM Plex Mono', 'text-dim'); x += state.label.length * 7.2 + 35;
  }

  text('Area = lines · Hatched = never tested', 40, 598, 13, 'IBM Plex Mono', 'text-label');
}
