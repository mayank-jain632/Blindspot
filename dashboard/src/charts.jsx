import React, { useEffect, useLayoutEffect, useId, useRef, useState } from 'react';
import { coverageColor, coverageStyle, gapSummary, filename, layout, number, label } from './data';

export function Treemap({ files, onSelect }) {
  const ref = useRef(null);
  const [size, setSize] = useState([900, 600]);
  // Measure before the first paint so a narrow window never renders the 900px default.
  useLayoutEffect(() => { const box = ref.current.getBoundingClientRect(); setSize([Math.max(1, box.width), Math.max(1, box.height)]); }, []);
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
        style: { ...coverageStyle(f.reported_lines, f.line_count, f.current_uncertain), left: n.x0, top: n.y0, width, height },
        title: `${f.path} · ${number(f.line_count)} lines · ${label(f.state)} · ${f.review.tested ? 'Tested' : 'Never tested'}` };
      const content = width > 75 && height > 55 ? <><strong>{filename(f.path)}</strong><span>{label(f.state)}</span><small>{number(f.line_count)} lines</small></> : null;
      return roomy ? <button {...props} key={f.path} onClick={() => onSelect(f)} aria-label={`Inspect ${f.path}`}>{content}</button>
        : <span {...props} key={f.path} aria-hidden="true" />;
    })}
  </div>;
}

export function Weekly({ axis, ticks }) {
  const clip = useId().replaceAll(':', '');
  if (!axis || !axis.columns.some(w => w.files_touched > 0)) return null;
  const shown = axis.columns;
  const split = shown.some(w => Number.isFinite(w.files_on_screen));
  const series = split ? [{key:'files_on_screen', name:'Files on screen', type:'screen'}, {key:'files_changed', name:'Files changed', type:'changes'}] : [{key:'files_touched',name:'Files touched',type:'screen'}];
  const max = Math.max(1, ...shown.flatMap(w => series.map(s => w[s.key] || 0)));
  const width = Math.max(600, shown.length * 56), height = 240, left = 36, bottom = 190;
  const x = i => left + (shown.length === 1 ? (width - left - 20) / 2 : i / (shown.length - 1) * (width - left - 20));
  const y = count => bottom - count / max * 160;
  return <><div className="chart-legend mono">{series.map(s => <span key={s.key} className={`line-key ${s.type}`}>{s.name}</span>)}<span>│ Quiz completed</span></div>
    <div className="weekly-plot"><svg className="activity-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Weekly files on screen and files changed">
      <defs><clipPath id={clip}><rect className="chart-reveal" width={width} height={height} /></clipPath></defs>
      {[0, max].map(n => <g key={n}><line x1={left} x2={width} y1={y(n)} y2={y(n)} className="axis" /><text x="0" y={y(n)+4}>{n}</text></g>)}
      {shown.map((w,i) => (i % Math.max(1, Math.ceil(shown.length / 8)) === 0 || i === shown.length - 1) && <text key={w.week} x={x(i)} y="218" textAnchor="middle">{w.week.slice(5)}</text>)}
      <g clipPath={`url(#${clip})`}>{series.map(s => <g key={s.key} className={`activity-series ${s.type}`}>
        <path d={shown.map((w,i) => `${i ? 'L' : 'M'}${x(i)},${y(w[s.key] || 0)}`).join(' ')} />
        {shown.map((w,i) => <circle key={w.week} cx={x(i)} cy={y(w[s.key] || 0)} r="4"><title>{`${w.week}: ${w[s.key] || 0} ${s.name.toLowerCase()} · ${w.event_count || 0} events`}</title></circle>)}
      </g>)}{ticks.filter(t => +new Date(t.at) >= axis.start && +new Date(t.at) < axis.end).map(t => {
        const pos = left + (+new Date(t.at) - axis.start) / (axis.end - axis.start) * (width - left - 20);
        return <line key={t.attempt_id} x1={pos} x2={pos} y1="20" y2={bottom} className="review-tick"><title>Quiz completed · {t.at}</title></line>;
      })}</g>
    </svg></div><p className="mono dim">Counts are distinct files per week.</p></>;
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
          x2={(+new Date(e.observed_at) - start) / span * width} y1={e.kind === 'visibility' ? 17 : e.kind === 'interaction' ? 13 : 9} y2={e.kind === 'visibility' ? 27 : e.kind === 'interaction' ? 31 : 35} className={`event-stroke ${e.kind}`} strokeDasharray={e.kind === 'file_event' ? '2 2' : undefined}><title>{`${{ visibility: 'On screen', interaction: 'Editor interaction', file_event: 'File changed' }[e.kind]} · ${e.observed_at}`}</title></line>)}
        {ticks.filter(t => t.path === f.path).map(t => <circle key={t.attempt_id} cx={(+new Date(t.at) - start) / span * width} cy="22" r="4" className="review-dot"><title>Completed review · {t.at}</title></circle>)}
      </svg>
    </div>)}
  </div>;
}

