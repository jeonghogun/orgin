import React from 'react';

const LoadingSpinner = () => {
  const style = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    padding: '20px',
    fontSize: '1.2rem',
    color: '#888',
  };

  return (
    <div style={style}>
      <p>Loading...</p>
    </div>
  );
};

export default LoadingSpinner;
