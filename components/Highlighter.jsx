import React from 'react';
import './Highlighter.css';

/**
 * Magic UI - Highlighter Component
 * Adds a subtle animated underline highlight to emphasize key text phrases
 * with smooth entrance drawing and zero layout shift.
 */
export default function Highlighter({
  children,
  action = 'underline',
  color = '#6366F1',
  strokeWidth = 3.5,
  className = ''
}) {
  return (
    <span className={`magic-highlighter-wrapper action-${action} ${className}`}>
      <span className="magic-highlighter-text">{children}</span>
      {action === 'underline' && (
        <svg
          className="magic-highlighter-svg"
          viewBox="0 0 280 18"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M3 13.5C70 5.5 180 3.5 277 11.5"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="highlighter-path is-animated"
          />
        </svg>
      )}
    </span>
  );
}
