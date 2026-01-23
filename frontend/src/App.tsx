import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { HomePage } from './pages/HomePage'
import { CharactersPage } from './pages/CharactersPage'
import { CharacterCreatePage } from './pages/CharacterCreatePage'
import { CharacterSheetPage } from './pages/CharacterSheetPage'
import { CampaignsPage } from './pages/CampaignsPage'
import { SessionPage } from './pages/SessionPage'
import { PlayPage } from './pages/PlayPage'
import { SourcebooksPage } from './pages/SourcebooksPage'
import { JournalPage } from './pages/JournalPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="characters" element={<CharactersPage />} />
        <Route path="characters/create" element={<CharacterCreatePage />} />
        <Route path="characters/:characterId" element={<CharacterSheetPage />} />
        <Route path="play/:characterId/:campaignId?" element={<PlayPage />} />
        <Route path="campaigns" element={<CampaignsPage />} />
        <Route path="session/:sessionId" element={<SessionPage />} />
        <Route path="sourcebooks" element={<SourcebooksPage />} />
        <Route path="journal" element={<JournalPage />} />
      </Route>
    </Routes>
  )
}

export default App
