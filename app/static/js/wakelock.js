(function () {
  if (!("wakeLock" in navigator)) return;

  let sentinel = null;

  const acquire = async () => {
    try {
      sentinel = await navigator.wakeLock.request("screen");
      sentinel.addEventListener("release", () => {
        sentinel = null;
      });
    } catch (err) {
      sentinel = null;
    }
  };

  acquire();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !sentinel) acquire();
  });
})();
