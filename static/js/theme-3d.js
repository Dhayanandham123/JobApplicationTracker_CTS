/* ==========================================================================
   Theme 3D behaviors & React Bits enhancements
   Additive, defensive (never throws if elements absent)
   ========================================================================== */
(function () {
    "use strict";

    var prefersReducedMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var isTouchDevice = "ontouchstart" in window || navigator.maxTouchPoints > 0;

    /* ---------- 1. Ambient background orbs (inject once) ---------- */
    function injectOrbField() {
        if (document.querySelector(".bg-orb-field")) return;
        var field = document.createElement("div");
        field.className = "bg-orb-field";
        field.innerHTML =
            '<div class="bg-orb orb-1"></div>' +
            '<div class="bg-orb orb-2"></div>' +
            '<div class="bg-orb orb-3"></div>';
        document.body.appendChild(field);

        if (!document.querySelector(".bg-grid-overlay")) {
            var grid = document.createElement("div");
            grid.className = "bg-grid-overlay";
            document.body.appendChild(grid);
        }
    }

    /* ---------- 2. Hero 3D stack: subtle mouse-parallax ---------- */
    function initHeroParallax() {
        if (prefersReducedMotion || isTouchDevice) return;
        var stack = document.getElementById("hero3dStack");
        if (!stack) return;
        var front = stack.querySelector(".stack-card-front");
        var ghostA = stack.querySelector(".stack-card-ghost-a");
        var ghostB = stack.querySelector(".stack-card-ghost-b");

        stack.addEventListener("mousemove", function (e) {
            var rect = stack.getBoundingClientRect();
            var px = (e.clientX - rect.left) / rect.width - 0.5;
            var py = (e.clientY - rect.top) / rect.height - 0.5;
            if (front) {
                front.style.transform =
                    "rotateX(" + (5 - py * 8).toFixed(2) + "deg) rotateY(" + (-3 + px * 10).toFixed(2) + "deg)";
            }
            if (ghostA) {
                ghostA.style.transform =
                    "rotateX(" + (9 - py * 5).toFixed(2) + "deg) rotateY(" + (-12 + px * 6).toFixed(2) +
                    "deg) rotateZ(-5deg) translateZ(-60px)";
            }
            if (ghostB) {
                ghostB.style.transform =
                    "rotateX(" + (-5 - py * 5).toFixed(2) + "deg) rotateY(" + (10 + px * 6).toFixed(2) +
                    "deg) rotateZ(4deg) translateZ(-30px)";
            }
        });

        stack.addEventListener("mouseleave", function () {
            if (front) front.style.transform = "";
            if (ghostA) ghostA.style.transform = "";
            if (ghostB) ghostB.style.transform = "";
        });
    }

    /* ---------- 3. React Bits BlurText & Hero Intro Reveal ---------- */
    function initHeroIntroAnimations() {
        var heroTitle = document.getElementById("heroTitle");
        var heroDesc = document.getElementById("heroDescription");
        var heroCta = document.querySelector(".hero-fade-cta");

        if (prefersReducedMotion) {
            if (heroTitle) heroTitle.classList.add("is-animated");
            if (heroDesc) heroDesc.classList.add("is-animated");
            if (heroCta) heroCta.classList.add("is-animated");
            return;
        }

        // Trigger entrance immediately on load with smooth frame sync
        requestAnimationFrame(function () {
            setTimeout(function () {
                if (heroTitle) heroTitle.classList.add("is-animated");
                if (heroDesc) heroDesc.classList.add("is-animated");
                if (heroCta) heroCta.classList.add("is-animated");
            }, 60);
        });
    }

    /* ---------- 3b. React Bits ScrambledText Interaction (Optimized Architecture) ---------- */
    function initScrambledText() {
        if (prefersReducedMotion || isTouchDevice || window.innerWidth <= 768) return;
        var targets = document.querySelectorAll(".hero-scrambled-text");
        if (!targets.length) return;

        var scrambleChars = ".:";
        var radius = 65;
        var radiusSq = radius * radius;
        var duration = 0.45;
        var maxActive = 10;

        targets.forEach(function (el) {
            var rawText = el.textContent.trim();
            if (!rawText) return;

            // Break into words and character spans while preserving whitespace
            var words = rawText.split(/\s+/);
            el.innerHTML = "";
            var charElements = [];

            words.forEach(function (word, wIdx) {
                var wordSpan = document.createElement("span");
                wordSpan.className = "scramble-word";

                for (var i = 0; i < word.length; i++) {
                    var ch = word[i];
                    var charSpan = document.createElement("span");
                    charSpan.className = "scramble-char";
                    charSpan.textContent = ch;
                    charSpan.setAttribute("data-orig", ch);
                    wordSpan.appendChild(charSpan);
                    charElements.push(charSpan);
                }

                el.appendChild(wordSpan);
                if (wIdx < words.length - 1) {
                    var spaceSpan = document.createElement("span");
                    spaceSpan.className = "scramble-space";
                    spaceSpan.innerHTML = " ";
                    el.appendChild(spaceSpan);
                }
            });

            // Cached character coordinate items
            var cachedPositions = [];
            var activeSet = new Set();
            var mouseX = -9999;
            var mouseY = -9999;
            var isTicking = false;

            function cachePositions() {
                cachedPositions = [];
                for (var i = 0; i < charElements.length; i++) {
                    var cs = charElements[i];
                    var rect = cs.getBoundingClientRect();
                    cachedPositions.push({
                        el: cs,
                        cx: rect.left + rect.width / 2,
                        cy: rect.top + rect.height / 2,
                        orig: cs.getAttribute("data-orig")
                    });
                }
            }

            // Cache positions once after DOM layout is stable
            setTimeout(cachePositions, 100);

            var resizeDebounce = null;
            window.addEventListener("resize", function () {
                clearTimeout(resizeDebounce);
                resizeDebounce = setTimeout(cachePositions, 150);
            }, { passive: true });

            function processNearbyCharacters() {
                isTicking = false;
                if (mouseX === -9999) return;
                var charsLen = scrambleChars.length;
                var currentlyActive = activeSet.size;

                for (var i = 0; i < cachedPositions.length; i++) {
                    var item = cachedPositions[i];
                    if (!item.orig || item.orig === " ") continue;

                    var dx = item.cx - mouseX;
                    var dy = item.cy - mouseY;
                    var distSq = dx * dx + dy * dy;

                    if (distSq < radiusSq) {
                        if (!activeSet.has(item.el) && currentlyActive < maxActive) {
                            activeSet.add(item.el);
                            currentlyActive++;

                            var randomChar = scrambleChars[Math.floor(Math.random() * charsLen)];
                            item.el.textContent = randomChar;
                            item.el.classList.add("is-scrambling");

                            (function (targetItem) {
                                setTimeout(function () {
                                    targetItem.el.textContent = targetItem.orig;
                                    targetItem.el.classList.remove("is-scrambling");
                                    activeSet.delete(targetItem.el);
                                }, duration * 1000);
                            })(item);
                        }
                    }
                }
            }

            el.addEventListener("pointermove", function (e) {
                mouseX = e.clientX;
                mouseY = e.clientY;
                if (!isTicking) {
                    isTicking = true;
                    requestAnimationFrame(processNearbyCharacters);
                }
            }, { passive: true });

            el.addEventListener("pointerleave", function () {
                mouseX = -9999;
                mouseY = -9999;
                for (var i = 0; i < cachedPositions.length; i++) {
                    var item = cachedPositions[i];
                    item.el.textContent = item.orig;
                    item.el.classList.remove("is-scrambling");
                }
                activeSet.clear();
            }, { passive: true });
        });
    }

    /* ---------- 4. React Bits Animated List: Live Application Feed ---------- */
    function initLiveActivityFeed() {
        var feedContainer = document.getElementById("animatedFeedContainer");
        if (!feedContainer) return;

        var activities = [
            {
                company: "Google",
                role: "Software Engineer",
                initial: "G",
                color: "#4285F4",
                status: "Applied",
                pillClass: "activity-pill-applied",
                time: "Just now"
            },
            {
                company: "Microsoft",
                role: "Software Engineer Intern",
                initial: "M",
                color: "#00A4EF",
                status: "Interview Scheduled",
                pillClass: "activity-pill-interview",
                time: "2m ago"
            },
            {
                company: "Amazon",
                role: "SDE Intern",
                initial: "A",
                color: "#FF9900",
                status: "Follow-up Due",
                pillClass: "activity-pill-followup",
                time: "1h ago"
            },
            {
                company: "Startup AI",
                role: "AI Engineer",
                initial: "S",
                color: "#8B5CF6",
                status: "Offer Received",
                pillClass: "activity-pill-offered",
                time: "Today"
            }
        ];

        function createCardElement(item) {
            var row = document.createElement("div");
            row.className = "activity-card-row active";
            row.innerHTML =
                '<div class="activity-left">' +
                    '<div class="activity-avatar" style="background-color: ' + item.color + ';">' + item.initial + '</div>' +
                    '<div class="activity-info">' +
                        '<span class="activity-company">' + item.company + '</span>' +
                        '<span class="activity-role">' + item.role + '</span>' +
                    '</div>' +
                '</div>' +
                '<div class="activity-right">' +
                    '<span class="activity-time">' + item.time + '</span>' +
                    '<span class="activity-pill ' + item.pillClass + '">' + item.status + '</span>' +
                '</div>';
            return row;
        }

        // Render initial 2 items
        feedContainer.innerHTML = "";
        feedContainer.appendChild(createCardElement(activities[0]));
        feedContainer.appendChild(createCardElement(activities[1]));

        if (prefersReducedMotion) return;

        var currentIndex = 2;
        var intervalId = setInterval(function () {
            if (!document.body.contains(feedContainer)) {
                clearInterval(intervalId);
                return;
            }

            var nextItem = activities[currentIndex % activities.length];
            currentIndex++;

            var newRow = createCardElement(nextItem);
            newRow.classList.remove("active");
            newRow.classList.add("entering");

            feedContainer.insertBefore(newRow, feedContainer.firstChild);

            // Reflow and animate in
            void newRow.offsetWidth;
            newRow.classList.remove("entering");
            newRow.classList.add("active");

            // Maintain max 2 items visible for calm, executive look
            var children = feedContainer.children;
            if (children.length > 2) {
                var lastChild = children[children.length - 1];
                lastChild.classList.remove("active");
                lastChild.classList.add("exiting");
                setTimeout(function () {
                    if (lastChild.parentNode) {
                        lastChild.parentNode.removeChild(lastChild);
                    }
                }, 450);
            }
        }, 2400);
    }

    /* ---------- 5. React Bits AccordionGallery Component Controller ---------- */
    function initAccordionGallery() {
        var gallery = document.getElementById("accordionGallery");
        if (!gallery) return;

        var panels = gallery.querySelectorAll(".accordion-panel");
        if (!panels.length) return;

        var activeIndex = 0;
        var hasGsap = typeof window.gsap !== "undefined";

        function setActivePanel(newIndex) {
            if (newIndex === activeIndex) return;
            activeIndex = newIndex;

            panels.forEach(function (panel, idx) {
                var isExpanded = (idx === activeIndex);
                var content = panel.querySelector(".accordion-panel-content");
                var collapsedLabel = panel.querySelector(".accordion-collapsed-label");

                panel.setAttribute("aria-expanded", isExpanded ? "true" : "false");

                if (isExpanded) {
                    panel.classList.add("is-expanded");
                    panel.classList.remove("is-collapsed");
                } else {
                    panel.classList.remove("is-expanded");
                    panel.classList.add("is-collapsed");
                }

                if (hasGsap && !prefersReducedMotion && window.innerWidth > 860) {
                    window.gsap.to(panel, {
                        flex: isExpanded ? 5.5 : 1,
                        duration: 0.4,
                        ease: "power2.out",
                        overwrite: "auto"
                    });

                    if (content) {
                        window.gsap.to(content, {
                            opacity: isExpanded ? 1 : 0,
                            y: isExpanded ? 0 : 6,
                            scale: isExpanded ? 1 : 0.98,
                            duration: isExpanded ? 0.35 : 0.2,
                            ease: "power2.out",
                            overwrite: "auto"
                        });
                    }

                    if (collapsedLabel) {
                        window.gsap.to(collapsedLabel, {
                            opacity: isExpanded ? 0 : 1,
                            duration: 0.2,
                            ease: "power2.out",
                            overwrite: "auto"
                        });
                    }
                }
            });
        }

        panels.forEach(function (panel, idx) {
            var index = parseInt(panel.getAttribute("data-index") || idx, 10);

            // Instant hover trigger - no delays
            panel.addEventListener("mouseenter", function () {
                if (window.innerWidth > 860) {
                    setActivePanel(index);
                }
            });

            // Click / tap trigger (for touch and mobile)
            panel.addEventListener("click", function () {
                setActivePanel(index);
            });

            // Pointer subtle parallax tilt (clamped to 2deg)
            panel.addEventListener("mousemove", function (e) {
                if (prefersReducedMotion || isTouchDevice || window.innerWidth <= 860) return;
                if (!panel.classList.contains("is-expanded")) return;

                var rect = panel.getBoundingClientRect();
                var px = (e.clientX - rect.left) / rect.width - 0.5;
                var py = (e.clientY - rect.top) / rect.height - 0.5;
                var tiltMax = 2.0;

                if (hasGsap) {
                    window.gsap.to(panel, {
                        rotateY: (px * tiltMax).toFixed(2),
                        rotateX: (-py * tiltMax).toFixed(2),
                        duration: 0.15,
                        ease: "power1.out",
                        overwrite: "auto"
                    });
                } else {
                    panel.style.transform = "perspective(1000px) rotateY(" + (px * tiltMax).toFixed(2) + "deg) rotateX(" + (-py * tiltMax).toFixed(2) + "deg)";
                }
            });

            panel.addEventListener("mouseleave", function () {
                if (prefersReducedMotion || isTouchDevice) return;
                if (hasGsap) {
                    window.gsap.to(panel, {
                        rotateY: 0,
                        rotateX: 0,
                        duration: 0.25,
                        ease: "power2.out",
                        overwrite: "auto"
                    });
                } else {
                    panel.style.transform = "";
                }
            });

            // Keyboard accessibility (Arrow navigation & Enter/Space)
            panel.addEventListener("keydown", function (e) {
                if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                    e.preventDefault();
                    var next = (index + 1) % panels.length;
                    setActivePanel(next);
                    panels[next].focus();
                } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                    e.preventDefault();
                    var prev = (index - 1 + panels.length) % panels.length;
                    setActivePanel(prev);
                    panels[prev].focus();
                } else if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setActivePanel(index);
                }
            });
        });
    }

    /* ---------- 6. React Bits Magnet Button (Subtle 3-5px cursor pull) ---------- */
    function initMagnetButtons() {
        if (prefersReducedMotion || isTouchDevice) return;
        var magnetButtons = document.querySelectorAll(".magnet-btn");
        if (!magnetButtons.length) return;

        magnetButtons.forEach(function (btn) {
            btn.addEventListener("mousemove", function (e) {
                var rect = btn.getBoundingClientRect();
                var cx = rect.left + rect.width / 2;
                var cy = rect.top + rect.height / 2;
                var dx = (e.clientX - cx) * 0.15;
                var dy = (e.clientY - cy) * 0.15;

                // Max clamp strictly to 3.5px
                dx = Math.max(-3.5, Math.min(3.5, dx));
                dy = Math.max(-3.5, Math.min(3.5, dy));

                btn.style.transform = "translate(" + dx.toFixed(1) + "px, " + dy.toFixed(1) + "px)";
            });

            btn.addEventListener("mouseleave", function () {
                btn.style.transform = "";
            });
        });
    }

    /* ---------- 7. Pointer-based 3D tilt on dashboard cards ---------- */
    function initTilt() {
        if (prefersReducedMotion || isTouchDevice) return;
        var selector = ".app-card, .kpi-metric-card, .upcoming-interview-card";

        document.addEventListener("mousemove", function (e) {
            var target = e.target.closest ? e.target.closest(selector) : null;
            if (!target) return;
            applyTilt(target, e);
        });

        document.addEventListener("mouseover", function (e) {
            var target = e.target.closest ? e.target.closest(selector) : null;
            if (target) target.classList.add("tilt-target");
        });

        document.addEventListener("mouseout", function (e) {
            var target = e.target.closest ? e.target.closest(selector) : null;
            if (target && (!e.relatedTarget || !target.contains(e.relatedTarget))) {
                resetTilt(target);
            }
        });
    }

    function applyTilt(el, e) {
        var rect = el.getBoundingClientRect();
        var px = (e.clientX - rect.left) / rect.width;
        var py = (e.clientY - rect.top) / rect.height;
        var maxDeg = 5;
        var rx = (px - 0.5) * maxDeg * 2;
        var ry = (0.5 - py) * maxDeg * 2;
        el.style.setProperty("--rx", rx.toFixed(2) + "deg");
        el.style.setProperty("--ry", ry.toFixed(2) + "deg");
        el.style.setProperty("--tz", "5px");
    }

    function resetTilt(el) {
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
        el.style.setProperty("--tz", "0px");
    }

    /* ---------- 8. Animated KPI & Dashboard Count-Up ---------- */
    function animateValue(el, endValue, suffix, duration) {
        var startTime = null;
        function step(ts) {
            if (!startTime) startTime = ts;
            var progress = Math.min((ts - startTime) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3);
            var current = endValue * eased;
            el.textContent = (Number.isInteger(endValue) ? Math.round(current) : current.toFixed(1)) + suffix;
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    function initHeroMetricCountUp() {
        var countEl = document.getElementById("statTrackerCount");
        if (!countEl) return;

        if (prefersReducedMotion || !("IntersectionObserver" in window)) {
            countEl.textContent = "100%";
            return;
        }

        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    animateValue(countEl, 100, "%", 850);
                    io.unobserve(countEl);
                }
            });
        }, { threshold: 0.2 });

        io.observe(countEl);
    }

    function initKpiCountUp() {
        if (prefersReducedMotion) return;
        var kpiEls = document.querySelectorAll(".kpi-value");
        if (!kpiEls.length) return;

        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                if (m.target.dataset.animated === "1") return;
                var text = m.target.textContent.trim();
                var match = text.match(/^([\d.]+)(.*)$/);
                if (!match) return;
                var num = parseFloat(match[1]);
                var suffix = match[2] || "";
                if (isNaN(num)) return;
                m.target.dataset.animated = "1";
                animateValue(m.target, num, suffix, 900);
                setTimeout(function () { m.target.dataset.animated = "0"; }, 1000);
            });
        });

        kpiEls.forEach(function (el) {
            observer.observe(el, { childList: true, characterData: true, subtree: true });
        });
    }

    /* ---------- 9. Scroll Reveal for Features and CTA sections ---------- */
    function initScrollReveal() {
        var targets = document.querySelectorAll(
            ".reveal-title-group, .accordion-gallery-wrapper, .reveal-cta-content, .reveal-on-scroll"
        );
        if (!targets.length) return;

        if (prefersReducedMotion || !("IntersectionObserver" in window)) {
            targets.forEach(function (t) { t.classList.add("is-visible"); });
            return;
        }

        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.15 });

        targets.forEach(function (t) { io.observe(t); });
    }

    /* ---------- Init ---------- */
    document.addEventListener("DOMContentLoaded", function () {
        injectOrbField();
        initTilt();
        initHeroParallax();
        initHeroIntroAnimations();
        initScrambledText();
        initLiveActivityFeed();
        initHeroMetricCountUp();
        initAccordionGallery();
        initMagnetButtons();
        initKpiCountUp();
        initScrollReveal();
    });
})();


