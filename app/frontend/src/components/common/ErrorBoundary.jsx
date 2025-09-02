import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error: error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 m-4 rounded-md bg-danger/10 text-danger border border-danger">
          <h1 className="text-lg font-bold">Something went wrong.</h1>
          <p>An error occurred in this part of the application. Please try refreshing the page.</p>
          {this.state.error && <pre className="mt-2 text-xs whitespace-pre-wrap">{this.state.error.toString()}</pre>}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
