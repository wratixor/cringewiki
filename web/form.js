/* SPDX-License-Identifier: AGPL-3.0-or-later */

let session;
let index;
const selectedTags = new Set();
const newTags = new Set();
const form = document.querySelector("form");
const message = document.querySelector("#message");

for (const slider of form.querySelectorAll('input[type="range"]')) {
  const output = form.querySelector(`output[for="${slider.name}"]`);
  const update = () => { output.value = slider.value; output.textContent = slider.value; };
  slider.addEventListener("input", update);
  update();
}

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

function setupTags() {
  const list = document.querySelector("#tag-list");
  const search = document.querySelector("#tag-search");
  const suggestions = document.querySelector("#tag-suggestions");
  const parentId = new URLSearchParams(location.search).get("parent") || "";
  const byId = (id) => index.concepts.find((concept) => concept.id === id);
  const render = () => {
    list.replaceChildren();
    const fixed = [index.currentUserPointId, parentId].filter((id, position, values) => id && values.indexOf(id) === position);
    for (const id of [...fixed, ...selectedTags]) {
      const concept = byId(id);
      if (!concept) continue;
      const chip = document.createElement("span");
      chip.className = `tag-chip${fixed.includes(id) ? " fixed" : ""}`;
      chip.textContent = concept.title;
      if (!fixed.includes(id)) {
        const remove = document.createElement("button");
        remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `Убрать тег ${concept.title}`);
        remove.addEventListener("click", () => { selectedTags.delete(id); render(); });
        chip.append(remove);
      }
      list.append(chip);
    }
    for (const title of newTags) {
      const chip = document.createElement("span");
      chip.className = "tag-chip new";
      chip.textContent = title;
      const remove = document.createElement("button");
      remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `Убрать тег ${title}`);
      remove.addEventListener("click", () => { newTags.delete(title); render(); });
      chip.append(remove);
      list.append(chip);
    }
  };
  const renderSuggestions = () => {
    const query = search.value.trim().toLocaleLowerCase("ru");
    suggestions.replaceChildren();
    if (!query) return;
    const fixed = new Set([index.currentUserPointId, parentId]);
    for (const concept of index.concepts.filter((item) => item.title.toLocaleLowerCase("ru").includes(query) && !fixed.has(item.id) && !selectedTags.has(item.id)).slice(0, 8)) {
      const button = document.createElement("button");
      button.type = "button"; button.textContent = concept.title;
      button.addEventListener("click", () => { selectedTags.add(concept.id); search.value = ""; suggestions.replaceChildren(); render(); });
      suggestions.append(button);
    }
    const hasExactTitle = index.concepts.some((item) => item.title.toLocaleLowerCase("ru") === query)
      || [...newTags].some((title) => title.toLocaleLowerCase("ru") === query);
    if (!hasExactTitle && selectedTags.size + newTags.size < 20) {
      const create = document.createElement("button");
      create.type = "button"; create.className = "new-tag-button"; create.textContent = `Создать тег «${search.value.trim()}»`;
      create.addEventListener("click", () => {
        newTags.add(search.value.trim()); search.value = ""; suggestions.replaceChildren(); render();
      });
      suggestions.append(create);
    }
  };
  search.addEventListener("input", renderSuggestions);
  form.dataset.parentId = byId(parentId) ? parentId : "";
  render();
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
    if (form.dataset.kind === "article") {
      payload.parentId = form.dataset.parentId || "";
      payload.tags = [...selectedTags];
      payload.newTags = [...newTags];
    }
    const result = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    location.href = form.dataset.kind === "article" ? `./#${result.id}` : "./";
  } catch (error) {
    message.textContent = error.message;
  }
});

start().then(async () => {
  if (form.dataset.kind === "article") index = await api("/api/index");
  if (form.dataset.kind === "article") setupTags();
}).catch((error) => { message.textContent = error.message; });
