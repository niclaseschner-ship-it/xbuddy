// Tests für DC-17 — Iframe-Permissions für Browser-APIs (#960).
// Lauf: node --test display-client/tests/  (vom Repo-Root aus)
//
// Smoke-Test: index.html liefert den Inhalt-iframe mit dem
// allow-Attribut für Mikrofon und Autoplay aus. Ohne diese Klausel
// blockt der Browser getUserMedia() und Auto-Play von Buddy-Apps im
// iframe — selbst wenn am Top-Frame Permission gewährt ist.

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const INDEX_PATH = path.join(__dirname, '..', 'index.html');
const HTML = fs.readFileSync(INDEX_PATH, 'utf8');

test('DC-17 — Inhalt-iframe hat allow-Attribut mit microphone', () => {
  // Iframe-Tag mit id="content" und allow-Attribut, das microphone enthält.
  const match = HTML.match(/<iframe[^>]*id="content"[^>]*allow="([^"]+)"/);
  assert.ok(match,
    'iframe#content muss ein allow-Attribut tragen (DC-17)');
  const allow = match[1];
  assert.ok(/\bmicrophone\b/.test(allow),
    `allow="${allow}" muss "microphone" enthalten (DC-17 / KIBUDDY-5)`);
});

test('DC-17 — Inhalt-iframe hat allow-Attribut mit autoplay', () => {
  const match = HTML.match(/<iframe[^>]*id="content"[^>]*allow="([^"]+)"/);
  assert.ok(match,
    'iframe#content muss ein allow-Attribut tragen (DC-17)');
  const allow = match[1];
  assert.ok(/\bautoplay\b/.test(allow),
    `allow="${allow}" muss "autoplay" enthalten (DC-17 / KIBUDDY-20)`);
});
