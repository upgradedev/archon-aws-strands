import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Activity } from '../src/Activity';
import { Approvals } from '../src/Approvals';
import { Dashboard } from '../src/Dashboard';
import { Documents } from '../src/Documents';
import { DraftEvidence } from '../src/DraftEvidence';
import { Welcome } from '../src/Welcome';
import { WorkspaceMode } from '../src/WorkspaceMode';
import type { Workspace } from '../src/types';
import * as api from '../src/api';
import { filled, received } from './fixtures';

vi.mock('../src/api', async original => ({ ...await original<typeof api>(), request: vi.fn() }));
beforeEach(() => { vi.mocked(api.request).mockReset(); });

const modes = ['live', 'synthetic', 'retained simulation'] as const;
type Mode = typeof modes[number];

function workspace(mode: Mode): Workspace {
  const data = filled();
  data.live_available = mode !== 'synthetic';
  if (mode === 'live') {
    data.live = { model: true, mail: true, data: 'fictional business examples', job: null };
    data.reader = 'Amazon Bedrock semantic extraction; source checks before posting';
    data.provider = 'Amazon SES; restricted verified test recipient';
    data.graph = null;
    data.draft!.recipient = 'verified-test@example.test';
  }
  return data;
}

test.each(modes)('%s draft evidence distinguishes email execution from bank evidence', mode => {
  const data = workspace(mode);
  render(<DraftEvidence data={data} invoiceId="JN-4410" />);
  const evidence = screen.getByRole('region', { name: 'Draft ledger evidence' });
  expect(evidence).toHaveTextContent('not independent bank verification');
  if (mode === 'live') {
    expect(evidence).toHaveTextContent('Explicit approval can send real email through controlled Amazon SES.');
    expect(evidence).toHaveTextContent('Provider acceptance is not delivery proof.');
    expect(evidence).not.toHaveTextContent('Delivery remains simulated.');
  } else {
    expect(evidence).toHaveTextContent('Delivery remains simulated.');
    expect(evidence).not.toHaveTextContent('can send real email');
  }
});

test.each(modes)('%s overview keeps fictional data distinct from session providers', mode => {
  const data = workspace(mode);
  render(<><Dashboard data={data} stale={false} /><WorkspaceMode live={!!data.live} available={data.live_available} /></>);
  expect(screen.getByText(mode === 'live'
    ? /All fictional business records in this session/ : /All records in this synthetic session/)).toBeInTheDocument();
  expect(screen.getByText(mode === 'live'
    ? /Fictional examples · real Bedrock and Strands/ : /Synthetic examples · real Strands graph with scripted model/)).toBeInTheDocument();
  expect(screen.getByText(mode === 'live'
    ? /Email can be sent through controlled SES after approval/ : /Email delivery is simulated/)).toBeInTheDocument();
  if (mode === 'retained simulation') {
    expect(screen.getByRole('region', { name: 'Older simulation workspace' }))
      .toHaveTextContent('Your saved records and simulated receipts have not been converted into live activity.');
  } else {
    expect(screen.queryByRole('region', { name: 'Older simulation workspace' })).not.toBeInTheDocument();
  }
});

test.each(modes)('%s records keep the fictional text boundary and actual reader visible', mode => {
  const mutate = vi.fn();
  render(<Documents data={workspace(mode)} busy={false} mutate={mutate} route="/records?intake=open" />);
  const editor = screen.getByRole('textbox', { name: /Email headers and body/ });
  expect(editor).toHaveAccessibleDescription(/Synthetic data only: fictional business examples, even with real providers/);
  expect(editor).toHaveAccessibleDescription(/English plain text only; no bank feed or OCR/);
  expect(screen.getByText(mode === 'live' ? /Real Bedrock semantic extraction/ : /No live model call/)).toBeInTheDocument();
  expect(screen.getByRole('group', { name: 'Load a synthetic sample' })).toBeInTheDocument();
  expect(mutate).not.toHaveBeenCalled();
});

