/**
 * telegram-anmeldung.js — die eine Übersicht meldet sich im Telegram-WebView
 * selbst an (#1946, Nic 2026-09-25: eine Seite für Browser und Telegram).
 *
 * Ablauf: Öffnet der Knopf im Familien-Chat die Übersicht, hängt Telegram die
 * signierte initData an die Adresse (`#tgWebAppData=…`). Fehlt dem WebView das
 * `xbuddy_session`-Cookie, tauscht dieses Skript die initData EINMAL gegen das
 * Cookie (`POST /auth/telegram`, Header `Authorization: tma <initData>`) und
 * lädt die Seite neu. Außerhalb von Telegram gibt es keine initData — dann tut
 * das Skript nichts.
 *
 * Getauscht wird nur, wenn das <script>-Tag `data-tauschen` trägt (der Server
 * setzt es, wenn kein gültiges Cookie da ist: auf der 401-Anweisungsseite immer,
 * auf der Übersicht im observe-Modus). Ein Merker in sessionStorage verhindert
 * eine Neulade-Schleife, falls das Cookie nicht haften bleibt.
 *
 * Links (#1946 Punkt 5): Links auf derselben Origin öffnen im WebView; Links
 * auf eine andere Origin gehen über Telegram.WebApp.openLink in den Browser.
 */
(function () {
  "use strict";

  var MERKER = "xbuddy-telegram-tausch";
  var SPERRE_MS = 60 * 1000;
  var SDK_URL = "https://telegram.org/js/telegram-web-app.js";

  function webApp() {
    return (window.Telegram && window.Telegram.WebApp) || null;
  }

  function initDataLesen() {
    var wa = webApp();
    if (wa && wa.initData) return wa.initData;
    var hash = (window.location.hash || "").replace(/^#/, "");
    if (!hash) return "";
    try {
      return new URLSearchParams(hash).get("tgWebAppData") || "";
    } catch (e) {
      return "";
    }
  }

  function imTelegram() {
    return !!initDataLesen() || !!window.TelegramWebviewProxy;
  }

  function kuerzlichVersucht() {
    try {
      var t = parseInt(window.sessionStorage.getItem(MERKER) || "0", 10);
      return Date.now() - t < SPERRE_MS;
    } catch (e) {
      // Ohne sessionStorage keine Schleifensperre — dann lieber nicht tauschen.
      return true;
    }
  }

  function merken() {
    try { window.sessionStorage.setItem(MERKER, String(Date.now())); } catch (e) { /* egal */ }
  }

  function tauschen(initData) {
    merken();
    return fetch("/auth/telegram", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Authorization": "tma " + initData },
    }).then(function (r) {
      if (r.ok) {
        window.location.reload();
        return true;
      }
      console.warn("Telegram-Anmeldung abgelehnt:", r.status);
      return false;
    }).catch(function (e) {
      console.warn("Telegram-Anmeldung fehlgeschlagen:", e);
      return false;
    });
  }

  function sdkLaden() {
    if (webApp()) { sdkBereit(); return; }
    var s = document.createElement("script");
    s.src = SDK_URL;
    s.onload = sdkBereit;
    document.head.appendChild(s);
  }

  function sdkBereit() {
    var wa = webApp();
    if (!wa) return;
    try { wa.ready(); wa.expand(); } catch (e) { /* ältere Clients */ }
  }

  function fremdeLinksUeberTelegram() {
    document.addEventListener("click", function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
      if (!a) return;
      var ziel;
      try { ziel = new URL(a.href, window.location.href); } catch (e) { return; }
      if (ziel.origin === window.location.origin) return;
      var wa = webApp();
      if (!wa || typeof wa.openLink !== "function") return;
      ev.preventDefault();
      wa.openLink(ziel.href);
    });
  }

  var skript = document.currentScript;
  var sollTauschen = !!(skript && skript.hasAttribute("data-tauschen"));

  if (!imTelegram()) return;

  sdkLaden();
  fremdeLinksUeberTelegram();

  var initData = initDataLesen();
  if (sollTauschen && initData && !kuerzlichVersucht()) {
    tauschen(initData);
  }
})();
