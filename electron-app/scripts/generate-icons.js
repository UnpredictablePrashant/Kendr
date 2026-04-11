// Generates icon.png (1024×1024) and icon.ico (multi-size) from icon.svg
// Run: node scripts/generate-icons.js
const { readFileSync, writeFileSync } = require('fs')
const path = require('path')
const sharp = require('sharp')
const { default: pngToIco } = require('png-to-ico')

const resources = path.join(__dirname, '..', 'resources')
const svgBuffer = readFileSync(path.join(resources, 'icon.svg'))

async function main() {
  // ── PNG 1024×1024 (Linux packaging + dev window icon) ──────────────────
  const png1024 = await sharp(svgBuffer).resize(1024, 1024).png().toBuffer()
  writeFileSync(path.join(resources, 'icon.png'), png1024)
  console.log('✓ icon.png  (1024×1024)')

  // ── ICO with embedded sizes (Windows packaging) ─────────────────────────
  const icoSizes = [16, 32, 48, 256]
  const pngBuffers = await Promise.all(
    icoSizes.map(size => sharp(svgBuffer).resize(size, size).png().toBuffer())
  )
  const ico = await pngToIco(pngBuffers)
  writeFileSync(path.join(resources, 'icon.ico'), ico)
  console.log('✓ icon.ico  (16 / 32 / 48 / 256 px)')

  console.log('\nDone. For macOS, generate icon.icns from icon.png with:')
  console.log('  electron-icon-maker --input=resources/icon.png --output=resources/')
}

main().catch(err => { console.error(err); process.exit(1) })
