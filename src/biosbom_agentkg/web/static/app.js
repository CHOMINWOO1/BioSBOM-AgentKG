'use strict';
const $ = id => document.getElementById(id);
const state = {
  session: null,
  jobs: [],
  selected: null,
  job: null,
  events: [],
  tab: 'findings',
  limit: 50,
  busy: false
};
const labels = {
  queued: '대기 중',
  running: '분석 중',
  awaiting_human: '검토 대기',
  blocked: '검증 차단',
  cancelled: '취소됨',
  interrupted: '중단됨',
  failed: '실행 실패',
  urgent: '긴급',
  high: '높음',
  normal: '일반',
  review: '확인 필요',
  exact_version: '명시 버전 일치',
  ambiguous: '범위 확인 필요',
  version_missing: '버전 누락',
  matched: '후보 발견',
  unmatched: '스냅샷 미일치',
  missing_identity: '식별자 부족',
  affected: '영향 버전 일치',
  under_investigation: '추가 확인',
  approve: '승인',
  hold: '보류',
  reject: '반려'
};
const errors = {
  csrf_refused: '세션이 만료되었습니다. 페이지를 새로고침하세요.',
  session_required: '서버가 재시작되었습니다. 페이지를 새로고침하세요.',
  invalid_request: '입력 형식과 설정 범위를 확인하세요.',
  invalid_input_or_artifact: '입력 구조 또는 저장 파일의 무결성을 확인할 수 없습니다.',
  queue_full: '실행 대기열이 가득 찼습니다.',
  review_already_recorded: '이미 최종 검토가 기록된 분석입니다.',
  run_already_finished: '분석이 이미 종료되었습니다.',
  llm_consent_required: '모델 전송과 호출 비용 확인이 필요합니다.',
  idempotency_key_reused: '요청 키가 다른 입력에 사용되었습니다. 창을 다시 열어주세요.'
};

function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}

function pill(value) {
  return node('span', labels[value] || value, 'pill ' + ({
    awaiting_human: 'success'
  } [value] || value || 'neutral'));
}

function button(text, action, cls = 'secondary') {
  const b = node('button', text, cls);
  b.type = 'button';
  b.addEventListener('click', action);
  return b;
}

function notice(text) {
  $('notice').textContent = text;
  $('notice').hidden = !text;
}
async function api(path, body) {
  const opts = {
    credentials: 'same-origin',
    headers: {}
  };
  if (body !== undefined) {
    opts.method = 'POST';
    opts.headers = {
      'Content-Type': 'application/json',
      'X-BioSBOM-CSRF': state.session.csrf
    };
    opts.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch('/api/' + path, opts);
  } catch {
    throw new Error('서버에 연결할 수 없습니다. 실행 상태를 확인하세요.');
  }
  const data = await response.json();
  if (!response.ok) throw new Error(errors[data.error] || ('요청을 처리할 수 없습니다: ' + (data.error || response.status)));
  return data;
}

function date(value) {
  return new Date(value).toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

function saveJSON(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {
    type: 'application/json'
  }));
  const a = node('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function showNew(example = 'rnaseq-case') {
  $('example').value = example;
  $('upload-fields').hidden = example !== 'upload';
  $('form-error').textContent = '';
  $('new-form').dataset.key = crypto.randomUUID();
  $('new-dialog').showModal();
}

