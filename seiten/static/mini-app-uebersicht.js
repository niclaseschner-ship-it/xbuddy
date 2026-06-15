/**
 * mini-app-uebersicht.js — MAU-Mini-App-Frontend.
 *
 * MAU-2: Inventar-Quelle ist /api/v1/seiten (Aggregator), keine hardcoded Liste.
 * MAU-4: drei Accordion-Sektionen via <details>; JS rendert Inhalt dynamisch.
 * MAU-5: Mini-App-Kachel-Tap → WebApp.openTelegramLink(web_app_url); Fallback funnel_url.
 * MAU-6: URL-Karten — Oeffnen via platform.openLink; Kopieren via platform.copyText + Toast.
 * MAU-8: Loading-State, 401-Fehler, 5xx-Fehler, snapshot_pending-Banner.
 * MAD-5: kein direktes Telegram.WebApp — alles ueber platform.js.
 * MAD-7: initData aus Telegram.WebApp.initData als Authorization-Header bei API-Call.
 */

(async function main() {
  const platform = getPlatform();
  await platform.ready();

  // MAD-11: JS-Side-Auth-Probe (HTML-Route ist public — Skeleton lädt ohne Auth,
  // hier prüft JS, ob valide initData für die API-Aufrufe vorliegt).
  if (!(await platform.ensureAuth())) {
    document.body.innerHTML = '<div style="padding:2rem;text-align:center;font-family:system-ui;color:#666;font-size:1rem">Bitte über den Familien-Bot öffnen (initData fehlt oder ist ungültig).</div>';
    return;
  }

  // ── DOM-Referenzen ────────────────────────────────────────────────────────

  // Accordion-Bodies der drei Skeleton-Sektionen (direkt im HTML vorhanden, MAU-8)
  const secMiniApps    = document.getElementById("sec-mini-apps");
  const secGeraete     = document.getElementById("sec-geraete-paare");
  const secBuddySeiten = document.getElementById("sec-buddy-seiten");
  const fehlerBanner   = document.getElementById("fehler-banner");
  const fehlerText     = document.getElementById("fehler-text");
  const btnSchliessen  = document.getElementById("btn-schliessen");
  const btnRetry       = document.getElementById("btn-retry");
  const snapshotBanner = document.getElementById("snapshot-banner");
  const toast          = document.getElementById("toast");

  // ── Toast-Hilfsfunktion ───────────────────────────────────────────────────

  let _toastTimer = null;

  function zeigeToast(text, istFehler) {
    toast.textContent = text;
    toast.className = "toast" + (istFehler ? " toast-fehler" : "");
    // Micro-Task: Klasse setzen NACH dem Reflow fuer CSS-Transition
    requestAnimationFrame(() => {
      toast.classList.add("sichtbar");
    });
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => {
      toast.classList.remove("sichtbar");
    }, 2800);
  }

  // ── Inventar laden (MAU-8) ────────────────────────────────────────────────

  function _getInitData() {
    // MAD-7: initData aus Telegram-Property (nur in Telegram-Context verfuegbar).
    // Im Browser-Fallback liefert die Property leer — API-Call geht dann ohne Auth.
    try {
      return (window.Telegram && window.Telegram.WebApp)
        ? window.Telegram.WebApp.initData || ""
        : "";
    } catch (e) {
      return "";
    }
  }

  async function ladeInventar() {
    const initData = _getInitData();
    const headers = initData
      ? { "Authorization": "tma " + initData }
      : {};

    const resp = await fetch("/api/v1/seiten", { headers });

    if (resp.status === 401) {
      throw Object.assign(new Error("auth"), { code: 401 });
    }
    if (!resp.ok) {
      throw Object.assign(new Error("netz"), { code: resp.status });
    }
    return resp.json();
  }

  // ── Fehler anzeigen (MAU-8) ───────────────────────────────────────────────

  function zeigeFehler(code) {
    if (code === 401) {
      fehlerText.textContent = "Bitte App neu oeffnen — Auth abgelaufen.";
      btnSchliessen.hidden = false;
      btnRetry.hidden = true;
      btnSchliessen.onclick = () => {
        try { window.Telegram.WebApp.close(); } catch (e) { window.close(); }
      };
    } else {
      fehlerText.textContent = "Inventar nicht erreichbar.";
      btnSchliessen.hidden = true;
      btnRetry.hidden = false;
      btnRetry.onclick = () => {
        fehlerBanner.hidden = true;
        hauptInhalt.innerHTML = "<p class=\"lade-hinweis\">Inventar wird geladen …</p>";
        startLaden();
      };
    }

    fehlerBanner.hidden = false;
  }

  // ── Render-Hilfsfunktionen ────────────────────────────────────────────────

  /**
   * Rendert eine URL-Karte (MAU-6): Label + Typ-Badge + URL-Mono + Oeffnen/Kopieren-Buttons.
   * Kein <a href> — Long-Press-Browser-Menue ist in Telegram-WebView unzuverlaessig (MAU-6).
   */
  function _bauUrlKarte(label, typ, url) {
    const karte = document.createElement("div");
    karte.className = "url-karte";

    const kopfzeile = document.createElement("div");
    kopfzeile.className = "url-karte-kopfzeile";

    const labelEl = document.createElement("span");
    labelEl.className = "url-karte-label";
    labelEl.textContent = label;

    const typEl = document.createElement("span");
    typEl.className = "url-karte-typ";
    typEl.textContent = typ;

    kopfzeile.appendChild(labelEl);
    kopfzeile.appendChild(typEl);

    const urlEl = document.createElement("code");
    urlEl.className = "url-mono";
    urlEl.textContent = url;

    const btnGruppe = document.createElement("div");
    btnGruppe.className = "url-btn-gruppe";

    const btnOeffnen = document.createElement("button");
    btnOeffnen.className = "url-btn url-btn-primary";
    btnOeffnen.textContent = "🔗 Oeffnen";
    btnOeffnen.setAttribute("aria-label", "URL im Browser oeffnen: " + url);
    btnOeffnen.addEventListener("click", () => {
      platform.openLink(url);
    });

    const btnKopieren = document.createElement("button");
    btnKopieren.className = "url-btn";
    btnKopieren.textContent = "📋 Kopieren";
    btnKopieren.setAttribute("aria-label", "URL kopieren: " + url);
    btnKopieren.addEventListener("click", () => {
      const ok = platform.copyText(url);
      if (ok) {
        zeigeToast("Link kopiert", false);
      } else {
        zeigeToast("Kopieren ging nicht — oeffne im Browser", true);
        platform.openLink(url);
      }
    });

    btnGruppe.appendChild(btnOeffnen);
    btnGruppe.appendChild(btnKopieren);

    karte.appendChild(kopfzeile);
    karte.appendChild(urlEl);
    karte.appendChild(btnGruppe);

    return karte;
  }

  // ── Sektion 1: Mini Telegram Apps (MAU-4 Punkt 1) ────────────────────────

  function rendereMinApps(container, miniApps) {
    if (!miniApps.length) {
      const leer = document.createElement("p");
      leer.className = "leer-hinweis";
      leer.textContent = "Keine Mini-Apps gefunden.";
      container.appendChild(leer);
      return;
    }

    const grid = document.createElement("div");
    grid.className = "kachel-grid";

    for (const app of miniApps) {
      const kachel = document.createElement("button");
      kachel.className = "mini-app-kachel";
      kachel.setAttribute("aria-label", app.label + " oeffnen");
      kachel.dataset.webAppUrl = app.web_app_url || "";
      kachel.dataset.funnelUrl = app.funnel_url || "";

      // Icon (MAD-6: /display/_shared/icons/arasaac/ — falls vorhanden)
      const icons = app.icons || [];
      const bild = document.createElement("img");
      bild.className = "kachel-bild";
      bild.loading = "lazy";
      bild.alt = "";
      if (icons.length > 0) {
        bild.src = "/display/_shared/icons/arasaac/" + icons[0] + ".png";
      } else {
        bild.src = "";
        bild.alt = "📱";
        bild.style.display = "none";
      }

      const textDiv = document.createElement("div");
      textDiv.className = "kachel-text";

      const labelSpan = document.createElement("span");
      labelSpan.className = "kachel-label";
      labelSpan.textContent = app.label;

      textDiv.appendChild(labelSpan);

      const pfeil = document.createElement("span");
      pfeil.className = "kachel-oeffnen-pfeil";
      pfeil.textContent = "▶︎";
      pfeil.setAttribute("aria-hidden", "true");

      kachel.appendChild(bild);
      kachel.appendChild(textDiv);
      kachel.appendChild(pfeil);

      // MAU-5: Tap → Mini-App im selben Overlay oeffnen via openTelegramLink
      kachel.addEventListener("click", () => {
        const webAppUrl = kachel.dataset.webAppUrl;
        const funnelUrl = kachel.dataset.funnelUrl;

        if (webAppUrl) {
          try {
            // MAU-5 Default-Pfad: openTelegramLink wechselt im selben Overlay
            window.Telegram.WebApp.openTelegramLink(webAppUrl);
          } catch (e) {
            // MAU-5 Fallback: funnel_url
            if (funnelUrl) {
              window.location.href = funnelUrl;
            }
          }
        } else if (funnelUrl) {
          window.location.href = funnelUrl;
        }
      });

      grid.appendChild(kachel);
    }

    container.appendChild(grid);
  }

  // ── Sektion 2: Geraete-Paare (MAU-4 Punkt 2) ─────────────────────────────

  function rendereGeraetePaare(container, displayClients, panels) {
    // Sortierung: alphabetisch nach instanz (display_id) — MAU-4
    const displays = [...displayClients].sort((a, b) =>
      (a.instanz || "").localeCompare(b.instanz || "")
    );

    if (!displays.length) {
      const leer = document.createElement("p");
      leer.className = "leer-hinweis";
      leer.textContent = "Keine Geraete-Paare gefunden.";
      container.appendChild(leer);
      return;
    }

    // Panel-Index fuer Reverse-Lookup (panel_id → panel-Eintrag)
    const panelIndex = {};
    for (const p of panels) {
      if (p.instanz) panelIndex[p.instanz] = p;
    }

    for (const display of displays) {
      const paar = document.createElement("div");
      paar.className = "geraete-paar";

      const paarLabel = document.createElement("div");
      paarLabel.className = "geraete-paar-label";
      paarLabel.textContent = display.label || display.instanz || "Display";
      paar.appendChild(paarLabel);

      // Display-Karte mit URL (Heim + Tailscale wenn vorhanden)
      // URL = pfad des display-client-Eintrags
      const displayUrl = (window.location.origin || "") + (display.pfad || "");
      const displayKarte = _bauUrlKarte(
        display.label || display.instanz,
        "Display",
        displayUrl
      );
      paar.appendChild(displayKarte);

      // Panel(s) die dieses Display steuern
      const verbPanelIds = display.verknuepft_mit_panels || [];
      for (const panelId of verbPanelIds) {
        const panelEintrag = panelIndex[panelId];
        const panelPfad = (panelEintrag && panelEintrag.pfad)
          ? panelEintrag.pfad
          : "/controller/app-panel/" + panelId;
        const panelUrl = (window.location.origin || "") + panelPfad;
        const panelKarte = _bauUrlKarte(
          (panelEintrag && panelEintrag.label) || "Panel " + panelId,
          "Panel",
          panelUrl
        );
        paar.appendChild(panelKarte);
      }

      container.appendChild(paar);
    }
  }

  // ── Sektion 3: Buddy-Seiten (MAU-4 Punkt 3) ──────────────────────────────

  function rendereBuddySeiten(container, elternViews) {
    if (!elternViews.length) {
      const leer = document.createElement("p");
      leer.className = "leer-hinweis";
      leer.textContent = "Keine Buddy-Seiten gefunden.";
      container.appendChild(leer);
      return;
    }

    // Gruppieren nach app-Slug (MAU-4: analog SREG-12)
    const gruppen = {};
    for (const view of elternViews) {
      const slug = view.app || "sonstige";
      if (!gruppen[slug]) gruppen[slug] = [];
      gruppen[slug].push(view);
    }

    // Sortierung: Gruppen nach Karten-Anzahl absteigend, dann alphabetisch (MAU-4)
    const sortierteSlugs = Object.keys(gruppen).sort((a, b) => {
      const diff = gruppen[b].length - gruppen[a].length;
      return diff !== 0 ? diff : a.localeCompare(b);
    });

    for (const slug of sortierteSlugs) {
      const gruppe = document.createElement("div");
      gruppe.className = "buddy-gruppe";

      const gruppeLabel = document.createElement("div");
      gruppeLabel.className = "buddy-gruppe-label";
      gruppeLabel.textContent = slug;
      gruppe.appendChild(gruppeLabel);

      const kartenContainer = document.createElement("div");
      kartenContainer.className = "buddy-gruppe-karten";

      for (const view of gruppen[slug]) {
        const url = (window.location.origin || "") + (view.pfad || "");
        const karte = _bauUrlKarte(view.label, "Seite", url);
        kartenContainer.appendChild(karte);
      }

      gruppe.appendChild(kartenContainer);
      container.appendChild(gruppe);
    }
  }

  // ── Inventar rendern (MAU-4) ──────────────────────────────────────────────

  function rendereInventar(inventar) {
    const eintraege = inventar.eintraege || [];
    const snapshotPending = inventar.snapshot_pending || [];

    // MAU-8: snapshot_pending Banner
    if (snapshotPending.length > 0) {
      snapshotBanner.hidden = false;
    }

    // Eintraege nach Typ filtern
    const miniApps       = eintraege.filter(e => e.typ === "mini-app");
    const displayClients = eintraege.filter(e => e.typ === "display-client");
    const panels         = eintraege.filter(e => e.typ === "panel");
    // Buddy-Seiten: eltern-Views (Sorte b)
    const elternViews    = eintraege.filter(e => e.typ === "eltern");

    // Skeleton-Bodies mit realem Inhalt befuellen (ersetzt Lade-Hinweis)
    // MAU-8: Skeleton-Elemente sind schon im HTML (drei collapsed <details>) — nur Inhalt ersetzen.

    // Sektion 1: Mini Telegram Apps
    const body1 = secMiniApps.querySelector(".accordion-body");
    body1.innerHTML = "";
    rendereMinApps(body1, miniApps);

    // Sektion 2: Geraete-Paare
    const body2 = secGeraete.querySelector(".accordion-body");
    body2.innerHTML = "";
    rendereGeraetePaare(body2, displayClients, panels);

    // Sektion 3: Buddy-Seiten
    const body3 = secBuddySeiten.querySelector(".accordion-body");
    body3.innerHTML = "";
    rendereBuddySeiten(body3, elternViews);
  }

  // ── Haupt-Lade-Sequenz (MAU-8) ────────────────────────────────────────────

  async function startLaden() {
    try {
      const inventar = await ladeInventar();
      rendereInventar(inventar);
    } catch (err) {
      zeigeFehler(err.code || 0);
    }
  }

  await startLaden();
})();
