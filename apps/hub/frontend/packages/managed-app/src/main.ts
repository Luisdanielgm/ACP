import { createApp } from 'vue'
import '../../shared/src/tokens/dashboard.css'
import './styles/managed-theme.css'
import App from './App.vue'
import { router } from './router'

createApp(App).use(router).mount('#app')
