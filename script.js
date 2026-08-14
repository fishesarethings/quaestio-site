(() => {
  "use strict";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- Terminal typing animation ---------------- */
  const termBody = document.getElementById("terminalBody");
  if (termBody) {
    const script = [
      { p: "$", cmd: " /ask \"who are you?\"", out: null },
      { p: "Q", cmd: "", out: '▸ "I\'m <b>Quaestio</b> — your server\'s own local AI. No cloud, no paywall. Ask me anything."' },
      { p: "$", cmd: " /rank @nova", out: null },
      { p: "Q", cmd: "", out: "▸ <b>Nova</b> is level <b>12</b> · 2,340 XP · next level in 160 XP" },
      { p: "$", cmd: " /welcomechannel #welcome", out: null },
      { p: "Q", cmd: "", out: '<span class="t-ok">✓</span> Welcome messages will now post in <b>#welcome</b>' },
      { p: "$", cmd: " /warn @spammer breaking rule 3", out: null },
      { p: "Q", cmd: "", out: '<span class="t-ok">✓</span> <b>@spammer</b> warned · 2/3 warns (auto-kick at 3)' },
      { p: "$", cmd: " /ask how should I structure a #resources channel?", out: null },
      { p: "Q", cmd: "", out: "▸ \"Pin the quick links first, then group by topic — and let members add tags so the channel stays tidy.\"" },
    ];

    const line = (p, cmd, out) => {
      const div = document.createElement("div");
      div.className = "t-line";
      if (out === null) {
        div.innerHTML = `<span class="t-prompt">${p}</span><span class="t-cmd">${cmd}</span>`;
      } else {
        div.innerHTML = `<span class="t-out">${out}</span>`;
      }
      termBody.appendChild(div);
    };

    const cursor = document.createElement("span");
    cursor.className = "t-cursor";
    termBody.appendChild(cursor);

    let i = 0;
    const tick = () => {
      if (i >= script.length) {
        cursor.remove();
        return;
      }
      const { p, cmd, out } = script[i];
      if (out === null) {
        line(p, cmd, out);
      } else {
        const typing = document.createElement("div");
        typing.className = "t-line";
        typing.innerHTML = `<span class="t-prompt">${p}</span><span class="t-cmd">${cmd}</span>`;
        termBody.insertBefore(typing, cursor);
        setTimeout(() => { typing.remove(); line(p, cmd, out); }, 900);
      }
      i++;
      setTimeout(tick, out === null ? 1100 : 1400);
    };
    reduced ? script.forEach(s => line(s.p, s.cmd, s.out)) : tick();
  }

  /* ---------------- Scroll reveal ---------------- */
  const revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduced) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("in"));
  }

  /* ---------------- Animated counters ---------------- */
  const counters = document.querySelectorAll("[data-count]");
  const animate = (el) => {
    const target = parseInt(el.dataset.count, 10);
    const suffix = el.dataset.suffix || "";
    if (reduced) { el.textContent = target + suffix; return; }
    const dur = 1300;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const counterIO = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { animate(e.target); counterIO.unobserve(e.target); }
      });
    },
    { threshold: 0.6 }
  );
  counters.forEach((c) => counterIO.observe(c));

  /* ---------------- Copy commands to clipboard ---------------- */
  const toast = document.getElementById("toast");
  let toastTimer = null;
  const showToast = (msg) => {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 1800);
  };

  document.querySelectorAll(".cmd").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cmd = btn.dataset.cmd;
      try {
        await navigator.clipboard.writeText(cmd);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = cmd;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      btn.classList.add("copied");
      showToast(`Copied ${cmd} — paste it in your server`);
      setTimeout(() => btn.classList.remove("copied"), 1200);
    });
  });

  /* ---------------- Subtle card tilt ---------------- */
  if (!reduced && window.matchMedia("(pointer: fine)").matches) {
    document.querySelectorAll(".card, .step").forEach((card) => {
      card.addEventListener("mousemove", (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `translateY(-6px) perspective(700px) rotateX(${-y * 5}deg) rotateY(${x * 5}deg)`;
      });
      card.addEventListener("mouseleave", () => {
        card.style.transform = "";
      });
    });
  }

  /* ---------------- Active nav link ---------------- */
  const sections = [...document.querySelectorAll("section[id]")];
  const navLinks = [...document.querySelectorAll(".nav .links a")];
  if (sections.length && navLinks.length && "IntersectionObserver" in window) {
    const spy = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            const id = e.target.id;
            navLinks.forEach((a) => {
              a.style.color = a.getAttribute("href") === `#${id}` ? "var(--text)" : "";
            });
          }
        });
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    sections.forEach((s) => spy.observe(s));
  }
})();
