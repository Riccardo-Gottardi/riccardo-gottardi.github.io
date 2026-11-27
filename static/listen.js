// Audio version of a post: one <audio> per voice, the chosen one shown (the voice switch is a
// preference, handled by prefs.js). When the reader switches voice, the player that was in use
// stops and the newly shown one continues from the same point (by fraction: the voices read
// at slightly different speeds), playing if the other one was.

const players = [...document.querySelectorAll(".listen audio")];
let last = null; // the player the reader used last

for (const a of players) {
  for (const ev of ["play", "seeked"]) a.addEventListener(ev, () => { last = a; });
}

for (const button of document.querySelectorAll('[data-pref="voice"]')) {
  button.addEventListener("click", () => {
    const shown = players.find((a) => a.dataset.voice === button.dataset.value);
    if (!last || !shown || last === shown) return;
    const fraction = last.duration ? last.currentTime / last.duration : 0;
    const wasPlaying = !last.paused;
    last.pause();
    const resume = () => {
      shown.currentTime = fraction * shown.duration;
      if (wasPlaying) shown.play();
    };
    if (shown.readyState >= 1) resume();  // duration known
    else shown.addEventListener("loadedmetadata", resume, { once: true });
    last = shown;
  });
}
