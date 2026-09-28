import React from 'react';
import './GradientMenu.css';

/**
 * GradientMenu - React Bits Navigation Interaction Component
 * Compact circular/pill navigation items with smooth hover/focus expansion,
 * tailored blue/purple gradients, and zero-latency CSS transitions.
 */
export default function GradientMenu({
  items = [
    { id: 'dashboard', label: 'Dashboard', gradient: 'linear-gradient(135deg, #3b82f6, #6366f1)', glow: 'rgba(59, 130, 246, 0.45)' },
    { id: 'analytics', label: 'Analytics', gradient: 'linear-gradient(135deg, #4f46e5, #7c3aed)', glow: 'rgba(124, 58, 237, 0.45)' },
    { id: 'calendar', label: 'Calendar', gradient: 'linear-gradient(135deg, #2563eb, #6366f1)', glow: 'rgba(37, 99, 235, 0.45)' },
    { id: 'fit-score', label: 'Fit Score', gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)', glow: 'rgba(139, 92, 246, 0.45)' },
    { id: 'resume-versions', label: 'Resume Versions', gradient: 'linear-gradient(135deg, #3b82f6, #7c3aed)', glow: 'rgba(59, 130, 246, 0.45)' }
  ],
  activeId = 'dashboard',
  onItemClick = () => {},
  className = ''
}) {
  return (
    <nav className={`gradient-menu-container ${className}`} aria-label="Main Navigation" role="tablist">
      {items.map((item) => {
        const isActive = item.id === activeId;
        const style = {
          '--item-gradient': item.gradient || 'linear-gradient(135deg, #2563eb, #7c3aed)',
          '--item-glow': item.glow || 'rgba(37, 99, 235, 0.45)',
          background: isActive ? item.gradient : undefined,
          boxShadow: isActive ? `0 6px 18px -2px ${item.glow}` : undefined
        };

        return (
          <button
            key={item.id}
            type="button"
            className={`gradient-menu-item ${isActive ? 'active' : ''}`}
            onClick={() => onItemClick(item.id)}
            role="tab"
            aria-selected={isActive}
            title={item.label}
            style={style}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.background = item.gradient;
                e.currentTarget.style.boxShadow = `0 6px 20px -3px ${item.glow}`;
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.boxShadow = 'none';
              }
            }}
          >
            <span className="gradient-menu-icon">
              {item.icon || (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="7" height="7" rx="1"></rect>
                  <rect x="14" y="3" width="7" height="7" rx="1"></rect>
                  <rect x="14" y="14" width="7" height="7" rx="1"></rect>
                  <rect x="3" y="14" width="7" height="7" rx="1"></rect>
                </svg>
              )}
            </span>
            <span className="gradient-menu-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
