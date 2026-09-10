import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import { assertSafeBuildEnvironment } from './config/environment'
import { liquidGlass } from './directives/liquidGlass'
import router from './router'

assertSafeBuildEnvironment(import.meta.env)

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.directive('liquid-glass', liquidGlass)
app.mount('#app')
window.LiquidGlass?.init()
