import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import '@fontsource/ibm-plex-mono/latin-600.css';
import '@fontsource/eb-garamond/latin-400.css';
import '@fontsource/eb-garamond/latin-500.css';
import '@fontsource/cormorant-garamond/latin-400.css';
import '@fontsource/cormorant-garamond/latin-500.css';
import '@fontsource/cormorant-garamond/latin-600.css';
import { api, calendarAxis, directory, directories, filename, gapSummary, inRanges, label, missingLines, number, percent, states } from './data';
import { drawShare, Lanes, Treemap, Weekly } from './charts';
import './style.css';

function Empty({ title, children }) { return <p className="empty-line"><strong>{title}.</strong> {children}</p>; }
function Chip({ state, tested = true }) { return <span className={`state-chip state-${state} ${!tested ? 'untested' : ''}`}>{label(state)}</span>; }
function FileName({ path }) { return <span className="file-name"><strong>{filename(path)}</strong><span>{directory(path)}</span></span>; }
function startReview(file) { window.location.hash = `review?set_id=${encodeURIComponent(file.review.available[0].set_id)}`; }
function ReviewAction({ file, inspect }) {
  return <button onClick={() => file.review.available.length ? startReview(file) : inspect(file)}
    title={file.review.available.length ? 'Answer this file’s quiz.' : 'Open this file.'}>
    {file.review.available.length ? 'Review' : 'Inspect'}</button>;
}

