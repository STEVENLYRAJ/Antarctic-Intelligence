// Dev-only visual check: node scripts/shoot.mjs <url> <out.png> [waitMs] [scrollY] [width] [height]
import puppeteer from "puppeteer-core";
const [url, out, wait = "12000", scrollY = "0", w = "1600", h = "900"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: "new",
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: +w, height: +h });
const errs = [];
page.on("pageerror", (e) => errs.push(String(e)));
page.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && errs.push(m.text()));
page.on("response", (r) => r.status() >= 400 && errs.push(`${r.status()} ${r.url()}`));
await page.goto(url, { waitUntil: "networkidle2", timeout: 120000 });
if (+scrollY) {
  // scroll in steps so ScrollTrigger sees intermediate positions
  for (let y = 0; y <= +scrollY; y += 400) { await page.evaluate((v) => window.scrollTo(0, v), y); await new Promise((r) => setTimeout(r, 60)); }
}
await new Promise((r) => setTimeout(r, +wait));
await page.screenshot({ path: out });
console.log(JSON.stringify({ errors: errs.slice(0, 8) }));
await browser.close();
