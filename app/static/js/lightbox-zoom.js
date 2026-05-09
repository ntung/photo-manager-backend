// Zoom + pan extension for Lightbox v2 — wheel, pinch, drag, double-click, and +/- buttons
(function () {
    'use strict';

    let zoomLevel = 1;
    let panX = 0, panY = 0;
    const MIN_ZOOM = 1;
    const MAX_ZOOM = 5;
    const ZOOM_STEP = 0.25;

    let lastTouchDistance = null;
    let isPanning = false;
    let panLastX = 0, panLastY = 0;
    let panPathLength = 0;   // cumulative drag distance — robust on high-polling mice
    let didPan = false;
    let panBlockNextClick = false;

    let lb = null;  // #lightbox element, set in setup()

    // --- cursor via CSS classes on #lightbox (avoids fighting lightbox.css inline/rule specificity) ---

    function setZoomedCursor(grabbing) {
        if (!lb) return;
        lb.classList.toggle('lb-zoomed',   zoomLevel > MIN_ZOOM);
        lb.classList.toggle('lb-panning',  grabbing === true);
    }

    // --- transform ---

    function getImg() { return lb && lb.querySelector('.lb-image'); }

    function applyTransform() {
        const img = getImg();
        if (!img) return;
        img.style.transform = zoomLevel === MIN_ZOOM
            ? ''
            : `translate(${panX}px, ${panY}px) scale(${zoomLevel})`;
    }

    // --- controls UI ---

    function syncUI() {
        const btnIn  = document.getElementById('lb-zoom-in');
        const btnOut = document.getElementById('lb-zoom-out');
        const label  = document.getElementById('lb-zoom-level');
        if (btnIn)  btnIn.style.opacity  = zoomLevel >= MAX_ZOOM ? '0.35' : '1';
        if (btnOut) btnOut.style.opacity = zoomLevel <= MIN_ZOOM ? '0.35' : '1';
        if (label)  label.textContent    = Math.round(zoomLevel * 100) + '%';
    }

    function setControlsVisible(visible) {
        const ctrl = document.getElementById('lb-zoom-controls');
        if (ctrl) ctrl.style.display = visible ? 'flex' : 'none';
    }

    // --- zoom ---

    function resetZoom() {
        zoomLevel = 1;
        panX = 0;
        panY = 0;
        const img = getImg();
        if (img) img.style.transform = '';
        setZoomedCursor(false);
        syncUI();
        // Controls visibility is managed by the lightbox open/close observer — not reset here.
    }

    // Zoom toward/away from screen point (cursorX, cursorY), keeping that point visually fixed.
    // With transform: translate(panX, panY) scale(zoomLevel) and transformOrigin 50% 50%,
    // the visual center of the image is at (layoutCenter + pan), so:
    //   newPan = pan + (cursor - visualCenter) * (1 - newScale/oldScale)
    function applyZoom(newLevel, cursorX, cursorY) {
        newLevel = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newLevel));
        if (newLevel === zoomLevel) return;

        const img = getImg();
        if (!img) return;

        const sf = newLevel / zoomLevel;
        if (cursorX !== undefined && cursorY !== undefined) {
            const rect = img.getBoundingClientRect();
            panX += (cursorX - (rect.left + rect.width  / 2)) * (1 - sf);
            panY += (cursorY - (rect.top  + rect.height / 2)) * (1 - sf);
        }

        if (newLevel === MIN_ZOOM) { panX = 0; panY = 0; }

        zoomLevel = newLevel;
        applyTransform();
        setZoomedCursor(false);
        syncUI();
    }

    // --- event handlers ---

    function onWheel(e) {
        e.preventDefault();
        applyZoom(zoomLevel + (e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP), e.clientX, e.clientY);
    }

    function onMouseDown(e) {
        if (zoomLevel <= MIN_ZOOM || e.button !== 0) return;
        if (e.target.closest('.lb-close, .lb-cancel, #lb-zoom-controls')) return;
        isPanning      = true;
        didPan         = false;
        panPathLength  = 0;
        panLastX       = e.clientX;
        panLastY       = e.clientY;
        setZoomedCursor(true);
        e.preventDefault();
    }

    function onMouseMove(e) {
        if (!isPanning) return;
        const dx = e.clientX - panLastX;
        const dy = e.clientY - panLastY;
        panPathLength += Math.hypot(dx, dy);
        if (!didPan && panPathLength > 5) didPan = true;
        panX    += dx;
        panY    += dy;
        panLastX = e.clientX;
        panLastY = e.clientY;
        applyTransform();
    }

    function onMouseUp() {
        if (!isPanning) return;
        isPanning = false;
        if (didPan) panBlockNextClick = true;
        didPan = false;
        setZoomedCursor(false);
    }

    // Capture-phase click guard: swallows click after a drag so nav/close don't fire.
    function onClickCapture(e) {
        if (panBlockNextClick) {
            e.stopPropagation();
            panBlockNextClick = false;
        }
    }

    function onTouchStart(e) {
        if (e.touches.length === 2) {
            lastTouchDistance = Math.hypot(
                e.touches[1].clientX - e.touches[0].clientX,
                e.touches[1].clientY - e.touches[0].clientY
            );
        }
    }

    function onTouchMove(e) {
        if (e.touches.length === 2 && lastTouchDistance) {
            e.preventDefault();
            const dist = Math.hypot(
                e.touches[1].clientX - e.touches[0].clientX,
                e.touches[1].clientY - e.touches[0].clientY
            );
            applyZoom(
                zoomLevel * (dist / lastTouchDistance),
                (e.touches[0].clientX + e.touches[1].clientX) / 2,
                (e.touches[0].clientY + e.touches[1].clientY) / 2
            );
            lastTouchDistance = dist;
        }
    }

    function onTouchEnd(e) {
        if (e.touches.length < 2) lastTouchDistance = null;
    }

    function onDblClick(e) {
        if (e.target.closest('#lb-zoom-controls')) return;
        if (zoomLevel > MIN_ZOOM) {
            resetZoom();
        } else {
            applyZoom(2, e.clientX, e.clientY);
        }
    }

    // --- DOM setup ---

    function injectStyles() {
        const style = document.createElement('style');
        style.textContent = `
            /* grab cursor — class-driven so it beats lightbox.css cursor:pointer on .lb-prev/.lb-next */
            #lightbox.lb-zoomed .lb-nav,
            #lightbox.lb-zoomed .lb-prev,
            #lightbox.lb-zoomed .lb-next,
            #lightbox.lb-zoomed .lb-image { cursor: grab !important; }

            #lightbox.lb-panning .lb-nav,
            #lightbox.lb-panning .lb-prev,
            #lightbox.lb-panning .lb-next,
            #lightbox.lb-panning .lb-image { cursor: grabbing !important; }

            #lightbox .lb-image { transition: transform 0.1s ease; transform-origin: 50% 50%; }

            #lb-zoom-controls {
                position: fixed;
                bottom: 24px;
                left: 50%;
                transform: translateX(-50%);
                align-items: center;
                gap: 6px;
                background: rgba(0, 0, 0, 0.55);
                padding: 5px 10px;
                border-radius: 20px;
                z-index: 10100;
                backdrop-filter: blur(4px);
                -webkit-backdrop-filter: blur(4px);
            }
            #lb-zoom-controls button {
                background: none;
                border: 1px solid rgba(255, 255, 255, 0.45);
                color: #fff;
                width: 26px; height: 26px;
                border-radius: 4px;
                font-size: 18px;
                line-height: 1;
                cursor: pointer;
                padding: 0;
                transition: opacity 0.2s;
            }
            #lb-zoom-controls button:hover { background: rgba(255, 255, 255, 0.15); }
            #lb-zoom-level { color: #bbb; font-size: 12px; min-width: 36px; text-align: center; }
        `;
        document.head.appendChild(style);
    }

    function createControls() {
        const ctrl = document.createElement('div');
        ctrl.id = 'lb-zoom-controls';
        ctrl.style.display = 'none';
        ctrl.innerHTML =
            '<button id="lb-zoom-out" title="Zoom out (scroll down)">&#8722;</button>' +
            '<span id="lb-zoom-level">100%</span>' +
            '<button id="lb-zoom-in" title="Zoom in (scroll up)">+</button>';
        document.body.appendChild(ctrl);

        document.getElementById('lb-zoom-in').addEventListener('click', e => {
            e.stopPropagation();
            applyZoom(zoomLevel + ZOOM_STEP);
        });
        document.getElementById('lb-zoom-out').addEventListener('click', e => {
            e.stopPropagation();
            applyZoom(zoomLevel - ZOOM_STEP);
        });
    }

    function setup(lbEl) {
        lb = lbEl;

        lb.addEventListener('wheel',      onWheel,        { passive: false });
        lb.addEventListener('mousedown',  onMouseDown);
        lb.addEventListener('touchstart', onTouchStart,   { passive: true });
        lb.addEventListener('touchmove',  onTouchMove,    { passive: false });
        lb.addEventListener('touchend',   onTouchEnd,     { passive: true });
        lb.addEventListener('dblclick',   onDblClick);

        // Use document for move/up/click so events outside #lightbox (e.g. on the
        // overlay sibling) are still caught — a drag released over the overlay would
        // otherwise close the lightbox despite the pan-block guard.
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup',   onMouseUp);
        document.addEventListener('click',     onClickCapture, { capture: true });

        // Reset zoom on image navigation (src change = new image loaded).
        const img = lb.querySelector('.lb-image');
        if (img) {
            new MutationObserver(muts => {
                muts.forEach(m => { if (m.attributeName === 'src') resetZoom(); });
            }).observe(img, { attributes: true, attributeFilter: ['src'] });
        }

        // Show controls while lightbox is open; hide and reset when it closes.
        new MutationObserver(() => {
            const open = lb.style.display !== 'none';
            setControlsVisible(open);
            if (open) syncUI(); else resetZoom();
        }).observe(lb, { attributes: true, attributeFilter: ['style'] });

        createControls();
        injectStyles();
    }

    document.addEventListener('DOMContentLoaded', () => {
        new MutationObserver((_, obs) => {
            const el = document.getElementById('lightbox');
            if (el) { obs.disconnect(); setup(el); }
        }).observe(document.body, { childList: true });
    });
}());
