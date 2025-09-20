import React from 'react';
import { render, screen } from '@testing-library/react';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('renders the default message when none is provided', () => {
    render(<EmptyState />);
    expect(screen.getByText('No data available.')).toBeInTheDocument();
  });

  it('renders a custom message', () => {
    render(<EmptyState message="Custom empty state" />);
    expect(screen.getByText('Custom empty state')).toBeInTheDocument();
  });
});
