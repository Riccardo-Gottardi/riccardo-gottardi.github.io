// Display preferences: the sidebar toggles and the Folders/Graph switch on folder pages.
//
// A button with data-pref="spacing" data-value="wide" toggles <html data-spacing="wide">.
// Buttons marked data-exclusive form a group instead: clicking one selects its value
// (e.g. data-pref="view" data-value="tree"), and the one marked data-default is selected
// when nothing is saved. Choices are saved in localStorage as "pref-<name>" and re-applied
// by the inline script in <head> on every page. To add a preference: add the button(s)
// and the matching :root[data-...] CSS rules. No JS changes needed.

const root = document.documentElement;
const buttons = [...document.querySelectorAll("[data-pref]")];

function save(pref, value) {
  try {
    if (value) localStorage.setItem(`pref-${pref}`, value);
    else localStorage.removeItem(`pref-${pref}`);
  } catch (e) {
    // storage blocked (private mode etc.): the choice still works for this page
  }
}

function isOn(button) {
  const { pref, value } = button.dataset;
  const current = root.dataset[pref];
  return current === value || (current === undefined && "default" in button.dataset);
}

function syncAll() {
  for (const b of buttons) b.setAttribute("aria-pressed", String(isOn(b)));
}

for (const button of buttons) {
  button.addEventListener("click", () => {
    const { pref, value } = button.dataset;
    let next;
    if ("exclusive" in button.dataset) next = "default" in button.dataset ? null : value;
    else next = root.dataset[pref] === value ? null : value;
    if (next) root.dataset[pref] = next;
    else delete root.dataset[pref];
    save(pref, next);
    syncAll();
  });
}
syncAll();
