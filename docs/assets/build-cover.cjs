// Generates the Fastro (open-source FastAPI boilerplate) cover as transparent
// light/dark PNGs, used at the top of the docs.
// Run: NODE_PATH=<a sharp install> node docs/assets/build-cover.cjs
const path = require('path');
const sharp = require('sharp');

const OUT = __dirname;

// Wordmark tracking. Negative = tighter. The previous cover jammed the letters
// together; this opens them up to match the rest of the brand covers.
const WORDMARK_TRACKING = -0.5;

const MODES = {
  light: { primary: '#111827', body: '#4b5563', muted: '#6b7280', termBorder: '#1f2937' },
  dark: { primary: '#f9fafb', body: '#d1d5db', muted: '#9ca3af', termBorder: '#30363d' },
};

const cover = ({ primary, body, muted, termBorder }) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430">
  <text x="66" y="78" font-family="'JetBrains Mono','SF Mono',ui-monospace,monospace" font-size="13" font-weight="700" letter-spacing="3.5" fill="${muted}">OPEN SOURCE · FASTAPI BOILERPLATE</text>
  <text x="62" y="172" font-family="'Space Grotesk',system-ui,sans-serif" font-size="82" font-weight="700" letter-spacing="${WORDMARK_TRACKING}" fill="${primary}">Fastro</text>

  <rect x="384" y="116" width="118" height="52" rx="26" fill="#0d9488"/>
  <text x="443" y="150" text-anchor="middle" font-family="'Space Grotesk',system-ui,sans-serif" font-size="22" font-weight="700" letter-spacing="2" fill="#ffffff">FREE</text>

  <rect x="66" y="198" width="4" height="62" rx="2" fill="#0d9488"/>
  <text x="86" y="224" font-family="system-ui,sans-serif" font-size="20" fill="${body}">Batteries-included FastAPI starter -</text>
  <text x="86" y="252" font-family="system-ui,sans-serif" font-size="20" fill="${body}">auth, CRUD, jobs, caching, rate-limits.</text>
  <text x="66" y="318" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" fill="${muted}" letter-spacing="0.5">MIT · uv workspace · plugin-ready <tspan fill="#0d9488">bp</tspan> CLI</text>

  <rect x="624" y="50" width="512" height="312" rx="12" fill="#030712"/>
  <rect x="624" y="50" width="512" height="312" rx="12" fill="none" stroke="${termBorder}" stroke-width="1"/>
  <path d="M624 62 a12 12 0 0 1 12 -12 h488 a12 12 0 0 1 12 12 v28 h-512 z" fill="#111827"/>
  <line x1="624" y1="90" x2="1136" y2="90" stroke="#1f2937" stroke-width="1"/>
  <circle cx="650" cy="70" r="5.5" fill="#ef4444" opacity="0.85"/>
  <circle cx="670" cy="70" r="5.5" fill="#eab308" opacity="0.85"/>
  <circle cx="690" cy="70" r="5.5" fill="#22c55e" opacity="0.85"/>
  <text x="880" y="75" text-anchor="middle" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="12" fill="#6b7280">fastro - zsh</text>
  <g font-family="'JetBrains Mono',ui-monospace,monospace" font-size="14">
    <text x="650" y="132" fill="#6b7280">$</text><text x="668" y="132" fill="#d1d5db">uv run bp deploy generate prod</text>
    <text x="650" y="168" fill="#4ade80">&#x2713;</text><text x="668" y="168" fill="#d1d5db">Auth + sessions ..........</text><text x="1016" y="168" fill="#4ade80">ready</text>
    <text x="650" y="196" fill="#4ade80">&#x2713;</text><text x="668" y="196" fill="#d1d5db">FastCRUD + SQLAdmin ......</text><text x="1016" y="196" fill="#4ade80">ready</text>
    <text x="650" y="224" fill="#4ade80">&#x2713;</text><text x="668" y="224" fill="#d1d5db">Taskiq workers ...........</text><text x="1016" y="224" fill="#4ade80">ready</text>
    <text x="650" y="252" fill="#4ade80">&#x2713;</text><text x="668" y="252" fill="#d1d5db">Rate limiting + cache ....</text><text x="1016" y="252" fill="#4ade80">ready</text>
    <text x="650" y="288" fill="#6b7280">$</text><text x="668" y="288" fill="#d1d5db">docker compose up --build</text>
    <text x="650" y="316" fill="#2dd4bf">{"status": "healthy"}</text>
    <text x="650" y="346" fill="#ffffff" font-weight="700">→ Build on it.</text>
  </g>

  <text x="66" y="416" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" fill="${muted}" letter-spacing="1">FastAPI · SQLAlchemy 2.0 · Taskiq · SQLAdmin · FastCRUD</text>
  <text x="1136" y="416" text-anchor="end" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" font-weight="700" letter-spacing="0.5" fill="#0d9488">github.com/benavlabs/FastAPI-boilerplate</text>
</svg>`;

(async () => {
  for (const [mode, vars] of Object.entries(MODES)) {
    const out = path.join(OUT, `fastro-cover-${mode}.png`);
    const info = await sharp(Buffer.from(cover(vars)), { density: 240 }).resize(2400).png({ compressionLevel: 9 }).toFile(out);
    console.log('ok', path.basename(out), `${info.width}x${info.height}`);
  }
})();
