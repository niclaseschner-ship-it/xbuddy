/**
 * app-installieren.js — gemeinsames Install-Skript aller PWA-Mäntel (#1955).
 *
 * Vorgeschichte: #1953 baute den Install-Hinweis nur für die Übersicht (eigene
 * Kopie in uebersicht.html). Ein Browser kann aber nur die gerade offene Seite
 * installieren — jeder Mantel (einkauf, plan, routine, wetter-regeln,
 * hoerspiel-eltern, hoerspiel-player, connector, shell, uebersicht) braucht
 * darum denselben Hinweis auf sich selbst. #1955 zieht die Logik hierher —
 * EINE Datei, von jedem Mantel eingebunden — statt einer zweiten Kopie.
 *
 * Sichtbarkeit (#1955-Abnahme):
 *   - Trägt das <script>-Tag `data-immer`, zeigt die Leiste immer (die
 *     Übersicht behält ihr bisheriges Verhalten unverändert).
 *   - Sonst nur bei `?installieren=1` in der Adresse (der „Installieren"-
 *     Knopf der Übersicht hängt den Parameter an) — ohne Parameter bleibt
 *     die Seite unverändert (#1955-AC).
 *   - Läuft die Seite schon standalone (installiert), zeigt sie nichts.
 *
 * Umgebungen:
 *   - Telegram-WebView: Installieren geht dort nicht — ein Knopf öffnet die
 *     aktuelle Adresse per `Telegram.WebApp.openLink` im externen Browser.
 *     Erkennung wie in platform.js (RAT-16): `window.Telegram.WebApp`
 *     existiert nur, wenn Telegram sie injiziert hat — kein SDK-Nachladen
 *     nötig (die Mini-App-Flotte verlässt sich bereits darauf). Läuft die
 *     Seite zusätzlich neben telegram-anmeldung.js (Übersicht/Kacheln), nutzt
 *     dieses Skript dessen `window.xbuddyTelegram` — selbe robustere
 *     Erkennung (Hash/initData), keine zweite Zustandsquelle.
 *   - iPhone/iPad (kein Telegram): Hinweis „Teilen → Zum Home-Bildschirm".
 *   - Sonst: wartet auf `beforeinstallprompt` und zeigt dann „App
 *     installieren" (Standard-Install-Dialog).
 *
 * Die Leiste ist selbst gestylt (eigenes <style>-Tag) — Mäntel haben völlig
 * unterschiedliche CSS-Systeme (mini-app-base.css, eigene Buddy-Styles, …);
 * eine gemeinsame Klasse in jedem Mantel-CSS nachzuziehen wäre eine zweite
 * Kopie an anderer Stelle.
 */
(function () {
  "use strict";

  // document.currentScript ist nur synchron beim Erstausführen gültig —
  // deshalb hier oben sichern, bevor irgendetwas auf DOMContentLoaded wartet.
  var skript = document.currentScript;

  function sollZeigen() {
    if (skript && skript.hasAttribute("data-immer")) return true;
    try {
      return new URLSearchParams(window.location.search).get("installieren") === "1";
    } catch (e) {
      return false;
    }
  }

  if (!sollZeigen()) return;

  function laeuftStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches
      || window.navigator.standalone === true;
  }

  // Telegram-Erkennung: bevorzugt window.xbuddyTelegram (telegram-anmeldung.js,
  // Übersicht/Kacheln — robuster, erkennt Telegram schon vor dem SDK-Laden).
  // Sonst die einfache platform.js-Heuristik (reicht für die übrigen Mäntel —
  // dieselbe Erkennung treibt dort bereits erfolgreich den Mini-App-Betrieb).
  function telegramBruecke() {
    if (window.xbuddyTelegram) return window.xbuddyTelegram;
    var wa = (window.Telegram && window.Telegram.WebApp) || null;
    return {
      imTelegram: !!wa,
      imBrowserOeffnen: function (url) {
        if (wa && typeof wa.openLink === "function") {
          wa.openLink(url, { tryBrowser: "chrome" });
          return;
        }
        window.open(url, "_blank", "noopener,noreferrer");
      },
    };
  }

  var STIL =
    ".xbi-leiste{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;" +
    "margin:0;background:#F5F1E8;border-top:2px solid #47503C;" +
    "padding:12px 16px calc(12px + env(safe-area-inset-bottom,0px));" +
    "font:15px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;" +
    "color:#23271E;box-shadow:0 -2px 10px rgba(0,0,0,.15)}" +
    ".xbi-leiste p{margin:0 0 8px}" +
    ".xbi-knopf{display:block;width:100%;box-sizing:border-box;padding:12px 16px;" +
    "font:inherit;font-size:16px;font-weight:600;border:none;border-radius:10px;" +
    "background:#47503C;color:#F5F1E8;cursor:pointer}" +
    ".xbi-knopf:active{opacity:.85}" +
    ".xbi-klein{margin:6px 0 0;font-size:13px;opacity:.8}";

  function leisteEinfuegen() {
    var style = document.createElement("style");
    style.textContent = STIL;
    document.head.appendChild(style);

    var box = document.createElement("section");
    box.className = "xbi-leiste";
    box.setAttribute("aria-label", "Als App installieren");
    document.body.insertBefore(box, document.body.firstChild);
    return box;
  }

  function leisteEntfernen() {
    var vorhanden = document.querySelectorAll(".xbi-leiste");
    vorhanden.forEach(function (el) { el.remove(); });
  }

  function haupt() {
    if (laeuftStandalone()) return;

    var tg = telegramBruecke();
    if (tg.imTelegram) {
      var boxTg = leisteEinfuegen();
      boxTg.innerHTML =
        "<p><strong>Als App installieren?</strong> In Telegram geht das nicht — " +
        "öffne die Seite im Browser und installiere sie dort.</p>" +
        '<button type="button" class="xbi-knopf" id="xbi-im-browser">' +
        "Als App installieren → im Browser öffnen</button>" +
        '<p class="xbi-klein">Ist das Gerät im Browser noch nicht angemeldet, ' +
        "frag den Familien-Bot nach einem Anmelde-Link.</p>";
      document.getElementById("xbi-im-browser").addEventListener("click", function () {
        tg.imBrowserOeffnen(window.location.href);
      });
      return;
    }

    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    if (ios) {
      var boxIos = leisteEinfuegen();
      boxIos.innerHTML =
        "<p><strong>Als App installieren:</strong> unten auf <em>Teilen</em> " +
        "tippen, dann <em>Zum Home-Bildschirm</em>.</p>";
      return;
    }

    var aufschub = null;
    window.addEventListener("beforeinstallprompt", function (ev) {
      ev.preventDefault();
      aufschub = ev;
      var boxBrowser = leisteEinfuegen();
      boxBrowser.innerHTML =
        "<p><strong>XBuddy als App</strong> — mit eigenem Symbol auf dem " +
        "Startbildschirm.</p>" +
        '<button type="button" class="xbi-knopf" id="xbi-app-installieren">' +
        "App installieren</button>";
      document.getElementById("xbi-app-installieren").addEventListener("click", function () {
        if (!aufschub) return;
        aufschub.prompt();
        aufschub.userChoice.catch(function () { return null; }).then(function () {
          aufschub = null;
          leisteEntfernen();
        });
      });
    });
    window.addEventListener("appinstalled", leisteEntfernen);
  }

  if (document.body) {
    haupt();
  } else {
    document.addEventListener("DOMContentLoaded", haupt);
  }
})();
