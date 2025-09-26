import React, { useMemo } from 'react';

const ROUND_LABELS = {
  1: {
    title: '1단계 — 독립 관점',
    description: '각 패널이 자신의 시각을 자유롭게 펼칩니다.',
  },
  2: {
    title: '2단계 — 상호 검토',
    description: '다른 패널의 주장에 공감하거나 반박하며 논지를 다듬습니다.',
  },
  3: {
    title: '3단계 — 공동 정리',
    description: '합의와 남은 쟁점을 정리하며 실행 초안을 맞춥니다.',
  },
  4: {
    title: '최종 단계 — 요약 정리',
    description: '합의 사항과 다음 단계를 명확하게 정리합니다.',
  },
};

const AVATAR_PALETTE = [
  'bg-accent',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-slate-500',
];

const stanceLabel = {
  support: '공감',
  challenge: '반박',
  build: '보완',
  clarify: '질문',
};

const formatTime = (timestamp) => {
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

const normalizeRoundNumber = (message) => {
  if (!message) return null;
  if (typeof message.round === 'number') {
    return message.round;
  }
  if (message.structuredPayload?.round) {
    return message.structuredPayload.round;
  }
  return null;
};

const TriadDiscussionFeed = ({ messages = [] }) => {
  const personaOrder = useMemo(() => {
    const seen = new Set();
    const order = [];
    messages.forEach((message) => {
      if (!message) return;
      const persona = message.persona || message.structuredPayload?.panelist;
      if (persona && !seen.has(persona)) {
        seen.add(persona);
        order.push(persona);
      }
    });
    return order;
  }, [messages]);

  const personaColors = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, index) => {
      map.set(persona, AVATAR_PALETTE[index % AVATAR_PALETTE.length]);
    });
    return map;
  }, [personaOrder]);

  const rounds = useMemo(() => {
    const roundMap = new Map();

    messages.forEach((message) => {
      if (!message) return;
      const roundNumber = normalizeRoundNumber(message);
      if (!roundNumber) return;

      const payload = message.structuredPayload || {};
      const persona = message.persona || payload.panelist || '패널';
      const timestamp = message.timestamp;
      const keyTakeaway = payload.key_takeaway || payload.final_position || '';
      const mainText =
        payload.message ||
        payload.final_position ||
        message.content ||
        '';
      const references = Array.isArray(payload.references)
        ? payload.references
        : [];

      const consensus = Array.isArray(payload.consensus_highlights)
        ? payload.consensus_highlights
        : [];
      const openQuestions = Array.isArray(payload.open_questions)
        ? payload.open_questions
        : [];
      const nextSteps = Array.isArray(payload.next_steps)
        ? payload.next_steps
        : [];

      if (!roundMap.has(roundNumber)) {
        roundMap.set(roundNumber, []);
      }

      roundMap.get(roundNumber).push({
        id: message.message_id,
        persona,
        timestamp,
        mainText,
        keyTakeaway,
        references,
        consensus,
        openQuestions,
        nextSteps,
        noNewArguments: Boolean(payload.no_new_arguments),
      });
    });

    const sortedEntries = Array.from(roundMap.entries()).sort((a, b) => a[0] - b[0]);
    return sortedEntries.map(([roundNumber, entries]) => ({
      roundNumber,
      entries: entries.sort((a, b) => {
        const personaIndexA = personaOrder.indexOf(a.persona);
        const personaIndexB = personaOrder.indexOf(b.persona);
        if (personaIndexA !== personaIndexB) {
          const safeA = personaIndexA === -1 ? Number.MAX_SAFE_INTEGER : personaIndexA;
          const safeB = personaIndexB === -1 ? Number.MAX_SAFE_INTEGER : personaIndexB;
          return safeA - safeB;
        }
        return (a.timestamp || 0) - (b.timestamp || 0);
      }),
    }));
  }, [messages, personaOrder]);

  if (rounds.length === 0) {
    return (
      <section className="rounded-card border border-border bg-panel p-6 text-center text-sm text-muted">
        아직 토론 메시지가 도착하지 않았습니다.
      </section>
    );
  }

  return (
    <section className="rounded-card border border-border bg-panel p-6 space-y-8">
      <header className="space-y-1">
        <h2 className="text-h2 text-text">세 패널의 라이브 토론</h2>
        <p className="text-sm text-muted">
          복잡한 타임라인 대신, 단계별로 세 패널이 어떤 이야기를 주고받았는지 바로 확인할 수 있습니다.
        </p>
      </header>

      {rounds.map(({ roundNumber, entries }) => {
        const meta = ROUND_LABELS[roundNumber] || {
          title: `토론 단계 ${roundNumber}`,
          description: '',
        };

        return (
          <article key={`round-${roundNumber}`} className="space-y-4">
            <div className="flex flex-col gap-1">
              <h3 className="text-h3 text-text">{meta.title}</h3>
              {meta.description && (
                <p className="text-sm text-muted">{meta.description}</p>
              )}
            </div>

            <div className="space-y-3">
              {entries.map((entry) => {
                const badgeColor = personaColors.get(entry.persona) || 'bg-accent';
                const timeLabel = formatTime(entry.timestamp);
                return (
                  <div
                    key={entry.id}
                    className="rounded-card border border-border/70 bg-panel-elev px-4 py-3 shadow-sm"
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <span className={`inline-flex items-center justify-center rounded-full px-3 py-1 text-xs font-semibold text-white ${badgeColor}`}>
                        {entry.persona}
                      </span>
                      {timeLabel && <span className="text-xs text-muted">{timeLabel}</span>}
                      {entry.noNewArguments && (
                        <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
                          추가 발언 없음
                        </span>
                      )}
                    </div>

                    <div className="mt-3 space-y-2 text-body text-text">
                      {entry.mainText && (
                        <p className="whitespace-pre-line leading-relaxed">{entry.mainText}</p>
                      )}
                      {entry.keyTakeaway && (
                        <p className="rounded-md bg-border/10 px-3 py-2 text-sm text-muted">
                          핵심: {entry.keyTakeaway}
                        </p>
                      )}

                      {entry.references.length > 0 && (
                        <div className="text-sm text-muted">
                          <p className="font-semibold text-text">참조</p>
                          <ul className="mt-1 space-y-1">
                            {entry.references.map((ref, index) => (
                              <li key={`ref-${entry.id}-${index}`} className="flex flex-wrap gap-1">
                                <span className="rounded-full border border-border/60 px-2 py-0.5 text-[11px] font-medium text-muted">
                                  {stanceLabel[ref.stance] || '참조'}
                                </span>
              <span className="text-sm text-muted">
                {ref.panelist} · 단계 {ref.round}{ref.quote ? ` — “${ref.quote.trim()}”` : ''}
              </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {roundNumber === 4 && (
                        <div className="space-y-2 text-sm text-muted">
                          {entry.consensus.length > 0 && (
                            <div>
                              <p className="font-semibold text-text">합의 강조</p>
                              <ul className="mt-1 list-disc list-inside space-y-1">
                                {entry.consensus.map((item, idx) => (
                                  <li key={`consensus-${entry.id}-${idx}`}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {entry.openQuestions.length > 0 && (
                            <div>
                              <p className="font-semibold text-text">남은 질문</p>
                              <ul className="mt-1 list-disc list-inside space-y-1">
                                {entry.openQuestions.map((item, idx) => (
                                  <li key={`open-${entry.id}-${idx}`}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {entry.nextSteps.length > 0 && (
                            <div>
                              <p className="font-semibold text-text">다음 단계</p>
                              <ul className="mt-1 list-disc list-inside space-y-1">
                                {entry.nextSteps.map((item, idx) => (
                                  <li key={`next-${entry.id}-${idx}`}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </article>
        );
      })}
    </section>
  );
};

export default TriadDiscussionFeed;
