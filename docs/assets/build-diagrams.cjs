// Generates the architecture diagrams as transparent light/dark PNGs, used in
// the Composable Features guide, the permissions guide and the release notes.
// Run: NODE_PATH=<a sharp install> node docs/assets/build-diagrams.cjs
const path = require('path');
const sharp = require('sharp');

const OUT = __dirname;

const TEAL = '#0d9488';

const MODES = {
  light: { primary: '#111827', body: '#4b5563', muted: '#6b7280', line: '#9ca3af', panel: '#e5e7eb' },
  dark: { primary: '#f9fafb', body: '#d1d5db', muted: '#9ca3af', line: '#6b7280', panel: '#30363d' },
};

const MONO = "'JetBrains Mono','SF Mono',ui-monospace,monospace";
const SANS = "'Space Grotesk',system-ui,sans-serif";

/** An arrow marker, one per mode so the head matches the line colour. */
const marker = (line) => `<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="${line}"/>
    </marker>
  </defs>`;

const compositionRoot = ({ primary, body, muted, line, panel }) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="560" viewBox="0 0 1200 560">
  ${marker(line)}
  <text x="40" y="40" font-family="${MONO}" font-size="13" font-weight="700" letter-spacing="3" fill="${muted}">THE COMPOSITION ROOT</text>

  <text x="40" y="84" font-family="${SANS}" font-size="17" font-weight="700" fill="${primary}">features</text>
  <text x="432" y="84" font-family="${SANS}" font-size="17" font-weight="700" fill="${TEAL}">src/wiring/</text>
  <text x="900" y="84" font-family="${SANS}" font-size="17" font-weight="700" fill="${primary}">what reads the lists</text>

  <g font-family="${MONO}" font-size="14" fill="${body}">
    <rect x="40" y="104" width="306" height="78" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="60" y="132" fill="${primary}">modules/role/</text>
    <text x="60" y="158" font-size="12.5" fill="${muted}">routes · models · admin · settings</text>

    <rect x="40" y="198" width="306" height="78" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="60" y="226" fill="${primary}">modules/api_keys/</text>
    <text x="60" y="252" font-size="12.5" fill="${muted}">routes · models · transport · tasks</text>

    <rect x="40" y="292" width="306" height="78" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="60" y="320" fill="${primary}">modules/tier/</text>
    <text x="60" y="346" font-size="12.5" fill="${muted}">routes · models · contrib · seeder</text>

    <rect x="40" y="386" width="306" height="78" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="60" y="414" fill="${primary}">infrastructure/cache/</text>
    <text x="60" y="440" font-size="12.5" fill="${muted}">backends · decorator · health</text>
  </g>

  <line x1="354" y1="284" x2="424" y2="284" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>
  <text x="389" y="268" text-anchor="middle" font-family="${MONO}" font-size="11.5" fill="${muted}">contributes</text>

  <rect x="432" y="104" width="400" height="360" rx="10" fill="none" stroke="${TEAL}" stroke-width="1.5"/>
  <g font-family="${MONO}" font-size="13">
    <text x="456" y="138" fill="${primary}">app.py</text><text x="610" y="138" fill="${muted}">ROUTER_MOUNTS, LIFECYCLES</text>
    <text x="456" y="170" fill="${primary}">settings.py</text><text x="610" y="170" fill="${muted}">the settings mixins</text>
    <text x="456" y="202" fill="${primary}">hooks.py</text><text x="610" y="202" fill="${muted}">PERMISSION_SOURCES</text>
    <text x="456" y="234" fill="${primary}">models.py</text><text x="610" y="234" fill="${muted}">UserModelExtensions</text>
    <text x="456" y="266" fill="${primary}">admin.py</text><text x="610" y="266" fill="${muted}">ADMIN_VIEWS</text>
    <text x="456" y="298" fill="${primary}">email.py</text><text x="610" y="298" fill="${muted}">EMAIL_SENDER</text>
    <text x="456" y="330" fill="${primary}">tasks.py</text><text x="610" y="330" fill="${muted}">TASK_MODULES</text>
    <text x="456" y="362" fill="${primary}">tables.py</text><text x="610" y="362" fill="${muted}">TABLE_MODULES</text>
    <text x="456" y="394" fill="${primary}">transports.py</text><text x="610" y="394" fill="${muted}">EXTRA_TRANSPORTS</text>
    <text x="456" y="426" fill="${primary}">cache.py</text><text x="610" y="426" fill="${muted}">cached</text>
  </g>

  <line x1="840" y1="284" x2="948" y2="284" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>
  <text x="894" y="272" text-anchor="middle" font-family="${MONO}" font-size="12" fill="${muted}">reads</text>

  <g font-family="${MONO}" font-size="13.5" fill="${body}">
    <text x="956" y="150" fill="${primary}">interfaces/api/v1</text>
    <text x="956" y="172" font-size="12" fill="${muted}">mounts the routers</text>
    <text x="956" y="222" fill="${primary}">infrastructure/auth</text>
    <text x="956" y="244" font-size="12" fill="${muted}">asks who holds what</text>
    <text x="956" y="294" fill="${primary}">interfaces/admin</text>
    <text x="956" y="316" font-size="12" fill="${muted}">registers the views</text>
    <text x="956" y="366" fill="${primary}">taskiq worker</text>
    <text x="956" y="388" font-size="12" fill="${muted}">imports the task modules</text>
  </g>

  <line x1="40" y1="496" x2="1160" y2="496" stroke="${panel}" stroke-width="1"/>
  <text x="40" y="528" font-family="${SANS}" font-size="16" fill="${body}">The wiring imports every feature. No feature imports another, and nothing imports the wiring back.</text>
  <text x="40" y="552" font-family="${MONO}" font-size="12.5" fill="${muted}">written by tools/removal_drill.py from the feature manifest · compared with what it writes by tests/unit/test_removal_drill.py</text>
