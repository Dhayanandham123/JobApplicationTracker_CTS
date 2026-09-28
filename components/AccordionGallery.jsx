import React, { useState, useEffect, useRef } from 'react';
import gsap from 'gsap';
import './AccordionGallery.css';

/**
 * AccordionGallery - React Bits Component
 * Fast, responsive interactive multi-panel showcase with immediate hover/click trigger,
 * clean two-column expanded content layout, and no animation lag.
 */
export default function AccordionGallery({
  items = [],
  defaultIndex = 0,
  trigger = 'hover',
  expandRatio = 0.58,
  duration = 0.4,
  ease = 'power2.out',
  parallax = 0.15,
  tilt = 2,
  showLabels = false,
  grayscale = false,
  height = 410,
  gap = 14,
  radius = 18,
  orientation = 'horizontal',
  className = ''
}) {
  const [activeIndex, setActiveIndex] = useState(defaultIndex);
  const containerRef = useRef(null);
  const panelsRef = useRef([]);

  useEffect(() => {
    const panels = panelsRef.current.filter(Boolean);
    if (!panels.length) return;

    const prefersReducedMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion || window.innerWidth <= 860) {
      panels.forEach((p, idx) => {
        p.style.flex = idx === activeIndex ? '5.5' : '1';
      });
      return;
    }

    // Snappy, non-queued GSAP tween with overwrite: "auto"
    panels.forEach((panel, idx) => {
      const isExpanded = idx === activeIndex;
      const targetFlex = isExpanded ? 5.5 : 1;

      gsap.to(panel, {
        flex: targetFlex,
        duration: duration,
        ease: ease,
        overwrite: 'auto'
      });

      const content = panel.querySelector('.accordion-panel-content');
      const collapsedLabel = panel.querySelector('.accordion-collapsed-label');

      if (content) {
        gsap.to(content, {
          opacity: isExpanded ? 1 : 0,
          y: isExpanded ? 0 : 6,
          scale: isExpanded ? 1 : 0.98,
          duration: isExpanded ? duration * 0.85 : duration * 0.5,
          ease: ease,
          overwrite: 'auto',
          pointerEvents: isExpanded ? 'auto' : 'none'
        });
      }

      if (collapsedLabel) {
        gsap.to(collapsedLabel, {
          opacity: isExpanded ? 0 : 1,
          duration: duration * 0.5,
          ease: ease,
          overwrite: 'auto'
        });
      }
    });
  }, [activeIndex, duration, ease]);

  const handlePointerMove = (e, idx) => {
    if (idx !== activeIndex || tilt === 0 || window.innerWidth <= 860) return;
    const panel = panelsRef.current[idx];
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;

    gsap.to(panel, {
      rotateY: (x * tilt).toFixed(2),
      rotateX: (-y * tilt).toFixed(2),
      duration: 0.15,
      ease: 'power1.out',
      overwrite: 'auto',
      transformPerspective: 1000
    });
  };

  const handlePointerLeave = (idx) => {
    const panel = panelsRef.current[idx];
    if (!panel) return;
    gsap.to(panel, {
      rotateY: 0,
      rotateX: 0,
      duration: 0.25,
      ease: 'power2.out',
      overwrite: 'auto'
    });
  };

  const handleKeyDown = (e, idx) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIdx = (idx + 1) % items.length;
      setActiveIndex(nextIdx);
      panelsRef.current[nextIdx]?.focus();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIdx = (idx - 1 + items.length) % items.length;
      setActiveIndex(prevIdx);
      panelsRef.current[prevIdx]?.focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setActiveIndex(idx);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`accordion-gallery ${orientation} ${className}`}
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        gap: `${gap}px`,
        borderRadius: `${radius}px`
      }}
      role="region"
      aria-label="Features Interactive Gallery"
    >
      {items.map((item, index) => {
        const isExpanded = index === activeIndex;
        return (
          <div
            key={index}
            ref={(el) => (panelsRef.current[index] = el)}
            className={`accordion-panel panel-${item.theme || 'blue'} ${
              isExpanded ? 'is-expanded' : 'is-collapsed'
            }`}
            style={{ borderRadius: `${radius}px` }}
            tabIndex={0}
            role="button"
            aria-expanded={isExpanded}
            aria-label={item.title}
            onClick={() => setActiveIndex(index)}
            onMouseEnter={() => trigger === 'hover' && setActiveIndex(index)}
            onMouseMove={(e) => handlePointerMove(e, index)}
            onMouseLeave={() => handlePointerLeave(index)}
            onKeyDown={(e) => handleKeyDown(e, index)}
          >
            {/* Collapsed view indicator */}
            <div className="accordion-collapsed-label" aria-hidden={isExpanded}>
              <div className={`collapsed-icon-box icon-${item.theme || 'blue'}`}>
                {item.icon}
              </div>
              <span className="collapsed-title">{item.shortTitle || item.title}</span>
            </div>

            {/* Expanded view content */}
            <div className="accordion-panel-content" aria-hidden={!isExpanded}>
              <div className="panel-text-column">
                <div className={`panel-icon-badge icon-${item.theme || 'blue'}`}>
                  {item.icon}
                </div>
                <h3 className="panel-title">{item.title}</h3>
                <p className="panel-description">{item.description}</p>
              </div>

              <div className="panel-visual-column">
                {item.visual}
              </div>
            </div>

            {/* Ambient background glow layer */}
            <div className={`panel-ambient-glow glow-${item.theme || 'blue'}`} />
          </div>
        );
      })}
    </div>
  );
}
