// figlib.js — pure logic and state machine for the figure-recognition controller.
// FIG-IDs verweisen auf specs/platform/figuren-erkennung.md.
// UMD-Wrapper: läuft sowohl im Browser (globalThis.figLib) als auch in Node (require).

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.figLib = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ============================================================
  //  Geometrie
  // ============================================================

  function dist(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function centroid(pts) {
    if (!pts || pts.length === 0) return { x: 0, y: 0 };
    let sx = 0, sy = 0;
    for (const p of pts) { sx += p.x; sy += p.y; }
    return { x: sx / pts.length, y: sy / pts.length };
  }

  // FIG-3 — Pattern-Descriptor: sortierte, auf längste Seite normalisierte Seitenlängen.
  function descriptor(p0, p1, p2) {
    const d = [dist(p0, p1), dist(p0, p2), dist(p1, p2)].sort((a, b) => a - b);
    const m = d[2] || 1;
    return [d[0] / m, d[1] / m, 1.0];
  }

  // FIG-5 — L1-Mittel-Distanz über die drei Descriptor-Komponenten.
  function patternDist(p, q) {
    return (Math.abs(p[0] - q[0]) + Math.abs(p[1] - q[1]) + Math.abs(p[2] - q[2])) / 3;
  }

  // FIG-5 — bestes Match unter Toleranz, sonst null.
  function identify(desc, registry, tol) {
    let bestId = null, bestScore = Infinity;
    for (const id in registry) {
      if (!Object.prototype.hasOwnProperty.call(registry, id)) continue;
      const s = patternDist(desc, registry[id]);
      if (s < bestScore) { bestScore = s; bestId = id; }
    }
    return bestScore <= tol ? bestId : null;
  }

  // FIG-6 — vorzeichen-behaftetes Delta zweier Winkel, normalisiert auf [-180, 180].
  function wrapDelta(d) {
    while (d >  180) d -= 360;
    while (d < -180) d += 360;
    return d;
  }

  // FIG-7 — Nächste-Nachbar-Zuordnung. Liefert Array {from, to} oder null wenn
  // eine Distanz > maxDist überschreitet (Kontakt-Bruch).
  function matchPoints(prev, curr, maxDist) {
    if (!prev || !curr || prev.length !== curr.length) return null;
    const usedCurr = new Set();
    const result = [];
    for (const p of prev) {
      let bestIdx = -1, bestD = Infinity;
      for (let i = 0; i < curr.length; i++) {
        if (usedCurr.has(i)) continue;
        const d = dist(p, curr[i]);
        if (d < bestD) { bestD = d; bestIdx = i; }
      }
      if (bestIdx === -1 || bestD > maxDist) return null;
      usedCurr.add(bestIdx);
      result.push({ from: p, to: curr[bestIdx] });
    }
    return result;
  }

  // FIG-7 — gemittelter Pro-Punkt-Rotations-Delta um den jeweiligen Schwerpunkt, in Grad.
  function frameRotationDelta(matches) {
    if (!matches || matches.length === 0) return 0;
    const cPrev = centroid(matches.map(m => m.from));
    const cCurr = centroid(matches.map(m => m.to));
    let sum = 0;
    for (const m of matches) {
      const a1 = Math.atan2(m.from.y - cPrev.y, m.from.x - cPrev.x);
      const a2 = Math.atan2(m.to.y   - cCurr.y, m.to.x   - cCurr.x);
      sum += wrapDelta((a2 - a1) * 180 / Math.PI);
    }
    return sum / matches.length;
  }

  // FIG-8 — Button-Kreis aus 3 Punkten: Mittelpunkt = Schwerpunkt,
  // Radius = max(distance to any vertex) + Padding.
  function buttonCircle(pts, padding) {
    if (!pts || pts.length < 3) return null;
    const c = centroid(pts);
    let r = 0;
    for (const p of pts) r = Math.max(r, dist(p, c));
    return { x: c.x, y: c.y, r: r + (padding || 30) };
  }

  function pointInCircle(p, circle) {
    if (!circle) return false;
    return Math.hypot(p.x - circle.x, p.y - circle.y) <= circle.r;
  }

  // ============================================================
  //  Konfiguration (FIG-17)
  // ============================================================

  function configDefaults() {
    return {
      source_id: 'phone:test-1',
      router_url: '',
      figure_present_ms: 150,
      pattern_tolerance: 0.05,
      match_distance_px: 60,
      tap_dwell_ms: 100,
      button_padding_px: 30,
      angle_update_max_hz: 10,
      angle_update_min_delta_deg: 3,
      registry: {
        'demo-dreieck-A': [0.50, 0.70, 1.0],
        'demo-dreieck-B': [0.85, 0.92, 1.0],
      },
    };
  }

  // ============================================================
  //  State Machine
  // ============================================================

  function createSession(config) {
    return {
      config: Object.assign({}, configDefaults(), config || {}),
      // FIG-2 Präsenz
      figurePresent: false,
      identifiedFigureId: null,
      lastIdentifiedFigureId: null,
      presentSince: null,
      // FIG-6 Akku
      cumulativeAngle: 0,
      lastFramePoints: null,
      lastSentCumulative: null,
      lastAngleSentAt: 0,
      // FIG-14 Diagnose: pro-Frame-Delta und Status der räumlichen Zuordnung
      lastFrameDelta: 0,
      lastMatchOk: null,  // 'ok' | 'fail' | 'reanchor' | null
      // FIG-8 Button
      buttonCircle: null,
      buttonDwellStart: null,
      buttonDwellTouchId: null,
      // sonst
      sessionId: null,
    };
  }

  function makeEvent(session, type, fields) {
    // FIG-10 — Pflichtfelder auf jedem Event
    return Object.assign({
      source_id: session.config.source_id,
      ts: new Date().toISOString(),
      type,
    }, fields);
  }

  // Wenn mehr als 3 Touches vorhanden sind: nimm die drei mit niedrigster id.
  function pickThree(touches) {
    if (touches.length <= 3) return touches.slice();
    return touches.slice().sort((a, b) => a.id - b.id).slice(0, 3);
  }

  function startNewFigureSession(session, figureId, now, events) {
    session.sessionId = randomUuid();
    session.identifiedFigureId = figureId;
    session.lastIdentifiedFigureId = figureId;
    session.cumulativeAngle = 0;
    session.lastFramePoints = null;
    session.lastFrameDelta = 0;
    session.lastMatchOk = null;
    session.lastSentCumulative = 0;
    session.lastAngleSentAt = now;
    events.push(makeEvent(session, 'figure_detected', {
      figure_id: figureId,
      angle: 0,
    }));
  }

  function endSessionViaButton(session, now, events) {
    events.push(makeEvent(session, 'session_ended', {
      figure_id: session.identifiedFigureId,
      reason: 'user_button',
    }));
    session.lastIdentifiedFigureId = session.identifiedFigureId;
    session.figurePresent = false;
    session.identifiedFigureId = null;
    session.cumulativeAngle = 0;
    session.lastFramePoints = null;
    session.lastFrameDelta = 0;
    session.lastMatchOk = null;
    session.lastSentCumulative = null;
    session.buttonCircle = null;
    session.buttonDwellStart = null;
    session.buttonDwellTouchId = null;
    session.sessionId = null;
    session.presentSince = null;
  }

  // Verarbeitet einen Touch-Frame. touches: [{id, x, y}], now in ms.
  // Liefert die Events, die diese Verarbeitung emittiert.
  function feedTouches(session, touches, now) {
    const events = [];
    const cfg = session.config;
    const n = touches.length;

    if (n >= 3) {
      // === 3-Punkt-Frame ===
      const three = pickThree(touches);
      const desc = descriptor(three[0], three[1], three[2]);
      const matched = identify(desc, cfg.registry, cfg.pattern_tolerance);

      // FIG-2 Eintritt
      if (!session.figurePresent) {
        if (session.presentSince === null) session.presentSince = now;
        if (now - session.presentSince >= cfg.figure_present_ms) {
          session.figurePresent = true;
          if (matched) {
            startNewFigureSession(session, matched, now, events);
          } else {
            session.identifiedFigureId = null;
          }
        }
      } else if (matched && matched !== session.identifiedFigureId) {
        // FIG-11 — Wechsel auf andere Figur während Präsenz
        startNewFigureSession(session, matched, now, events);
      }

      // FIG-8 — Button nachführen
      if (session.figurePresent && session.identifiedFigureId) {
        session.buttonCircle = buttonCircle(three, cfg.button_padding_px);
      }

      // FIG-6 + FIG-7 — kumulativer Winkel
      if (session.figurePresent && session.identifiedFigureId) {
        const snapshot = three.map(p => ({ x: p.x, y: p.y }));
        if (session.lastFramePoints === null) {
          // erstmalig nach figure_detected: re-ankern, kein Delta
          session.lastFramePoints = snapshot;
          session.lastFrameDelta = 0;
          session.lastMatchOk = 'reanchor';
        } else {
          const m = matchPoints(session.lastFramePoints, snapshot, cfg.match_distance_px);
          if (!m) {
            // Zuordnung gescheitert → re-ankern ohne Delta (echtes Re-Placement)
            session.lastFramePoints = snapshot;
            session.lastFrameDelta = 0;
            session.lastMatchOk = 'fail';
          } else {
            const delta = frameRotationDelta(m);
            session.cumulativeAngle += delta;
            session.lastFramePoints = snapshot;
            session.lastFrameDelta = delta;
            session.lastMatchOk = 'ok';
          }
        }

        // FIG-11 — Drosselung + Dead-Zone
        const minInterval = 1000 / cfg.angle_update_max_hz;
        if (now - session.lastAngleSentAt >= minInterval &&
            (session.lastSentCumulative === null ||
             Math.abs(session.cumulativeAngle - session.lastSentCumulative) >= cfg.angle_update_min_delta_deg)) {
          events.push(makeEvent(session, 'angle_update', {
            figure_id: session.identifiedFigureId,
            angle: Math.round(session.cumulativeAngle * 10) / 10,
          }));
          session.lastSentCumulative = session.cumulativeAngle;
          session.lastAngleSentAt = now;
        }
      }

      // Button-Dwell zurücksetzen, weil 3-Punkt-Frame
      session.buttonDwellStart = null;
      session.buttonDwellTouchId = null;
    } else {
      // === n < 3 — KEIN Auto-Exit (FIG-2) ===
      session.presentSince = null;
      // lastFramePoints bleibt stehen: räumliche Zuordnung beim nächsten
      // 3-Punkt-Frame entscheidet, ob es Continuity ist (kleines Delta) oder
      // ein echtes Re-Placement (matchPoints liefert null → re-anker ohne
      // Delta). Re-Test 2026-05-20: ohne diese Persistenz blieb cum bei 0,
      // weil kapazitives Flackern jeden Frame re-ankerte.

      if (session.figurePresent && session.buttonCircle && n === 1) {
        const t = touches[0];
        if (pointInCircle(t, session.buttonCircle)) {
          // FIG-8 — Dwell innerhalb des Button-Kreises
          if (session.buttonDwellTouchId !== t.id) {
            session.buttonDwellTouchId = t.id;
            session.buttonDwellStart = now;
          } else if (session.buttonDwellStart !== null &&
                     now - session.buttonDwellStart >= cfg.tap_dwell_ms) {
            endSessionViaButton(session, now, events);
          }
        } else {
          session.buttonDwellStart = null;
          session.buttonDwellTouchId = null;
        }
      } else {
        session.buttonDwellStart = null;
        session.buttonDwellTouchId = null;
      }
    }

    return events;
  }

  function randomUuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  // ============================================================
  //  API
  // ============================================================

  return {
    // pure geometry & matching (genutzt extern in index.html und Tests)
    dist, centroid, descriptor, patternDist, identify,
    matchPoints, frameRotationDelta, pickThree,
    // session
    configDefaults, createSession, feedTouches,
  };
  // Interne Helfer (nicht exportiert): wrapDelta, buttonCircle, pointInCircle,
  // randomUuid, makeEvent, startNewFigureSession, endSessionViaButton.
});
