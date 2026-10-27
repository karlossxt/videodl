/* Pruebas del núcleo puro del generador de QR.
   Se ejecutan con `node --test tests/qr-core.test.js` y no necesitan DOM. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const qr = require("../static/qr-core.js");

test("escapa los caracteres especiales del formato WIFI", () => {
  assert.equal(qr.escapeWifi("Mi;WiFi"), "Mi\\;WiFi");
  assert.equal(qr.escapeWifi('Casa "2"'), 'Casa \\"2\\"');
  assert.equal(qr.escapeWifi("a\\b,c:d"), "a\\\\b\\,c\\:d");
});

test("construye un QR de WiFi WPA con contraseña", () => {
  assert.equal(
    qr.buildPayload("wifi", {
      ssid: "MiRed",
      password: "secreto;123",
      encryption: "WPA",
    }),
    "WIFI:T:WPA;S:MiRed;P:secreto\\;123;;"
  );
});

test("una red abierta no incluye contraseña", () => {
  assert.equal(
    qr.buildPayload("wifi", {
      ssid: "Biblioteca",
      password: "ignorada",
      encryption: "nopass",
    }),
    "WIFI:T:nopass;S:Biblioteca;;"
  );
});

test("una red oculta añade H:true", () => {
  assert.equal(
    qr.buildPayload("wifi", {
      ssid: "Oculta",
      password: "1234",
      encryption: "WPA",
      hidden: true,
    }),
    "WIFI:T:WPA;S:Oculta;P:1234;H:true;;"
  );
});

test("el email codifica asunto y cuerpo", () => {
  assert.equal(
    qr.buildPayload("email", {
      email: "hola@example.com",
      subject: "Presupuesto",
      body: "Hola, quiero información",
    }),
    "mailto:hola@example.com?subject=Presupuesto&body=Hola%2C%20quiero%20informaci%C3%B3n"
  );
});

test("normaliza teléfonos y genera tel: y SMSTO:", () => {
  assert.equal(qr.normalizePhone("+34 600-123-456"), "+34600123456");
  assert.equal(qr.buildPayload("phone", { phone: "600 123 456" }), "tel:600123456");
  assert.equal(
    qr.buildPayload("sms", { phone: "+34 600 123 456", message: "Hola" }),
    "SMSTO:+34600123456:Hola"
  );
});

test("el texto se recorta y se devuelve tal cual", () => {
  assert.equal(qr.buildPayload("text", { text: "  https://example.com  " }), "https://example.com");
  assert.equal(qr.buildPayload("text", { text: "   " }), "");
});

test("valida el tamaño en bytes", () => {
  assert.equal(qr.byteLength("hola"), 4);
  assert.equal(qr.byteLength("ñ"), 2);
  assert.equal(qr.validatePayload("text", "a".repeat(1200)).ok, true);
  assert.equal(qr.validatePayload("text", "a".repeat(1201)).ok, false);
  assert.equal(qr.validatePayload("text", "ñ".repeat(601)).ok, false);
});

test("valida email y teléfono", () => {
  assert.equal(qr.validatePayload("email", "mailto:no-es-un-correo").ok, false);
  assert.equal(qr.validatePayload("email", "mailto:hola@example.com").ok, true);
  assert.equal(qr.validatePayload("phone", "tel:12").ok, false);
  assert.equal(qr.validatePayload("phone", "tel:+34600123456").ok, true);
  assert.equal(qr.validatePayload("sms", "SMSTO:+34600123456:Hola").ok, true);
});

test("calcula contraste y detecta estilos problemáticos", () => {
  assert.equal(Math.round(qr.contrastRatio("#000000", "#ffffff")), 21);
  assert.equal(Math.round(qr.contrastRatio("#ffffff", "#ffffff")), 1);
  assert.equal(qr.styleProblem("#000000", "#ffffff"), "");
  assert.match(qr.styleProblem("#ffffff", "#000000"), /oscuros/);
  assert.match(qr.styleProblem("#777777", "#888888"), /contraste/);
  assert.match(qr.styleProblem("negro", "#ffffff"), /#rrggbb/);
});
