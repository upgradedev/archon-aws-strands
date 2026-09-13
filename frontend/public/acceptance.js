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
async function read(path, html = false) {
  const response = await fetch(path, { cache: 'no-store', credentials: 'omit' });
  if (!response.ok) throw new Error('Unavailable evidence');
  if (!html) return response.json();
  const document = new DOMParser().parseFromString(await response.text(), 'text/html');
  const markers = document.querySelectorAll('meta[name="application-commit"]');
  return markers.length === 1 ? markers[0].getAttribute('content') : null;
}
function valid(record) {
  const counts = record?.counts;
  const providers = record?.provider_checks;
  const synthetic = record?.schema_version === 1 && record.status === 'AUTOMATED_JOURNEYS_PASSED'
    && counts?.total >= 34 && record.mode === 'synthetic' && record.live_send === false && record.live_model === false;
  const live = record?.schema_version === 2 && record.status === 'CONTROLLED_PROVIDER_JOURNEYS_PASSED'
    && counts?.total === 3 && record.mode === 'controlled-live' && record.live_send === true && record.live_model === true
    && ['model_calls', 'input_tokens', 'output_tokens'].every(k => Number.isInteger(providers?.[k]) && providers[k] > 0)
    && providers.emails_accepted === 3 && providers.delivery_proven === false
    && record.limits === 'Fictional business data; actual Bedrock and controlled SES provider acceptance. No mailbox arrival, bank settlement, independent model superiority or human UAT proven.';
  return (synthetic || live) && record.application === 'Archon' && record.environment === 'live_aws'
    && record.human_uat === 'NOT_RUN'
    && typeof record.frontend_commit === 'string' && sha.test(record.frontend_commit)
    && typeof record.backend_commit === 'string' && sha.test(record.backend_commit)
    && typeof record.run_id === 'string' && number.test(record.run_id)
    && typeof record.run_attempt === 'string' && number.test(record.run_attempt)
    && record.run_url === `https://github.com/upgradedev/archon-aws-strands/actions/runs/${record.run_id}/attempts/${record.run_attempt}`
    && typeof record.observed_at === 'string' && Number.isFinite(Date.parse(record.observed_at))
    && ['preflight', 'journeys', 'postflight'].every(key => record.checks?.[key] === 'success')
    && Number.isInteger(counts?.total) && counts.passed === counts.total
    && counts.failed === 0 && counts.skipped === 0;
}
try {
  const [release, health, record, served] = await Promise.all([read('/release.json'), read('/api/health'), read('/acceptance.json'), read('/', true)]);
  if (!valid(record) || !sha.test(release?.commit ?? '') || !sha.test(health?.commit ?? '') || !sha.test(served ?? '')) throw new Error('Invalid evidence');
  for (const [label, value] of [['Frontend tested', record.frontend_commit], ['Backend tested', record.backend_commit], ['Observed at', record.observed_at], ['Browser cases', `${record.counts.passed}/${record.counts.total}; no failures or skips`]]) {
    const term = document.createElement('dt'), description = document.createElement('dd');
    term.textContent = label; description.textContent = value; facts.append(term, description);
  }
  run.href = record.run_url; run.hidden = false;
  const live = record.schema_version === 2;
  const matches = health.status === 'ok' && health.mode === record.mode
    && health.live_send === record.live_send && health.live_model === record.live_model
    && health.model === (live ? 'eu.anthropic.claude-opus-5' : 'LedgerScriptModel')
    && health.provider === (live ? 'SES-controlled-recipient' : 'SimulatedProvider') && health.orchestration === 'Strands';
  if (release.commit !== record.frontend_commit || served !== record.frontend_commit || health.commit !== record.backend_commit) {
    show('stale', 'Historical evidence only', 'The served frontend or backend differs from this record. Current release acceptance is not established.');
  } else if (!matches) {
    show('unknown', 'Runtime scope does not match', 'Current runtime mode differs from the recorded provider scope. No current acceptance is claimed.');
  } else {
    show('passed', live ? 'Controlled real-provider journeys passed for this release pair' : 'Automated journeys passed for this release pair',
      live ? 'Actual model usage and three SES acceptances were recorded across desktop, mobile and WebKit. Mailbox arrival and human signoff remain unproven.'
        : 'Both served revisions match the recorded run. This is automated evidence, not human signoff.');
  }
} catch {
  facts.replaceChildren(); run.hidden = true; run.removeAttribute('href');
  show('unknown', 'Current acceptance unavailable', 'Evidence is missing, pending, unreadable or invalid. This does not establish a pass or a product failure. Open the testbook for the scope and historical records.');
}
