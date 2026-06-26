import { createApp } from 'vue'
import '../../shared/src/tokens/marketing.css'
import App from './App.vue'
import { router } from './router'

createApp(App).use(router).mount('#app')