function renderList() {
  const list = $('run-list');
  list.replaceChildren();
  const q = $('search').value.toLowerCase();
  for (const j of state.jobs.filter(x => x.name.toLowerCase().includes(q))) {
    const b = button('', () => selectJob(j.id), 'run-card' + (state.selected === j.id ? ' selected' : ''));
    b.append(node('strong', j.name), node('small', date(j.created_at) + ' · ' + (j.review_decision ? '검토 완료 · ' + labels[j.review_decision] : (labels[j.state] || j.state))));
    list.append(b);
  }
  if (!list.children.length) list.append(node('p', q ? '일치하는 기록이 없습니다' : '아직 분석 기록이 없습니다.', 'empty'));
}
async function refreshList() {
  let items = [],
    total = 0;
  for (let offset = 0; offset < state.limit; offset += 100) {
    const data = await api('jobs?offset=' + offset + '&limit=' + Math.min(100, state.limit - offset));
    items.push(...data.items);
    total = data.total;
    if (items.length >= total) break;
  }
  state.jobs = items;
  $('run-count').textContent = total;
  $('more').hidden = total <= items.length;
  renderList();
}
async function selectJob(id) {
  state.selected = id;
  state.job = null;
  state.events = [];
  state.tab = 'findings';
  renderList();
  $('welcome').hidden = true;
  $('workspace').hidden = false;
  try {
    await refreshJob();
  } catch (e) {
    notice(e.message);
  }
}
async function refreshJob() {
  if (!state.selected) return;
  const id = state.selected;
  const [job, events] = await Promise.all([api('jobs/' + id), api('jobs/' + id + '/events')]);
  if (id !== state.selected) return;
  const changed = !state.job || JSON.stringify(job) !== JSON.stringify(state.job);
  state.job = job;
  state.events = events;
  if (changed) renderJob();
  renderPipeline();
}

function renderJob() {
  const j = state.job,
    r = j.result;
  $('run-title').textContent = j.name;
  $('run-kind').textContent = (j.mode === 'llm' ? 'LLM SPECIALISTS' : 'DETERMINISTIC ANALYSIS') + (r?.synthetic ? ' · SYNTHETIC DEPLOYMENT' : '');
  $('run-meta').textContent = date(j.created_at) + ' · ' + j.id.slice(0, 8) + (j.parent_id ? ' · 이전 실행 ' + j.parent_id.slice(0, 8) + '에서 재실행' : '');
  const a = $('run-actions');
  a.replaceChildren();
  if (['queued', 'running'].includes(j.state)) {
    const b = button(j.cancel_requested ? '취소 요청됨' : '분석 취소', async () => {
      try {
        await api('jobs/' + j.id + '/cancel', {});
        await refreshJob();
      } catch (e) {
        notice(e.message);
      }
    });
    b.disabled = !!j.cancel_requested;
    a.append(b);
  }
  if (['blocked', 'failed', 'interrupted', 'cancelled'].includes(j.state)) a.append(button('새 실행으로 재시도', async () => {
    let ack = false;
    if (j.mode === 'llm') {
      ack = window.confirm('새 모델 호출과 데이터 전송이 발생합니다. 재실행할까요?');
      if (!ack) return;
    }
    try {
      const n = await api('jobs/' + j.id + '/retry', {
        request_key: crypto.randomUUID(),
        llm_acknowledged: ack
      });
      await refreshList();
      await selectJob(n.id);
    } catch (e) {
      notice(e.message);
    }
  }));
  if (r) {
    for (const [kind, text] of [
        ['html', '보고서 ↓'],
        ['bundle', '전체 근거 ZIP ↓']
      ]) {
      const link = node('a', text, 'secondary');
      link.href = '/api/jobs/' + j.id + '/download/' + kind;
      link.download = '';
      a.append(link);
    }
  }
  const banner = $('status-banner');
  banner.replaceChildren(pill(j.review_decision || j.state));
  const descriptions = {
    queued: ' 분석 큐에 저장되었습니다. 페이지를 닫아도 서버가 실행 중이면 계속 진행합니다.',
    running: j.cancel_requested ? ' 취소 대기 중입니다. 진행 중인 모델 요청은 응답 또는 제한 시간 후 종료됩니다.' : ' 근거 수집과 단계별 검증을 진행하고 있습니다.',
    awaiting_human: ' 정책과 근거 검증을 통과했습니다. 원문을 확인하고 최종 검토를 기록하세요.',
    blocked: ' 검증을 통과하지 못했습니다. 검증 결과의 오류 코드를 확인하세요.',
    failed: ' 실행을 완료하지 못했습니다. 입력·서버의 모델 설정을 점검한 뒤 재실행하세요.',
    interrupted: ' 서버 종료 또는 재시작으로 중단되었습니다. 자동으로 유료 호출을 반복하지 않습니다.',
    cancelled: ' 요청에 따라 종료되었습니다. 부분 결과는 승인할 수 없습니다.'
  };
  banner.append(node('span', j.review_decision ? ' 최종 검토가 기록되었습니다. 결정과 판단 근거는 아래에서 확인할 수 있습니다.' : (descriptions[j.state] || '')));
  const metrics = $('metrics');
  metrics.replaceChildren();
  const findings = r?.collection.findings || [];
  const assessments = r?.decisions?.assessments || [];
  const urgent = assessments.filter(x => ['urgent', 'high'].includes(x.priority)).length;
  const stats = [
    ['컴포넌트', r ? r.collection.sbom.components.length : '—', '정규화된 입력 구성요소'],
    ['검토 항목', r ? findings.length : '—', '명시 일치와 불확실 후보'],
    ['긴급 · 높음', r ? urgent : '—', '검증을 통과한 우선순위'],
    ['모델 호출', r ? r.calls : '—', r ? `${r.duration_seconds.toFixed(3)}초 · ${r.reported_total_tokens} 보고 토큰${r.usage_complete?'':' (일부 누락)'}` : '호출별 예산 적용']
  ];
  for (const [label, value, detail] of stats) {
    const card = node('div', undefined, 'metric');
    card.append(node('span', label, 'label'), node('strong', String(value)), node('small', detail));
    metrics.append(card);
  }
  renderResult();
  renderReview();
}

