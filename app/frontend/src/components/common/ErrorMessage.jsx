import React from 'react';

const ErrorMessage = ({ message = 'An error occurred while fetching data.', error }) => {
  const style = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    padding: '20px',
    color: '#e53e3e', // Red color for errors
    backgroundColor: '#fff5f5', // Light red background
    border: '1px solid #e53e3e',
    borderRadius: '8px',
  };

  console.error("UI Error:", error);

  return (
    <div style={style}>
      <p>{message}</p>
    </div>
  );
};

export default ErrorMessage;
