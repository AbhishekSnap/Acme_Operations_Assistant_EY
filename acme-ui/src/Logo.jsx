/**
 * Logo.jsx - Acme Operations Assistant logo
 * Three variants: "icon" | "horizontal" | "dark"
 *
 * Usage:
 *   <Logo />                        horizontal (default)
 *   <Logo variant="icon" />         standalone icon mark
 *   <Logo variant="dark" width={200} />   dark sidebar lockup
 */

/* ── Design tokens ────────────────────────────────────────────────────── */
const AMBER        = '#c9a84c'
const AMBER_DIM    = 'rgba(201,168,76,0.22)'
const AMBER_STROKE = 'rgba(201,168,76,0.3)'
const DARK         = '#111110'
const DARK_INNER   = '#1e1e1c'
const WHITE_PRIMARY = '#ffffff'
const WHITE_MID    = 'rgba(255,255,255,0.18)'
const WHITE_SUB    = 'rgba(255,255,255,0.3)'
const SANS         = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

/**
 * IconMark - the shared icon element.
 *
 * Props:
 *   x, y        - top-left origin inside parent SVG
 *   size        - overall size of the square (default 44)
 *   squareFill  - fill colour of the outer rounded rect (default DARK)
 */
function IconMark({ x = 0, y = 0, size = 44, squareFill = DARK }) {
  const rx     = size * 0.18          // corner radius proportional to size
  const pad    = size * 0.18          // inner padding
  const inner  = size - pad * 2       // drawable area

  // Row bar positions
  const bar1Y  = y + pad + inner * 0.12
  const bar2Y  = y + pad + inner * 0.38
  const bar3Y  = y + pad + inner * 0.54
  const barH   = Math.max(2, size * 0.065)
  const bar1W  = inner * 0.62
  const bar2W  = inner * 0.82
  const bar3W  = inner * 0.52

  // Circle in bottom-right
  const circR  = size * 0.155
  const circX  = x + size - pad - circR * 0.6
  const circY  = y + size - pad - circR * 0.6

  // Chevron inside circle (upward arrow)
  const chevH  = circR * 0.55
  const chevW  = circR * 0.55
  const cx     = circX
  const cy     = circY
  // Arrow: up-pointing V shape
  const arrowPts = [
    `${cx - chevW * 0.5} ${cy + chevH * 0.3}`,
    `${cx}               ${cy - chevH * 0.4}`,
    `${cx + chevW * 0.5} ${cy + chevH * 0.3}`,
  ].join(' ')

  return (
    <g>
      {/* Outer square */}
      <rect x={x} y={y} width={size} height={size} rx={rx} fill={squareFill} />
      {/* Inset border */}
      <rect
        x={x + 0.75} y={y + 0.75}
        width={size - 1.5} height={size - 1.5}
        rx={rx - 0.5}
        fill="none"
        stroke={AMBER_STROKE}
        strokeWidth={0.5}
      />

      {/* Row 1 - amber active line */}
      <rect
        x={x + pad} y={bar1Y}
        width={bar1W} height={barH}
        rx={barH / 2}
        fill={AMBER}
      />
      {/* Row 2 - faint white */}
      <rect
        x={x + pad} y={bar2Y}
        width={bar2W} height={barH}
        rx={barH / 2}
        fill={WHITE_MID}
      />
      {/* Row 3 - faint white, shorter */}
      <rect
        x={x + pad} y={bar3Y}
        width={bar3W} height={barH}
        rx={barH / 2}
        fill={WHITE_MID}
      />

      {/* Circle - bottom right */}
      <circle cx={circX} cy={circY} r={circR} fill={AMBER_DIM} />
      <circle cx={circX} cy={circY} r={circR} fill="none" stroke={AMBER} strokeWidth={0.5} />

      {/* Chevron arrow inside circle */}
      <polyline
        points={arrowPts}
        fill="none"
        stroke={AMBER}
        strokeWidth={1.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   VARIANTS
══════════════════════════════════════════════════════════════════════════ */

/** Standalone icon - 72×72 */
function IconVariant() {
  return (
    <svg width={72} height={72} viewBox="0 0 72 72" fill="none"
         xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Acme logo">
      <IconMark x={0} y={0} size={72} squareFill={DARK} />
    </svg>
  )
}

/** Horizontal lockup - icon left, text right, transparent bg */
function HorizontalVariant() {
  const iconSize  = 44
  const gap       = 14
  const textX     = iconSize + gap
  const svgWidth  = 260
  const svgHeight = iconSize

  return (
    <svg width={svgWidth} height={svgHeight} viewBox={`0 0 ${svgWidth} ${svgHeight}`}
         fill="none" xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Acme Operations Assistant">
      <IconMark x={0} y={0} size={iconSize} squareFill={DARK} />

      {/* ACME wordmark */}
      <text
        x={textX} y={22}
        fontFamily="'DM Mono', monospace"
        fontSize={18} fontWeight={500}
        letterSpacing="0.04em"
        fill={DARK}
      >
        ACME
      </text>

      {/* Hairline rule under ACME */}
      <line
        x1={textX} y1={27}
        x2={svgWidth} y2={27}
        stroke="rgba(0,0,0,0.1)" strokeWidth={0.5}
      />

      {/* Subtitle */}
      <text
        x={textX} y={40}
        fontFamily={SANS}
        fontSize={11} fontWeight={400}
        letterSpacing="0.08em"
        textAnchor="start"
        fill="#888780"
      >
        OPERATIONS ASSISTANT
      </text>
    </svg>
  )
}

/**
 * Dark sidebar lockup - no background rect, no border, no live badge.
 * Floats directly on the dark sidebar. Icon + ACME + subtitle only.
 */
function DarkVariant({ width = 200 }) {
  const height   = 44
  const iconSize = 34
  const textX    = iconSize + 10

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         fill="none" xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Acme Operations Assistant">

      {/* Icon mark - DARK_INNER square on dark sidebar */}
      <IconMark x={0} y={(height - iconSize) / 2} size={iconSize} squareFill={DARK_INNER} />

      {/* ACME wordmark */}
      <text
        x={textX} y={20}
        fontFamily="'DM Mono', monospace"
        fontSize={14} fontWeight={500}
        letterSpacing="0.05em"
        fill={WHITE_PRIMARY}
      >
        ACME
      </text>

      {/* Subtitle */}
      <text
        x={textX} y={34}
        fontFamily={SANS}
        fontSize={9} fontWeight={400}
        letterSpacing="0.09em"
        fill={WHITE_SUB}
      >
        OPERATIONS ASSISTANT
      </text>
    </svg>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   EXPORT
══════════════════════════════════════════════════════════════════════════ */
export default function Logo({ variant = 'horizontal', width }) {
  if (variant === 'icon')       return <IconVariant />
  if (variant === 'dark')       return <DarkVariant width={width} />
  return <HorizontalVariant />
}
