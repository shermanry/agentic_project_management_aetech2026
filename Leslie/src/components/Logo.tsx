// YBuild logo, inlined from src/assets/brand/*.svg so it inherits the text colour and ships in one file.
// Geometry is copied unchanged from the supplied brand assets.

const Mark = () => (
  <>
    <path d="M0 0 H44 L108 88 L86 119 Z" />
    <path d="M164 0 H207 L64 220 H20 Z" />
    <path d="M224 0 H261 C294 0 316 23 316 56 C316 88 294 113 261 113 H161 L171 98 H261 C285 98 301 80 301 56 C301 31 285 14 261 14 H215 Z" />
    <path d="M171 98 H261 C300 98 322 125 322 160 C322 195 297 220 261 220 H96 L106 205 H261 C289 205 306 187 306 160 C306 133 289 113 261 113 H161 Z" />
  </>
)

/** Full wordmark: YBuild. */
export function Wordmark({ height = 22 }: { height?: number }) {
  return (
    <svg className="logo" height={height} viewBox="-8 -8 784 236" fill="currentColor" role="img" aria-label="YBuild">
      <Mark />
      <path d="M349 66 H364 V152 C364 188 385 205 413 205 C441 205 462 188 462 152 V66 H477 V153 C477 193 453 220 413 220 C373 220 349 193 349 153 Z" />
      <path d="M513 66 H529 V220 H513 Z" />
      <circle cx="521" cy="19" r="13" />
      <path d="M572 0 H588 V220 H572 Z" />
      <path
        fillRule="evenodd"
        d="M690 65 C730 65 756 97 756 142 C756 187 728 220 690 220 C645 220 611 187 611 142 C611 97 645 65 690 65 Z M690 80 C654 80 627 107 627 142 C627 178 654 205 690 205 C724 205 749 177 749 142 C749 108 724 80 690 80 Z"
      />
      <path d="M752 0 H768 V220 H752 Z" />
    </svg>
  )
}

/** YB monogram, for tight spaces. */
export function Monogram({ height = 22 }: { height?: number }) {
  return (
    <svg className="logo" height={height} viewBox="-8 -8 339 236" fill="currentColor" role="img" aria-label="YBuild">
      <Mark />
    </svg>
  )
}