</svg>`;

const removalDrill = ({ primary, body, muted, line, panel }) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
  ${marker(line)}
  <text x="40" y="40" font-family="${MONO}" font-size="13" font-weight="700" letter-spacing="3" fill="${muted}">THE REMOVAL DRILL, ONCE PER PRESET</text>

  <g font-family="${MONO}" font-size="13.5">
    <rect x="40" y="76" width="200" height="72" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="140" y="108" text-anchor="middle" fill="${primary}">copy the repo</text>
    <text x="140" y="130" text-anchor="middle" font-size="12" fill="${muted}">to a scratch dir</text>

    <rect x="288" y="76" width="200" height="72" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="388" y="108" text-anchor="middle" fill="${primary}">delete the paths</text>
    <text x="388" y="130" text-anchor="middle" font-size="12" fill="${muted}">of the features left out</text>

    <rect x="536" y="76" width="200" height="72" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="636" y="108" text-anchor="middle" fill="${primary}">regenerate</text>
    <text x="636" y="130" text-anchor="middle" font-size="12" fill="${muted}">src/wiring/ for the rest</text>

    <rect x="784" y="76" width="376" height="72" rx="8" fill="none" stroke="${TEAL}" stroke-width="1.5"/>
    <text x="972" y="108" text-anchor="middle" fill="${TEAL}">run six checks over what is left</text>
    <text x="972" y="130" text-anchor="middle" font-size="12" fill="${muted}">any one of them fails the preset</text>
  </g>

  <line x1="248" y1="112" x2="280" y2="112" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="496" y1="112" x2="528" y2="112" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="744" y1="112" x2="776" y2="112" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>

  <g font-family="${MONO}" font-size="13.5" fill="${body}">
    <text x="800" y="196" fill="${primary}">1</text><text x="828" y="196">the app imports</text>
    <text x="800" y="226" fill="${primary}">2</text><text x="828" y="226">every module imports</text>
    <text x="800" y="256" fill="${primary}">3</text><text x="828" y="256">ruff</text>
    <text x="800" y="286" fill="${primary}">4</text><text x="828" y="286">mypy</text>
    <text x="800" y="316" fill="${primary}">5</text><text x="828" y="316">the remaining tests</text>
    <text x="800" y="346" fill="${primary}">6</text><text x="828" y="346">an Alembic baseline on an empty database</text>
  </g>
  <line x1="972" y1="156" x2="972" y2="176" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>

  <text x="40" y="200" font-family="${SANS}" font-size="16" font-weight="700" fill="${primary}">nine presets run as a CI matrix</text>
  <g font-family="${MONO}" font-size="13" fill="${muted}">
    <text x="40" y="232">core-only</text>
    <text x="40" y="258">core-taskiq</text>
    <text x="40" y="284">accounts-only</text>
    <text x="40" y="310">accounts-rbac</text>
    <text x="40" y="336">accounts-admin</text>
    <text x="260" y="232">accounts-api-keys</text>
    <text x="260" y="258">accounts-rbac-tiers</text>
    <text x="260" y="284">accounts-cache-taskiq</text>
    <text x="260" y="310" fill="${TEAL}">everything</text>
  </g>

  <line x1="40" y1="396" x2="1160" y2="396" stroke="${panel}" stroke-width="1"/>
  <text x="40" y="428" font-family="${SANS}" font-size="16" fill="${body}">The baseline is the check that makes a removal visible: a feature's tables leave with it.</text>
  <text x="40" y="452" font-family="${MONO}" font-size="12.5" fill="${muted}">uv run --no-sync python tools/removal_drill.py [preset]</text>
</svg>`;