export async function drawShare(canvas, data) {
  await Promise.all([document.fonts.load('400 108px "IBM Plex Mono"'), document.fonts.load('400 26px "EB Garamond"'), document.fonts.load('400 84px "EB Garamond"'), document.fonts.load('400 28px "Cormorant Garamond"')]);
  await document.fonts.ready;
  const css = getComputedStyle(document.documentElement);
  const color = token => css.getPropertyValue(`--${token}`).trim();
  const palette = { red: color('coverage-red'), yellow: color('coverage-yellow'), blue: color('coverage-blue'), unknown: color('state-uncertain') };
  const ctx = canvas.getContext('2d'); canvas.width = 1200; canvas.height = 630;
  ctx.fillStyle = color('ground'); ctx.fillRect(0, 0, 1200, 630);
  const sun = ctx.createRadialGradient(24, 38, 0, 24, 38, 15); sun.addColorStop(0, '#000'); sun.addColorStop(.3, '#000'); sun.addColorStop(.38, color('sun')); sun.addColorStop(.7, color('corona')); sun.addColorStop(1, 'rgba(255,138,43,0)'); ctx.fillStyle = sun; ctx.fillRect(0, 20, 50, 40);
  const text = (value, x, y, size, family = 'IBM Plex Mono', token = 'text') => {
    ctx.font = `${size}px "${family}"`; ctx.fillStyle = color(token); ctx.fillText(value, x, y);
  };
  text('blindspot', 56, 48, 28, 'Cormorant Garamond'); text(data.workspace.split('/').at(-1), 760, 48, 14, 'IBM Plex Mono', 'text-dim');
  ctx.strokeStyle = color('border'); ctx.beginPath(); ctx.moveTo(40, 75); ctx.lineTo(1160, 75); ctx.stroke();
  const gap = gapSummary(data);
  text('Not seen', 40, 155, 26, 'EB Garamond');
  ctx.save(); ctx.shadowColor = 'rgba(255,138,43,.6)'; ctx.shadowBlur = 0; text(gap.headline, 40, 275, gap.known ? 84 : 44, 'IBM Plex Mono', 'text'); ctx.restore();
  text(gap.known ? `${number(gap.gap)} of ${number(data.totals.line_count)} lines not seen` : gap.detail, 40, 337, 17, 'IBM Plex Mono', 'text-dim');
  if (gap.known) text(`${number(data.files.length)} files tracked`, 40, 385, 13);
  if (data.totals.uncertain_files > 0) text(`${number(data.totals.uncertain_files)} files unknown`, 40, 447, 14, 'IBM Plex Mono', 'text-dim');
  const root = layout(data.files, 560, 350);
  for (const n of root.leaves().filter(n => n.data.file)) {
    const f = n.data.file, x = 600 + n.x0, y = 114 + n.y0, w = n.x1 - n.x0, h = n.y1 - n.y0;
    ctx.fillStyle = coverageColor(f.reported_lines, f.line_count, palette, f.current_uncertain); ctx.fillRect(x, y, w, h);
    if (!f.review.tested) {
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); ctx.globalAlpha = 0.08; ctx.strokeStyle = color('hatch');
      for (let d = -h; d < w + h; d += 8) { ctx.beginPath(); ctx.moveTo(x + d, y); ctx.lineTo(x + d + h, y + h); ctx.stroke(); }
      ctx.restore();
    }
  }
  let x = 40;
  for (const [seen, label] of [[0, '0% seen'], [0.5, '50% seen'], [0.999, 'Below 100%'], [1, '100% seen'], [null, 'Unknown']]) {
    ctx.fillStyle = coverageColor(seen, 1, palette); ctx.fillRect(x, 506, 10, 10);
    text(label, x + 17, 516, 12, 'IBM Plex Mono', 'text-dim'); x += label.length * 7.2 + 35;
  }

  text('Area = lines · Hatched = never tested', 40, 598, 13, 'IBM Plex Mono', 'text-label');
}