test.each(modes)('%s approval keeps exact consent and matches its linked evidence', async mode => {
  const data = workspace(mode);
  const mutate = vi.fn().mockResolvedValue(false);
  render(<Approvals data={data} busy={false} mutate={mutate} mode="draft" />);
  const live = mode === 'live';
  const approval = screen.getByRole('button', { name: live
    ? 'Approve exact draft · send real email' : 'Approve exact draft · simulate' });
  expect(approval).toBeDisabled();
  expect(screen.getByText(data.draft!.body)).toBeInTheDocument();
  if (live) {
    expect(screen.queryByText(/Delivery remains simulated/)).not.toBeInTheDocument();
    expect(screen.getByText(/Provider acceptance is not delivery proof/)).toBeInTheDocument();
  } else {
    expect(screen.getByText(/Delivery remains simulated/)).toBeInTheDocument();
    expect(screen.getByText(/No message is sent to this address/)).toBeInTheDocument();
  }
  expect(mutate).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('checkbox', { name: live
    ? /I authorize this real email to the verified test recipient/ : /I authorize a simulated send only/ }));
  expect(approval).toBeEnabled();
  await userEvent.click(approval);
  expect(mutate).toHaveBeenCalledExactlyOnceWith('/approve', live
    ? { fingerprint: data.draft!.fingerprint, live_send_consent: 'real-email' }
    : { fingerprint: data.draft!.fingerprint });
});

test.each(modes)('%s history and export preserve acceptance without claiming arrival', async mode => {
  const data = received(workspace(mode));
  const receipt = data.receipts[0];
  if (mode === 'live') {
    receipt.message_id = 'ses-accepted-test-id';
    receipt.to_address = data.draft!.recipient;
  }
  const retained = JSON.stringify(data);
  const text = `${mode === 'live' ? 'FICTIONAL BUSINESS DATA / restricted SES' : 'SYNTHETIC SESSION / simulated outbox'}\nRecorded provider outcomes: ${JSON.stringify(data.receipts)}\nArrival unproven`;
  const load = vi.fn().mockResolvedValue({ revision: data.revision, commit: 'source-sha', text });
  const view = render(<Activity data={data} loadEvidence={load} />);
  expect(screen.getByText(mode === 'live'
    ? 'Session provider: controlled Amazon SES' : 'Session provider: simulated outbox')).toBeInTheDocument();
  expect(view.container).not.toHaveTextContent('Real sending requires a separate operator configuration');
  const record = screen.getByRole('article');
  expect(record).toHaveTextContent(mode === 'live' ? 'SES · provider-accepted' : 'Simulated · provider-accepted');
  expect(within(record).getByText(receipt.message_id!)).toBeInTheDocument();
  expect(record).toHaveTextContent(mode === 'live'
    ? 'Unproven unless separately confirmed by delivery evidence' : 'Unproven · no real email sent');
  if (mode === 'live') {
    expect(view.container).toHaveTextContent('Arrival remains unproven in this session record.');
    expect(view.container).not.toHaveTextContent('No real email was sent');
  } else {
    expect(view.container).toHaveTextContent('Current provider availability does not convert its saved receipts into real email.');
  }
  expect(view.container).toHaveTextContent('Exporting preserves recorded provider outcomes; it does not prove bank settlement or email arrival.');
  expect(load).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Prepare evidence bundle' }));
  const download = await screen.findByRole('link', { name: 'Download readable evidence' });
  expect(download).toHaveAttribute('href', `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`);
  expect(load).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(data)).toBe(retained);
});

test.each([true, false])('welcome provider availability %s does not relabel a saved session', async live => {
  vi.mocked(api.request).mockResolvedValue({ live });
  render(<Welcome />);
  await waitFor(() => expect(screen.queryByText(/Checking provider availability/)).not.toBeInTheDocument());
  if (live) {
    expect(screen.getByText(/Saved simulation workspaces keep their original provider mode/)).toBeInTheDocument();
    expect(screen.getByText(/Real Bedrock AI · controlled real email · fictional business examples/)).toBeInTheDocument();
  } else {
    expect(screen.getByText(/Synthetic demo · scripted model · simulated email/)).toBeInTheDocument();
  }
  expect(api.request).toHaveBeenCalledExactlyOnceWith('/providers', null);
});
