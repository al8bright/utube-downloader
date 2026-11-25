import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

/** @fontsource CSS 는 woff2 와 옛 브라우저용 woff 를 함께 적는다. WebView2 는 woff2 만 쓰므로 woff 를 빼서 설치 파일을 줄인다. */
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
  // Tauri 개발 실행은 이 포트를 기다린다(jamak 이 5173 을 쓴다). 다른 포트로 밀려나면 빈 창이 뜬다
  server: { port: 5174, strictPort: true },
})