function renderPipeline() {
  const p = $('pipeline');
  p.replaceChildren();
  const events = state.events;
  const single = state.job?.result?.config.architecture === 'single_agent' || events.some(e => e.role === 'single');
  const steps = [
    ['collector', '근거 수집'],
    [single ? 'single' : 'context', single ? '통합 전문가' : '자산 맥락'],
    ['triage', '위험 분류'],
    ['verifier', '독립 검증'],
    ['human_gate', '사람 검토']
  ];
  for (const [i, [role, name]] of steps.entries()) {
    const own = events.filter(e => e.role === role);
    const done = role === 'human_gate' ? !!state.job?.review : role === 'verifier' ? !!state.job?.result?.audit.passed : own.some(e => ['completed', 'proposed', 'ready'].includes(e.outcome)) || (role === 'triage' && single && events.some(e => e.role === 'single' && e.outcome === 'proposed'));
    const s = node('div', undefined, 'stage' + (done ? ' done' : ''));
    s.append(node('span', String(i + 1).padStart(2, '0'), 'stage-number'), node('b', name), node('span', done ? '✓ 기록됨' : own.length ? '검토 중' : '대기'));
    p.append(s);
  }
  const timeline = $('timeline');
  timeline.replaceChildren();
  for (const e of events) {
    const li = node('li');
    li.append(node('time', date(e.created_at)), node('b', e.role), node('span', e.outcome + (e.attempt ? ' · 시도 ' + (e.attempt + 1) : '')), node('span', e.issue_codes.join(', ')));
    timeline.append(li);
  }
  if (!events.length) timeline.append(node('li', '아직 기록된 이벤트가 없습니다.'));
}

function table(headers, rows) {
  const wrap = node('div', undefined, 'table-wrap'),
    t = node('table'),
    thead = node('thead'),
    head = node('tr'),
    body = node('tbody');
  for (const h of headers) head.append(node('th', h));
  thead.append(head);
  for (const row of rows) {
    const tr = node('tr');
    for (const value of row) {
      const td = node('td');
      td.append(value instanceof Node ? value : document.createTextNode(String(value ?? '—')));
      tr.append(td);
    }
    body.append(tr);
  }
  t.append(thead, body);
  wrap.append(t);
  return wrap;
}

