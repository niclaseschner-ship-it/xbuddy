/**
 * platform.js — vendor-neutraler Wrapper für Mini-App-Frontends.
 *
 * RAT-16 (decisions/RAT-16-telegram-mvp-matrix-vertagt.md): Frontends
 * nutzen diesen Wrapper. Sie kennen kein Telegram-Vokabular — späterer
 * Plattform-Wechsel = nur dieses File anfassen, kein App-Neubau.
 *
 * Auto-Detect: Telegram.WebApp ODER reiner Browser.
 *
 * API:
 *   const platform = getPlatform();
 *   await platform.ready();
 *   const user = platform.getCurrentUser();      // {id, first_name} oder null
 *   platform.setMainButton(label, onClick, opts);// Telegram MainButton oder DOM-Fallback
 *                                                // opts: {enabled: bool} (default: true)
 *   platform.hideMainButton();                   // Button vollständig verstecken
 *   platform.showMainButton();                   // Button wieder anzeigen (Label + State bleiben)
 *   platform.enableClosingConfirmation();        // Dirty-Guard aktivieren
 *   platform.setDirty(bool);                    // Änderungs-Signal
 *   platform.onSave(callback);                  // Speicher-Handler registrieren
 *   platform.openLink(url);                     // URL im System-Browser oeffnen (MAU-6)
 *   platform.copyText(text);                    // Text in Zwischenablage kopieren — gibt bool zurueck (MAU-6)
 */

// --- Telegram-Branch --------------------------------------------------------

class TelegramPlatform {
  constructor(webApp) {
    this._wa = webApp;
    this._saveCallback = null;
  }

  async ready() {
    this._wa.ready();
  }

  getCurrentUser() {
    // initDataUnsafe: nur für Anzeige, nicht server-seitig geprüft (Track B).
    return this._wa.initDataUnsafe?.user ?? null;
  }

  setMainButton(label, onClick, opts) {
    const btn = this._wa.MainButton;
    const enabled = !opts || opts.enabled !== false;
    btn.setText(label);
    // Bestehenden Listener austauschen, um Doppelung zu vermeiden.
    btn.offClick(this._mainButtonHandler);
    this._mainButtonHandler = () => {
      if (this._saveCallback) this._saveCallback();
      if (onClick) onClick();
    };
    btn.onClick(this._mainButtonHandler);
    if (enabled) {
      btn.enable();
    } else {
      btn.disable();
    }
    btn.show();
    // Handler + Label merken für show/hide-Restore
    this._mainButtonLabel = label;
    this._mainButtonOnClick = onClick;
    this._mainButtonEnabled = enabled;
  }

  hideMainButton() {
    this._wa.MainButton.hide();
  }

  showMainButton() {
    // Setzt den Button sichtbar; Label/enabled-State bleiben erhalten.
    this._wa.MainButton.show();
  }

  enableClosingConfirmation() {
    this._wa.enableClosingConfirmation();
  }

  setDirty(isDirty) {
    // Telegram: closing-confirmation per enableClosingConfirmation() aktiv.
    // Platzhalter für spätere Adapter (z.B. Matrix-Widget-API).
    void isDirty;
  }

  onSave(callback) {
    this._saveCallback = callback;
  }

  // MAU-6: URL im System-Browser oeffnen via WebApp.openLink (offiziell garantiert).
  // tryBrowser: 'chrome' hint damit Telegram moeglichst den nativen Browser nutzt.
  openLink(url) {
    this._wa.openLink(url, { tryBrowser: "chrome" });
  }

  // MAU-6: Text in Zwischenablage kopieren.
  // navigator.clipboard.writeText ist in Telegram-Mini-App gesperrt (NotAllowedError, memory).
  // execCommand('copy') ist deprecated aber praktisch haeufig erfolgreich (Best-Effort-Fallback).
  // Gibt true bei Erfolg, false bei Fehler zurueck.
  copyText(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok === true;
    } catch (e) {
      return false;
    }
  }
}

// --- Browser-Branch (DOM-Fallback) ------------------------------------------

class BrowserPlatform {
  constructor() {
    this._saveCallback = null;
    this._beforeUnloadHandler = null;
    this._btn = null;
  }

  async ready() {
    // Browser: sofort bereit.
  }

  getCurrentUser() {
    // Im reinen Browser keine Identität verfügbar (kein Telegram-Kontext).
    return null;
  }

  setMainButton(label, onClick, opts) {
    const enabled = !opts || opts.enabled !== false;
    if (!this._btn) {
      this._btn = document.createElement("button");
      // Browser-Fallback, keine Design-Token-Bindung in V1.
      Object.assign(this._btn.style, {
        position:     "fixed",
        bottom:       "16px",
        left:         "16px",
        right:        "16px",
        width:        "calc(100% - 32px)",
        padding:      "14px 16px",
        fontSize:     "1rem",
        fontWeight:   "600",
        background:   "#2d62d8",
        color:        "#ffffff",
        border:       "none",
        borderRadius: "8px",
        cursor:       "pointer",
        zIndex:       "100",
        boxShadow:    "0 2px 8px rgba(0,0,0,0.18)",
        minHeight:    "44px",
      });
      document.body.appendChild(this._btn);
    }

    this._btn.textContent = label;
    this._btn.disabled = !enabled;

    // Handler tauschen (kein doppelter Listener).
    if (this._clickHandler) {
      this._btn.removeEventListener("click", this._clickHandler);
    }
    this._clickHandler = () => {
      if (this._saveCallback) this._saveCallback();
      if (onClick) onClick();
    };
    this._btn.addEventListener("click", this._clickHandler);
    this._btn.style.display = "block";
  }

  hideMainButton() {
    if (this._btn) {
      this._btn.style.display = "none";
    }
  }

  showMainButton() {
    // Setzt den Button sichtbar; Label/disabled-State bleiben erhalten.
    if (this._btn) {
      this._btn.style.display = "block";
    }
  }

  enableClosingConfirmation() {
    if (this._beforeUnloadHandler) return; // nicht doppelt registrieren
    this._beforeUnloadHandler = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", this._beforeUnloadHandler);
  }

  setDirty(isDirty) {
    if (isDirty) {
      this.enableClosingConfirmation();
    } else if (this._beforeUnloadHandler) {
      window.removeEventListener("beforeunload", this._beforeUnloadHandler);
      this._beforeUnloadHandler = null;
    }
  }

  onSave(callback) {
    this._saveCallback = callback;
  }

  // MAU-6: URL in neuem Tab oeffnen (Browser-Fallback fuer openLink).
  openLink(url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  // MAU-6: Text in Zwischenablage kopieren via navigator.clipboard (Browser unterstuetzt es).
  // Gibt true zurueck wenn erfolgreich, false bei Fehler.
  copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      // Asynchron — wir starten den Promise, koennen aber nicht synchron warten.
      // Rueckgabe true als optimistisches Signal (Browser-Kontext).
      navigator.clipboard.writeText(text).catch(() => {});
      return true;
    }
    // Fallback fuer aeltere Browser
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok === true;
    } catch (e) {
      return false;
    }
  }
}

// --- Auto-Detect + Export ---------------------------------------------------

function getPlatform() {
  if (window.Telegram && window.Telegram.WebApp) {
    return new TelegramPlatform(window.Telegram.WebApp);
  }
  return new BrowserPlatform();
}
