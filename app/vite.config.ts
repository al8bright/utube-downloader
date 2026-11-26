// (공통 파일: 네 앱이 같은 내용을 쓴다. 포트는 src/appInfo.ts. docs/STRUCTURE.md)
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VITE_PORT } from './src/appInfo.ts'

/** @fontsource CSS는 woff2와 옛 브라우저용 woff를 함께 적는다. 웹뷰는 woff2만 쓰므로 woff를 빼서 설치 파일을 줄인다. */
function woff2Only(): Plugin {
  return {
    name: 'woff2-only',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes('@fontsource') || !id.endsWith('.css')) return
      return code.replace(/,\s*url\([^)]+\.woff\)\s*format\(['"]woff['"]\)/g, '')
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [woff2Only(), react()],
  // Tauri 개발 실행은 이 포트(tauri.conf.json의 devUrl)를 기다린다. 다른 포트로 밀려나면 빈 창이 뜬다
  // src-tauri는 cargo가 다시 빌드하므로 Vite가 지켜볼 필요가 없다(빌드 중 잠긴 파일 오류가 난다)
  server: { port: VITE_PORT, strictPort: true, watch: { ignored: ['**/src-tauri/**'] } },
})
