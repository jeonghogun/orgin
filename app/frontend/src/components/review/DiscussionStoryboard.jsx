import React, { useMemo } from 'react';

const ROUND_DETAILS = {
  1: {
    title: '라운드 1 — 독립 관점',
    description: '각 모델이 자신의 시각으로 주제를 제시합니다.',
  },
  2: {
    title: '라운드 2 — 상호 검토',
    description: '다른 패널 발언을 인용하며 찬반과 보완을 주고받습니다.',
  },
  3: {
    title: '라운드 3 — 공동 정리',
    description: '합의와 쟁점을 조율하며 실행안을 다듬습니다.',
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

const STANCE_STYLES = {
  support: {
    label: '공감',
    className: 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-500',
  },
  challenge: {
    label: '반박',
    className: 'border border-rose-500/40 bg-rose-500/10 text-rose-500',
  },
  build: {
    label: '보완',
    className: 'border border-sky-500/40 bg-sky-500/10 text-sky-500',
  },
  clarify: {
    label: '질문',
    className: 'border border-amber-500/40 bg-amber-500/10 text-amber-500',
  },
  default: {
    label: '참조',
    className: 'border border-slate-500/40 bg-slate-500/10 text-slate-500',
  },
};

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

const truncate = (text = '', limit = 160) => {
  if (!text) return '';
  const squashed = text.replace(/\s+/g, ' ').trim();
  if (squashed.length <= limit) return squashed;
  return `${squashed.slice(0, limit - 1).trim()}…`;
};

const DiscussionStoryboard = ({ messages = [] }) => {
  const personaOrder = useMemo(() => {
    const seen = new Set();
    const order = [];
    messages.forEach((message) => {
      const payloadPersona = message?.structuredPayload?.panelist;
      const fallbackPersona = message?.persona;
      const persona = payloadPersona || fallbackPersona || 'AI Panelist';
      if (!seen.has(persona)) {
        seen.add(persona);
        order.push(persona);
      }
    });
    return order;
  }, [messages]);

  const personaColorMap = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, AVATAR_COLORS[idx % AVATAR_COLORS.length]);
    });
    return map;
  }, [personaOrder]);

  const personaAlignMap = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, idx % 2 === 0 ? 'left' : 'right');
    });
    return map;
  }, [personaOrder]);

  const roundGroups = useMemo(() => {
    const map = new Map();
    messages.forEach((message) => {
      if (!message) return;
      const roundValue = Number.isFinite(message.round)
        ? message.round
        : Number.isFinite(message?.structuredPayload?.round)
        ? message.structuredPayload.round
        : null;
      if (!roundValue) return;
      if (!map.has(roundValue)) {
        map.set(roundValue, []);
      }
      const payload = message.structuredPayload || {};
      const persona = payload.panelist || message.persona || 'AI Panelist';
      map.get(roundValue).push({
        persona,
        payload,
        timestamp: message.timestamp,
        rawContent: message.rawContent || message.content,
        messageId: message.message_id,
      });
    });
    map.forEach((items, round) => {
      items.sort((a, b) => {
        const indexA = personaOrder.indexOf(a.persona);
        const indexB = personaOrder.indexOf(b.persona);
        if (indexA !== indexB) {
          return (indexA === -1 ? Number.MAX_SAFE_INTEGER : indexA) -
            (indexB === -1 ? Number.MAX_SAFE_INTEGER : indexB);
        }
        return (a.timestamp || 0) - (b.timestamp || 0);
      });
      map.set(round, items);
    });
    return map;
  }, [messages, personaOrder]);

  const rounds = useMemo(() => Array.from(roundGroups.keys()).sort((a, b) => a - b), [roundGroups]);

  if (rounds.length === 0) {
    return (
      <section className="rounded-card border border-border bg-panel p-6 text-center text-sm text-muted">
        아직 토론 메시지가 도착하지 않았습니다.
      </section>
    );
  }

  const renderReferences = (references = [], align = 'left') => {
    if (!Array.isArray(references) || references.length === 0) {
      return null;
    }

    return (
      <ul
        className={`mt-2 flex flex-col gap-1 text-xs text-muted ${align === 'right' ? 'items-end' : 'items-start'}`}
      >
        {references.map((ref, idx) => {
          if (!ref) return null;
          const stanceStyle = STANCE_STYLES[ref.stance] || STANCE_STYLES.default;
          const quote = ref.quote ? `“${truncate(ref.quote, 80)}”` : '';
          const roundInfo = Number.isFinite(ref.round) ? ` 라운드 ${ref.round}` : '';
          return (
            <li key={`ref-${idx}`} className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'justify-end' : ''}`}>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${stanceStyle.className}`}>
                {stanceStyle.label}
              </span>
              <span className="text-muted">{ref.panelist || '패널'}{roundInfo}{quote ? ` — ${quote}` : ''}</span>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <section className="rounded-card border border-border bg-panel p-6">
      <header className="mb-6 space-y-1">
        <h2 className="text-h2 text-text">토론 스토리보드</h2>
        <p className="text-sm text-muted">
          JSON 메시지를 채팅 말풍선으로 해석해, 세 패널이 실제로 대화하는 흐름을 담았습니다. 라운드 구획은 타임라인으로, 발언은 실시간 대화처럼 이어집니다.
        </p>
      </header>

      <div className="space-y-10">
        {rounds.map((round) => {
          const roundInfo = ROUND_DETAILS[round] || {
            title: `라운드 ${round}`,
            description: '토론 내용을 확인하세요.',
          };
          const entries = roundGroups.get(round) || [];

          return (
            <section key={round} className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted">
                  {roundInfo.title}
                </div>
                <div className="h-px flex-1 bg-border/60" />
              </div>
              <p className="text-xs text-muted">{roundInfo.description}</p>

              <div className="space-y-6">
                {entries.map((entry) => {
                  const { persona, payload, timestamp, rawContent, messageId } = entry;
                  const colorClass = personaColorMap.get(persona) || 'bg-slate-500';
                  const align = personaAlignMap.get(persona) || 'left';
                  const stanceList = Array.isArray(payload?.references) ? payload.references : [];
                  const keyTakeaway = payload?.key_takeaway;
                  const messageText = payload?.message;

                  return (
                    <article
                      key={`${round}-${persona}-${messageId}`}
                      className={`flex gap-3 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}
                    >
                      <div
                        className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${colorClass}`}
                      >
                        {getInitials(persona)}
                      </div>

                      <div className={`flex flex-col gap-2 ${align === 'right' ? 'items-end' : 'items-start'} max-w-3xl`}>
                        <div className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'flex-row-reverse justify-end' : ''}`}>
                          <p className="text-sm font-semibold text-text">{persona}</p>
                          <span className="text-xs text-muted">라운드 {round}</span>
                          {timestamp && (
                            <time className="text-xs text-muted" dateTime={String(timestamp)}>
                              {formatTimestamp(timestamp)}
                            </time>
                          )}
                        </div>

                        <div
                          className={`w-full rounded-2xl border border-border/60 px-4 py-3 text-sm leading-relaxed text-text ${align === 'right' ? 'bg-panel' : 'bg-panel-elev'}`}
                        >
                          {messageText ? (
                            <p className="whitespace-pre-line">{messageText}</p>
                          ) : (
                            <p className="text-muted">구조화된 메시지를 표시할 수 없어 원문을 확인하세요.</p>
                          )}
                          {!messageText && rawContent && (
                            <p className="mt-2 text-xs text-muted">{truncate(rawContent, 140)}</p>
                          )}
                        </div>

                        {keyTakeaway && (
                          <span
                            className={`inline-flex items-center rounded-full bg-border/20 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted ${align === 'right' ? 'justify-end' : ''}`}
                          >
                            {keyTakeaway}
                          </span>
                        )}

                        {renderReferences(stanceList, align)}

                        {payload?.no_new_arguments && (
                          <span className="inline-flex items-center rounded-full border border-border/60 bg-panel px-2 py-0.5 text-[11px] text-muted">
                            새로운 주장은 없지만 이전 입장을 재확인했습니다.
                          </span>
                        )}
                      </div>
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
