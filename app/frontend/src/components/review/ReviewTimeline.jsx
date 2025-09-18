import React from 'react';

const statusLabels = {
  created: '리뷰 요청 생성',
  pending: '대기 중',
  processing: '패널 초기 분석 중',
  initial_turn_complete: '라운드 1 완료',
  rebuttal_turn_complete: '라운드 2 완료',
  synthesis_turn_complete: '라운드 3 완료',
  round4_turn_complete: '라운드 4 완료',
  no_new_arguments_stop: '추가 주장 없음으로 조기 종료',
  in_progress: '리뷰 진행 중',
  completed: '리뷰 완료',
  failed: '리뷰 실패',
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '시간 정보 없음';
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) {
    return '시간 정보 없음';
  }
  return date.toLocaleString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
    day: 'numeric',
  });
};

const ReviewTimeline = ({ statusEvents = [], personaEvents = {} }) => {
  const personas = Object.keys(personaEvents).filter((persona) => personaEvents[persona]?.length);

  if (statusEvents.length === 0 && personas.length === 0) {
    return null;
  }

  return (
    <section className="mb-8 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <div className="rounded-card border border-border bg-panel p-4">
        <h3 className="text-h3 text-text">리뷰 진행 상태</h3>
        <ol className="mt-3 space-y-3">
          {[...statusEvents].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0)).map((event, index) => (
            <li key={`${event.status}-${event.timestamp}-${index}`} className="flex items-start gap-3">
              <span className="mt-1 inline-flex h-2.5 w-2.5 flex-shrink-0 rounded-full bg-accent" aria-hidden />
              <div>
                <p className="text-sm font-semibold text-text">{statusLabels[event.status] || event.status}</p>
                <p className="text-xs text-muted">{formatTimestamp(event.timestamp)}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className="rounded-card border border-border bg-panel p-4">
        <h3 className="text-h3 text-text">패널 타임라인</h3>
        {personas.length === 0 ? (
          <p className="mt-3 text-sm text-muted">아직 패널 메시지가 수집되지 않았습니다.</p>
        ) : (
          <div className="mt-3 space-y-4">
            {personas.sort().map((persona) => (
              <div key={persona}>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-text">{persona}</p>
                  <span className="text-xs text-muted">{personaEvents[persona].length}건</span>
                </div>
                <ol className="relative mt-2 space-y-3 border-l border-border/60 pl-4">
                  {personaEvents[persona]
                    .slice()
                    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
                    .map((event) => (
                      <li key={event.id} className="text-sm text-muted">
                        <div className="absolute -left-2 top-1 h-3 w-3 rounded-full border border-accent bg-panel" aria-hidden />
                        <p className="font-medium text-text">
                          {event.round ? `라운드 ${event.round}` : '응답'}
                          <span className="ml-2 text-xs text-muted">{formatTimestamp(event.timestamp)}</span>
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-muted">
                          {event.preview}
                        </p>
                      </li>
                    ))}
                </ol>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

export default ReviewTimeline;
