import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { MatchRing } from '../../components/MatchRing';

describe('MatchRing', () => {
  it('renders the rounded score percentage', async () => {
    await render(<MatchRing score={87.6} />);
    expect(screen.getByText('88%')).toBeTruthy();
  });

  it('clamps scores above 100 and below 0', async () => {
    await render(<MatchRing score={140} />);
    expect(screen.getByText('100%')).toBeTruthy();
  });

  it('clamps negative scores to 0', async () => {
    await render(<MatchRing score={-20} />);
    expect(screen.getByText('0%')).toBeTruthy();
  });

  it('renders an optional label', async () => {
    await render(<MatchRing score={72} label="match" />);
    expect(screen.getByText('72%')).toBeTruthy();
    expect(screen.getByText('match')).toBeTruthy();
  });
});
