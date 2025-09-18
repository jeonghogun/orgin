import React, { useEffect, useMemo, useRef } from 'react';

const AVATAR_COLORS = [
  'bg-accent',
  'bg-blue-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-rose-500',
  'bg-slate-500',
];

const getInitials = (persona = '') => {
  if (!persona) return 'AI';
  const matches = persona.trim().split(/\s+/).slice(0, 2);
  const initials = matches.map((part) => part.charAt(0)).join('');
  return initials || persona.charAt(0) || 'AI';
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '';
  try {
    return new Date(timestamp * 1000).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (error) {
    return '';
  }
};

const TranscriptContent = ({ content, isTrimmed }) => {
  if (!content) {
    return <p className="text-sm text-muted">내용이 아직 제공되지 않았습니다.</p>;
  }

  let formattedContent = null;
  if (!isTrimmed) {
    try {
      const parsed = JSON.parse(content);
      formattedContent = (
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-muted">
          {JSON.stringify(parsed, null, 2)}
        </pre>
      );
    } catch (error) {
      formattedContent = null;
    }
  }

  if (!formattedContent) {
    formattedContent = (
      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-text">
        {content}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {formattedContent}
      {isTrimmed && (
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted">
          메시지가 길어 일부만 표시됩니다.
        </p>
      )}
    </div>
  );
};

const DebateTranscript = ({
  messages = [],
  onRequestRound,
  canRequestRound = false,
  isRequestingRound = false,
  totalRoundsCompleted = 0,
  maxRounds = 4,
  isDebateConcluded = false,
}) => {
  const transcriptEndRef = useRef(null);

  const roundGroups = useMemo(() => {
    const groups = [];
    const indexByKey = new Map();

    messages.forEach((message) => {
      const round = Number.isFinite(message?.round) ? Number(message.round) : null;
      const key = round === null ? 'intro' : `round-${round}`;
      if (!indexByKey.has(key)) {
        indexByKey.set(key, groups.length);
        groups.push({ round, messages: [] });
      }
      const groupIndex = indexByKey.get(key);
      groups[groupIndex].messages.push(message);
    });

    return groups;
  }, [messages]);

  const personaColors = useMemo(() => {
    const colorMap = new Map();
    let paletteIndex = 0;

    roundGroups.forEach((group) => {
      group.messages.forEach((message) => {
        const persona = message?.persona || 'AI Panelist';
        if (!colorMap.has(persona)) {
          const color = AVATAR_COLORS[paletteIndex % AVATAR_COLORS.length];
          colorMap.set(persona, color);
          paletteIndex += 1;
        }
      });
    });

    return colorMap;
  }, [roundGroups]);

  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages.length]);

  const buttonDisabled = !canRequestRound || isRequestingRound || isDebateConcluded;
  const buttonLabel = isDebateConcluded
    ? 'Debate Concluded'
    : isRequestingRound
      ? 'Requesting...'
      : 'Continue Debate';

  return (
    <section className="rounded-card border border-border bg-panel overflow-hidden">
      <header className="flex flex-col gap-1 border-b border-border/60 px-4 py-3">
        <h2 className="text-h2 text-text">토론 기록</h2>
        <p className="text-meta text-muted">
          진행 라운드 {Math.min(totalRoundsCompleted, maxRounds)} / {maxRounds}
        </p>
      </header>

      <div className="px-4 py-4">
        {roundGroups.length === 0 ? (
          <div className="py-10 text-center text-body text-muted">
            아직 토론 메시지가 도착하지 않았습니다.
          </div>
        ) : (
          <ol className="space-y-6" aria-live="polite">
            {roundGroups.map((group) => (
              <li key={group.round ?? 'intro'} className="space-y-4">
                <div className="flex items-center gap-3 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  <span className="h-px flex-1 bg-border" aria-hidden />
                  <span className="rounded-full border border-border bg-panel-elev px-3 py-1 text-meta text-muted">
                    {group.round ? `라운드 ${group.round}` : '사전 안내'}
                  </span>
                  <span className="h-px flex-1 bg-border" aria-hidden />
                </div>
                <ol className="space-y-4">
                  {group.messages.map((message) => {
                    const persona = message?.persona || 'AI Panelist';
                    const colorClass = personaColors.get(persona) || 'bg-accent';
                    return (
                      <li key={message.message_id} className="flex gap-3">
                        <div
                          className={`mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${colorClass}`}
                          aria-hidden
                        >
                          {getInitials(persona)}
                        </div>
                        <div className="flex-1 rounded-card border border-border/60 bg-panel-elev px-4 py-3 shadow-sm">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <div className="text-sm font-semibold text-text">{persona}</div>
                            <div className="text-xs text-muted">{formatTimestamp(message.timestamp)}</div>
                          </div>
                          <TranscriptContent content={message.content} isTrimmed={message.isTrimmed} />
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </li>
            ))}
          </ol>
        )}
        <div ref={transcriptEndRef} />
      </div>

      <footer className="flex flex-col gap-3 border-t border-border/60 bg-panel-elev px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted">
          최대 {maxRounds}라운드까지 추가 진행을 요청할 수 있습니다.
        </p>
        <button
          type="button"
          onClick={onRequestRound}
          disabled={buttonDisabled}
          className="inline-flex items-center justify-center rounded-button bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:bg-accent-weak disabled:cursor-not-allowed disabled:opacity-60"
        >
          {buttonLabel}
        </button>
      </footer>
    </section>
  );
};

export default DebateTranscript;
