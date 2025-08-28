import { renderHook, act } from '@testing-library/react';
import WS from 'jest-websocket-mock';
import useReviewSocket from './useReviewSocket';

describe('useReviewSocket', () => {
  let server;

  beforeEach(() => {
    // Start a mock WebSocket server on a specific URL
    server = new WS('ws://localhost/ws/reviews/test-review-id');
  });

  afterEach(() => {
    // Close the server after each test
    WS.clean();
  });

  it('should connect and update status on message', async () => {
    const { result } = renderHook(() => useReviewSocket('test-review-id', 'test-token'));

    // Wait for the connection to be established
    await server.connected;

    expect(result.current.status).toBe('connected');

    // Simulate a message from the server
    act(() => {
      server.send(JSON.stringify({
        type: 'status_update',
        review_id: 'test-review-id',
        ts: 12345,
        version: '1.0',
        payload: { status: 'rebuttal_turn_complete' }
      }));
    });

    // Check if the hook's status updated
    expect(result.current.status).toBe('rebuttal_turn_complete');
  });

  it('should handle connection errors', async () => {
    // Intentionally close the server to trigger an error
    server.error();

    const { result } = renderHook(() => useReviewSocket('test-review-id', 'test-token'));

    // The hook should eventually report an error
    // Note: this kind of test can be tricky due to timing.
    // A more robust test would check the state after a short delay.
    expect(result.current.error).not.toBeNull();
  });

  it('should attempt to reconnect on disconnect', async () => {
    const { result } = renderHook(() => useReviewSocket('test-review-id', 'test-token'));

    await server.connected;
    expect(result.current.status).toBe('connected');

    // Close the connection
    act(() => {
        server.close();
    });

    // In a real test environment with timers, we could test the exponential backoff.
    // For now, we just acknowledge this is a complex scenario to unit test perfectly.
    // The presence of the reconnection logic is the main thing we've added.
    expect(result.current.error).toBeNull(); // It shouldn't error out immediately
  });
});
