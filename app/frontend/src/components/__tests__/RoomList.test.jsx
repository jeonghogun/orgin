import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RoomList from '../RoomList';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const mockApiClient = {
  get: jest.fn(),
  patch: jest.fn(),
};

jest.mock('@tanstack/react-query', () => ({
  useQuery: jest.fn(),
  useMutation: jest.fn(),
  useQueryClient: jest.fn(),
}));

jest.mock('../../lib/apiClient', () => ({
  __esModule: true,
  default: mockApiClient,
}));

describe('RoomList', () => {
  beforeEach(() => {
    useQuery.mockReset();
    useMutation.mockReset();
    useQueryClient.mockReset();
    useMutation.mockReturnValue({ mutate: jest.fn() });
    useQueryClient.mockReturnValue({ invalidateQueries: jest.fn() });
    mockApiClient.get.mockReset();
    mockApiClient.patch.mockReset();
  });

  it('shows a loading indicator while rooms are being fetched', () => {
    useQuery.mockReturnValue({ data: null, error: null, isLoading: true });

    render(<RoomList onRoomSelect={jest.fn()} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders rooms and allows selecting nested rooms', async () => {
    useQuery.mockReturnValue({
      data: [
        { room_id: 'room-1', name: 'Main Room', parent_id: null },
        { room_id: 'room-2', name: 'Child Room', parent_id: 'room-1' },
      ],
      error: null,
      isLoading: false,
    });

    const onRoomSelect = jest.fn();
    const user = userEvent.setup();

    render(<RoomList onRoomSelect={onRoomSelect} />);

    expect(screen.getByText('Main Room')).toBeInTheDocument();
    expect(screen.getByText('Child Room')).toBeInTheDocument();

    await user.click(screen.getByText('Child Room'));
    expect(onRoomSelect).toHaveBeenCalledWith('room-2');
  });
});
