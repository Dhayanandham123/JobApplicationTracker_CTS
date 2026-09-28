import React, { useState, useMemo } from 'react';
import './JobCalendar.css';

/**
 * JobCalendar - Modular React / Ark UI Inspired Component
 * Interactive application tracking calendar with status indicators,
 * hover tooltips, quick detail popover/modal, and multi-event day handling.
 */
export default function JobCalendar({
  events = [],
  initialDate = new Date(),
  onEventClick
}) {
  const [currentDate, setCurrentDate] = useState(initialDate);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [hoveredEvent, setHoveredEvent] = useState(null);
  const [popoverPos, setPopoverPos] = useState({ x: 0, y: 0 });

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  // Group events by date string YYYY-MM-DD
  const eventsByDate = useMemo(() => {
    const map = {};
    events.forEach((evt) => {
      if (!evt.date) return;
      if (!map[evt.date]) map[evt.date] = [];
      map[evt.date].push(evt);
    });
    return map;
  }, [events]);

  const handlePrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  const handleEventMouseEnter = (evt, e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setPopoverPos({
      x: rect.left + rect.width / 2,
      y: rect.top - 10
    });
    setHoveredEvent(evt);
  };

  const handleEventMouseLeave = () => {
    setHoveredEvent(null);
  };

  // Calendar Grid Math
  const firstDayIndex = new Date(year, month, 1).getDay();
  const totalDays = new Date(year, month + 1, 0).getDate();
  const prevMonthDays = new Date(year, month, 0).getDate();

  const cells = [];

  // 1. Prev month padding
  for (let i = firstDayIndex - 1; i >= 0; i--) {
    cells.push({
      day: prevMonthDays - i,
      isOtherMonth: true,
      key: `prev-${i}`
    });
  }

  // 2. Current month
  for (let d = 1; d <= totalDays; d++) {
    const monthStr = String(month + 1).padStart(2, '0');
    const dayStr = String(d).padStart(2, '0');
    const dateKey = `${year}-${monthStr}-${dayStr}`;
    cells.push({
      day: d,
      dateKey,
      isOtherMonth: false,
      events: eventsByDate[dateKey] || [],
      key: `cur-${d}`
    });
  }

  // 3. Next month padding
  const remaining = (cells.length % 7 === 0) ? 0 : 7 - (cells.length % 7);
  for (let i = 1; i <= remaining; i++) {
    cells.push({
      day: i,
      isOtherMonth: true,
      key: `next-${i}`
    });
  }

  return (
    <div className="job-calendar-wrapper">
      {/* Calendar Toolbar */}
      <div className="job-calendar-header">
        <div className="job-calendar-nav">
          <button type="button" className="cal-btn" onClick={handlePrevMonth}>
            &lt; Prev
          </button>
          <div className="cal-title-selects">
            <span className="cal-month-title">
              {monthNames[month]} {year}
            </span>
            <button type="button" className="cal-btn-today" onClick={handleToday}>
              Today
            </button>
          </div>
          <button type="button" className="cal-btn" onClick={handleNextMonth}>
            Next &gt;
          </button>
        </div>
      </div>

      {/* Status Legend */}
      <div className="job-calendar-legend">
        <span className="legend-item"><span className="dot dot-applied"></span> Applied</span>
        <span className="legend-item"><span className="dot dot-interviewing pulse"></span> Interviewing</span>
        <span className="legend-item"><span className="dot dot-offered"></span> Offered</span>
        <span className="legend-item"><span className="dot dot-rejected"></span> Rejected</span>
      </div>

      {/* Weekday Header */}
      <div className="job-calendar-days-row">
        <span>SUN</span><span>MON</span><span>TUE</span><span>WED</span><span>THU</span><span>FRI</span><span>SAT</span>
      </div>

      {/* Days Grid */}
      <div className="job-calendar-grid">
        {cells.map((cell) => {
          if (cell.isOtherMonth) {
            return (
              <div key={cell.key} className="job-calendar-cell other-month">
                <span className="day-number">{cell.day}</span>
              </div>
            );
          }

          const dayEvents = cell.events || [];
          const visibleEvents = dayEvents.slice(0, 2);
          const overflow = dayEvents.length - 2;

          return (
            <div key={cell.key} className="job-calendar-cell">
              <span className="day-number">{cell.day}</span>

              {visibleEvents.map((evt, idx) => (
                <div
                  key={idx}
                  className={`cal-event-pill status-${(evt.status || 'applied').toLowerCase()}`}
                  onClick={() => {
                    setSelectedEvent(evt);
                    if (onEventClick) onEventClick(evt);
                  }}
                  onMouseEnter={(e) => handleEventMouseEnter(evt, e)}
                  onMouseLeave={handleEventMouseLeave}
                >
                  <span className="status-indicator"></span>
                  <span className="company-text">{evt.company_name}</span>
                </div>
              ))}

              {overflow > 0 && (
                <span className="cal-more-badge">+{overflow} more</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Hover Popover */}
      {hoveredEvent && (
        <div
          className="cal-hover-popover"
          style={{
            left: `${popoverPos.x}px`,
            top: `${popoverPos.y}px`
          }}
        >
          <div className="popover-top">
            <strong>{hoveredEvent.company_name}</strong>
            <span className={`badge-${(hoveredEvent.status || 'applied').toLowerCase()}`}>
              {hoveredEvent.status}
            </span>
          </div>
          <div className="popover-role">{hoveredEvent.job_title}</div>
          {hoveredEvent.meta?.notes && (
            <p className="popover-notes">{hoveredEvent.meta.notes}</p>
          )}
        </div>
      )}

      {/* Detail Modal */}
      {selectedEvent && (
        <div className="cal-modal-overlay" onClick={() => setSelectedEvent(null)}>
          <div className="cal-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="cal-modal-header">
              <h3>{selectedEvent.company_name}</h3>
              <button type="button" onClick={() => setSelectedEvent(null)}>&times;</button>
            </div>
            <div className="cal-modal-body">
              <p><strong>Role:</strong> {selectedEvent.job_title}</p>
              <p><strong>Status:</strong> {selectedEvent.status}</p>
              <p><strong>Date:</strong> {selectedEvent.date}</p>
              {selectedEvent.meta?.location && (
                <p><strong>Location:</strong> {selectedEvent.meta.location}</p>
              )}
              {selectedEvent.meta?.salary && (
                <p><strong>Salary:</strong> {selectedEvent.meta.salary}</p>
              )}
              {selectedEvent.meta?.notes && (
                <p><strong>Notes:</strong> {selectedEvent.meta.notes}</p>
              )}
            </div>
            <div className="cal-modal-footer">
              <button type="button" onClick={() => setSelectedEvent(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
