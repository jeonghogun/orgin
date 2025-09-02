/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0E0F13',
        panel: '#14161C',
        'panel-elev': '#171A21',
        border: '#242936',
        text: '#E8ECF1',
        muted: '#A0A6B3',
        accent: '#22C55E',
        'accent-weak': '#16A34A',
        warn: '#F59E0B',
        danger: '#EF4444',
      },
      fontFamily: {
        sans: ['Inter', 'Pretendard', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'h1': ['18px', { lineHeight: '26px', fontWeight: '600' }],
        'h2': ['16px', { lineHeight: '24px', fontWeight: '600' }],
        'body': ['14px', { lineHeight: '22px' }],
        'meta': ['12px', { lineHeight: '18px' }],
      },
      borderRadius: {
        'card': '12px',
        'input': '12px',
        'button': '10px',
      },
      boxShadow: {
        'card': '0 2px 12px rgba(0,0,0,0.35)',
      },
      animation: {
        'fade-in': 'fadeIn 150ms ease-out',
        'slide-in': 'slideIn 150ms ease-out',
        'bounce': 'bounce 1s infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        bounce: {
          '0%, 100%': {
            transform: 'translateY(-25%)',
            animationTimingFunction: 'cubic-bezier(0.8, 0, 1, 1)',
          },
          '50%': {
            transform: 'translateY(0)',
            animationTimingFunction: 'cubic-bezier(0, 0, 0.2, 1)',
          },
        },
      },
    },
  },
  plugins: [],
}