const credentialNarrowing = ({ primary, body, muted, line, panel }) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
  ${marker(line)}
  <text x="40" y="40" font-family="${MONO}" font-size="13" font-weight="700" letter-spacing="3" fill="${muted}">WHAT A CREDENTIAL MAY DO</text>

  <g font-family="${MONO}" font-size="13.5">
    <rect x="40" y="88" width="252" height="112" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="64" y="120" fill="${primary}">session cookie</text>
    <text x="64" y="146" font-size="12" fill="${muted}">everything the account holds</text>
    <text x="64" y="176" font-size="12" fill="${muted}">superuser flag kept</text>

    <rect x="40" y="228" width="252" height="112" rx="8" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="64" y="260" fill="${primary}">X-API-Key</text>
    <text x="64" y="286" font-size="12" fill="${muted}">a scope of registry names</text>
    <text x="64" y="316" font-size="12" fill="${TEAL}">superuser flag cancelled</text>
  </g>

  <line x1="300" y1="214" x2="356" y2="214" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>

  <rect x="364" y="140" width="320" height="148" rx="10" fill="none" stroke="${TEAL}" stroke-width="1.5"/>
  <text x="524" y="178" text-anchor="middle" font-family="${SANS}" font-size="17" font-weight="700" fill="${TEAL}">effective permissions</text>
  <text x="524" y="214" text-anchor="middle" font-family="${MONO}" font-size="14" fill="${primary}">what the account holds</text>
  <text x="524" y="240" text-anchor="middle" font-family="${MONO}" font-size="14" fill="${muted}">narrowed to</text>
  <text x="524" y="266" text-anchor="middle" font-family="${MONO}" font-size="14" fill="${primary}">what the credential carries</text>

  <line x1="692" y1="214" x2="748" y2="214" stroke="${line}" stroke-width="1.5" marker-end="url(#arrow)"/>

  <g font-family="${MONO}" font-size="13.5">
    <rect x="756" y="140" width="404" height="148" rx="10" fill="none" stroke="${panel}" stroke-width="1.5"/>
    <text x="780" y="176" fill="${primary}">require_permissions("user.update")</text>
    <text x="780" y="212" font-size="12.5" fill="${muted}">the route's gate, resolved once per request</text>
    <text x="780" y="248" font-size="12.5" fill="${muted}">a name the registry doesn't know can't be stored</text>
    <text x="780" y="274" font-size="12.5" fill="${muted}">a name it forgot is ignored when permissions load</text>
  </g>

  <line x1="40" y1="372" x2="1160" y2="372" stroke="${panel}" stroke-width="1"/>
  <text x="40" y="404" font-family="${SANS}" font-size="16" fill="${body}">A superuser's key scoped to nothing can't rename its owner's account. One scoped user.update can.</text>
  <text x="40" y="430" font-family="${SANS}" font-size="16" fill="${body}">Owning the account doesn't widen what the key may do.</text>
  <text x="40" y="456" font-family="${MONO}" font-size="12.5" fill="${muted}">roles and key scopes name the same registry permissions · nobody hands out what they don't hold</text>
</svg>`;

const DIAGRAMS = {
  'composition-root': compositionRoot,
  'removal-drill': removalDrill,
  'credential-narrowing': credentialNarrowing,
};

(async () => {
  for (const [name, draw] of Object.entries(DIAGRAMS)) {
    for (const [mode, vars] of Object.entries(MODES)) {
      const out = path.join(OUT, `${name}-${mode}.png`);
      const info = await sharp(Buffer.from(draw(vars)), { density: 240 }).resize(2400).png({ compressionLevel: 9 }).toFile(out);
      console.log('ok', path.basename(out), `${info.width}x${info.height}`);
    }
  }
})();
