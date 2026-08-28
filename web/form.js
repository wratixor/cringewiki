/* SPDX-License-Identifier: AGPL-3.0-or-later */

let session;
const form = document.querySelector("form");
const message = document.querySelector("#message");

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": session?.csrfToken || "" },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function start() {
  session = await api("/api/session");
  if (form.dataset.kind === "article" && !session.user) location.href = "login.html";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "Сохраняю…";
  const values = Object.fromEntries(new FormData(form));
  try {
    let endpoint;
    if (form.dataset.kind === "register") endpoint = "/api/register";
    if (form.dataset.kind === "login") endpoint = "/api/login";
    if (form.dataset.kind === "article") endpoint = "/api/articles";
    const payload = { ...values };
    if (form.dataset.coordinates === "true") {
      payload.coordinates = Array.from({ length: 6 }, (_, index) => Number(values[`c${index}`]));
      for (let index = 0; index < 6; index += 1) delete payload[`c${index}`];
    }
    const result = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    location.href = form.dataset.kind === "article" ? `./#${result.id}` : "./";
  } catch (error) {
    message.textContent = error.message;
  }
});

start().catch((error) => { message.textContent = error.message; });