function renderResult() {
  document.querySelectorAll('[data-tab]').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === state.tab);
    b.setAttribute('aria-selected', String(b.dataset.tab === state.tab));
  });
  const target = $('result-content');
  target.replaceChildren();
  const r = state.job?.result;
  if (!r) {
    target.append(node('p', '분석이 완료되면 검증 가능한 결과가 표시됩니다.', 'empty'));
    return;
  }
  const c = r.collection;
  if (state.tab === 'findings') {
    target.append(node('p', '명시 버전 일치는 취약점 악용 가능성의 증명이 아닙니다. 불확실한 버전 범위와 누락된 버전은 별도 검토합니다.', 'section-note'));
    const assessments = new Map((r.decisions?.assessments || []).map(a => [a.finding_id, a]));
    const rank = {
      urgent: 0,
      high: 1,
      normal: 2,
      review: 3
    };
    const findings = [...c.findings].sort((a, b) => (rank[assessments.get(a.finding_id)?.priority] ?? 4) - (rank[assessments.get(b.finding_id)?.priority] ?? 4));
    target.append(table(['우선순위', '컴포넌트 / 버전', 'Advisory', '일치 근거', '원문'], findings.map(f => {
      const comp = node('div', f.component_name);
      comp.append(node('small', f.component_version || '버전 없음'));
      return [pill(assessments.get(f.finding_id)?.priority || '미검증'), comp, f.advisory_id, pill(f.match), button('근거 ' + f.evidence_ids.length + '건 →', () => showEvidence(f), 'text-button')];
    })));
    if (!findings.length) target.append(node('p', '이 스냅샷에서 후보가 발견되지 않았습니다. 전체 안전성은 보장하지 않습니다.', 'empty'));
  } else if (state.tab === 'inventory') {
    const dispositions = new Map(c.dispositions.map(d => [d.component_ref, d]));
    target.append(node('p', '미일치는 현재 스냅샷 안에서 후보를 찾지 못했다는 의미입니다.', 'section-note'), table(['이름', '버전', 'Package URL', '처리 상태'], c.sbom.components.map(x => [x.name, x.version, x.purl, pill(dispositions.get(x.bom_ref)?.status)])));
  } else if (state.tab === 'graph') {
    renderGraph(target, c);
  } else {
    target.append(pill(r.audit.passed ? 'success' : 'blocked'), node('p', r.audit.passed ? '근거·전체 항목 포함·영향 판정·정책 하한 검증 통과' : '검증 미통과', 'section-note'));
    if (r.audit.issues.length) target.append(table(['코드', '대상', '설명'], r.audit.issues.map(i => [i.code, i.target, i.message])));
    target.append(node('h3', '입력과 실행 설정'), node('p', 'SHA-256 · ' + r.input_sha256, 'hash'), node('pre', JSON.stringify({
      config: r.config,
      models: r.models,
      completion_tokens_reserved: r.completion_tokens_reserved,
      usage_complete: r.usage_complete,
      warnings: c.warnings
    }, null, 2)));
  }
}

