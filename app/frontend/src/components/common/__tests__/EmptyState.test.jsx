import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('renders the default heading and helper tips when no props are provided', () => {
    render(<EmptyState />);
    expect(screen.getByText('표시할 데이터가 아직 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('새 메시지를 작성하거나 파일을 업로드해보세요.')).toBeInTheDocument();
  });

  it('renders custom content and fires actions', () => {
    const onClick = jest.fn();
    render(
      <EmptyState
        heading="테스트 비어 있음"
        message="설명을 추가합니다."
        tips={['첫 번째 팁']}
        actions={[{ label: '다시 시도', onClick }]}
      />
    );

    expect(screen.getByText('테스트 비어 있음')).toBeInTheDocument();
    expect(screen.getByText('설명을 추가합니다.')).toBeInTheDocument();
    fireEvent.click(screen.getByText('다시 시도'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
