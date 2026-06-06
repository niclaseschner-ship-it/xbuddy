/* Photo-Buddy — clientseitiger Slideshow-/Grid-/Pause-Zustand (PHOTO-3/4/5).
 *
 * Siehe specs/buddies/photo.md §1. E-PHOTO-10: Übersicht und Pause sind
 * In-View-Zustände derselben Seite — kein Reload, der Slideshow-Index bleibt
 * erhalten. Die geordnete Medien-Liste + das Intervall kommen aus dem
 * <script id="photo-daten">-JSON, das render.baue_view (PHOTO-2/11) gefüllt hat.
 */
(function () {
  "use strict";

  var daten = JSON.parse(document.getElementById("photo-daten").textContent);
  var medien = daten.medien || [];
  var intervallMs = (daten.intervall_s || 8) * 1000;

  var bild = document.getElementById("medium-bild");
  var video = document.getElementById("medium-video");
  var karte = document.getElementById("medium-karte");
  var leer = document.getElementById("leer-zustand");
  var btnPrev = document.getElementById("nav-prev");
  var btnNext = document.getElementById("nav-next");
  var btnPause = document.getElementById("btn-pause");
  var btnGrid = document.getElementById("btn-grid");
  var iconPause = btnPause.querySelector(".icon-pause");
  var iconPlay = btnPause.querySelector(".icon-play");
  var gridOverlay = document.getElementById("grid-overlay");
  var gridScroll = document.getElementById("grid-scroll");
  var gridSchliessen = document.getElementById("grid-schliessen");

  var index = 0;
  var pausiert = false;
  var timer = null;

  // PHOTO-6: leere Library → neutraler Zustand, keine Bedienung nötig.
  if (medien.length === 0) {
    return;
  }

  function clearTimer() {
    if (timer) { clearTimeout(timer); timer = null; }
  }

  // Auto-Durchlauf: nach Intervall (Foto) bzw. nach Video-Ende weiterblättern
  // (PHOTO-3). Pausiert oder im Grid läuft kein Timer.
  function planeWeiter(medium) {
    clearTimer();
    if (pausiert || !gridOverlay.hidden) { return; }
    if (medium.typ === "video") {
      // Bei Video blättert der ended-Handler weiter; das Intervall ist die
      // Obergrenze, falls das Video nicht startet (Autoplay-Block).
      timer = setTimeout(weiter, Math.max(intervallMs, 1000));
    } else {
      timer = setTimeout(weiter, intervallMs);
    }
  }

  function zeige(i) {
    // Wrap-around am Anfang/Ende (PHOTO-4).
    index = (i + medien.length) % medien.length;
    var medium = medien[index];

    video.pause();
    video.hidden = true;
    video.removeAttribute("src");
    bild.hidden = true;

    if (medium.typ === "video") {
      video.src = medium.url;
      video.hidden = false;
      video.muted = true;           // PHOTO-6: stumm (Autoplay-sicher)
      var p = video.play();
      if (p && p.catch) { p.catch(function () {}); }
    } else {
      bild.src = medium.url;
      bild.hidden = false;
    }
    planeWeiter(medium);
  }

  function weiter() { zeige(index + 1); }
  function zurueck() { zeige(index - 1); }

  // Video-Ende → weiterblättern (PHOTO-3).
  video.addEventListener("ended", function () {
    if (!pausiert && gridOverlay.hidden) { weiter(); }
  });

  btnNext.addEventListener("click", function () { zeige(index + 1); });
  btnPrev.addEventListener("click", function () { zeige(index - 1); });

  // Pause/Play-Toggle (PHOTO-4).
  btnPause.addEventListener("click", function () {
    pausiert = !pausiert;
    iconPause.hidden = pausiert;
    iconPlay.hidden = !pausiert;
    btnPause.setAttribute("aria-label", pausiert ? "Abspielen" : "Pause");
    if (pausiert) {
      clearTimer();
      video.pause();
    } else {
      if (medien[index].typ === "video") {
        var p = video.play();
        if (p && p.catch) { p.catch(function () {}); }
      }
      planeWeiter(medien[index]);
    }
  });

  // ── Übersichts-Grid (PHOTO-5): In-View-Zustand, kein Reload ──────────────
  function baueGrid() {
    gridScroll.innerHTML = "";
    medien.forEach(function (medium, i) {
      var kachel = document.createElement("div");
      kachel.className = "grid-kachel";
      var img = document.createElement("img");
      img.src = medium.thumbnail;
      img.alt = "";
      kachel.appendChild(img);
      if (medium.typ === "video") {
        // PHOTO-5: Video-Thumbnails tragen ein Play-Icon-Overlay.
        var ov = document.createElement("div");
        ov.className = "grid-video-overlay";
        ov.innerHTML =
          '<svg width="64" height="64" viewBox="0 0 24 24" fill="currentColor">' +
          '<path d="M7 5v14l11-7z"/></svg>';
        kachel.appendChild(ov);
      }
      // Tap → zurück in die Einzelansicht auf genau dieses Medium (PHOTO-5).
      kachel.addEventListener("click", function () {
        schliesseGrid();
        zeige(i);
      });
      gridScroll.appendChild(kachel);
    });
  }

  function oeffneGrid() {
    baueGrid();
    gridOverlay.hidden = false;
    // PHOTO-5: im Übersichts-Modus pausiert der Durchlauf.
    clearTimer();
    video.pause();
  }

  function schliesseGrid() {
    gridOverlay.hidden = true;
    // Durchlauf nur fortsetzen, wenn nicht explizit pausiert (Zustand bleibt
    // erhalten, E-PHOTO-10).
    if (!pausiert) { planeWeiter(medien[index]); }
  }

  btnGrid.addEventListener("click", oeffneGrid);
  gridSchliessen.addEventListener("click", schliesseGrid);

  // Start (PHOTO-3): erstes (geordnetes) Medium zeigen, Durchlauf läuft.
  karte.hidden = false;
  leer.hidden = true;
  zeige(0);
})();
