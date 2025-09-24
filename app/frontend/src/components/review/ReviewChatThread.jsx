import React, { useMemo } from 'react';

const COLOR_PALETTE = [
  'bg-accent',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-slate-500',
];

const STANCE_LABELS = {
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
  if (!timestamp) return null;
  try {
    return new Date(timestamp * 1000).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (error) {
    return null;
  }
};

const buildConversation = (messages) => {
  return messages
    .map((message) => {
      if (!message?.message_id) return null;
      const payload = message.structuredPayload || {};
      const persona =
        message.persona ||
        payload.panelist ||
        payload.persona ||
        '패널';
      const text =
        payload.message ||
        payload.final_position ||
        message.rawContent ||
        message.content ||
        '';
      if (!text.trim()) return null;
      return {
        id: message.message_id,
        persona,
        timestamp: message.timestamp,
        text,
        keyTakeaway: payload.key_takeaway || payload.final_position || '',
        references: Array.isArray(payload.references) ? payload.references : [],
        noNewArguments: Boolean(payload.no_new_arguments),
      };
    })
    .filter(Boolean)
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
};

const ReviewChatThread = ({ messages = [] }) => {
  const conversation = useMemo(() => buildConversation(messages), [messages]);

  const personaOrder = useMemo(() => {
    const seen = new Set();
    const order = [];
    conversation.forEach((entry) => {
      if (!seen.has(entry.persona)) {
        seen.add(entry.persona);
        order.push(entry.persona);
      }
    });
    return order;
  }, [conversation]);

  const personaColors = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, COLOR_PALETTE[idx % COLOR_PALETTE.length]);
    });
    return map;
  }, [personaOrder]);

  const personaAlignment = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, idx % 2 === 0 ? 'left' : 'right');
    });
    return map;
  }, [personaOrder]);

  if (conversation.length === 0) {
    return (
      <section className="rounded-card border border-border bg-panel p-6 text-center text-sm text-muted">
        아직 패널 대화가 기록되지 않았습니다.
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
          const stance = STANCE_LABELS[ref.stance] || {
            label: '참조',
            className: 'border border-slate-500/40 bg-slate-500/10 text-slate-500',
          };
          return (
            <li key={`ref-${idx}`} className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'justify-end' : ''}`}>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${stance.className}`}>
                {stance.label}
              </span>
              <span className="text-muted">
                {ref.panelist || '패널'}
                {ref.quote ? ` — “${String(ref.quote).slice(0, 80)}”` : ''}
              </span>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <section className="rounded-card border border-border bg-panel p-6">
      <header className="mb-6 space-y-1">
        <h2 className="text-h2 text-text">단톡방 토론 흐름</h2>
        <p className="text-sm text-muted">
          패널들의 모든 발언을 시간순으로 나열해 실제 채팅처럼 읽을 수 있습니다.
        </p>
      </header>

      <div className="flex flex-col gap-6">
        {conversation.map((entry) => {
          const align = personaAlignment.get(entry.persona) || 'left';
          const colorClass = personaColors.get(entry.persona) || 'bg-accent';
          const timestampLabel = formatTimestamp(entry.timestamp);

          return (
            <article
              key={entry.id}
              className={`flex gap-3 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}
            >
              <div
                className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${colorClass}`}
              >
                {getInitials(entry.persona)}
              </div>

              <div className={`flex flex-col gap-2 ${align === 'right' ? 'items-end' : 'items-start'} max-w-3xl`}>
                <div className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'flex-row-reverse justify-end' : ''}`}>
                  <p className="text-sm font-semibold text-text">{entry.persona}</p>
                  {timestampLabel && <time className="text-xs text-muted">{timestampLabel}</time>}
                  {entry.noNewArguments && (
                    <span className="rounded-full border border-border/60 bg-panel px-2 py-0.5 text-[11px] text-muted">
                      추가 발언 없음
                    </span>
                  )}
                </div>

                <div
                  className={`w-full rounded-2xl border border-border/60 px-4 py-3 text-sm leading-relaxed text-text ${align === 'right' ? 'bg-panel' : 'bg-panel-elev'}`}
                >
                  <p className="whitespace-pre-line">{entry.text}</p>
                </div>

                {entry.keyTakeaway && (
                  <span
                    className={`inline-flex items-center rounded-full bg-border/20 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted ${align === 'right' ? 'justify-end' : ''}`}
                  >
                    {entry.keyTakeaway}
                  </span>
                )}

                {renderReferences(entry.references, align)}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};

export default ReviewChatThread;
