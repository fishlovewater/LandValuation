import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const cliPath = fileURLToPath(new URL('../node_modules/@playwright/test/cli.js', import.meta.url))
const env = { ...process.env }
delete env.NO_COLOR
delete env.FORCE_COLOR

const child = spawn(process.execPath, [cliPath, 'test', ...process.argv.slice(2)], {
  env,
  stdio: 'inherit',
  windowsHide: true,
})

child.on('error', (error) => {
  console.error(error)
  process.exitCode = 1
})

child.on('exit', (code) => {
  process.exitCode = code ?? 1
})
