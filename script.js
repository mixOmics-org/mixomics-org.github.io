/* Copy-to-clipboard for code blocks.
   Progressive enhancement: the button is in the markup but does nothing
   without this file, and the block remains selectable either way. */
(() => {
  "use strict";

  const RESET_MS = 2000;

  function textOf(pre) {
    // innerText collapses the <span> wrappers and preserves line breaks
    return (pre.innerText || pre.textContent || "").replace(/\s+$/, "");
  }

  async function writeClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    // fallback for non-secure contexts (e.g. plain-http previews)
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:absolute;left:-9999px;top:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    if (!ok) throw new Error("execCommand copy failed");
  }

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    const target = document.querySelector(btn.getAttribute("data-copy"));
    if (!target) return;

    const status = btn.closest("section")?.querySelector(".code__status");
    let timer;

    btn.addEventListener("click", async () => {
      try {
        await writeClipboard(textOf(target));
        btn.dataset.state = "copied";
        btn.title = "Copied";
        if (status) status.textContent = "Copied to clipboard.";
      } catch {
        btn.title = "Press Ctrl/Cmd+C to copy";
        if (status) status.textContent = "Copy failed — select the text and press Ctrl/Cmd+C.";
      }
      clearTimeout(timer);
      timer = setTimeout(() => {
        delete btn.dataset.state;
        btn.title = "Copy";
        if (status) status.textContent = "";
      }, RESET_MS);
    });

    btn.title = "Copy";
  });
})();
