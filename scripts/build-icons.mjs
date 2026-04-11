#!/usr/bin/env node
/**
 * build-icons.mjs  —  Generate electron-app/resources/icon.{png,ico,icns}
 *                     from a single source PNG (1024×1024 recommended).
 *
 * Uses sharp + png-to-ico (already in electron-app devDependencies).
 * Works on all platforms — no ImageMagick required.
 *
 * Usage (run from repo root):
 *   node scripts/build-icons.mjs path/to/source-logo.png
 *
 * Or via npm (from electron-app/):
 *   npm run build-icons -- ../path/to/source-logo.png
 */
import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT_DIR  = resolve(__dirname, '..')
const OUT_DIR   = resolve(ROOT_DIR, 'electron-app', 'resources')
mkdirSync(OUT_DIR, { recursive: true })

const sourcePath = process.argv[2]
if (!sourcePath) {
  console.error('Usage: node scripts/build-icons.mjs path/to/source-logo.png')
  process.exit(1)
}

// Load sharp from electron-app/node_modules
let sharp
try {
  sharp = require(resolve(ROOT_DIR, 'electron-app', 'node_modules', 'sharp'))
} catch {
  console.error('sharp not found. Run: cd electron-app && npm install')
  process.exit(1)
}

let pngToIco
try {
  pngToIco = require(resolve(ROOT_DIR, 'electron-app', 'node_modules', 'png-to-ico'))
} catch {
  console.error('png-to-ico not found. Run: cd electron-app && npm install')
  process.exit(1)
}

const src = resolve(process.cwd(), sourcePath)
console.log(`\nSource : ${src}`)
console.log(`Output : ${OUT_DIR}\n`)

// ── 1. icon.png (1024×1024) ──────────────────────────────────────────────────
process.stdout.write('▸ Generating icon.png… ')
await sharp(src).resize(1024, 1024).toFile(resolve(OUT_DIR, 'icon.png'))
console.log('✔')

// ── 2. icon.ico (multi-resolution Windows icon) ───────────────────────────────
process.stdout.write('▸ Generating icon.ico… ')
const icoSizes = [16, 24, 32, 48, 64, 128, 256]
const icoBuffers = await Promise.all(
  icoSizes.map(s => sharp(src).resize(s, s).png().toBuffer())
)
const icoBuffer = await pngToIco(icoBuffers)
writeFileSync(resolve(OUT_DIR, 'icon.ico'), icoBuffer)
console.log('✔')

// ── 3. icon.icns (macOS) — requires iconutil on macOS ────────────────────────
if (process.platform === 'darwin') {
  process.stdout.write('▸ Generating icon.icns… ')
  const { execSync } = await import('child_process')
  const { mkdtempSync, rmSync } = await import('fs')
  const { tmpdir } = await import('os')

  const iconsetDir = mkdtempSync(resolve(tmpdir(), 'kendr-iconset-'))
  const iconsetPath = resolve(iconsetDir, 'icon.iconset')
  mkdirSync(iconsetPath)

  const icnsSizes = [16, 32, 128, 256, 512]
  await Promise.all(icnsSizes.flatMap(s => [
    sharp(src).resize(s, s).toFile(resolve(iconsetPath, `icon_${s}x${s}.png`)),
    sharp(src).resize(s * 2, s * 2).toFile(resolve(iconsetPath, `icon_${s}x${s}@2x.png`)),
  ]))
  execSync(`iconutil -c icns "${iconsetPath}" -o "${resolve(OUT_DIR, 'icon.icns')}"`)
  rmSync(iconsetDir, { recursive: true, force: true })
  console.log('✔')
} else {
  console.log('▸ icon.icns skipped (macOS only — run this script on your Mac build machine)')
}

console.log(`\nDone! Icons written to electron-app/resources/`)
