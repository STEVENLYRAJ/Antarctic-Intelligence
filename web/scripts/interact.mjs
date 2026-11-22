// Dev-only interaction test: exercises explorer timeline, search, regions, keyboard and the nav mega menu.
import puppeteer from "puppeteer-core";
const base = process.argv[2] ?? "http://localhost:3000";
const out = process.argv[3];
const b = await puppeteer.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900 });
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => m.type() === "error" && errors.push(m.text()));
p.on("response", (r) => r.status() >= 400 && errors.push(`${r.status()} ${r.url()}`));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const res = {};
await p.goto(`${base}/explore`, { waitUntil: "domcontentloaded" });
await wait(14000);
const label = () => p.$eval('input[aria-label^="Time:"]', (e) => e.getAttribute("aria-label"));
res.timeline_start = await label();
await p.click('button[aria-label="Play"]');
await wait(3000);
res.timeline_after_play = await label();
await p.keyboard.press("Space"); // pause
await p.keyboard.press("ArrowRight");
await wait(300);
res.timeline_after_step = await label();
// region chip
await p.evaluate(() => [...document.querySelectorAll('[aria-label="Camera destinations"] button')].find((b) => b.textContent === "Ross Sea").click());
await wait(4000);
res.region_panel = await p.$eval('aside[aria-label$="details"] p.font-display', (e) => e.textContent).catch(() => null);
res.camera_after_region = await p.evaluate(() => [...document.querySelectorAll("span")].map((s) => s.textContent).find((t) => t?.startsWith("Camera ")));
// search
await p.type('input[aria-label="Search places or coordinates"]', "Thwaites");
await wait(300);
res.suggestions = await p.$$eval("ul.glass li button", (bs) => bs.map((b) => b.textContent.trim()).slice(0, 3));
await p.keyboard.press("Enter");
await wait(4000);
res.camera_after_search = await p.evaluate(() => [...document.querySelectorAll("span")].map((s) => s.textContent).find((t) => t?.startsWith("Camera ")));
// layer toggle on
await p.evaluate(() => [...document.querySelectorAll('aside[aria-label="Map layers"] label')].find((l) => l.textContent.includes("drift")).querySelector("input").click());
await wait(3000);
res.active_layers_footer = await p.$$eval('aside[aria-label="Map layers"] footer p.truncate', (ps) => ps.map((x) => x.textContent).filter((t) => t.length > 20));
// keyboard L toggles panel
await p.keyboard.press("l");
await wait(700);
res.panel_hidden_after_L = await p.$eval('aside[aria-label="Map layers"]', (e) => e.getAttribute("aria-hidden"));
if (out) await p.screenshot({ path: out });
// mega menu
await p.goto(`${base}/`, { waitUntil: "domcontentloaded" });
await wait(3000);
await p.click('button[aria-controls="mega-models"]');
await wait(500);
res.mega_links = await p.$$eval("#mega-models a", (as) => as.map((a) => a.getAttribute("href")));
await p.keyboard.press("Escape");
await wait(400);
res.mega_hidden_after_esc = await p.$eval("#mega-models", (e) => e.getAttribute("aria-hidden"));
res.errors = errors;
console.log(JSON.stringify(res, null, 1));
await b.close();
