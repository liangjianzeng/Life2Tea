// i18n setup — Life2Tea frontend
import { createI18n } from "vue-i18n"
import zhCN from "./locales/zh-CN"
import en from "./locales/en"

const saved = localStorage.getItem("life2tea-locale")
const locale = saved === "en" ? "en" : "zh-CN"

const i18n = createI18n({
  legacy: false, // Vue 3 composition API
  locale,
  fallbackLocale: "en",
  messages: {
    "zh-CN": zhCN,
    en,
  },
})

export default i18n

// Helper: toggle between zh-CN and en
export function toggleLocale() {
  const next = i18n.global.locale.value === "zh-CN" ? "en" : "zh-CN"
  i18n.global.locale.value = next
  localStorage.setItem("life2tea-locale", next)
}
