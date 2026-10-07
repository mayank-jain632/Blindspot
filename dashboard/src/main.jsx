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
import { api, coverageRatio, coverageStyle, explainApi, directory, directories, filename, gapSummary, guideItems, guideMarkdown, GUIDE_STATES, inRanges, label, lineSpan, quizForUnit, missingLines, number, percent, rangeText } from './data';
import { drawShare, Treemap } from './charts';
import './style.css';

function Empty({ title, children }) { return <p className="empty-line"><strong>{title}.</strong> {children}</p>; }
function Chip({ state, tested = true, seen, total, uncertain = false }) {
  const ratio = coverageRatio(seen, total, uncertain);
  return <span style={seen === undefined ? undefined : coverageStyle(seen, total, uncertain)} title={ratio === null ? undefined : `${number(seen)} of ${number(total)} lines have been on screen.`} className={`state-chip state-${state} ${!tested ? 'untested' : ''}`}>{label(state)}{ratio !== null && ` · ${Math.floor(ratio * 1000) / 10}%`}</span>;
}
function UnitSource({ lines, item, file }) {
  let remaining = CODE_CAP;
  const spans = (item.ranges || [[item.start, item.end]]).flatMap(([a, b]) => {
    if (remaining <= 0) return [];
    const end = Math.min(b, a + remaining - 1); remaining -= end - a + 1;
    return [[a, end]];
  });
  return <>{spans.map(([a, b]) => <React.Fragment key={a}><p className="mono dim">Lines {a}–{b}</p><Source text={lines.slice(a - 1, b).join('\n')} file={file} start={a} trimTerminal={false} /></React.Fragment>)}{item.lines > CODE_CAP && <p className="mono dim">Showing the first {CODE_CAP} lines of this section. Open the file for the rest.</p>}</>;
}
function ChangedBadge({ file }) { return file.changed_unseen_lines > 0 ? <span className="changed-badge mono">{number(file.changed_unseen_lines)} changed {file.changed_unseen_lines === 1 ? 'line' : 'lines'} unseen</span> : null; }
function FileName({ path }) { return <span className="file-name"><strong>{filename(path)}</strong><span>{directory(path)}</span></span>; }
function startReview(file) { window.location.hash = `review?set_id=${encodeURIComponent(file.review.available[0].set_id)}&path=${encodeURIComponent(file.path)}`; }

