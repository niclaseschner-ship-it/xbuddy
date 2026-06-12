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
}

// --- Auto-Detect + Export ---------------------------------------------------

function getPlatform() {
  if (window.Telegram && window.Telegram.WebApp) {
    return new TelegramPlatform(window.Telegram.WebApp);
  }
  return new BrowserPlatform();
}
