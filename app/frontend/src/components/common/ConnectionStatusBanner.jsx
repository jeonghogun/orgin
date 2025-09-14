import React from 'react';

const ConnectionStatusBanner = ({ status }) => {
  if (status === 'connected' || status === 'connecting' || status === 'idle') {
    return null;
  }

  const getBannerStyle = () => {
    switch (status) {
      case 'reconnecting':
        return 'bg-yellow-500/80 text-white';
      case 'disconnected':
      case 'failed':
        return 'bg-red-500/80 text-white';
      default:
        return 'bg-gray-500/80 text-white';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'reconnecting':
        return '실시간 연결이 끊겼습니다. 재연결 중...';
      case 'disconnected':
        return '실시간 연결이 끊겼습니다.';
      case 'failed':
        return '실시간 서버에 연결할 수 없습니다. 페이지를 새로고침 해주세요.';
      default:
        return `알 수 없는 연결 상태: ${status}`;
    }
  };

  return (
    <div className={`w-full text-center p-1 text-sm ${getBannerStyle()}`}>
      {getStatusText()}
    </div>
  );
};

export default ConnectionStatusBanner;
