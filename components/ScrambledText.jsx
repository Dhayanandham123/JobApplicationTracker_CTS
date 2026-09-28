import React, { useRef, useEffect, useCallback } from 'react';
import './ScrambledText.css';

/**
 * ScrambledText - React Bits Component (Aggressively Optimized)
 * High-performance, zero-latency character scrambler.
 *
 * Performance Architecture:
 * 1. Caches character centers relative to viewport on mount/resize (zero getBoundingClientRect on pointermove).
 * 2. Compares squared distances (dx*dx + dy*dy < radius*radius) to skip Math.hypot.
 * 3. Throttles pointer coordinates via single requestAnimationFrame.
 * 4. Tracks active scrambling characters in a Set to prevent animation thrashing.
 * 5. Caps maximum concurrent scrambling characters (maxActive = 10).
 * 6. Inherits exact parent text color for an ultra-subtle, non-distracting effect.
 */
export default function ScrambledText({
  children,
  radius = 65,
  duration = 0.45,
  speed = 0.2,
  scrambleChars = '.:',
  className = '',
  as: Component = 'p'
}) {
  const containerRef = useRef(null);
  const charsRef = useRef([]);
  const cachedPositionsRef = useRef([]);
  const activeCharsSetRef = useRef(new Set());
  const rafIdRef = useRef(null);
  const pointerPosRef = useRef({ x: -9999, y: -9999 });
  const isTickingRef = useRef(false);

  const rawText = typeof children === 'string' ? children : '';

  // Measure and cache character center coordinates once
  const updateCachedPositions = useCallback(() => {
    const chars = charsRef.current;
    const positions = [];
    for (let i = 0; i < chars.length; i++) {
      const el = chars[i];
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      positions.push({
        el,
        cx: rect.left + rect.width / 2,
        cy: rect.top + rect.height / 2,
        orig: el.dataset.orig || el.textContent
      });
    }
    cachedPositionsRef.current = positions;
  }, []);

  const processProximity = useCallback(() => {
    isTickingRef.current = false;
    const { x: mouseX, y: mouseY } = pointerPosRef.current;
    if (mouseX === -9999) return;

    const positions = cachedPositionsRef.current;
    const activeSet = activeCharsSetRef.current;
    const charsLen = scrambleChars.length;
    const radiusSq = radius * radius;
    const maxActive = 10;
    let currentlyActive = activeSet.size;

    for (let i = 0; i < positions.length; i++) {
      const item = positions[i];
      if (!item.orig || item.orig === ' ') continue;

      const dx = item.cx - mouseX;
      const dy = item.cy - mouseY;
      const distSq = dx * dx + dy * dy;

      if (distSq < radiusSq) {
        if (!activeSet.has(item.el) && currentlyActive < maxActive) {
          activeSet.add(item.el);
          currentlyActive++;

          const randomChar = scrambleChars[Math.floor(Math.random() * charsLen)];
          item.el.textContent = randomChar;
          item.el.classList.add('is-scrambling');

          setTimeout(() => {
            item.el.textContent = item.orig;
            item.el.classList.remove('is-scrambling');
            activeSet.delete(item.el);
          }, duration * 1000);
        }
      }
    }
  }, [radius, duration, scrambleChars]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const prefersReducedMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    if (prefersReducedMotion || isTouch) return;

    // Cache initial positions
    updateCachedPositions();

    const handleResize = () => {
      updateCachedPositions();
    };

    const handlePointerMove = (e) => {
      pointerPosRef.current = { x: e.clientX, y: e.clientY };
      if (!isTickingRef.current) {
        isTickingRef.current = true;
        rafIdRef.current = requestAnimationFrame(processProximity);
      }
    };

    const handlePointerLeave = () => {
      pointerPosRef.current = { x: -9999, y: -9999 };
      const positions = cachedPositionsRef.current;
      positions.forEach((item) => {
        if (item.el) {
          item.el.textContent = item.orig;
          item.el.classList.remove('is-scrambling');
        }
      });
      activeCharsSetRef.current.clear();
    };

    window.addEventListener('resize', handleResize, { passive: true });
    container.addEventListener('pointermove', handlePointerMove, { passive: true });
    container.addEventListener('pointerleave', handlePointerLeave, { passive: true });

    return () => {
      window.removeEventListener('resize', handleResize);
      container.removeEventListener('pointermove', handlePointerMove);
      container.removeEventListener('pointerleave', handlePointerLeave);
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
    };
  }, [updateCachedPositions, processProximity]);

  // Split text into words and individual character spans
  const words = rawText.split(' ');
  let charGlobalIndex = 0;

  return (
    <Component
      ref={containerRef}
      className={`scrambled-text-container ${className}`}
      aria-label={rawText}
    >
      {words.map((word, wIdx) => (
        <span key={wIdx} className="scramble-word" style={{ display: 'inline-block', whiteSpace: 'nowrap' }}>
          {word.split('').map((char, cIdx) => {
            const idx = charGlobalIndex++;
            return (
              <span
                key={cIdx}
                ref={(el) => (charsRef.current[idx] = el)}
                className="scramble-char"
                data-orig={char}
              >
                {char}
              </span>
            );
          })}
          {wIdx < words.length - 1 && (
            <span className="scramble-space">&nbsp;</span>
          )}
        </span>
      ))}
    </Component>
  );
}
