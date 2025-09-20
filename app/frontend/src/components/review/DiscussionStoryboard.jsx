import React, { useMemo } from 'react';

const ROUND_DETAILS = {
  1: {
    title: '라운드 1 — 독립 관점',
    description: '각 모델이 자신의 시각으로 주제를 해석합니다.',
  },
  2: {
    title: '라운드 2 — 상호 검토',
    description: '서로의 발언을 인용하며 동의/반박 포인트를 조율합니다.',
  },
  3: {
    title: '라운드 3 — 공동 정리',
    description: '합의된 실행 계획과 남은 쟁점을 정리합니다.',
  },
};

const AVATAR_COLORS = [
  'bg-accent',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-slate-500',
];

const getInitials = (name = '') => {
  if (!name) return 'AI';
  return name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '';
  try {
    return new Date(timestamp * 1000).toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (error) {
    return '';
  }
};

const renderRoundContent = (round, payload = {}) => {
  if (!payload || typeof payload !== 'object') {
    return (
      <p className="text-sm text-muted">구조화된 데이터가 없어 원문을 참고하세요.</p>
    );
  }

  if (payload.no_new_arguments) {
    return (
      <p className="rounded-md bg-panel border border-border px-3 py-2 text-xs text-muted">
        새로운 주장 없이 이전 라운드 결론을 유지했습니다.
      </p>
    );
  }

  if (round === 1) {
    return (
      <div className="space-y-3 text-sm text-text">
        {payload.key_takeaway && (
          <p className="rounded-md bg-panel-elev px-3 py-2 text-text font-semibold">
            {payload.key_takeaway}
          </p>
        )}
        {Array.isArray(payload.arguments) && payload.arguments.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">핵심 논거</p>
            <ul className="mt-1 space-y-1 text-sm text-text">
              {payload.arguments.map((item, idx) => (
                <li key={`arg-${idx}`}>• {item}</li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(payload.risks) && payload.risks.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">주의해야 할 위험</p>
            <ul className="mt-1 space-y-1 text-sm text-text">
              {payload.risks.map((item, idx) => (
                <li key={`risk-${idx}`}>• {item}</li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(payload.opportunities) && payload.opportunities.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">기회 요소</p>
            <ul className="mt-1 space-y-1 text-sm text-text">
              {payload.opportunities.map((item, idx) => (
                <li key={`opp-${idx}`}>• {item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (round === 2) {
    return (
      <div className="space-y-3 text-sm text-text">
        {Array.isArray(payload.agreements) && payload.agreements.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">공감한 지점</p>
            <ul className="mt-1 space-y-1 text-sm text-text">
              {payload.agreements.map((item, idx) => (
                <li key={`agree-${idx}`}>• {item}</li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(payload.disagreements) && payload.disagreements.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">반박 또는 보완</p>
            <ul className="mt-1 space-y-2 text-sm text-text">
              {payload.disagreements.map((item, idx) => (
                <li key={`disagree-${idx}`}
                  className="rounded-md border border-border/60 bg-panel-elev px-3 py-2">
                  {item.point && (
                    <p className="font-medium">{item.point}</p>
                  )}
                  {item.reasoning && (
                    <p className="text-xs text-muted">{item.reasoning}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(payload.additions) && payload.additions.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">추가 제안</p>
            <ul className="mt-1 space-y-2 text-sm text-text">
              {payload.additions.map((item, idx) => (
                <li key={`addition-${idx}`}
                  className="rounded-md border border-border/60 bg-panel px-3 py-2">
                  {item.point && (
                    <p className="font-medium">{item.point}</p>
                  )}
                  {item.reasoning && (
                    <p className="text-xs text-muted">{item.reasoning}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm text-text">
      {payload.executive_summary && (
        <p className="rounded-md bg-panel-elev px-3 py-2 text-text font-semibold">
          {payload.executive_summary}
        </p>
      )}
      {payload.conclusion && (
        <p className="whitespace-pre-wrap rounded-md border border-border/60 bg-panel px-3 py-2 text-sm text-text">
          {payload.conclusion}
        </p>
      )}
      {Array.isArray(payload.recommendations) && payload.recommendations.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted">실행 제안</p>
          <ol className="mt-1 list-decimal list-inside space-y-1 text-sm text-text">
            {payload.recommendations.map((item, idx) => (
              <li key={`rec-${idx}`}>{item}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
};

const DiscussionStoryboard = ({ messages = [] }) => {
  const personaOrder = useMemo(() => {
    const seen = new Set();
    const order = [];
    messages.forEach((message) => {
      const persona = message?.persona || 'AI Panelist';
      if (!seen.has(persona)) {
        seen.add(persona);
        order.push(persona);
      }
    });
    return order;
  }, [messages]);

  const roundGroups = useMemo(() => {
    const map = new Map();
    messages.forEach((message) => {
      if (!message) return;
      const roundKey = Number.isFinite(message.round) ? message.round : null;
      if (!roundKey) return;
      if (!map.has(roundKey)) {
        map.set(roundKey, new Map());
      }
      map.get(roundKey).set(message.persona || 'AI Panelist', message);
    });
    return map;
  }, [messages]);

  const personaColorMap = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, AVATAR_COLORS[idx % AVATAR_COLORS.length]);
    });
    return map;
  }, [personaOrder]);

  const rounds = useMemo(() => {
    return Array.from(roundGroups.keys()).sort((a, b) => a - b);
  }, [roundGroups]);

  if (rounds.length === 0) {
    return (
      <section className="rounded-card border border-border bg-panel p-6 text-center text-sm text-muted">
        아직 토론 메시지가 도착하지 않았습니다.
      </section>
    );
  }

  return (
    <section className="rounded-card border border-border bg-panel p-6">
      <header className="mb-6 space-y-1">
        <h2 className="text-h2 text-text">토론 스토리보드</h2>
        <p className="text-sm text-muted">
          라운드별로 각 모델의 발언을 카드 형태로 정리했습니다. 발언은 JSON 구조를 기반으로 렌더링됩니다.
        </p>
      </header>

      <div className="space-y-10">
        {rounds.map((round) => {
          const roundInfo = ROUND_DETAILS[round] || {
            title: `라운드 ${round}`,
            description: '토론 내용을 확인하세요.',
          };
          const roundMap = roundGroups.get(round) || new Map();

          return (
            <section key={round} className="space-y-4">
              <div>
                <h3 className="text-h3 text-text">{roundInfo.title}</h3>
                <p className="text-xs text-muted">{roundInfo.description}</p>
              </div>

              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {personaOrder.map((persona) => {
                  const message = roundMap.get(persona);
                  const payload = message?.structuredPayload;
                  const colorClass = personaColorMap.get(persona) || 'bg-slate-500';

                  return (
                    <article
                      key={`${round}-${persona}`}
                      className="flex flex-col gap-3 rounded-card border border-border bg-panel-elev p-4 shadow-sm"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className={`flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold text-white ${colorClass}`}
                          >
                            {getInitials(persona)}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-text">{persona}</p>
                            <p className="text-xs text-muted">라운드 {round}</p>
                          </div>
                        </div>
                        {message?.timestamp && (
                          <time className="text-xs text-muted" dateTime={String(message.timestamp)}>
                            {formatTimestamp(message.timestamp)}
                          </time>
                        )}
                      </div>

                      {message ? (
                        renderRoundContent(round, payload)
                      ) : (
                        <p className="text-sm text-muted">이 라운드에 대한 발언이 아직 없습니다.</p>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
};

export default DiscussionStoryboard;
