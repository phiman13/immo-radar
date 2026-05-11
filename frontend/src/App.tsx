import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { ListingsPage } from './pages/ListingsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SystemPage } from './pages/SystemPage'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ListingsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/system" element={<SystemPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
