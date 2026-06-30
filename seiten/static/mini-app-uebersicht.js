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

  // Fallback-Icons je Typ (display-client + panel haben heute keine icons[]
  // im Aggregator-Output — Server-Side-Spec-Folge-Ticket; bis dahin Emoji).
  const _TYP_FALLBACK_EMOJI = {
    "Display":         "📺",
    "Display-Client":  "📺",
    "Panel":           "📱",
    "Editor":          "⚙️",
    "Mini-App":        "🟦",
    "Controller":      "🎛️",
    "Eltern":          "📄",
    "Seite":           "📄",
    "Shell":           "🖥️",
  };

  /**
   * Rendert eine URL-Karte (MAU-6): Icon + Label + Typ-Badge + URL-Mono + Oeffnen/Kopieren-Buttons.
   * Kein <a href> — Long-Press-Browser-Menue ist in Telegram-WebView unzuverlaessig (MAU-6).
   * iconRef (optional): ARASAAC-Pfad (z.B. "arasaac/28339.png") aus inventar.icons[0].
   * Wenn iconRef fehlt: Emoji-Fallback je Typ (display-client/panel haben keine icons[]).
   * Wenn url eine t.me/-URL ist, oeffnet der Open-Button via openTelegramLink
   * (Mini-App-zu-Mini-App-Navigation im selben Telegram-Overlay).
   */
  function _bauUrlKarte(label, typ, url, iconRef) {
    const karte = document.createElement("div");
    karte.className = "url-karte";

    const kopfzeile = document.createElement("div");
    kopfzeile.className = "url-karte-kopfzeile";

    // Icon analog zur Mini-App-Kachel — SREG-12-konsistent: jede Seite ihr Icon.
    if (iconRef) {
      const ikon = document.createElement("img");
      ikon.className = "url-karte-icon";
      ikon.src = "/display/_shared/icons/" + iconRef;
      ikon.alt = "";
      ikon.loading = "lazy";
      kopfzeile.appendChild(ikon);
    } else if (_TYP_FALLBACK_EMOJI[typ]) {
      const ikonText = document.createElement("span");
      ikonText.className = "url-karte-icon-fallback";
      ikonText.textContent = _TYP_FALLBACK_EMOJI[typ];
      ikonText.setAttribute("aria-hidden", "true");
      kopfzeile.appendChild(ikonText);
    }

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

    // Telegram-Mini-App-Aware: t.me/-URLs gehen via openTelegramLink, alles
    // andere via platform.openLink (System-Browser). Lego-konsistent fuer alle
    // Karten-Typen, inkl. Mini-Apps.
    const _istTelegramDeepLink = url && url.indexOf("https://t.me/") === 0;

    const btnOeffnen = document.createElement("button");
    btnOeffnen.className = "url-btn url-btn-primary";
    btnOeffnen.textContent = "🔗 Oeffnen";
    btnOeffnen.setAttribute("aria-label", "Oeffnen: " + url);
    btnOeffnen.addEventListener("click", () => {
      if (_istTelegramDeepLink) {
        try {
          window.Telegram.WebApp.openTelegramLink(url);
          return;
        } catch (e) {
          // Fallback unten
        }
      }
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

    // Lego-Konsistenz: Mini-Apps rendern als URL-Karte (gleiche Form wie alle
    // anderen Karten in MAU). _bauUrlKarte erkennt t.me/-URLs und nutzt
    // openTelegramLink fuer den Open-Click. Icon kommt direkt aus icons[0]
    // (Aggregator liefert "arasaac/<id>.png" — kein doppelter Prefix).
    for (const app of miniApps) {
      const url = app.web_app_url || app.funnel_url || "";
      const ikon = (app.icons || [])[0];
      const karte = _bauUrlKarte(app.label, "Mini-App", url, ikon);
      container.appendChild(karte);
    }
  }

  // ── Sektion 2: Geraete-Paare (MAU-4 Punkt 2) ─────────────────────────────

  function rendereGeraetePaare(container, heroDisplays, panelIndex, editorByPanelId) {
    // Sortierung: alphabetisch nach instanz (SREG-12 Pattern).
    const displays = [...heroDisplays].sort((a, b) =>
      (a.instanz || "").localeCompare(b.instanz || "")
    );

    if (!displays.length) {
      const leer = document.createElement("p");
      leer.className = "leer-hinweis";
      leer.textContent = "Keine gekoppelten Display-Panel-Paare gefunden.";
      container.appendChild(leer);
      return;
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
      const displayIcon = (display.icons || [])[0];
      const displayKarte = _bauUrlKarte(
        display.label || display.instanz,
        "Display",
        displayUrl,
        displayIcon
      );
      paar.appendChild(displayKarte);

      // Panel(s) die dieses Display steuern — plus jeweils ihre Editor-Karte.
      // Editor-Lookup über verknuepft_mit_panel-Feld (SREG-12 Datentreue).
      const verbPanelIds = display.verknuepft_mit_panels || [];
      for (const panelId of verbPanelIds) {
        const panelEintrag = panelIndex[panelId];
        const panelPfad = (panelEintrag && panelEintrag.pfad)
          ? panelEintrag.pfad
          : "/controller/app-panel/" + panelId;
        const panelUrl = (window.location.origin || "") + panelPfad;
        const panelIcon = (panelEintrag && panelEintrag.icons || [])[0];
        const panelKarte = _bauUrlKarte(
          (panelEintrag && panelEintrag.label) || "Panel " + panelId,
          "Panel",
          panelUrl,
          panelIcon
        );
        paar.appendChild(panelKarte);

        // Shell-URL-Karten (SHELL-10, SREG-12-Form: Heim + Tailscale).
        // shell_urls kommt server-seitig aus dem Inventar-Eintrag (panel_id + origins,
        // gebaut in seiten/main.py::get_seiten — kein Hardcode im JS).
        const shellUrls = panelEintrag && panelEintrag.shell_urls;
        if (shellUrls) {
          if (shellUrls.heim) {
            const shellKarteHeim = _bauUrlKarte(
              "Shell Heim: " + ((panelEintrag && panelEintrag.label) || "Panel " + panelId),
              "Shell",
              shellUrls.heim,
              null
            );
            paar.appendChild(shellKarteHeim);
          }
          if (shellUrls.tailscale) {
            const shellKarteTailscale = _bauUrlKarte(
              "Shell Tailscale: " + ((panelEintrag && panelEintrag.label) || "Panel " + panelId),
              "Shell",
              shellUrls.tailscale,
              null
            );
            paar.appendChild(shellKarteTailscale);
          }
        }

        // Editor-Karte angedockt an dieses Panel (Lego via verknuepft_mit_panel).
        const editorView = editorByPanelId && editorByPanelId[panelId];
        if (editorView) {
          const editorUrl = (window.location.origin || "") + editorView.pfad;
          const editorIcon = (editorView.icons || [])[0];
          const editorKarte = _bauUrlKarte(
            editorView.label || ("Panel " + panelId + " bearbeiten"),
            "Editor",
            editorUrl,
            editorIcon
          );
          paar.appendChild(editorKarte);
        }
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

    // Gruppieren nach app-Slug (SREG-12 Pattern, render.py::_buddy_gruppen).
    // Sorten ohne app fallen in eine Sammel-Gruppe "instanz" (SREG-12 Punkt 3).
    const gruppen = {};
    for (const view of elternViews) {
      const slug = view.app || "instanz";
      if (!gruppen[slug]) gruppen[slug] = [];
      gruppen[slug].push(view);
    }

    // Sortierung Nics Setzung 2026-06-15: alphabetisch nach app-Slug
    // (deutlicher als SREG-12 "Karten-Anzahl absteigend").
    const sortierteSlugs = Object.keys(gruppen).sort((a, b) => a.localeCompare(b));

    for (const slug of sortierteSlugs) {
      const gruppe = document.createElement("div");
      gruppe.className = "buddy-gruppe";

      const gruppeLabel = document.createElement("div");
      gruppeLabel.className = "buddy-gruppe-label";
      gruppeLabel.textContent = slug;
      gruppe.appendChild(gruppeLabel);

      const kartenContainer = document.createElement("div");
      kartenContainer.className = "buddy-gruppe-karten";

      // Innerhalb der Gruppe: nach label alphabetisch (Lesbarkeit).
      const sortierteViews = [...gruppen[slug]].sort((a, b) =>
        (a.label || "").localeCompare(b.label || "")
      );
      for (const view of sortierteViews) {
        const url = (window.location.origin || "") + (view.pfad || "");
        const ikon = (view.icons || [])[0];
        // Typ-Badge je Sorte: Display für Kind-Tablet, Eltern, Controller, Panel.
        let typLabel = "Seite";
        if (view.typ === "display") typLabel = "Display";
        else if (view.typ === "controller") typLabel = "Controller";
        else if (view.typ === "panel") typLabel = "Panel";
        else if (view.typ === "display-client") typLabel = "Display-Client";
        else if (view.typ === "eltern") typLabel = "Eltern";
        const karte = _bauUrlKarte(view.label, typLabel, url, ikon);
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

    // Pattern aus SREG-12 (`seiten/render.py::_hero_paare`): Hero-Paare sind nur
    // Displays mit verknuepft_mit_panels. Panel-Editor-Anhang per
    // verknuepft_mit_panel-Feld (sauberer Lookup als Pfad-Regex).
    const miniApps = eintraege.filter(e => e.typ === "mini-app");
    const allePanels = eintraege.filter(e => e.typ === "panel");
    const panelIndex = {};
    for (const p of allePanels) {
      if (p.instanz) panelIndex[p.instanz] = p;
    }

    // Panel-Editor-Lookup via verknuepft_mit_panel-Feld (Datentreue-Lego).
    const editorByPanelId = {};
    for (const v of eintraege) {
      if (v.typ === "eltern" && v.verknuepft_mit_panel) {
        editorByPanelId[v.verknuepft_mit_panel] = v;
      }
    }

    // Hero-Paare: nur display-clients MIT verknuepft_mit_panels.
    const heroDisplays = eintraege.filter(e =>
      e.typ === "display-client"
      && Array.isArray(e.verknuepft_mit_panels)
      && e.verknuepft_mit_panels.length > 0
    );

    // Mitglieder der Hero-Paare — werden aus den Buddy-Gruppen ausgeschlossen.
    const inHero = new Set();
    for (const d of heroDisplays) {
      inHero.add("display-client:" + (d.instanz || ""));
      for (const pid of d.verknuepft_mit_panels) {
        inHero.add("panel:" + pid);
        if (editorByPanelId[pid]) {
          inHero.add("eltern:" + (editorByPanelId[pid].pfad || ""));
        }
      }
    }

    // Buddy-Gruppen-Einträge: ALLES außer mini-apps, Hero-Mitglieder, snapshot-pending.
    const buddyViews = eintraege.filter(e => {
      if (e.typ === "mini-app") return false;
      const key = e.typ + ":" + (e.instanz || e.pfad || "");
      if (e.typ === "display-client" && inHero.has("display-client:" + e.instanz)) return false;
      if (e.typ === "panel" && inHero.has("panel:" + e.instanz)) return false;
      if (e.typ === "eltern" && inHero.has("eltern:" + e.pfad)) return false;
      return true;
    });

    // Skeleton-Bodies mit realem Inhalt befuellen (ersetzt Lade-Hinweis)
    // MAU-8: Skeleton-Elemente sind schon im HTML (drei collapsed <details>) — nur Inhalt ersetzen.

    // Sektion 1: Mini Telegram Apps
    const body1 = secMiniApps.querySelector(".accordion-body");
    body1.innerHTML = "";
    rendereMinApps(body1, miniApps);

    // Sektion 2: Geraete-Paare (Hero — nur Displays mit Panel-Kopplung)
    const body2 = secGeraete.querySelector(".accordion-body");
    body2.innerHTML = "";
    rendereGeraetePaare(body2, heroDisplays, panelIndex, editorByPanelId);

    // Sektion 3: Buddy-Seiten (eltern + controller, ohne Panel-Editoren)
    const body3 = secBuddySeiten.querySelector(".accordion-body");
    body3.innerHTML = "";
    rendereBuddySeiten(body3, buddyViews);
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
