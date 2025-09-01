import React, { useState, useEffect } from 'react';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const Review = ({ reviewId, onBackToSub }) => {
  const [reviewData, setReviewData] = useState(null);

  // 검토 데이터 조회
  const { data: review, isLoading } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: async () => {
      const response = await axios.get(`/api/reviews/${reviewId}`);
      return response.data;
    },
    enabled: !!reviewId,
  });

  // ESC 키로 뒤로가기
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onBackToSub();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onBackToSub]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text">검토 데이터를 불러오는 중...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-bg">
      {/* 헤더 - 고정 */}
      <RoomHeader
        title={`검토: ${review?.title || '검토'}`}
        subtitle={review?.description || 'AI 검토 결과'}
        showBackButton={true}
        onBack={onBackToSub}
      />

      {/* 검토 리포트 - 스크롤 가능 */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {review?.report && (
          <div className="mb-6">
            <h2 className="text-h1 text-text mb-4">검토 리포트</h2>
            <div className="bg-panel border border-border rounded-card p-4">
              <pre className="text-body text-text whitespace-pre-wrap">{review.report}</pre>
            </div>
          </div>
        )}

        {/* 메시지 목록 */}
        <MessageList roomId={review?.room_id} />
      </div>

      {/* 채팅 입력창 - 항상 하단 고정 */}
      <div className="border-t border-border bg-panel p-4">
        <ChatInput roomId={review?.room_id} />
      </div>
    </div>
  );
};

export default Review;
