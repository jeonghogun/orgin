import React, { useCallback, useMemo, useState } from 'react';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../lib/apiClient';
import { useAppContext } from '../context/AppContext';
import toast from 'react-hot-toast';
import ExportRoomModal from '../components/modals/ExportRoomModal';

const Sub = ({ roomId, onToggleReview, createRoomMutation }) => {
  const { sidebarOpen } = useAppContext();
  
  // 룸 정보 조회
  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: async () => {
      if (!roomId) return null;
      const response = await apiClient.get(`/api/rooms/${roomId}`);
      return response.data;
    },
    enabled: !!roomId,
  });

  const [isExportModalOpen, setExportModalOpen] = useState(false);

  const handleExport = useCallback(async ({ format = 'json', includeInstructions = false }) => {
    if (!roomId) {
      toast.error('내보낼 세부 룸을 찾을 수 없습니다.');
      return;
    }

    try {
      const response = await apiClient.get(`/api/rooms/${roomId}/export`, {
        params: {
          format,
          include_instructions: includeInstructions,
        },
        responseType: 'blob',
      });

      const contentDisposition = response.headers?.['content-disposition'] || '';
      const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
      const fallbackExtension = format === 'markdown' ? 'md' : 'json';
      const filename = match ? match[1] : `export_room_${roomId}.${fallbackExtension}`;

      const contentType = response.headers?.['content-type'] || (format === 'markdown' ? 'text/markdown' : 'application/json');
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: contentType });
      const downloadUrl = window.URL.createObjectURL(blob);

      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      toast.success('내보내기 파일 다운로드를 시작했습니다.');
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || '내보내기 중 오류가 발생했습니다.';
      toast.error(detail);
    }
  }, [roomId]);

  const headerActions = useMemo(() => {
    if (!roomData) {
      return [];
    }

    return [
      {
        label: '검토 시작',
        onClick: () => onToggleReview(roomData),
        variant: 'primary',
      },
      {
        label: '내보내기',
        onClick: () => setExportModalOpen(true),
        variant: 'secondary',
      }
    ];
  }, [onToggleReview, roomData]);

  return (
    <div className="flex flex-col h-full bg-bg relative overflow-hidden">
      {/* 헤더 - 고정 */}
      <div className="flex-shrink-0 z-10">
        <RoomHeader
          title={roomData?.name || "세부 룸"}
          subtitle={roomData?.description || "세부 대화"}
          showBackButton={true}
          actions={headerActions}
        />
      </div>

      {/* 메시지 목록 - 독립적인 스크롤 영역 */}
      <div className="flex-1 overflow-y-auto px-4 pb-20 min-h-0">
          <div className="max-w-3xl mx-auto">
            <MessageList
              roomId={roomId}
              currentRoom={roomData}
              createRoomMutation={createRoomMutation}
            />
          </div>
        </div>

      {/* 채팅 입력창 - 화면 전체 하단에 고정 */}
      <div 
        className="fixed bottom-0 border-t border-border bg-panel p-4 z-10 transition-all duration-150"
        style={{ 
          left: sidebarOpen ? '280px' : '0px', 
          right: '0px' 
        }}
      >
        <div className="max-w-3xl mx-auto">
            <ChatInput
              roomId={roomId}
              roomData={roomData}
              createRoomMutation={createRoomMutation}
            />
          </div>
        </div>

      <ExportRoomModal
        isOpen={isExportModalOpen}
        onClose={() => setExportModalOpen(false)}
        onConfirm={(options) => {
          setExportModalOpen(false);
          handleExport(options);
        }}
      />
    </div>
  );
};

export default Sub;