function renderGraph(target, c) {
  target.append(node('p', '자산 → 구성요소, 구성요소 간 의존 관계. 최대 40개를 표시하며 전체 데이터는 ZIP의 graph.json에 있습니다.', 'section-note'));
  const ns = 'http://www.w3.org/2000/svg',
    svg = document.createElementNS(ns, 'svg'),
    comps = c.sbom.components.slice(0, 40),
    height = Math.max(150, comps.length * 54);
  svg.setAttribute('viewBox', `0 0 800 ${height}`);
  svg.setAttribute('class', 'graph');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '자산과 컴포넌트 의존 관계');
  const positions = new Map(comps.map((c, i) => [c.bom_ref, 27 + i * 54]));

  function element(tag, attrs, text) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = text;
    svg.append(e);
    return e;
  }
  for (const [i, c] of comps.entries()) element('line', {
    x1: 220,
    y1: height / 2,
    x2: 390,
    y2: 27 + i * 54
  });
  for (const [parent, children] of Object.entries(c.sbom?.dependencies || c.dependencies || {}))
    for (const child of children)
      if (positions.has(parent) && positions.has(child)) element('line', {
        x1: 720,
        y1: positions.get(parent),
        x2: 750,
        y2: positions.get(child)
      });
  element('rect', {
    x: 15,
    y: height / 2 - 24,
    width: 205,
    height: 48,
    rx: 9,
    class: 'root'
  });
  element('text', {
    x: 30,
    y: height / 2 + 4,
    class: 'root-text'
  }, 'SBOM · ' + c.sbom.asset_id.slice(0, 22));
  comps.forEach((comp, i) => {
    element('rect', {
      x: 390,
      y: i * 54 + 5,
      width: 330,
      height: 44,
      rx: 8
    });
    element('text', {
      x: 405,
      y: i * 54 + 32
    }, (comp.name + ' @ ' + (comp.version || '?')).slice(0, 49));
  });
  const wrap = node('div', undefined, 'table-wrap');
  wrap.append(svg);
  target.append(wrap);
  const edges = Object.entries(c.sbom.dependencies).flatMap(([parent, children]) => children.map(child => [parent, child]));
  if (edges.length) target.append(table(['상위 컴포넌트', '의존 대상'], edges));
}
async function showEvidence(f) {
  const target = $('evidence-content');
  target.replaceChildren(node('p', f.component_name + ' · ' + f.advisory_id), node('p', f.reason, 'help'));
  const buttons = node('div', undefined, 'evidence-list'),
    body = node('div');
  for (const id of f.evidence_ids) buttons.append(button(id.split(':')[0] + ' 원문', () => load(id)));
  target.append(buttons, body);
  $('evidence-dialog').showModal();
  async function load(id) {
    body.replaceChildren(node('p', '불러오는 중…', 'help'));
    try {
      const data = await api('jobs/' + state.selected + '/evidence/' + encodeURIComponent(id));
      body.replaceChildren(node('p', data.record.pointer, 'help'), node('p', 'SHA-256 · ' + data.record.sha256, 'hash'), node('pre', JSON.stringify(data.source, null, 2)));
    } catch (e) {
      body.replaceChildren(node('p', e.message, 'form-error'));
    }
  }
  await load(f.evidence_ids.find(x => x.startsWith('advisory:')) || f.evidence_ids[0]);
}

