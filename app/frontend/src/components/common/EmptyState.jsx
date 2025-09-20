import React from 'react';

const EmptyState = ({
  heading,
  message = '표시할 데이터가 아직 없습니다.',
  icon = '🧭',
  tips,
  actions = [],
}) => {
  const resolvedHeading = heading || message;
  const resolvedMessage = heading ? message : '';
  const defaultTips = [
    '새 메시지를 작성하거나 파일을 업로드해보세요.',
    '좌측 패널에서 새 룸을 만들면 협업을 시작할 수 있어요.',
  ];
  const resolvedTips = tips === undefined ? defaultTips : Array.isArray(tips) ? tips : defaultTips;

  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '12px',
    height: '100%',
    padding: '32px 16px',
    textAlign: 'center',
    color: '#4a5568',
  };

  const iconStyle = {
    fontSize: '2.5rem',
  };

  const headingStyle = {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: '#2d3748',
  };

  const messageStyle = {
    maxWidth: '480px',
    fontSize: '1rem',
    lineHeight: 1.6,
  };

  const listStyle = {
    listStyleType: 'disc',
    textAlign: 'left',
    paddingLeft: '1.5rem',
    color: '#4a5568',
    maxWidth: '420px',
  };

  const actionStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '8px 16px',
    borderRadius: '9999px',
    backgroundColor: '#2563eb',
    color: '#ffffff',
    fontWeight: 500,
    textDecoration: 'none',
    border: 'none',
    cursor: 'pointer',
  };

  return (
    <div style={containerStyle}>
      <span aria-hidden="true" style={iconStyle}>{icon}</span>
      <h3 style={headingStyle}>{resolvedHeading}</h3>
      {resolvedMessage && <p style={messageStyle}>{resolvedMessage}</p>}
      {resolvedTips.length > 0 && (
        <ul style={listStyle}>
          {resolvedTips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      )}
      {actions.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
          {actions.map(({ label, onClick, href }) => (
            href ? (
              <a key={label} href={href} style={actionStyle}>
                {label}
              </a>
            ) : (
              <button key={label} type="button" style={actionStyle} onClick={onClick}>
                {label}
              </button>
            )
          ))}
        </div>
      )}
    </div>
  );
};

export default EmptyState;
