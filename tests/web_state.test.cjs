// Targeted state/concurrency tests; these do not replace real browser validation.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function setup() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      hidden: false, textContent: '', value: '', listeners: {}, closed: false,
      addEventListener(type, fn) { this.listeners[type] = fn; },
      close() { this.closed = true; }
    });
    return elements.get(id);
  };
  const ctx = vm.createContext({document: {getElementById: get, querySelectorAll: () => []},
    fetch: () => { throw Error('unexpected network'); }, setTimeout, clearTimeout});
  const source = fs.readFileSync(path.join(__dirname, '../src/biosbom_agentkg/web/static/app.js'), 'utf8');
  vm.runInContext(source.replace(/\ninit\(\);\s*$/, ''), ctx);
  vm.runInContext('renderList=()=>{}; renderJob=()=>{}; renderPipeline=()=>{};', ctx);
  return {ctx, get, run: text => vm.runInContext(text, ctx)};
}
test('late record response cannot replace a newer selection', async () => {
  const {ctx, get, run} = setup();
  const pending = {};
  ctx.stubAPI = key => new Promise(resolve => { pending[key] = resolve; });
  run('api=stubAPI');
  const first = run('selectJob("old")');
  assert.equal(get('workspace').hidden, true);
  const second = run('selectJob("new")');
  pending['jobs/new']({id:'new'}); pending['jobs/new/events']([]); await second;
  pending['jobs/old']({id:'old'}); pending['jobs/old/events']([]); await first;
  assert.equal(run('state.job.id'), 'new');
  assert.equal(get('workspace').hidden, false);
  assert.equal(get('review-dialog').closed, true);
});
test('failed record load keeps previous action controls hidden', async () => {
  const {ctx, get, run} = setup();
  ctx.stubAPI = async () => {throw Error('load failed');}; run('api=stubAPI');
  await run('selectJob("broken")');
  assert.equal(get('workspace').hidden, true);
  assert.equal(get('notice').textContent, 'load failed');
});
test('review submits the record the dialog was opened for', async () => {
  const {ctx, get, run} = setup(); const paths=[];
  ctx.stubAPI = async p => {paths.push(p);return {};};
  run('api=stubAPI; refreshJob=async()=>{}; state.selected="other"; state.reviewJob={id:"reviewed"};');
  get('reviewer').value='demo'; get('reason').value='checked'; get('decision').value='hold';
  await get('review-form').listeners.submit({preventDefault(){},submitter:{}});
  assert.deepEqual(paths,['jobs/reviewed/review']);
});
test('non-JSON response gets a safe actionable message', async () => {
  const {ctx, run} = setup();
  ctx.fetch = async () => ({json:async()=>{throw Error('private upstream detail');}});
  await assert.rejects(run('api("health")'), error => !error.message.includes('private') && error.message.includes('서버 응답'));
});
test('evidence source clicks keep the newest response and original record', async () => {
  const {ctx,get,run} = setup();
  const created=[], pending={}, actions=[];
  ctx.fakeNode = (tag,text) => {
    const n={tag,text,children:[],append(...xs){this.children.push(...xs);},replaceChildren(...xs){this.children=xs;}};
    created.push(n); return n;
  };
  ctx.fakeButton = (label,fn) => {actions.push(fn);return {};};
  ctx.stubAPI = key => new Promise(resolve=>{pending[key]=resolve;});
  get('evidence-content').replaceChildren=()=>{}; get('evidence-content').append=()=>{};
  get('evidence-dialog').showModal=()=>{};
  run('node=fakeNode;button=fakeButton;api=stubAPI;state.selected="source-job";');
  const first=run('showEvidence({component_name:"demo",advisory_id:"synthetic",reason:"test",evidence_ids:["advisory:one","context:two"]})');
  run('state.selected="other-job"');
  const second=actions[1]();
  pending['jobs/source-job/evidence/context%3Atwo']({record:{pointer:'newer',sha256:'hash'},source:{}});
  await second;
  pending['jobs/source-job/evidence/advisory%3Aone']({record:{pointer:'older',sha256:'hash'},source:{}});
  await first;
  const body=created.find(n=>n.tag==='div' && n.children.some(x=>x.text==='newer'));
  assert.ok(body);
  assert.equal(body.children[0].text,'newer');
});
