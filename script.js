(() => {
  "use strict";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- Terminal typing animation ---------------- */
  const termBody = document.getElementById("terminalBody");
  if (termBody) {
    // Demo cast: Nova + Kai are server members, Quaestio is the bot.
    const script = [
      { p: "Nova 💬", cmd: " @Quaestio how does XP work?", out: null },
      { p: "Quaestio 🤖", cmd: "", out: '▸ "Chat and you earn XP — past messages count, and reward roles unlock as you level. Want the top chatters?"' },
      { p: "Nova 💬", cmd: " sure, who's winning?", out: null },
      { p: "Quaestio 🤖", cmd: "", out: "▸ Ranking now: <b>1.</b> Nova · <b>2.</b> Kai · <b>3.</b> Mara — <code>/leaderboard</code> shows it live." },
      { p: "$", cmd: " /ask \"who are you?\"", out: null },
      { p: "Quaestio 🤖", cmd: "", out: '▸ "I\'m <b>Quaestio</b> — your server\'s own local AI. No cloud, no paywall. Ask me anything."' },
      { p: "$", cmd: " /rank @nova", out: null },
      { p: "Quaestio 🤖", cmd: "", out: "▸ <b>Nova</b> is level <b>12</b> · 2,340 XP · next level in 160 XP" },
      { p: "Kai 💬", cmd: " anyone up for dice? /dice 2d6", out: null },
      { p: "Quaestio 🤖", cmd: "", out: "▸ 🎲 <b>9</b> (5 + 4) — Kai wins the roll!" },
      { p: "Kai 💬", cmd: " /8ball will we win tonight?", out: null },
      { p: "Quaestio 🤖", cmd: "", out: "▸ 🎱 Signs point to yes." },
      { p: "Nova 💬", cmd: " /trivia", out: null },
      { p: "Quaestio 🤖", cmd: "", out: "▸ ❓ Red planet? Reply <code>/answer mars</code>" },
      { p: "Kai 💬", cmd: " /answer mars", out: null },
      { p: "Quaestio 🤖", cmd: "", out: '▸ ✅ Correct, Kai! <b>+1</b> trivia point.' },
      { p: "$", cmd: " /warn @spammer breaking rule 3", out: null },
      { p: "Quaestio 🤖", cmd: "", out: '<span class="t-ok">✓</span> <b>@spammer</b> warned · 2/3 warns (auto-kick at 3)' },
    ];

    const MAX_LINES = 9;
    const trim = () => {
      const lines = termBody.querySelectorAll(".t-line");
      for (let k = 0; k + MAX_LINES < lines.length; k++) lines[k].remove();
    };
    const pinCursor = () => { termBody.appendChild(cursor); };
    const line = (p, cmd, out) => {
      const div = document.createElement("div");
      div.className = "t-line";
      if (out === null) {
        div.innerHTML = `<span class="t-prompt">${p}</span><span class="t-cmd">${cmd}</span>`;
      } else {
        div.innerHTML = `<span class="t-out">${out}</span>`;
      }
      termBody.appendChild(div);
      trim();
      pinCursor();
    };

    const cursor = document.createElement("span");
    cursor.className = "t-cursor";
    termBody.appendChild(cursor);

    let i = 0;
    const tick = () => {
      if (i >= script.length) {
        // Loop the demo so the panel always feels alive.
        setTimeout(() => {
          termBody.querySelectorAll(".t-line").forEach((el) => el.remove());
          termBody.appendChild(cursor);
          i = 0;
          setTimeout(tick, 600);
        }, 7000);
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
        trim();
        pinCursor();
        setTimeout(() => { typing.remove(); line(p, cmd, out); }, 900);
      }
      i++;
      setTimeout(tick, out === null ? 1100 : 1400);
    };
    reduced ? script.forEach(s => line(s.p, s.cmd, s.out)) : tick();
  }

  /* ---------------- Consent banner ---------------- */
  try {
    const saved = (() => { try { return JSON.parse(localStorage.getItem("q_consent_v1") || "null"); } catch { return null; } })();
    const bar = document.getElementById("consent");
    if (!saved && bar) {
      bar.classList.remove("hidden");
      const done = (analytics) => {
        try { localStorage.setItem("q_consent_v1", JSON.stringify({ essential: true, analytics: !!analytics, at: Date.now() })); } catch {}
        bar.classList.add("hidden");
      };
      document.getElementById("consent-accept")?.addEventListener("click", () =>
        done(document.getElementById("consent-analytics")?.checked));
      document.getElementById("consent-reject")?.addEventListener("click", () => done(false));
    }
  } catch {}

  /* ---------------- Live server count ---------------- */
  (() => {
    const el = document.getElementById("stat-servers");
    if (!el) return;
    let last = parseInt(el.dataset.count || "2", 10);
    const box = el.closest(".stat");
    const popBox = () => {
      if (!box) return;
      box.style.transition = "transform .35s";
      box.style.transform = "scale(1.12)";
      setTimeout(() => (box.style.transform = ""), 380);
    };
    const burst = () => {
      const c = document.createElement("canvas");
      c.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:9999";
      document.body.appendChild(c);
      const x = c.getContext("2d");
      c.width = innerWidth; c.height = innerHeight;
      const cols = ["#6366f1", "#22d3ee", "#34d399", "#f5c518", "#f472b6"];
      const ps = Array.from({ length: 60 }, () => ({
        x: innerWidth / 2 + (Math.random() - 0.5) * 300, y: innerHeight * 0.3,
        vx: (Math.random() - 0.5) * 10, vy: -Math.random() * 10 - 2,
        s: Math.random() * 8 + 3, c: cols[(Math.random() * cols.length) | 0],
      }));
      let f = 0;
      const tick = () => {
        x.clearRect(0, 0, c.width, c.height);
        ps.forEach((p) => {
          p.x += p.vx; p.y += p.vy; p.vy += 0.45;
          x.fillStyle = p.c; x.fillRect(p.x, p.y, p.s, p.s * 0.6);
        });
        if (++f < 100) requestAnimationFrame(tick);
        else c.remove();
      };
      tick();
    };
    const poll = async () => {
      try {
        const r = await fetch("https://admin.quaestio.online/api/site/stats");
        const d = await r.json();
        const n = parseInt(d.servers, 10);
        if (Number.isFinite(n) && n > last) {
          last = n;
          el.dataset.count = String(n);
          el.textContent = String(n);
          burst();
          popBox();
        }
        const msgs = document.getElementById("stat-messages");
        if (msgs && Number.isFinite(d.messages)) {
          msgs.dataset.count = String(d.messages);
          msgs.textContent = Number(d.messages).toLocaleString();
        }
        const cmds = document.getElementById("stat-cmds");
        if (cmds && Number.isFinite(d.cmds)) {
          cmds.dataset.count = String(d.cmds);
          cmds.textContent = Number(d.cmds).toLocaleString();
        }
        const nodes = document.getElementById("stat-nodes");
        if (nodes && Number.isFinite(d.nodes)) {
          if (Number(d.nodes) > parseInt(nodes.dataset.count || "0", 10)) {
            nodes.dataset.count = String(d.nodes);
            nodes.textContent = String(d.nodes);
            burst();
            popBox();
          } else {
            nodes.dataset.count = String(d.nodes);
            nodes.textContent = String(d.nodes);
          }
        }
      } catch {}
      setTimeout(poll, 60000);
    };
    setTimeout(poll, 5000);
  })();

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

  const hint = document.getElementById("cmd-hint");
  const live = {
    "/dice": () => {
      const a = 1 + Math.floor(Math.random() * 6), b = 1 + Math.floor(Math.random() * 6);
      return `🎲 live roll: ${a} + ${b} = ${a + b}`;
    },
    "/8ball": () => {
      const answers = ["Signs point to yes.", "Ask again later.", "Without a doubt.", "Don't count on it.", "Most likely."];
      return `🎱 live answer: ${answers[Math.floor(Math.random() * answers.length)]}`;
    },
    "/coin": () => `🪙 live flip: ${Math.random() < 0.5 ? "heads" : "tails"}`,
    "/rps": () => {
      const throws = ["rock", "paper", "scissors"];
      const you = throws[Math.floor(Math.random() * 3)], bot = throws[Math.floor(Math.random() * 3)];
      const win = you === bot ? "tie!" : ((you === "rock" && bot === "scissors") || (you === "paper" && bot === "rock") || (you === "scissors" && bot === "paper")) ? "you win!" : "bot wins!";
      return `✊ live rps: you ${you} vs ${bot} — ${win}`;
    },
    "/slot": () => {
      const sym = ["🍒", "🍋", "🔔", "⭐", "💎"];
      const roll = [0, 1, 2].map(() => sym[Math.floor(Math.random() * sym.length)]);
      const win = roll[0] === roll[1] || roll[1] === roll[2];
      return `🎰 live slots: ${roll.join(" ")} — ${win ? "win!" : "try again"}`;
    },
    "/trivia": () => "❓ live trivia: Red planet? It's Mars. Try /answer in Discord!",
  };
  document.querySelectorAll(".cmd").forEach((btn) => {
    btn.addEventListener("contextmenu", (e) => {
      const fn = live[btn.dataset.cmd];
      if (!fn) return; // only demo chips handle right-click
      e.preventDefault();
      showToast(fn());
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    });
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
