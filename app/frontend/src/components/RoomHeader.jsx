import React from 'react';

const RoomHeader = ({ 
  title, 
  subtitle, 
  actions = [], 
  onBack,
  showBackButton = false 
}) => {
  return (
    <div className="bg-panel-elev border-b border-border px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {showBackButton && (
            <button
              onClick={onBack}
              className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4">
                <path d="M10.5 12.5L5.5 8l5-4.5L9.5 2l-6 6 6 6 1-1.5z"/>
              </svg>
            </button>
          )}
          <div>
            <h1 className="text-h1 text-text">{title}</h1>
            {subtitle && (
              <p className="text-meta text-muted mt-1">{subtitle}</p>
            )}
          </div>
        </div>
        
        {actions.length > 0 && (
          <div className="flex items-center gap-2">
            {actions.map((action, index) => (
              <button
                key={index}
                onClick={action.onClick}
                className={`px-3 py-2 rounded-button transition-colors duration-150 focus-ring ${
                  action.variant === 'primary' 
                    ? 'bg-accent hover:bg-accent-weak text-white' 
                    : 'bg-panel hover:bg-panel-elev text-text border border-border'
                }`}
              >
                {action.icon && (
                  <span className="mr-2">{action.icon}</span>
                )}
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default RoomHeader;
