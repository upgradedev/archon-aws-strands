const sha = /^[0-9a-f]{40}$/;
const number = /^[1-9][0-9]*$/;
const verdict = document.getElementById('verdict');
const detail = document.getElementById('detail');
const facts = document.getElementById('facts');
const run = document.getElementById('run');

function show(state, title, message) {
  verdict.dataset.state = state;
  verdict.textContent = title;
  detail.textContent = message;
}
async function read(path) {
  const response = await fetch(path, { cache: 'no-store', credentials: 'omit' });
  if (!response.ok) throw new Error('Unavailable evidence');
  return response.json();
}
function valid(record) {
  const counts = record?.counts;
  return record?.schema_version === 1 && record.application === 'Archon' && record.environment === 'live_aws'
    && record.status === 'AUTOMATED_JOURNEYS_PASSED' && record.human_uat === 'NOT_RUN'
    && typeof record.frontend_commit === 'string' && sha.test(record.frontend_commit)
    && typeof record.backend_commit === 'string' && sha.test(record.backend_commit)
    && typeof record.run_id === 'string' && number.test(record.run_id)
    && typeof record.run_attempt === 'string' && number.test(record.run_attempt)
    && record.run_url === `https://github.com/upgradedev/archon-aws-strands/actions/runs/${record.run_id}/attempts/${record.run_attempt}`
    && typeof record.observed_at === 'string' && Number.isFinite(Date.parse(record.observed_at))
    && ['preflight', 'journeys', 'postflight'].every(key => record.checks?.[key] === 'success')
    && Number.isInteger(counts?.total) && counts.total >= 34 && counts.passed === counts.total
    && counts.failed === 0 && counts.skipped === 0 && record.mode === 'synthetic'
    && record.live_send === false && record.live_model === false;
}
try {
  const [release, health, record] = await Promise.all([read('/release.json'), read('/api/health'), read('/acceptance.json')]);
  if (!valid(record) || !sha.test(release?.commit ?? '') || !sha.test(health?.commit ?? '')) throw new Error('Invalid evidence');
  for (const [label, value] of [['Frontend tested', record.frontend_commit], ['Backend tested', record.backend_commit], ['Observed at', record.observed_at], ['Browser cases', `${record.counts.passed}/${record.counts.total}; no failures or skips`]]) {
    const term = document.createElement('dt'), description = document.createElement('dd');
    term.textContent = label; description.textContent = value; facts.append(term, description);
  }
  run.href = record.run_url; run.hidden = false;
  if (release.commit !== record.frontend_commit || health.commit !== record.backend_commit) {
    show('stale', 'Historical evidence only', 'The served frontend or backend differs from this record. Current release acceptance is not established.');
  } else if (health.status !== 'ok' || health.mode !== 'synthetic' || health.live_send !== false || health.live_model !== false
      || health.model !== 'LedgerScriptModel' || health.provider !== 'SimulatedProvider' || health.orchestration !== 'Strands') {
    show('unknown', 'Runtime scope does not match', 'Current runtime mode differs from the tested synthetic scope. No current acceptance is claimed.');
  } else {
    show('passed', 'Automated journeys passed for this release pair', 'Both served revisions match the recorded run. This is automated evidence, not human signoff.');
  }
} catch {
  facts.replaceChildren(); run.hidden = true; run.removeAttribute('href');
  show('unknown', 'Current acceptance unavailable', 'Evidence is missing, pending, unreadable or invalid. This does not establish a pass or a product failure. Open the testbook for the scope and historical records.');
}
