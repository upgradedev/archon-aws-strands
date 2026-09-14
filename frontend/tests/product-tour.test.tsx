import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductTour } from '../src/ProductTour';

const links = Object.fromEntries(['dashboard', 'records', 'incoming', 'workspace', 'journey', 'history'].map(page => [page, `#/${page}?invoice=TEST-7`]));

test('six explicit stops explain real tools and consent, with no automatic page navigation', async () => {
  location.hash = '/records';
  const close = vi.fn();
  render(<ProductTour page="records" live blocked={false} links={links} onClose={close} />);
  expect(screen.getByRole('heading', { name: /See the business/ })).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Previous stop' })).toBeDisabled();
  expect(screen.getByRole('link', { name: 'Open Dashboard' })).toHaveAttribute('href', '#/dashboard?invoice=TEST-7');
  for (const title of [/Follow a number/, /Know how new/, /Let Strands/, /Approve only/, /Read the recorded/]) {
    await userEvent.click(screen.getByRole('button', { name: 'Next stop' }));
    expect(screen.getByRole('heading', { name: title })).toHaveFocus();
    expect(location.hash).toBe('#/records');
  }
  expect(screen.getByRole('region', { name: 'Product tour' })).toHaveTextContent('SES acceptance is not proof of mailbox arrival');
  await userEvent.click(screen.getByRole('button', { name: 'Finish tour' }));
  expect(close).toHaveBeenCalledOnce();
});

test('blocked navigation is absent, simulation is honest and Escape is cleaned up', async () => {
  const close = vi.fn();
  const mounted = render(<ProductTour page="records" live={false} blocked links={links} onClose={close} />);
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Product tour' })).toHaveTextContent('scripted model and simulated outbox');
  expect(screen.getByText(/Page navigation is paused/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Next stop' }));
  expect(screen.getByText(/You are on Records/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Previous stop' }));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(close).toHaveBeenCalledOnce();
  mounted.unmount(); fireEvent.keyDown(window, { key: 'Escape' });
  expect(close).toHaveBeenCalledOnce();
});
