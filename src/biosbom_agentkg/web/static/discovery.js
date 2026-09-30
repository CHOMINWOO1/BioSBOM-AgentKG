/* Public source data is rendered only as text; never executed or treated as instructions. */
function renderPlan(target, plan) {
  target.replaceChildren(node('p', '패치 후보는 제공된 advisory 범위만 확인했습니다. 릴리스 존재·호환성·다른 취약점은 추가 검토가 필요합니다. 승인해도 설치나 배포는 실행되지 않습니다.', 'help'));
  if (!plan.items.length) target.append(node('p', '개선안 생성 대상이 없습니다. 취약점이 없거나 안전하다는 뜻은 아닙니다.'));
  for (const item of plan.items) {
    const article = node('article', undefined, 'panel');
    article.append(node('h3', item.package + ' · ' + (item.installed_version || '버전 불명')),
      node('p', item.candidate_version ? '검토할 업그레이드 후보: ' + item.candidate_version : '자동 후보를 정할 수 없어 수동 조사가 필요합니다.'),
      node('p', '관련 advisory: ' + item.advisories.join(', '), 'help'));
    if (item.parent_components.length) article.append(node('p', '의존하는 구성요소: ' + item.parent_components.join(', '), 'help'));
    const details = node('details'); details.append(node('summary', '근거와 확인 항목'), node('pre', JSON.stringify(item, null, 2)));
    article.append(details); target.append(article);
  }
  target.append(button('개선안 JSON 다운로드 ↓', () => saveJSON(plan, 'biosbom-remediation-plan.json')));
}
let planSequence = 0;
async function showRemediation(id) {
  const sequence = ++planSequence;
  $('plan-content').replaceChildren(node('p', '개선안을 확인하고 있습니다…'));
  $('plan-dialog').showModal();
  try {
    const plan = await api('jobs/' + id + '/plan');
    if (sequence === planSequence && $('plan-dialog').open) renderPlan($('plan-content'), plan);
  } catch (e) {
    if (sequence === planSequence) $('plan-content').textContent = e.message;
  }
}
$('open-discovery').addEventListener('click', () => $('discovery-dialog').showModal());
$('discovery-form').addEventListener('submit', async event => {
  event.preventDefault();
  const submit = $('discovery-submit');
  if (submit.disabled) return;
  submit.disabled = true;
  $('discovery-error').textContent = '';
  $('discovery-results').replaceChildren(node('p', 'OSV 조회 중 · 최대 약 45초 소요됩니다.'));
  try {
    if (!$('discovery-consent').checked) throw new Error(errors.public_lookup_consent_required);
    const input = await readFileJSON('discovery-file', 'SBOM 또는 Case');
    const caseInput = input.sbom ? input : {name: '공개 자료 조회', synthetic: false, sbom: input, advisories: [], intelligence: [],
      context: {asset_id: 'uploaded-environment', criticality: 5, data_sensitivity: 5, exposure: 5, security_control_score: 5}};
    const result = await api('discover', {case: caseInput, public_lookup_acknowledged: true});
    const acquisition = result.acquisition;
    const target = $('discovery-results');
    target.replaceChildren(node('h3', `조회 완료 ${acquisition.queried_components}/${acquisition.total_components}개 · ${acquisition.status === 'complete' ? '전체 조회' : '일부 미조회'}`),
      node('p', '미조회·조회 결과 없음은 안전 판정이 아닙니다. 조회 원자료는 아래에서 저장하세요. 분석에는 현재 수집된 스냅샷만 사용됩니다.', 'help'));
    for (const query of acquisition.queries.filter(q => q.status !== 'queried')) target.append(node('p', query.component_ref + ': ' + query.reason, 'form-error'));
    target.append(button('조회 원자료·개선안 저장 ↓', () => saveJSON(result, 'biosbom-discovery.json')),
      button('Case JSON 저장 ↓', () => saveJSON(acquisition.case, 'biosbom-discovered-case.json')));
    if (!acquisition.analysis_ready) target.append(node('p', '조회 누락을 해결하거나 입력 크기를 줄인 뒤 분석하세요. 현재 원자료는 다운로드할 수 있습니다.', 'help'));
    if (acquisition.analysis_ready) target.append(button('이 자료로 분석 구성', () => {
      state.discoveryCase = acquisition.case;
      if (!$('prepared-option')) {const option = node('option', '공개 조회로 준비한 입력'); option.id = 'prepared-option'; option.value = 'prepared'; $('example').append(option);}
      $('discovery-dialog').close();
      $('new-run').click(); $('example').value = 'prepared'; syncInputFields();
      $('input-preview').hidden = false;
      $('input-preview').textContent = 'SBOM만 올렸다면 자산 맥락은 기본값 5입니다. 실제 평가 전 Case JSON의 맥락 값을 수정해 다시 업로드하세요.';
    }));
    const planTarget = node('section'); renderPlan(planTarget, result.plan); target.append(planTarget);
  } catch (e) {
    $('discovery-error').textContent = e.message;
    $('discovery-results').replaceChildren();
  } finally { submit.disabled = false; }
});
