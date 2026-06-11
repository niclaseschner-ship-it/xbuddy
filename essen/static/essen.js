/**
 * Essens-Buddy — Client-Logik (ESSEN-3/8/9/27/28).
 *
 * Drei Tap-Affordanzen (ESSEN-3/27):
 *   (a) Kategorien-Tab tippen — wechselt das Item-Grid ohne Full-Reload.
 *   (b) Item-Kachel tippen — POST Wunsch, aktualisiert sichtbar die Liste.
 *   (c) Entfernen-Symbol tippen — DELETE Wunsch, Liste rendert neu (ESSEN-27).
 *
 * ESSEN-28: Kacheln mit .kachel-gesperrt lösen KEINEN POST aus (disabled +
 * Click-Handler-Guard). Nach POST/DELETE wird auch das Item-Grid neu gerendert,
 * damit Aktiv-Markierungen aktuell bleiben (Reload-on-Read, ESSEN-20).
 *
 * Kein Hover, kein Wischen, kein Aufklappen (ESSEN-3).
 * Tab-Wechsel und Wunsch-Ablage ohne Full-Reload (ESSEN-2/3, AC3).
 */

(function () {
  "use strict";

  // ── Tab-Wechsel (ESSEN-3a) ──────────────────────────────────────────────

  /**
   * Lädt das Item-Grid der gewählten Kategorie via GET ?tab=<slug> und
   * tauscht nur den Grid-Bereich aus (kein Full-Reload, ESSEN-8).
   */
  async function wechsleTab(slug) {
    // Aktiv-Markierung sofort visuell setzen (ESSEN-3: Tab-Wechsel wirkt ohne Reload).
    document.querySelectorAll(".tab").forEach(function (btn) {
      var aktiv = btn.dataset.tab === slug;
      btn.classList.toggle("aktiv", aktiv);
      btn.setAttribute("aria-pressed", aktiv ? "true" : "false");
    });

    try {
      var resp = await fetch("/display/essen/wunsch?tab=" + encodeURIComponent(slug), {
        headers: { "Accept": "text/html" }
      });
      if (!resp.ok) return;
      var html = await resp.text();
      // Aus der neuen Antwort nur den Grid-Bereich extrahieren.
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, "text/html");
      var neuesGrid = doc.getElementById("item-grid");
      if (neuesGrid) {
        var altes = document.getElementById("item-grid");
        if (altes) {
          altes.innerHTML = neuesGrid.innerHTML;
          // Neue Kacheln brauchen Event-Handler.
          bindKacheln();
        }
      }
    } catch (_) {
      // Netz-Fehler still ignorieren — Kiosk bleibt funktional (ESSEN-3).
    }
  }

  // ── Item-Tap: Wunsch ablegen (ESSEN-3b/ESSEN-16) ──────────────────────

  /**
   * POSTet einen neuen Wunsch und aktualisiert die Wunsch-Liste und das
   * Item-Grid (ESSEN-8/28). quelle ist immer "kind" für Display-Taps (ESSEN-16).
   * item_id wird mitgesendet, damit der Server Kacheln als .kachel-gesperrt
   * rendern kann (ESSEN-28, Render-Vertrag).
   */
  async function legeWunschAb(itemId, label, bildRef, kategorie) {
    try {
      var resp = await fetch("/api/v1/essen/wuensche", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          item_id: itemId,
          label: label,
          bild_ref: bildRef,
          quelle: "kind",
          kategorie: kategorie
        })
      });
      if (!resp.ok) return;  // Validierungsfehler still, Kiosk stabil (ESSEN-3).
      await aktualisiereGridUndListe();  // ESSEN-28: Grid-Refresh nötig für Sperr-Zustand.
    } catch (_) {
      // Netz-Fehler: Kiosk bleibt stabil.
    }
  }

  // ── Wunsch löschen (ESSEN-27) ─────────────────────────────────────────

  /**
   * Sendet DELETE /api/v1/essen/wuensche/<id> und rendert die Liste neu
   * (Reload-on-Read, ESSEN-20). Genau ein Tap auf das Entfernen-Symbol
   * löst genau einen DELETE-Request aus (ESSEN-27).
   */
  async function loescheWunsch(wunschId) {
    try {
      var resp = await fetch("/api/v1/essen/wuensche/" + encodeURIComponent(wunschId), {
        method: "DELETE"
      });
      if (!resp.ok) return;  // Kiosk bleibt stabil bei Netz-Fehler.
      await aktualisiereGridUndListe();  // ESSEN-28: Grid-Refresh gibt Kachel frei.
    } catch (_) {
      // Netz-Fehler: Kiosk bleibt stabil.
    }
  }

  // ── Grid + Liste aktualisieren (ESSEN-8/28) ──────────────────────────

  /**
   * Holt den aktuellen Stand via GET /display/essen/wunsch und ersetzt
   * den Liste-Bereich UND das Item-Grid (kein Full-Reload, ESSEN-3/8).
   *
   * ESSEN-28: Nach jedem POST/DELETE müssen auch die Kachel-Sperr-Zustände
   * aktualisiert werden. Ein einziger Fetch reicht — beide Bereiche werden
   * aus derselben Antwort extrahiert.
   */
  async function aktualisiereGridUndListe() {
    var aktivTab = document.querySelector(".tab.aktiv");
    var slug = aktivTab ? aktivTab.dataset.tab : "obst_gemuese";
    try {
      var resp = await fetch("/display/essen/wunsch?tab=" + encodeURIComponent(slug), {
        headers: { "Accept": "text/html" }
      });
      if (!resp.ok) return;
      var html = await resp.text();
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, "text/html");

      // Liste-Bereich tauschen (ESSEN-8).
      var neueEintraege = doc.getElementById("liste-eintraege");
      if (neueEintraege) {
        var alteListe = document.getElementById("liste-eintraege");
        if (alteListe) {
          alteListe.innerHTML = neueEintraege.innerHTML;
          // Neue Einträge brauchen Lösch-Handler (ESSEN-27).
          bindLoeschButtons();
        }
      }

      // Item-Grid tauschen — Kachel-Sperr-Zustand (ESSEN-28).
      var neuesGrid = doc.getElementById("item-grid");
      if (neuesGrid) {
        var altesGrid = document.getElementById("item-grid");
        if (altesGrid) {
          altesGrid.innerHTML = neuesGrid.innerHTML;
          // Neue Kacheln brauchen Event-Handler.
          bindKacheln();
        }
      }
    } catch (_) {}
  }

  // ── Event-Handler binden ─────────────────────────────────────────────

  function bindTabs() {
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        wechsleTab(btn.dataset.tab);
      });
    });
  }

  function bindKacheln() {
    document.querySelectorAll(".item-kachel").forEach(function (btn) {
      // Vorhandene Handler entfernen, um Doppel-Bindungen bei Grid-Refresh zu vermeiden.
      btn.replaceWith(btn.cloneNode(true));
    });
    // Neu binden nach Clone.
    document.querySelectorAll(".item-kachel").forEach(function (btn) {
      btn.addEventListener("click", function () {
        // ESSEN-28: gesperrte Kacheln lösen KEINEN POST aus (Click-Handler-Guard,
        // zusätzlich zum disabled-Attribut im HTML).
        if (btn.classList.contains("kachel-gesperrt")) return;
        legeWunschAb(
          btn.dataset.itemId,
          btn.dataset.label,
          btn.dataset.bildRef,
          btn.dataset.kategorie
        );
      });
    });
  }

  // ── Lösch-Buttons binden (ESSEN-27) ─────────────────────────────────

  /**
   * Bindet Click-Handler an alle .loeschen-btn-Elemente.
   * Die ID wird vom Eltern-Element .liste-eintrag[data-wunsch-id] gelesen.
   */
  function bindLoeschButtons() {
    document.querySelectorAll(".loeschen-btn").forEach(function (btn) {
      // Vorhandene Handler entfernen (Clone-Trick gegen Doppel-Bindungen).
      btn.replaceWith(btn.cloneNode(true));
    });
    document.querySelectorAll(".loeschen-btn").forEach(function (btn) {
      btn.addEventListener("click", function (evt) {
        evt.stopPropagation();  // Kein Bubble zum Eltern-Div.
        var eintrag = btn.closest(".liste-eintrag");
        var wunschId = eintrag ? eintrag.dataset.wunschId : null;
        if (wunschId) {
          loescheWunsch(wunschId);
        }
      });
    });
  }

  // ── Init ─────────────────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", function () {
    bindTabs();
    bindKacheln();
    bindLoeschButtons();
  });
})();
