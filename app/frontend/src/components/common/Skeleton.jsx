import React from 'react';
import './Skeleton.css';

/**
 * A reusable skeleton loader component.
 * It displays a placeholder with a pulsing animation to indicate that content is loading.
 *
 * @param {object} props - The component props.
 * @param {string} [props.className] - Additional CSS classes to apply to the skeleton element.
 * @param {React.CSSProperties} [props.style] - Custom styles to apply to the skeleton element.
 */
const Skeleton = ({ className, style }) => {
  return <div className={`skeleton-pulse ${className || ''}`} style={style}></div>;
};

export default Skeleton;
