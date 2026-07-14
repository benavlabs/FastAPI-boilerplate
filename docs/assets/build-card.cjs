// Generates the FastroAI cross-sell card as transparent light/dark PNGs.
// Used in the FastAPI-boilerplate docs to promote FastroAI.
// Run: NODE_PATH=<a sharp install> node docs/assets/build-card.cjs
const path = require('path');
const sharp = require('sharp');

const OUT = __dirname;

// Wordmark tracking. Negative = tighter. The previous card jammed the letters
// together; this opens them up to match the FastroAI docs cover.
const WORDMARK_TRACKING = -0.5;

const MODES = {
  light: { primary: '#111827', body: '#4b5563', muted: '#6b7280', termBorder: '#1f2937' },
  dark: { primary: '#f9fafb', body: '#d1d5db', muted: '#9ca3af', termBorder: '#30363d' },
};

const card = ({ primary, body, muted, termBorder }) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430">
  <text x="66" y="78" font-family="'JetBrains Mono','SF Mono',ui-monospace,monospace" font-size="13" font-weight="700" letter-spacing="3.5" fill="${muted}">THE COMPLETE SAAS TEMPLATE</text>
  <text x="62" y="172" font-family="'Space Grotesk',system-ui,sans-serif" font-size="82" font-weight="700" letter-spacing="${WORDMARK_TRACKING}" fill="${primary}">Fastro<tspan fill="#0d9488">AI</tspan></text>

  <rect x="500" y="116" width="104" height="52" rx="26" fill="#0d9488"/>
  <text x="552" y="150" text-anchor="middle" font-family="'Space Grotesk',system-ui,sans-serif" font-size="22" font-weight="700" letter-spacing="2" fill="#ffffff">PRO</text>

  <rect x="66" y="198" width="4" height="62" rx="2" fill="#0d9488"/>
  <text x="86" y="224" font-family="system-ui,sans-serif" font-size="20" fill="${body}">Everything in Fastro + payments, entitlements,</text>
  <text x="86" y="252" font-family="system-ui,sans-serif" font-size="20" fill="${body}">email, a frontend - and AI agents.</text>
  <text x="66" y="318" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" fill="${muted}" letter-spacing="0.5">one-time license · lifetime updates · <tspan fill="#0d9488">fastro.ai</tspan></text>

  <rect x="624" y="50" width="512" height="312" rx="12" fill="#030712"/>
  <rect x="624" y="50" width="512" height="312" rx="12" fill="none" stroke="${termBorder}" stroke-width="1"/>
  <path d="M624 62 a12 12 0 0 1 12 -12 h488 a12 12 0 0 1 12 12 v28 h-512 z" fill="#111827"/>
  <line x1="624" y1="90" x2="1136" y2="90" stroke="#1f2937" stroke-width="1"/>
  <circle cx="650" cy="70" r="5.5" fill="#ef4444" opacity="0.85"/>
  <circle cx="670" cy="70" r="5.5" fill="#eab308" opacity="0.85"/>
  <circle cx="690" cy="70" r="5.5" fill="#22c55e" opacity="0.85"/>
  <text x="880" y="75" text-anchor="middle" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="12" fill="#6b7280">fastroai - zsh</text>
  <g font-family="'JetBrains Mono',ui-monospace,monospace" font-size="14">
    <text x="650" y="132" fill="#6b7280">$</text><text x="668" y="132" fill="#d1d5db">docker compose up -d</text>
    <text x="650" y="168" fill="#4ade80">&#x2713;</text><text x="668" y="168" fill="#d1d5db">Auth + OAuth 2.0 .........</text><text x="1016" y="168" fill="#4ade80">ready</text>
    <text x="650" y="196" fill="#4ade80">&#x2713;</text><text x="668" y="196" fill="#d1d5db">Stripe payments ..........</text><text x="1016" y="196" fill="#4ade80">ready</text>
    <text x="650" y="224" fill="#4ade80">&#x2713;</text><text x="668" y="224" fill="#d1d5db">PydanticAI agents ........</text><text x="1016" y="224" fill="#4ade80">ready</text>
    <text x="650" y="252" fill="#4ade80">&#x2713;</text><text x="668" y="252" fill="#d1d5db">Astro frontend ...........</text><text x="1016" y="252" fill="#4ade80">ready</text>
    <text x="650" y="288" fill="#6b7280">$</text><text x="668" y="288" fill="#d1d5db">curl localhost:8000/health</text>
    <text x="650" y="316" fill="#2dd4bf">{"status": "healthy"}</text>
    <text x="650" y="346" fill="#ffffff" font-weight="700">→ Ship your SaaS.</text>
  </g>

  <text x="66" y="416" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" fill="${muted}" letter-spacing="1">FastAPI · AstroJS · PydanticAI · Stripe · Logfire</text>
  <text x="1136" y="416" text-anchor="end" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="13" font-weight="700" letter-spacing="0.5" fill="#0d9488">fastro.ai ↗</text>
</svg>`;

(async () => {
  for (const [mode, vars] of Object.entries(MODES)) {
    const out = path.join(OUT, `fastroai-card-${mode}.png`);
    const info = await sharp(Buffer.from(card(vars)), { density: 240 }).resize(2400).png({ compressionLevel: 9 }).toFile(out);
    console.log('ok', path.basename(out), `${info.width}x${info.height}`);
  }
})();