function Risk({ data, inspect }) {
  const [filter, setFilter] = useState('flagged'), [dir, setDir] = useState('all');
  const files = data.files.filter(f => (filter === 'all' || filter === 'wrong' && f.review.confidently_wrong || filter === 'flagged' && f.flagged) && (dir === 'all' || directory(f.path) === dir));
  const showMissing = files.some(f => missingLines(f) !== null);
  const showCommits = files.some(f => Number.isFinite(f.commits_90d));
  return <main className="risk-page">
    <div className="page-heading"><span className="eyebrow">Review queue</span><h1>Files with gaps</h1><p>Ranked by unseen lines and recent commits. Passing a quiz lowers a file's rank.</p></div>
    <div className="filters mono">
      {[['flagged', 'Flagged files'], ['all', 'All files'], ['wrong', 'Confidently wrong']].map(([key, name]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{name}</button>)}
      <label className="select-label">Directory<select value={dir} onChange={e => setDir(e.target.value)}><option value="all">All directories</option>{directories(data.files).map(d => <option key={d.name}>{d.name}</option>)}</select></label>
      <span className="dim filter-note">Commit window: 90 days</span>
    </div>
    {!data.has_observations && <Empty title="No recording yet">Start recording in Blindspot for VS Code.</Empty>}
    {!data.files.length && <Empty title="No files to show">Open a Git project in VS Code.</Empty>}
    {data.files.length > 0 && !files.length && <Empty title="Nothing currently flagged">Choose All files to browse the project.</Empty>}
    {files.length > 0 && <div className="table-scroll"><table className="risk-table mono"><thead><tr><th aria-label="Rank">#</th><th>File</th><th>Seen</th>{showMissing && <th title="Lines never on screen">Missing lines</th>}{showCommits && <th title="Commits touching this file in the last 90 days">Commits</th>}<th>Quiz sample</th><th aria-label="Action"></th></tr></thead>
      <tbody>{files.map(f => <tr key={f.path} className={f === files[0] ? 'first-row' : ''}>
        <td className="dim" title="Unseen lines and recent commits set the rank; passing a quiz lowers it.">{f.rank}</td><td><button className="file-link" onClick={() => inspect(f)}><FileName path={f.path} /></button></td>
        <td><Chip state={f.state} tested={f.review.tested} /></td>{showMissing && <td className="numeric missing-lines">{missingLines(f) === null ? 'Unknown' : <>{number(missingLines(f))}<i className="gap-bar" style={{ '--w': `${Math.min(100, 100 * missingLines(f) / (f.line_count || 1))}%` }} /></>}</td>}
        {showCommits && <td className="numeric">{Number.isFinite(f.commits_90d) ? number(f.commits_90d) : 'Unknown'}</td>}
        <td>{f.review.confidently_wrong ? <span className="attention-text">Confidently wrong</span> : f.review.passing_samples ? <Chip state="sample_passed" /> : <span className="dim">{f.review.tested ? 'Tested' : f.review.stale_results ? 'Changed since quiz' : 'Never tested'}</span>}</td>
        <td><ReviewAction file={f} inspect={inspect} /></td>
      </tr>)}</tbody></table></div>}
    {files.length > 0 && <p className="footnote">Hatched means never tested.</p>}
  </main>;
}

function MapView({ data, inspect }) {
  const gap = gapSummary(data);
  return <main className="map-layout"><aside className="map-sidebar"><div className="rollup"><span className="eyebrow">Seen</span>
    <div className={`headline mono ${!gap.known || !gap.gap ? 'headline-words' : ''}`}>{gap.headline}</div>
    <p className="mono dim">{gap.detail}</p>
    {gap.known && <><p className="mono dim">{gap.context}</p><p className="mono dim">{gap.percentage}</p></>}
    {data.totals.uncertain_files > 0 && <p className="mono dim">{number(data.totals.uncertain_files)} files unknown · reconnect the extension</p>}</div>
    {data.files.length > 0 && <div className="rollup"><span className="eyebrow">By directory · gaps first</span>{directories(data.files).map(d => <button className="directory-row" key={d.name} onClick={() => inspect(data.files.find(f => directory(f.path) === d.name))} title="Lines seen in this directory">
      <span>{d.name}</span><span>{data.has_observations && d.lines ? `${percent(d.reported, d.lines)}% seen` : 'Unknown'}</span>{data.has_observations && d.lines > 0 && <progress max={d.lines} value={d.reported} />}<small>{number(d.files)} files · {number(d.lines)} lines{d.uncertain ? ` · ${d.uncertain} unknown` : ''}</small>
    </button>)}</div>}
    <div className="rollup legend"><span className="eyebrow">States</span>{states.map(s => <div key={s.id} title={s.description}><span className={`swatch state-${s.id}`} /><span>{s.label}</span></div>)}<p className="mono dim">Hatched = never tested</p></div></aside>
    <section className="map-main"><div className="map-toolbar mono"><span>Grouped by directory</span><span>Size: lines</span></div>
      {data.files.length ? <><Treemap files={data.files} onSelect={inspect} /><details className="file-index"><summary>File index · {number(data.files.length)} files</summary><div>{data.files.map(f => <button key={f.path} onClick={() => inspect(f)}>{f.path}</button>)}</div></details></> : <Empty title="No files to map">Open a Git project in VS Code.</Empty>}
    </section></main>;
}

function Source({ text, file, start = 1, review = false }) {
  const lines = text.split('\n');
  if (review && lines.at(-1) === '') lines.pop();
  return <div className={`source-well ${review ? 'review-source' : ''}`}><pre>{lines.map((line, i) => {
    const n = start + i;
    const state = file ? file.current_uncertain ? 'uncertain' : inRanges(n, file.dwell_ranges) ? 'reported' : inRanges(n, file.brief_ranges) ? 'brief' : 'no_evidence' : null;
    const tested = file && inRanges(n, file.review.tested_ranges);
    return <span key={n} className={`source-line ${state ? `state-${state} ${tested ? '' : 'untested'}` : ''}`} title={state ? `${label(state)} · ${tested ? 'Tested' : 'Never tested'}` : undefined}><span className="line-number">{n}</span><code>{line || ' '}</code></span>;
  })}</pre></div>;
}

function FileDetail({ file, data, close }) {
  const ref = useRef(null), [source, setSource] = useState(null), [error, setError] = useState('');
  useEffect(() => { ref.current.showModal(); }, []);
  useEffect(() => {
    let cancelled = false; setSource(null); setError('');
    api(`/api/dashboard/source?${new URLSearchParams({ path: file.path, hash: file.content_hash })}`).then(s => { if (!cancelled) setSource(s); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [file.path, file.content_hash, file.current_uncertain]);
  const editor = `vscode://file${encodeURI(`${data.workspace}/${file.path}`).replaceAll('#', '%23').replaceAll('?', '%3F')}`;
  const current = source?.content_hash === file.content_hash && !file.current_uncertain;
  return <dialog ref={ref} className="detail-panel" onCancel={close} onClick={e => { if (e.target === ref.current && e.clientX < ref.current.getBoundingClientRect().left) close(); }} aria-labelledby="detail-title">
    <div className="detail-top"><h2 id="detail-title" className="mono">{file.path}</h2><button onClick={close} aria-label="Close file detail">×</button></div>
    <div className="detail-meta mono dim">{number(file.line_count)} lines · {file.origin}</div><div className="detail-state"><Chip state={file.state} tested={file.review.tested} />{file.review.passing_samples > 0 && <Chip state="sample_passed" />}</div>
    <section className="record"><h3>This file</h3><ul>{file.evidence.map((e, i) => <li key={i}><span className={`evidence-dot state-${e.state}`} /><div><p className="mono">{e.text}</p></div></li>)}</ul>
      </section>
    <section className="detail-source"><h3>The source</h3>{error ? <p className="notice">{error}</p> : current ? <Source text={source.text} file={file} /> : <p className="dim">Loading file.</p>}</section>
    <div className="detail-actions"><button disabled={!file.review.available.length || !current} onClick={() => startReview(file)}>Review this file</button><a href={editor}>Open in editor</a></div>
    {!file.review.available.length && <p className="footnote">No quiz ready for this file. Choose another file in Risk.</p>}
    <Methodology />
  </dialog>;
}

function Timeline({ data, inspect }) {
  const axis = calendarAxis(data.weekly, data.review.ticks);
  const hasWeekly = axis?.columns.some(w => w.files_touched > 0);
  const within = at => axis && +new Date(at) >= axis.start && +new Date(at) < axis.end;
  const hasLanes = data.timeline.some(e => within(e.observed_at) && data.files.some(f => f.path === e.payload.path) && ['visibility', 'interaction', 'file_event'].includes(e.kind)) || data.review.ticks.some(t => within(t.at) && data.files.some(f => f.path === t.path));
  return <main className="standard-page"><div className="page-heading"><span className="eyebrow">Activity</span><h1>Activity over time</h1><p>What the extension observed, by week.</p></div>
    {hasWeekly ? <section className="chart-panel"><h2>Files touched per week</h2><Weekly axis={axis} ticks={data.review.ticks} /></section> : <Empty title="No activity yet">Start recording in VS Code to see files touched per week.</Empty>}
    {hasLanes && <section className="chart-panel"><h2>Activity by file</h2><p className="mono">The last {number(data.timeline.length)} observed events, grouped by file.</p><Lanes files={data.files} events={data.timeline} ticks={data.review.ticks} onSelect={inspect} axis={axis} /></section>}
  </main>;
}

function Insights({ data }) {
  const review = data.review;
  const calibration = Object.entries(review.calibration).filter(([, c]) => c.answers > 0);
  return <main className="standard-page"><div className="page-heading"><span className="eyebrow">Quizzes</span><h1>What the quizzes found</h1><p>Quiz accuracy is measured against a generated answer key.</p></div>
    <section className="wrong-summary">{review.completed_attempts > 0 && <div className={`mono big-stat ${review.confidently_wrong_files ? 'flagged-stat' : ''}`}>{number(review.confidently_wrong_files)}</div>}<div><h2>Confidently wrong</h2>{review.completed_attempts ? <p>Files where you answered confidently and were wrong.</p> : <><p>No quizzes taken yet.</p><a className="button-link" href="#risk">Review a file</a></>}</div></section>
    {calibration.length > 0 && <section className="chart-panel calibration-panel"><h2>Confidence versus accuracy</h2><p>How often you were right, grouped by how sure you were.</p>
      {calibration.map(([confidence, c]) => <div className="calibration mono" key={confidence}><div><span>{confidence}</span><span>{number(c.correct)} / {number(c.answers)} answers correct</span></div><progress max={c.answers} value={c.correct} /><span>{percent(c.correct, c.answers)}% correct</span></div>)}
    </section>}
  </main>;
}

function Share({ data }) {
  const canvas = useRef(null), [error, setError] = useState(''), [ready, setReady] = useState(false);
  useEffect(() => { if (!data.files.length) return; let cancelled = false; setReady(false); drawShare(canvas.current, data).then(() => { if (!cancelled) setReady(true); }).catch(e => setError(e.message)); return () => { cancelled = true; }; }, [data]);
  const download = () => canvas.current.toBlob(blob => { if (!blob) return setError('PNG could not be rendered.'); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'blindspot-local.png'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }, 'image/png');
  if (!data.files.length) return <main className="standard-page"><Empty title="No files to share">Open a Git project in VS Code.</Empty></main>;
  return <main className="standard-page"><div className="page-heading"><span className="eyebrow">Local export</span><h1>What you have and have not seen</h1><p>Lines ever on screen.</p></div><canvas className="share-canvas" ref={canvas} aria-label="Share card showing unseen lines and a file map" /><div className="share-actions"><button disabled={!ready} onClick={download}>Download PNG</button><span className="mono dim">1200 × 630</span></div>{error && <p role="alert">{error}</p>}</main>;
}

function Review({ params }) {
  const [attempt, setAttempt] = useState(null), [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [chosen, setChosen] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      let id = params.get('attempt_id');
      if (!id) {
        const started = await api('/api/dashboard/review/start', { set_id: params.get('set_id') });
        id = started.attempt_id;
        if (cancelled) return;
        window.history.replaceState(null, '', `#review?attempt_id=${encodeURIComponent(id)}`);
        if (started.completed) { setResult(await api(`/api/dashboard/review/results?attempt_id=${encodeURIComponent(id)}`)); return; }
      }
      try { const view = await api(`/api/dashboard/review/attempt?attempt_id=${encodeURIComponent(id)}`); if (!cancelled) setAttempt(view); }
      catch (e) {
        try { const results = await api(`/api/dashboard/review/results?attempt_id=${encodeURIComponent(id)}`); if (!cancelled) setResult(results); }
        catch { throw e; }
      }
    }
    load().catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);
  const index = attempt?.questions.findIndex(q => !q.submitted) ?? -1;
  const question = attempt?.questions[index];
  async function submit(confidence) {
    setBusy(true); setError('');
    try {
      await api('/api/dashboard/review/answer', { attempt_id: attempt.attempt_id, question_id: question.id, chosen_index: chosen, confidence });
      const view = await api(`/api/dashboard/review/attempt?attempt_id=${encodeURIComponent(attempt.attempt_id)}`); setAttempt(view); setChosen(null);
      if (view.questions.every(q => q.submitted)) setResult(await api('/api/dashboard/review/complete', { attempt_id: view.attempt_id }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function finish() {
    setBusy(true); try { setResult(await api('/api/dashboard/review/complete', { attempt_id: attempt.attempt_id })); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  // This screen never mounts the dashboard shell, state chips, queue or scores.
  return <div className="review-screen"><header className="review-header"><a href="#risk">← Exit review</a>{attempt && <span className="mono">{attempt.target.path}</span>}{question && <div className="review-progress mono"><span>Question {index + 1} of {attempt.questions.length}</span><span className="progress-dots" aria-hidden="true">{attempt.questions.map((q, i) => <i key={q.id} className={i === index ? 'current' : q.submitted ? 'submitted' : ''} />)}</span></div>}</header>
    {error && <p role="alert" className="notice">{error}</p>}
    {result ? <main className="review-results"><span className="eyebrow">Completed sample</span><h1>Quiz results</h1><p className="mono">{result.questions.filter(q => q.correct).length} / {result.questions.length} answers correct</p><p>{result.current_sample_pass ? 'Quiz passed. Return to Risk to see the updated rank.' : 'Review the explanations, then choose another file.'}</p>
      {result.questions.map((q, i) => <section key={q.question_id} className={`answer-record ${q.correct ? 'matches' : 'differs'}`}><span className="eyebrow">Question {i + 1} · {q.confidence} · {q.correct ? 'Matches key' : 'Does not match key'}</span><h2>{q.prompt}</h2><p>Your answer: {q.options[q.chosen_index]}</p><p>Answer key: {q.options[q.correct_index]}</p><p>{q.explanation}</p><p className="mono dim">{q.rationale.path}:{q.rationale.start_line}–{q.rationale.end_line}</p><p>{q.rationale.reason}</p></section>)}<a className="button-link" href="#risk">Return to review queue</a></main>
      : attempt ? <main className="review-layout"><section className="review-code"><div className="source-caption mono">{attempt.target.path} · lines {attempt.target.start_line}–{attempt.target.end_line}</div><Source text={attempt.target.code} start={attempt.target.start_line} review />{attempt.context.map(c => <details key={`${c.path}:${c.start_line}`}><summary className="mono">Context · {c.path}:{c.start_line}–{c.end_line}</summary><Source text={c.code} start={c.start_line} review /></details>)}</section>
        <section className="question-panel">{question ? <><span className="eyebrow">Question</span><h1>{question.prompt}</h1><div className="options">{question.options.map((option, i) => <button key={i} aria-pressed={chosen === i} onClick={() => setChosen(i)} disabled={busy}><span className="option-letter">{String.fromCharCode(65 + i)}</span><span>{option}</span></button>)}</div><div className="confidence"><span className="eyebrow">How sure are you</span><div>{['guessed', 'shaky', 'solid'].map(c => <button key={c} disabled={chosen === null || busy} onClick={() => submit(c)}>{c[0].toUpperCase() + c.slice(1)}</button>)}</div><p>Choose your confidence to submit the answer.</p></div></> : <><h1>Answers recorded</h1><button disabled={busy} onClick={finish}>Finish review</button></>}</section></main> : !error && <Empty title="Loading review">Only source and questions are shown while answering.</Empty>}
  </div>;
}

function DashboardApp({ page }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [selected, setSelected] = useState(null), [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true); try { const next = await api('/api/dashboard'); setData(next); setError(''); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => { refresh(); const timer = setInterval(() => { if (!document.hidden) refresh(); }, 10000); return () => clearInterval(timer); }, []);
  const file = data?.files.find(f => f.path === selected);
  const inspect = f => setSelected(f.path);
  return <><header className="app-header"><a href="#risk" className="brand"><span className="brand-mark" />blindspot</a><nav aria-label="Dashboard views">{['Risk', 'Map', 'Timeline', 'Insights', 'Share'].map(name => <a key={name} href={`#${name.toLowerCase()}`} aria-current={page === name.toLowerCase() ? 'page' : undefined}>{name}</a>)}</nav>
    <div className="header-context mono">{data && <><span>{data.workspace.split('/').at(-1)} · {data.git.branch || 'Git unavailable'}</span><span className="session-count" title="Recording sessions">{number(data.health.sessions.length)} sessions</span></>}<button disabled={busy} onClick={refresh}>{busy ? 'Refreshing' : 'Refresh'}</button></div></header>
    {error && <p className="notice" role="alert">{error}</p>}
    {!data ? <Empty title={error ? 'Receiver unavailable' : 'Loading files'}>Start the local server, then refresh.</Empty> : <>
      <div className="connection-strip mono" title="Extension connection"><span>{data.health.sessions.some(s => s.connection_state === 'connected' && s.status === 'recording') ? 'Recording connected' : 'No active recording'}</span><span>Updated {new Date(data.generated_at).toLocaleTimeString()}</span><span>Local only</span></div>
      {data.review.error && <p className="notice">Cannot load quizzes. Check the quiz folder and refresh.</p>}
      {page === 'map' ? <MapView data={data} inspect={inspect} /> : page === 'timeline' ? <Timeline data={data} inspect={inspect} /> : page === 'insights' ? <Insights data={data} /> : page === 'share' ? <Share data={data} /> : <Risk data={data} inspect={inspect} />}
      {data.inventory_diagnostics.length > 0 && <p className="notice">Some files could not be loaded. Check the project folder and refresh.</p>}
      {file && <FileDetail key={file.path} file={file} data={data} close={() => setSelected(null)} />}
    </>}
  </>;
}

function Methodology() {
  const [open, setOpen] = useState(false);
  return <footer className="app-footer"><button className="methodology-link" onClick={() => setOpen(true)}>How this is measured</button>{open && <MethodologyPanel close={() => setOpen(false)} />}</footer>;
}

function MethodologyPanel({ close }) {
  const ref = useRef(null);
  useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} className="methodology-panel" aria-labelledby="methodology-title" onCancel={close}>
    <div className="detail-top"><h2 id="methodology-title">How this is measured</h2><button onClick={close} aria-label="Close methodology">×</button></div>
    <p>The extension samples visible line ranges in focused VS Code windows. Split panes count; background tabs do not.</p>
    <p>“Seen” means a line appeared on screen during a recording. “Never seen” means it has no matching on-screen activity. Earlier activity is unknown. A line being on screen does not establish that it was read or understood.</p>
    <p>Changed lines lose their seen status; unchanged lines can carry it forward. Unknown files are left out of line totals until their contents can be checked.</p>
    <p>Glimpsed means less than a second on screen. Weekly activity counts each file once across visible ranges, editor interactions and file changes. Weeks start on Monday in UTC.</p>
    <p>Quiz accuracy is agreement with a generated answer key, which may be wrong. Results cover the tested passage. Confidence totals include completed attempts and practice. Changed files need a new test; hatching marks passages without a matching test.</p>
    <p>On-screen activity is visible only in this editor while recording. Filesystem changes can come from other tools.</p>
    <p>Everything stays on this machine. Nothing is transmitted outside it.</p>
  </dialog>;
}

function Router() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => { const change = () => setHash(window.location.hash); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const [page, query = ''] = hash.replace(/^#/, '').split('?');
  return <>{page === 'review' ? <Review key={hash} params={new URLSearchParams(query)} /> : <DashboardApp page={page || 'risk'} />}<Methodology /></>;
}

createRoot(document.getElementById('root')).render(<Router />);
