import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react-native';
import { JobCard } from '../../components/JobCard';
import type { JobOrder } from '../../lib/api';

const baseJob: JobOrder = {
  id: 6,
  title: 'DevOps Engineer High-Tech',
  department: 'Engineering',
  seniority: 'mid',
  location_type: 'hybrid',
  salary_min: 60000,
  salary_max: 85000,
  salary_currency: 'EUR',
  description: null,
  requirements: null,
  nice_to_have: null,
  status: 'open',
  created_at: '2026-01-01T00:00:00Z',
};

describe('JobCard', () => {
  it('renders the title, seniority/department chips and the salary range', async () => {
    await render(<JobCard job={baseJob} onPress={() => {}} />);
    expect(screen.getByText('DevOps Engineer High-Tech')).toBeTruthy();
    expect(screen.getByText('Engineering')).toBeTruthy();
    // 'mid' maps to the "Medior" label (see lib/format.ts SENIORITY_LABELS).
    expect(screen.getByText('Medior')).toBeTruthy();
    expect(screen.getByText('€60k – €85k')).toBeTruthy();
  });

  it('shows the salary-unknown copy when no range is set', async () => {
    await render(<JobCard job={{ ...baseJob, salary_min: null, salary_max: null }} onPress={() => {}} />);
    expect(screen.getByText('Salaris in overleg')).toBeTruthy();
  });

  it('calls onPress when tapped', async () => {
    const onPress = jest.fn();
    await render(<JobCard job={baseJob} onPress={onPress} />);
    await fireEvent.press(screen.getByText('DevOps Engineer High-Tech'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