function renderReview() {
  const panel = $('review-panel');
  panel.replaceChildren();
  const j = state.job;
  if (j.review) {
    panel.append(node('h2', '최종 검토 기록'), pill(j.review.decision), node('p', j.review.reviewer + ' · ' + date(j.review.created_at), 'muted'), node('div', j.review.reason, 'review-record'), node('p', '검토 대상 SHA-256 · ' + j.review.reviewed_result_sha256, 'hash'));
    return;
  }
  const card = node('div', undefined, 'review-card'),
    info = node('div');
  info.append(node('h2', '사람의 검토로 마무리합니다'), node('p', '근거 원문과 판정을 확인한 뒤 최종 결정을 기록하세요. 패치·배포는 실행하지 않습니다.'));
  const b = button('최종 검토하기 →', () => {
    $('review-error').textContent = '';
    $('decision').options[0].disabled = j.state === 'blocked';
    $('decision').value = j.state === 'blocked' ? 'hold' : 'approve';
    $('review-dialog').showModal();
  }, 'primary');
  b.disabled = !j.result;
  card.append(info, b);
  panel.append(card);
}
document.querySelectorAll('dialog .close').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
$('new-run').addEventListener('click', () => showNew());
$('start-demo').addEventListener('click', () => showNew());
$('start-public').addEventListener('click', () => showNew('public-snapshot-case'));
$('search').addEventListener('input', renderList);
$('more').addEventListener('click', async () => {
  state.limit += 100;
  try {
    await refreshList();
  } catch (e) {
    notice(e.message);
  }
});
$('example').addEventListener('change', () => {
  $('upload-fields').hidden = $('example').value !== 'upload';
});
$('mode').addEventListener('change', () => {
  $('consent-label').hidden = $('mode').value !== 'llm';
});
$('download-example').addEventListener('click', async () => {
  try {
    saveJSON(await api('examples/rnaseq-case'), 'biosbom-case-example.json');
  } catch (e) {
    $('form-error').textContent = e.message;
  }
});
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => {
  state.tab = b.dataset.tab;
  renderResult();
}));
$('new-form').addEventListener('submit', async e => {
  e.preventDefault();
  const submit = $('submit-run');
  submit.disabled = true;
  $('form-error').textContent = '';
  try {
    let input;
    if ($('example').value === 'upload') {
      const file = $('upload').files[0];
      if (!file) throw new Error('Case JSON 파일을 선택하세요.');
      if (file.size > 2000000) throw new Error('파일은 2 MB 이하여야 합니다.');
      try {
        input = JSON.parse(await file.text());
      } catch {
        throw new Error('올바른 JSON 파일이 아닙니다.');
      }
    } else input = await api('examples/' + $('example').value);
    if ($('mode').value === 'llm' && !$('llm-consent').checked) throw new Error(errors.llm_consent_required);
    const result = await api('jobs', {
      case: input,
      request_key: $('new-form').dataset.key,
      llm_acknowledged: $('llm-consent').checked,
      config: {
        mode: $('mode').value,
        architecture: $('architecture').value,
        max_revisions: Number($('revisions').value),
        max_calls: Number($('calls').value),
        max_completion_tokens: Number($('budget').value),
        tokens_per_call: Number($('tokens').value),
        timeout_seconds: Number($('timeout').value)
      }
    });
    $('new-dialog').close();
    notice('');
    await refreshList();
    await selectJob(result.id);
  } catch (err) {
    $('form-error').textContent = err.message;
  } finally {
    submit.disabled = false;
  }
});
$('review-form').addEventListener('submit', async e => {
  e.preventDefault();
  const b = e.submitter;
  b.disabled = true;
  try {
    await api('jobs/' + state.selected + '/review', {
      decision: $('decision').value,
      reviewer: $('reviewer').value.trim(),
      reason: $('reason').value.trim()
    });
    $('review-dialog').close();
    await refreshJob();
  } catch (err) {
    $('review-error').textContent = err.message;
  } finally {
    b.disabled = false;
  }
});
async function poll() {
  if (state.busy || document.hidden) return;
  state.busy = true;
  try {
    await api('health');
    await refreshList();
    await refreshJob();
    $('connection').textContent = '로컬 연결됨';
    $('connection').className = 'pill success';
  } catch (e) {
    $('connection').textContent = '연결 확인 필요';
    $('connection').className = 'pill review';
    notice(e.message);
  } finally {
    state.busy = false;
  }
}
async function init() {
  try {
    state.session = await api('session');
    $('mode').options[1].disabled = !state.session.llm_configured;
    $('provider-note').textContent = state.session.llm_configured ? '서버에 모델 설정이 있습니다. 실제 연결 여부는 분석 실행 시 확인됩니다.' : 'LLM을 사용하려면 서버에서 BIOSBOM_MODEL과 연결 정보를 설정하세요. 규칙 기반 분석은 바로 사용할 수 있습니다.';
    await poll();
    setInterval(poll, 2000);
  } catch (e) {
    notice(e.message);
  }
}
init();