function Risk({ data, inspect }) {
  const [filter, setFilter] = useState(() => new URLSearchParams(window.location.hash.split('?')[1]).get('filter') === 'wrong' ? 'wrong' : 'flagged'), [dir, setDir] = useState('all');
  const files = data.files.filter(f => (filter === 'all' || filter === 'wrong' && f.review.confidently_wrong || filter === 'flagged' && f.flagged) && (dir === 'all' || directory(f.path) === dir));
  const showMissing = files.some(f => missingLines(f) !== null);
  const showCommits = files.some(f => Number.isFinite(f.commits_90d));
  return <main className="risk-page">
    <div className="page-heading"><span className="eyebrow">Review queue</span><h1>Files with gaps</h1><p>Ranked by unseen lines and recent commits.</p></div>
    <div className="filters mono">
      {[['flagged', 'Files with gaps'], ['all', 'All files'], ...(data.review.confidently_wrong_files ? [['wrong', `Confidently wrong · ${data.review.confidently_wrong_files}`]] : [])].map(([key, name]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{name}</button>)}
      <label className="select-label">Directory<select value={dir} onChange={e => setDir(e.target.value)}><option value="all">All directories</option>{directories(data.files).map(d => <option key={d.name}>{d.name}</option>)}</select></label>
    </div>
    {!data.has_observations && <Empty title="No display recorded">Start recording in Blindspot for VS Code.</Empty>}
    {!data.files.length && <Empty title="No files to show">Open a Git project in VS Code.</Empty>}
    {data.files.length > 0 && !files.length && <Empty title="Nothing currently flagged">Choose All files to browse the project.</Empty>}
    {files.length > 0 && <div className="table-scroll"><table className="risk-table mono"><thead><tr><th aria-label="Rank">#</th><th>File</th><th>Seen</th>{showMissing && <th title="Lines never on screen">Missing lines</th>}{showCommits && <th title="Commits touching this file in the last 90 days">Commits</th>}<th>Quiz sample</th><th aria-label="Action"></th></tr></thead>
      <tbody>{files.map(f => <tr key={f.path} className={f === files[0] ? 'first-row' : ''}>
        <td className="dim" title="Unseen lines and recent commits set the rank; passing a quiz lowers it.">{f.rank}</td><td><button className="file-link" onClick={() => inspect(f)}><FileName path={f.path} /></button><ChangedBadge file={f} /></td>
        <td><Chip state={f.state} tested={f.review.tested} seen={f.reported_lines} total={f.line_count} uncertain={f.current_uncertain} /></td>{showMissing && <td className="numeric missing-lines">{missingLines(f) === null ? 'Unknown' : number(missingLines(f))}</td>}
        {showCommits && <td className="numeric">{Number.isFinite(f.commits_90d) ? number(f.commits_90d) : 'Unknown'}</td>}
        <td>{f.review.confidently_wrong ? <span className="attention-text">Confidently wrong</span> : f.review.passing_samples ? <Chip state="sample_passed" /> : <span className="dim">{f.review.tested ? 'Tested' : f.review.stale_results ? 'Changed since quiz' : 'Never tested'}</span>}</td>
        <td><div className="row-actions">{!f.current_uncertain && <a className="button-link" href={`#learn?path=${encodeURIComponent(f.path)}`}>Study</a>}{f.review.available.length > 0 && <button onClick={() => startReview(f)}>Take quiz</button>}</div></td>
      </tr>)}</tbody></table></div>}
    {files.length > 0 && <p className="footnote">Hatched means never tested.</p>}
  </main>;
}

function MapView({ data, inspect }) {
  const gap = gapSummary(data);
  const [dir, setDir] = useState('all'), [search, setSearch] = useState('');
  const files = data.files.filter(f => (dir === 'all' || directory(f.path) === dir) && f.path.toLowerCase().includes(search.toLowerCase()));
  return <main className="map-layout"><aside className="map-sidebar"><div className="rollup"><span className="eyebrow">Not seen</span>
    <div className={`headline mono ${!gap.known ? 'headline-words' : ''}`}>{gap.headline}</div>
    <p className="mono dim">{gap.known ? `${number(gap.gap)} of ${number(data.totals.line_count)} lines not seen` : gap.detail}</p>
    {gap.known && <p className="mono dim">{number(data.files.length)} files tracked</p>}
    {data.totals.uncertain_files > 0 && <p className="mono dim">{number(data.totals.uncertain_files)} files unknown · reconnect the extension</p>}</div>
    {data.files.length > 0 && <details className="rollup map-directories" open={window.innerWidth > 760}><summary>Directories · gaps first</summary><button className="directory-reset" aria-pressed={dir === 'all'} onClick={() => setDir('all')}>All directories</button>{directories(data.files).map(d => <button className="directory-row" key={d.name} aria-pressed={dir === d.name} onClick={() => setDir(d.name)} title="Filter this directory">
      <span>{d.name}</span><span>{data.has_observations && d.lines ? `${percent(d.lines - d.reported, d.lines)}% not seen` : 'Unknown'}</span>{data.has_observations && d.lines > 0 && <progress style={coverageStyle(d.reported, d.lines)} title="Lines not seen in this directory" max={d.lines} value={d.lines - d.reported} />}<small>{number(d.files)} files · {number(d.lines)} lines{d.uncertain ? ` · ${d.uncertain} unknown` : ''}</small>
    </button>)}</details>}
    <details className="rollup coverage-legend" open={window.innerWidth > 760}><summary>Coverage legend</summary><div className="coverage-scale" /><div className="coverage-labels"><span>0%</span><span>Below 100%</span></div><div className="legend"><div><span className="swatch" style={coverageStyle(1, 1)} /><span>100% seen</span></div><div><span className="swatch state-uncertain" /><span>Unknown</span></div></div><p className="mono dim">Hatched = never tested</p></details></aside>
    <section className="map-main"><div className="map-toolbar mono"><label className="map-search">Find a file<input type="search" name="blindspot-file-filter" autoComplete="off" autoCapitalize="none" spellCheck={false} data-1p-ignore="true" data-lpignore="true" data-bwignore="true" data-form-type="other" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search files or paths" /></label><span>Size: lines</span><a className="button-link" href="#share">Export PNG</a></div>
      {data.files.length ? <>{files.length ? <Treemap files={files} onSelect={inspect} /> : <Empty title="No matching files">Change the search or select All directories.</Empty>}<details className="file-index" open={!!search}><summary>File index · {number(files.length)} files</summary><div>{files.map(f => <button key={f.path} onClick={() => inspect(f)}>{f.path}</button>)}</div></details></> : <Empty title="No files to map">Open a Git project in VS Code.</Empty>}
    </section></main>;
}

function Source({ text, file, start = 1, review = false, trimTerminal = true }) {
  const lines = text.split('\n');
  if (trimTerminal && lines.at(-1) === '') lines.pop();
  return <div className={`source-well ${review ? 'review-source' : ''}`}><pre>{lines.map((line, i) => {
    const n = start + i;
    const state = file ? file.current_uncertain ? 'uncertain' : inRanges(n, file.dwell_ranges) ? 'reported' : inRanges(n, file.brief_ranges) ? 'brief' : 'no_evidence' : null;
    const tested = file && inRanges(n, file.review.tested_ranges);
    const changed = file && inRanges(n, file.changed_unseen_ranges || []);
    return <span key={n} data-line={n} style={file ? coverageStyle(state === 'no_evidence' ? 0 : 1, 1, file.current_uncertain) : undefined} className={`source-line ${state ? `state-${state} ${tested ? '' : 'untested'}` : ''} ${changed ? 'changed-unseen' : ''}`} title={state ? `${changed ? 'Added or changed · ' : ''}${label(state)} · ${tested ? 'Tested' : 'Never tested'}` : undefined}><span className="line-number">{n}</span><code>{line || ' '}</code></span>;
  })}</pre></div>;
}

const GUIDE_LABELS = { unseen: 'No display recorded', partial: 'Partly seen', seen: 'Seen' };
function jumpTo(root, line) {
  const row = root?.querySelector(`[data-line="${line}"]`);
  if (!row) return;
  row.scrollIntoView({ block: 'center', behavior: 'smooth' });
  row.classList.add('jump'); setTimeout(() => row.classList.remove('jump'), 1800);
}
function useGuide(file) {
  const [guide, setGuide] = useState(null), [error, setError] = useState('');
  const visibility = JSON.stringify(file.reported_ranges);
  useEffect(() => {
    let cancelled = false; setGuide(null); setError('');
    api(`/api/dashboard/guide?${new URLSearchParams({ path: file.path, hash: file.content_hash })}`).then(g => { if (!cancelled) setGuide(g); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [file.path, file.content_hash, file.current_uncertain, visibility]);
  return [guide, error];
}
function GuideItem({ item, jump, id, code }) {
  const change = item.changes[0];
  const first = item.unseen_ranges[0]?.[0] ?? item.start;
  return <li className="guide-item" id={id}>
    <div className="guide-head">{jump ? <button className="guide-name mono" onClick={() => jump(first)} title="Show these lines in the source">{item.name}</button> : <h3 className="guide-name mono">{item.name}</h3>}
      <span style={coverageStyle(item.lines - item.unseen, item.lines)} className={`state-chip state-${GUIDE_STATES[item.state]}`}>{GUIDE_LABELS[item.state]}</span></div>
    <div className="guide-lines mono">{lineSpan(item)} · {item.unseen === 0 ? `all ${item.lines} lines seen` : `${item.unseen} of ${item.lines} never on screen`}{item.unseen > 0 && item.unseen_ranges.length > 0 && <> ({rangeText(item.unseen_ranges)}{item.unseen_ranges.length === 8 ? ', …' : ''})</>}</div>
    {item.doc && <p className="guide-doc">{item.doc}</p>}
    {item.signature && item.kind !== 'block' && <code className="guide-signature">{item.signature}</code>}
    <details className="unit-details"><summary>Details</summary>
    {(item.calls?.length > 0 || item.raises?.length > 0 || item.branches > 0) && <div className="guide-meta mono">
      {item.calls?.length > 0 && <span>Calls {item.calls.join(', ')}</span>}
      {item.raises?.length > 0 && <span>Raises {item.raises.join(', ')}</span>}
      {item.branches > 0 && <span>{item.branches} {item.branches === 1 ? 'branch' : 'branches'}</span>}</div>}
    {change && <div className="guide-change mono dim">Last changed {change.date || 'since the last commit'}: {change.summary}{item.changes.length > 1 && ` (+${item.changes.length - 1} more)`}</div>}
    </details>
    {code}
  </li>;
}
function StudyGuide({ guide, error, close }) {
  if (error) return <p className="dim">{error}</p>;
  if (!guide) return <p className="dim">Loading sections.</p>;
  const items = guideItems(guide, 'unseen');
  return items.length > 0 && <details className="study-guide"><summary>Unseen sections · {items.length}</summary>
    <ul className="section-links">{items.slice(0, 5).map(item => <li key={item.start}><a onClick={close} href={`#learn?path=${encodeURIComponent(guide.path)}&line=${item.start}`}><span>{item.name}</span><small>{item.unseen} unseen lines</small></a></li>)}</ul>
    <a className="button-link" onClick={close} href={`#guide?path=${encodeURIComponent(guide.path)}`}>Full guide</a>
    {items.length > 5 && <a onClick={close} href={`#learn?path=${encodeURIComponent(guide.path)}`}>Study all sections</a>}
  </details>;
}

function FileDetail({ file, data, close }) {
  const ref = useRef(null), [source, setSource] = useState(null), [error, setError] = useState('');
  const [guide, guideError] = useGuide(file);
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
    <div className="detail-meta mono dim">{number(file.line_count)} lines</div><div className="detail-state"><Chip state={file.state} tested={file.review.tested} seen={file.reported_lines} total={file.line_count} uncertain={file.current_uncertain} />{file.review.passing_samples > 0 && <Chip state="sample_passed" />}</div>
    <div className="detail-actions">
      {!file.current_uncertain && <a className="button-link" onClick={close} href={`#learn?path=${encodeURIComponent(file.path)}`}>{missingLines(file) === 0 ? 'Study file' : 'Study unseen code'}</a>}
      <a href={editor}>Open in VS Code</a>
      {file.review.available.length > 0 && <button disabled={!current} onClick={() => startReview(file)}>Take quiz</button>}
      {file.changed_unseen_lines > 0 && <button disabled={!current} onClick={() => jumpTo(ref.current, file.changed_unseen_ranges[0][0])}>Show changed lines</button>}
    </div>
    <section className="record"><h3>This file</h3>
      <ul>{file.evidence.filter(e => !/timed visibility|interaction records|Git HEAD/.test(e.source)).map((e, i) => <li key={i}><span className={`evidence-dot state-${e.state}`} /><p className="mono">{e.text}</p></li>)}</ul>
      <details><summary>More evidence</summary><ul>{file.evidence.filter(e => /timed visibility|interaction records|Git HEAD/.test(e.source)).map((e, i) => <li key={i}><span className={`evidence-dot state-${e.state}`} /><p className="mono">{e.text}</p></li>)}</ul></details>
    </section>
    <section className="detail-source"><h3>Source</h3>{error ? <p className="notice">{error}</p> : current ? <Source text={source.text} file={file} /> : <p className="dim">Loading file.</p>}</section>
    <StudyGuide guide={guide} error={guideError} close={close} />
    <Methodology />
  </dialog>;
}


function Insights({ data }) {
  const review = data.review;
  const calibration = Object.entries(review.calibration).filter(([, c]) => c.answers > 0);
  return <main className="standard-page"><div className="page-heading"><span className="eyebrow">Quizzes</span><h1>What the quizzes found</h1><p>Quiz accuracy is measured against a generated answer key.</p></div>
    <section className="wrong-summary">{review.completed_attempts > 0 && <div className={`mono big-stat ${review.confidently_wrong_files ? 'flagged-stat' : ''}`}>{number(review.confidently_wrong_files)}</div>}<div><h2>Confidently wrong</h2>{review.completed_attempts ? <><p>Files where you answered confidently and were wrong.</p>{review.confidently_wrong_files > 0 && <a className="button-link" href="#risk?filter=wrong">View affected files</a>}</> : <><p>No quizzes taken yet.</p><a className="button-link" href="#learn">Study a file</a></>}</div></section>
    {calibration.length > 0 && <section className="chart-panel calibration-panel"><h2>Confidence versus accuracy</h2><p>How often you were right, grouped by how sure you were.</p>
      {calibration.map(([confidence, c]) => <div className="calibration mono" key={confidence}><div><span>{confidence[0].toUpperCase() + confidence.slice(1)}</span><span>{number(c.correct)}/{number(c.answers)} correct · {percent(c.correct, c.answers)}%</span></div><progress max={c.answers} value={c.correct} /></div>)}
    </section>}
    {review.history?.length > 0 && <section className="chart-panel"><h2>Completed practice</h2>{review.history.map(a => <p className="mono" key={a.attempt_id}><a href={`#review?attempt_id=${encodeURIComponent(a.attempt_id)}&path=${encodeURIComponent(a.path)}`}>{a.path}</a> · {a.status} · {new Date(a.completed_at).toLocaleDateString()}</p>)}</section>}
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
        window.history.replaceState(null, '', `#review?attempt_id=${encodeURIComponent(id)}${params.get('path') ? `&path=${encodeURIComponent(params.get('path'))}` : ''}`);
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
    {result ? <main className="review-results"><span className="eyebrow">Completed sample</span><h1>Quiz results</h1><p className="guide-meta dim">Generated answer key · unverified</p><p className="mono">{result.questions.filter(q => q.correct).length} / {result.questions.length} answers correct</p><p>{result.set_status === 'rejected' ? 'Rejected answer key. Excluded from current results.' : result.currentness !== 'current' ? 'Historical result. Source has changed; excluded from current credit.' : 'Practice against an unverified answer key.'}</p>
      <div className="result-actions">{(attempt?.target.path || params.get('path')) && <><a className="button-link" href={`#map?path=${encodeURIComponent(attempt?.target.path || params.get('path'))}`}>Back to file</a><a className="button-link" href={`#learn?path=${encodeURIComponent(attempt?.target.path || params.get('path'))}&line=${attempt?.target.start_line || ''}`}>Study this section</a></>}</div>
      {result.questions.map((q, i) => ({ q, i })).sort((a, b) => Number(a.q.correct) - Number(b.q.correct)).map(({ q, i }) => <details open={!q.correct} key={q.question_id} className={`answer-record ${q.correct ? 'matches' : 'differs'}`}><summary><span className="eyebrow">Question {i + 1} · {q.confidence} · {q.correct ? 'Correct' : 'Incorrect'}</span><h2>{q.prompt}</h2></summary><p>Your answer: {q.options[q.chosen_index]}</p><p>Answer key: {q.options[q.correct_index]}</p><p>{q.explanation}</p><p className="mono dim">{q.rationale.path}:{q.rationale.start_line}–{q.rationale.end_line}</p><p>{q.rationale.reason}</p><ReportQuestion attemptId={result.attempt_id} questionId={q.question_id} /></details>)}<a className="button-link" href="#risk">Return to review queue</a></main>
      : attempt ? <main className="review-layout"><section className="review-code"><div className="source-caption mono">{attempt.target.path} · lines {attempt.target.start_line}–{attempt.target.end_line}</div><Source text={attempt.target.code} start={attempt.target.start_line} review />{attempt.context.map(c => <details key={`${c.path}:${c.start_line}`}><summary className="mono">Context · {c.path}:{c.start_line}–{c.end_line}</summary><Source text={c.code} start={c.start_line} review /></details>)}</section>
        <section className="question-panel">{question ? <><span className="eyebrow">Question</span><h1>{question.prompt}</h1><div className="options">{question.options.map((option, i) => <button key={i} aria-pressed={chosen === i} onClick={() => setChosen(i)} disabled={busy}><span className="option-letter">{String.fromCharCode(65 + i)}</span><span>{option}</span></button>)}</div><div className="confidence"><span className="eyebrow">How sure are you</span><div>{['guessed', 'shaky', 'solid'].map(c => <button key={c} disabled={chosen === null || busy} onClick={() => submit(c)}>{c[0].toUpperCase() + c.slice(1)}</button>)}</div><p>Choose your confidence to submit the answer.</p></div></> : <><h1>Answers recorded</h1><button disabled={busy} onClick={finish}>Finish review</button></>}</section></main> : !error && <Empty title="Loading review">Only source and questions are shown while answering.</Empty>}
  </div>;
}

function ExplainBox({ label, note, run }) {
  if (!note) return <button className="guide-explain-button" onClick={() => run(false)}>{label}</button>;
  if (note.loading) return <p className="guide-explain" role="status">Thinking. The first answer can take a while if the model has to load.</p>;
  if (note.error) return <div className="guide-explain"><p className="notice" role="alert">{note.error}</p><button onClick={() => run(false)}>Try again</button></div>;
  return <div className="guide-explain">
    <span className="eyebrow">Generated · unverified · {note.model}{note.cached ? ' · saved' : ''}</span>
    <p className="guide-explain-text">{note.text}</p>
    <button onClick={() => run(true)}>Regenerate</button></div>;
}

function QuizBox({ file, item }) {
  const [phase, setPhase] = useState('idle'), [made, setMade] = useState(null), [reply, setReply] = useState(''), [error, setError] = useState(''), [done, setDone] = useState(null), [copied, setCopied] = useState(false);
  const offer = quizForUnit(file, item);
  const request = { path: file.path, hash: file.content_hash, start: item.start, end: item.end };
  const start = id => { window.location.hash = `review?set_id=${encodeURIComponent(id)}&path=${encodeURIComponent(file.path)}`; };
  async function open(copyPrompt = false) {
    setPhase('loading'); setError('');
    try { const made = await explainApi('/api/dashboard/quiz/prompt', request); setMade(made); setPhase('prompt'); if (copyPrompt) { try { await navigator.clipboard.writeText(made.prompt); setCopied(true); } catch { setError('Copy was blocked. Open “Show prompt” and copy it by hand.'); } } } catch (e) { setError(e.message); setPhase('idle'); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(made.prompt); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setError('Copy was blocked. Open “Show prompt” and copy it by hand.'); }
  }
  async function create() {
    setPhase('creating'); setError('');
    try { setDone(await explainApi('/api/dashboard/quiz/import', { ...request, reply })); setPhase('done'); } catch (e) { setError(e.message); setPhase('prompt'); }
  }
  if (phase === 'done') return <div className="quiz-maker"><p><strong>Quiz ready.</strong> {done.question_count} questions{done.duplicate ? ' (you already had this one)' : ''}.</p>
    {done.warnings.map(w => <p key={w} className="guide-meta">{w}</p>)}
    <p className="guide-meta dim">{done.key_quality} If a question looks wrong afterwards, report it and the quiz is removed.</p>
    <button className="guide-explain-button" onClick={() => start(done.set_id)}>Start quiz</button></div>;
  if (phase === 'idle' || phase === 'loading') return <>
    {offer && <button className="guide-explain-button" onClick={() => start(offer.set_id)}>Take quiz · {offer.question_count} questions</button>}
    <button title="Pasting a quiz prompt into another service shares the selected code." className="guide-quiz-button" disabled={phase === 'loading'} onClick={() => open(!offer)}>{phase === 'loading' ? 'Preparing' : offer ? 'Make another quiz' : 'Copy prompt'}</button>
    {error && <p className="notice" role="alert">{error}</p>}</>;
  return <div className="quiz-maker">
    <span className="eyebrow">Quiz for lines {made.start}–{made.end} · {made.question_count} questions</span>
    {made.note && <p className="guide-meta dim">{made.note}</p>}
    <ol className="quiz-steps">
      <li><button onClick={copy}>{copied ? 'Copied' : 'Copy prompt'}</button><span className="quiz-instruction"> Paste into your chat model.</span> <details><summary>Show prompt</summary><textarea readOnly value={made.prompt} rows={8} aria-label="Prompt" /></details></li>
      <li>Paste the model’s reply here.<textarea value={reply} onChange={e => setReply(e.target.value)} rows={6} placeholder="Paste the reply here" aria-label="Model reply" /></li></ol>
    {error && <p className="notice" role="alert">{error}</p>}
    <div><button className="guide-explain-button" disabled={!reply.trim() || phase === 'creating'} onClick={create}>{phase === 'creating' ? 'Checking' : 'Create quiz'}</button><button onClick={() => { setPhase('idle'); setError(''); }}>Cancel</button></div>
    <p className="guide-meta dim">Generated answer key · unverified</p></div>;
}

function ReportQuestion({ attemptId, questionId }) {
  const [step, setStep] = useState('idle'), [error, setError] = useState('');
  async function remove() {
    try { await explainApi('/api/dashboard/review/report', { attempt_id: attemptId, question_id: questionId }); setStep('done'); } catch (e) { setError(e.message); setStep('idle'); }
  }
  if (step === 'done') return <p className="guide-meta dim">Quiz removed. It no longer counts toward your results.</p>;
  return <div className="report-question">{error && <p className="notice" role="alert">{error}</p>}
    {step === 'idle' ? <button onClick={() => setStep('confirm')}>This answer key looks wrong</button>
      : <><span className="guide-meta">Remove this whole quiz? Its results stop counting.</span> <button onClick={remove}>Remove quiz</button> <button onClick={() => setStep('idle')}>Keep it</button></>}</div>;
}

const CODE_CAP = 120;
function Learning({ data }) {
  const [scope, setScope] = useState('gaps');
  if (!data.has_observations) return <main className="standard-page"><Empty title="No display recorded">Start recording in VS Code, then open or scroll supported files to build a study guide.</Empty></main>;
  const known = data.files.filter(f => !f.current_uncertain);
  const gaps = known.filter(f => missingLines(f) > 0);
  const files = scope === 'gaps' ? gaps : known;
  const first = gaps[0];
  const lesson = file => `#learn?path=${encodeURIComponent(file.path)}`;
  return <main className="standard-page learning-page">
    <div className="page-heading"><span className="eyebrow">Learning</span><h1>Code to revisit</h1><p>Choose a file to study its unseen sections.</p></div>
    {gaps.length > 0 && <div className="learning-overview"><div><span className="eyebrow">To revisit</span><strong className="mono">{gaps.length} files</strong><p>Work through the unseen sections, then check a passage with a quiz.</p></div><div><span className="eyebrow">Unseen lines</span><strong className="mono">{number(gaps.reduce((n,f) => n + missingLines(f), 0))}</strong><p>Across files with known coverage.</p></div></div>}
    <div className="filters mono"><button aria-pressed={scope === 'gaps'} onClick={() => setScope('gaps')}>Files with gaps</button><button aria-pressed={scope === 'all'} onClick={() => setScope('all')}>All files</button><span className="dim">{number(files.length)} files</span></div>
    {!data.files.length ? <Empty title="No files to study">Open a Git project and start recording in VS Code.</Empty> : !files.length && <Empty title={known.length ? 'No gaps recorded' : 'File status unknown'}>{known.length ? 'Choose All files to revisit a section or take a quiz.' : 'Reconnect the extension and refresh.'}</Empty>}
    <div className="learning-files">{files.map(file => <article className={`learning-file ${scope === 'gaps' && file === first ? 'recommended-file' : ''}`} key={file.path}>
      <div className="learning-file-heading">{scope === 'gaps' && file === first && <span className="eyebrow">Start here</span>}<h2 className="mono">{file.path}</h2><Chip state={file.state} tested={file.review.tested} seen={file.reported_lines} total={file.line_count} /></div>
      <p className="mono dim">{number(missingLines(file))} unseen · {number(file.line_count)} total lines</p><progress aria-label={`Lines seen in ${file.path}`} style={coverageStyle(file.reported_lines, file.line_count)} max={Math.max(1, file.line_count)} value={file.reported_lines} />
      <ChangedBadge file={file} />
      {(file.review.confidently_wrong || file.review.stale_results || file.review.available.length > 0) && <p className="mono learning-quiz-status">{file.review.confidently_wrong ? 'Confidently wrong answer to revisit' : file.review.stale_results ? 'Changed since quiz' : `${number(file.review.available.length)} quizzes ready`}</p>}
      <div className="learning-file-actions"><a className="button-link" href={lesson(file)}>Study</a><a href={`#guide?path=${encodeURIComponent(file.path)}`}>Full guide</a>{file.review.available.length > 0 && <button onClick={() => startReview(file)}>Take quiz</button>}</div>
    </article>)}</div>
    {known.length < data.files.length && <p className="mono dim">{number(data.files.length - known.length)} files unknown · reconnect the extension</p>}
  </main>;
}

function LearningLesson({ file, guide, lines, local, chosen, pick, notes, explain, editor }) {
  const [scope, setScope] = useState(missingLines(file) === 0 ? 'whole' : 'unseen'), [selected, setSelected] = useState(Number(new URLSearchParams(window.location.hash.split('?')[1]).get('line')) || null), [tab, setTab] = useState('code');
  const items = guideItems(guide, scope);
  const index = Math.max(0, items.findIndex(i => i.start === selected));
  const item = items[index];
  function choose(unit) { setSelected(unit.start); setTab('code'); }
  const tabs = [['code', 'Code'], ['quiz', 'Quiz'], ['explanation', 'Explain']];
  function navigateTabs(event) {
    const current = tabs.findIndex(([id]) => id === tab);
    const target = event.key === 'ArrowRight' ? (current + 1) % tabs.length : event.key === 'ArrowLeft' ? (current + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
    if (target === null) return;
    event.preventDefault(); setTab(tabs[target][0]); document.getElementById(`lesson-tab-${tabs[target][0]}`).focus();
  }
  return <main className="lesson-layout">
    <aside className="lesson-sidebar">
      <a className="lesson-back" href="#learn">← Learning</a>
      <span className="eyebrow">Study this file</span><h1 className="mono">{file.path}</h1>
      <div className="guide-toggle" role="group" aria-label="Lesson scope"><button aria-pressed={scope === 'unseen'} onClick={() => { setScope('unseen'); setSelected(null); setTab('code'); }}>Unseen code</button><button aria-pressed={scope === 'whole'} onClick={() => { setScope('whole'); setSelected(null); setTab('code'); }}>Whole file</button></div>
      <label className="mobile-unit-select select-label">Section<select aria-label="Section" value={item?.start || ''} onChange={e => choose(items.find(unit => unit.start === Number(e.target.value)))}>{items.map(unit => <option key={unit.start} value={unit.start}>{unit.name} · {unit.unseen} unseen</option>)}</select></label>
      <ol className="lesson-outline">{items.map(unit => <li key={unit.start}><button aria-current={unit === item ? 'step' : undefined} onClick={() => choose(unit)}><span className="mono">{unit.name}</span><small className="mono">{lineSpan(unit)} · {number(unit.unseen)} unseen</small></button></li>)}</ol>
      <a className="button-link" href={`#guide?path=${encodeURIComponent(file.path)}`}>Full study guide</a>
    </aside>
    <section className="lesson-main">
      {item ? <>
        <div className="lesson-heading"><div><h2 className="mono">{item.name}</h2><p className="mono dim">{lineSpan(item)} · {number(item.unseen)} lines never on screen</p></div><span className="mono dim">Unit {index + 1} of {items.length}</span></div>
        <div className="lesson-tabs" role="tablist" aria-label="Learning activities" onKeyDown={navigateTabs}>{tabs.map(([id, text]) => <button key={id} id={`lesson-tab-${id}`} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} aria-controls="lesson-panel" onClick={() => setTab(id)}>{text}</button>)}</div>
        <div id="lesson-panel" className="lesson-panel" role="tabpanel" aria-labelledby={`lesson-tab-${tab}`}>
          {tab === 'code' && <>{item.doc && <p className="dim">{item.doc}</p>}{lines ? <UnitSource lines={lines} item={item} file={file} /> : <p className="dim">Loading code.</p>}<a className="button-link" href={editor}>Open in VS Code</a></>}
          {tab === 'explanation' && <>{!local ? <p role="status">Checking for Ollama.</p> : local.available ? <><label className="select-label lesson-model">Model<select aria-label="Local model" value={chosen} onChange={e => pick(e.target.value)}>{local.models.map(model => <option key={model}>{model}</option>)}</select></label><ExplainBox label="Explain this unit" note={notes[`${item.start}-${item.end}`]} run={regenerate => explain(item, regenerate)} /></> : <><p className="dim">Ollama is not available. Code and quizzes work without it.</p><button onClick={() => setTab('code')}>Back to code</button></>}</>}
          <div hidden={tab !== 'quiz'}><p className="guide-meta dim">Quiz prompts include code. Pasting them into another service shares it.</p><QuizBox key={`${file.content_hash}:${item.start}`} file={file} item={item} /></div>
        </div>
        <div className="lesson-navigation"><button disabled={index === 0} onClick={() => choose(items[index - 1])}>← Previous unit</button><button disabled={index === items.length - 1} onClick={() => choose(items[index + 1])}>Next unit →</button></div>
      </> : <Empty title={guide.items.length ? 'No unseen code units' : 'No code units found'}>{guide.items.length ? 'Choose Whole file to revisit a section.' : 'Open the file in VS Code.'}</Empty>}
    </section>
  </main>;
}

function GuidePage({ data, path, learning = false }) {
  if (!data.has_observations) return <main className="standard-page"><Empty title="No display recorded">Start recording in VS Code, then open or scroll supported files to build a study guide.</Empty><a href="#map">Back to Map</a></main>;
  const file = data.files.find(f => f.path === path);
  if (!file) return <main className="standard-page"><Empty title="File not found">Choose a file in Risk to open its guide.</Empty><a className="button-link" href="#risk">Back to Risk</a></main>;
  return <GuideBody key={`${file.path}:${file.content_hash}:${learning}`} file={file} data={data} learning={learning} />;
}
function GuideBody({ file, data, learning }) {
  const [guide, error] = useGuide(file);
  const [scope, setScope] = useState('unseen'), [open, setOpen] = useState(() => new Set()), [source, setSource] = useState(null), [copied, setCopied] = useState(false);
  const [local, setLocal] = useState(null), [model, setModel] = useState(() => { try { return localStorage.getItem('blindspot.model') || ''; } catch { return ''; } }), [notes, setNotes] = useState({});
  useEffect(() => {
    let cancelled = false;
    explainApi('/api/dashboard/explain/status').then(st => { if (!cancelled) setLocal(st); }).catch(() => { if (!cancelled) setLocal({ available: false, models: [], error: 'Cannot reach the local server.' }); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => { setNotes({}); }, [JSON.stringify(file.reported_ranges)]);
  const chosen = local?.models.includes(model) ? model : local?.default || '';
  function pick(name) { setModel(name); try { localStorage.setItem('blindspot.model', name); } catch { /* storage unavailable */ } }
  async function explain(unit, regenerate = false) {
    const id = unit ? `${unit.start}-${unit.end}` : 'file';
    setNotes(n => ({ ...n, [id]: { loading: true } }));
    try {
      const result = await explainApi('/api/dashboard/explain', { path: file.path, hash: file.content_hash, model: chosen, regenerate, ...(unit ? { start: unit.start, end: unit.end } : {}) });
      setNotes(n => ({ ...n, [id]: result }));
    } catch (e) { setNotes(n => ({ ...n, [id]: { error: e.message } })); }
  }
  useEffect(() => {
    let cancelled = false;
    api(`/api/dashboard/source?${new URLSearchParams({ path: file.path, hash: file.content_hash })}`).then(s => { if (!cancelled) setSource(s); }).catch(() => {});
    return () => { cancelled = true; };
  }, [file.path, file.content_hash]);
  const editor = `vscode://file${encodeURI(`${data.workspace}/${file.path}`).replaceAll('#', '%23').replaceAll('?', '%3F')}`;
  if (error) return <main className="standard-page"><p className="notice">{error}</p><a className="button-link" href="#risk">Back to Risk</a></main>;
  if (!guide) return <main className="standard-page"><Empty title="Loading guide">Reading the file’s structure and Git history.</Empty></main>;
  const items = guideItems(guide, scope), key = i => `u${i.start}-${i.end}-${i.name}`;
  const toggle = i => setOpen(prev => { const next = new Set(prev); next.has(key(i)) ? next.delete(key(i)) : next.add(key(i)); return next; });
  function goto(i) {
    setOpen(prev => new Set(prev).add(key(i)));
    setTimeout(() => document.getElementById(key(i))?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 0);
  }
  async function copy() {
    try { await navigator.clipboard.writeText(guideMarkdown(guide, scope, Object.fromEntries(Object.entries(notes).filter(([, v]) => v.text)))); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard unavailable */ }
  }
  const lines = source?.text.split('\n');
  if (learning) return <LearningLesson file={file} guide={guide} lines={lines} local={local} chosen={chosen} pick={pick} notes={notes} explain={explain} editor={editor} />;
  const codeFor = i => {
    if (!open.has(key(i))) return <button className="guide-code-toggle" onClick={() => toggle(i)} aria-expanded="false">Show code</button>;
    return <div className="guide-code"><button className="guide-code-toggle" onClick={() => toggle(i)} aria-expanded="true">Hide code</button>
      {lines ? <><UnitSource lines={lines} item={i} file={file} /></> : <p className="dim">Loading code.</p>}</div>;
  };
  return <main className="guide-layout">
    <aside className="guide-sidebar">
      <div className="rollup">
        <span className="eyebrow">Study guide</span>
        <h1 className="mono guide-file">{filename(file.path)}</h1>
        <p className="mono dim">{directory(file.path)}</p>
        <div className={`headline mono ${guide.unseen_lines === 0 ? 'headline-words' : ''}`}>{guide.unseen_lines === 0 ? 'All seen' : `${number(guide.unseen_lines)} lines`}</div>
        <p>{guide.unseen_lines === 0 ? 'Every line has been on screen.' : `never on screen, across ${guide.overview.units_with_unseen} of ${guide.overview.units} code units`}</p>
      </div>
      <div className="rollup">
        <div className="guide-toggle" role="group" aria-label="Guide scope">
          <button aria-pressed={scope === 'unseen'} onClick={() => setScope('unseen')}>Unseen code</button>
          <button aria-pressed={scope === 'whole'} onClick={() => setScope('whole')}>Whole file</button></div>
        <span className="eyebrow outline-title">{scope === 'unseen' ? 'Read first' : 'In file order'}</span>
        <ol className="guide-outline">{items.map(i => <li key={key(i)}><button onClick={() => goto(i)}><span className="mono">{i.name}</span><small className="mono">{i.unseen === 0 ? 'seen' : `${i.unseen} of ${i.lines} unseen`}</small><i className="gap-bar" style={{ ...coverageStyle(i.lines - i.unseen, i.lines), '--w': `${100 * i.unseen / i.lines}%` }} /></button></li>)}</ol>
        {items.length === 0 && <p className="dim">{guide.items.length === 0 ? 'No code units found.' : 'Nothing left unseen.'}</p>}
      </div>
      <div className="rollup local-model">
        <span className="eyebrow">Local model</span>
        {!local ? <p className="dim">Checking for Ollama.</p> : local.available
          ? <><label className="select-label">Model<select value={chosen} onChange={e => pick(e.target.value)} aria-label="Local model">{local.models.map(m => <option key={m}>{m}</option>)}</select></label>
              <p className="dim">Optional explanations run on this machine through Ollama. Only the selected code unit is sent.</p></>
          : <p className="dim">Ollama is not available. The guide works without it.</p>}
      </div>
      <div className="rollup guide-actions">
        <p className="guide-meta dim">Quiz prompts include code. Pasting them into another service shares it.</p>
        <details className="guide-export"><summary>Export guide</summary><button onClick={copy} disabled={items.length === 0}>{copied ? 'Copied' : 'Copy as Markdown'}</button><button onClick={() => window.print()}>Print</button></details>
        <a className="button-link" href={editor}>Open in VS Code</a>
        <a className="button-link" href="#risk">Back to Risk</a>
      </div>
    </aside>
    <div className="guide-main">

      {guide.overview.doc && <p className="guide-doc">{guide.overview.doc}</p>}
      {guide.overview.imports.length > 0 && <p className="guide-meta mono dim">Uses {guide.overview.imports.join(', ')}</p>}
      {local?.available && <ExplainBox label="Summarize this file" note={notes.file} run={regenerate => explain(null, regenerate)} />}
      {scope === 'unseen' && guide.recent_changes.length > 0 && <div className="guide-changes"><h2>Changes you haven’t seen</h2><ul>{guide.recent_changes.map(c => <li key={`${c.commit}${c.date}${c.summary}`} className="mono"><span className="dim">{c.date || 'uncommitted'}</span> {c.summary} <span className="dim">· {c.unseen} unseen {c.unseen === 1 ? 'line' : 'lines'}</span></li>)}</ul></div>}
      <ol className="guide-list">{items.map(i => <GuideItem key={key(i)} id={key(i)} item={i} code={<><QuizBox file={file} item={i} />{local?.available && <ExplainBox label="Explain" note={notes[`${i.start}-${i.end}`]} run={regenerate => explain(i, regenerate)} />}{codeFor(i)}</>} />)}</ol>
      {guide.notes.length > 0 && <details><summary>Guide details</summary>{guide.notes.map(n => <p key={n} className="guide-meta dim">{n}</p>)}</details>}
    </div>
  </main>;
}

function DashboardApp({ page, query }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [selected, setSelected] = useState(() => page === 'map' ? new URLSearchParams(query).get('path') : null), [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true); try { const next = await api('/api/dashboard'); setData(next); setError(''); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => { refresh(); const timer = setInterval(() => { if (!document.hidden) refresh(); }, 10000); return () => clearInterval(timer); }, []);
  const file = data?.files.find(f => f.path === selected);
  const inspect = f => setSelected(f.path);
  return <><header className="app-header"><a href="#map" className="brand"><span className="brand-mark" />blindspot</a><nav aria-label="Dashboard views">{[['map', 'Map'], ['risk', 'Risk'], ['learn', 'Learning'], ['insights', 'Insights']].map(([id, name]) => <a className={id === 'insights' ? 'desktop-nav' : undefined} key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined}>{name}</a>)}<details className="mobile-nav"><summary>More</summary><div>{[['insights', 'Insights']].map(([id, name]) => <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined}>{name}</a>)}</div></details></nav>
    <div className="header-context mono">{data && <>
      <span className="project-context">{data.workspace.split('/').at(-1)} · {data.git.branch || 'Git unavailable'}</span>
      <details className="connection-details"><summary>{data.health.sessions.some(s => s.connection_state === 'connected' && s.status === 'recording') ? 'Recording' : 'Not recording'}</summary><div>{number(data.health.sessions.length)} sessions<br />Updated {new Date(data.generated_at).toLocaleTimeString()}<br />Local only</div></details>
    </>}<button disabled={busy} onClick={refresh}>{busy ? 'Refreshing' : 'Refresh'}</button></div></header>
    {error && <p className="notice" role="alert">{error}</p>}
    {!data ? <Empty title={error ? 'Receiver unavailable' : 'Loading files'}>Start the local server, then refresh.</Empty> : <>
      {data.review.error && <p className="notice">Cannot load quizzes. Check the quiz folder and refresh.</p>}
      {page === 'learn' ? new URLSearchParams(query).get('path') ? <GuidePage data={data} path={new URLSearchParams(query).get('path')} learning /> : <Learning data={data} /> : page === 'guide' ? <GuidePage data={data} path={new URLSearchParams(query).get('path') || ''} /> : page === 'map' ? <MapView data={data} inspect={inspect} /> : page === 'insights' ? <Insights data={data} /> : page === 'share' ? <Share data={data} /> : <Risk data={data} inspect={inspect} />}
      {data.inventory_diagnostics.length > 0 && <p className="notice">{data.inventory_diagnostics.some(d => d.includes('truncated')) ? 'Only the first 500 supported file candidates are included. Coverage does not describe the whole project.' : 'Some files could not be loaded. Check the project folder and refresh.'}</p>}
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
    <p>Recording saves supported source snapshots, including unopened files, and activity in your chosen local state directory. Stop recording and the receiver before deleting that directory to remove saved data.</p>
    <p>The extension samples visible line ranges in focused VS Code windows. Split panes count; background tabs do not.</p>
    <p>“Seen” means a line appeared on screen during a recording. “No display recorded” means it has no matching on-screen activity. Earlier activity is unknown. A line being on screen does not establish that it was read or understood.</p>
    <p>Changed lines lose their seen status; unchanged lines can carry it forward. Unknown files are left out of line totals until their contents can be checked.</p>
    <p>Changed-line highlights compare this file with the most recently captured different version that had on-screen activity. They show added or replaced lines without matching display evidence. Files without an earlier viewed version have no change comparison.</p>
    <p>Glimpsed means less than a second on screen.</p>
    <p>Quiz accuracy is agreement with a generated answer key, which may be wrong. Results cover the tested passage. Confidence totals include completed attempts and practice. Changed files need a new test; hatching marks passages without a matching test.</p>
    <p>On-screen activity is visible only in this editor while recording. Filesystem changes can come from other tools.</p>
    <p>Everything stays on this machine. Nothing is transmitted outside it.</p>
  </dialog>;
}

function Router() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => { const change = () => { const next = window.location.hash.split('?')[0] === '#timeline' ? '#map' : window.location.hash; if (next !== window.location.hash) window.history.replaceState(null, '', next); setHash(next); }; change(); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const [page, query = ''] = hash.replace(/^#/, '').split('?');
  return <>{page === 'review' ? <Review key={hash} params={new URLSearchParams(query)} /> : <DashboardApp page={page === 'timeline' ? 'map' : page || 'map'} query={query} />}<Methodology /></>;
}

createRoot(document.getElementById('root')).render(<Router />);
