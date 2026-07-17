import { createBrowserRouter } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { Home } from '@/pages/Home/Home'
import { Athletes } from '@/pages/Athletes/Athletes'
import { AthleteProfile } from '@/pages/AthleteProfile/AthleteProfile'
import { Competitions } from '@/pages/Competitions/Competitions'
import { CompetitionDetail } from '@/pages/Competitions/CompetitionDetail'
import { News } from '@/pages/News/News'
import { NewsDetail } from '@/pages/News/NewsDetail'
import { Rankings } from '@/pages/Rankings/Rankings'
import { NotFound } from '@/pages/NotFound/NotFound'
import { AdminLogin } from '@/pages/admin/Login/Login'
import { AdminLayout } from '@/components/admin/AdminLayout'
import { RequireAuth } from '@/components/admin/RequireAuth'
import { AdminDashboard } from '@/pages/admin/Dashboard/Dashboard'
import { ClubsAdmin } from '@/pages/admin/Clubs/ClubsAdmin'
import { CoachesAdmin } from '@/pages/admin/Coaches/CoachesAdmin'
import { AthletesAdmin } from '@/pages/admin/Athletes/AthletesAdmin'
import { NewsAdmin } from '@/pages/admin/News/NewsAdmin'
import { GalleryAdmin } from '@/pages/admin/Gallery/GalleryAdmin'
import { CompetitionsAdmin } from '@/pages/admin/CompetitionsAdmin/CompetitionsAdmin'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <NotFound />,
    children: [
      { index: true, element: <Home /> },
      { path: 'athletes', element: <Athletes /> },
      { path: 'athletes/:id', element: <AthleteProfile /> },
      { path: 'competitions', element: <Competitions /> },
      { path: 'competitions/:id', element: <CompetitionDetail /> },
      { path: 'news', element: <News /> },
      { path: 'news/:slug', element: <NewsDetail /> },
      { path: 'rankings', element: <Rankings /> },
      { path: '*', element: <NotFound /> },
    ],
  },
  { path: '/admin/login', element: <AdminLogin /> },
  {
    path: '/admin',
    element: (
      <RequireAuth>
        <AdminLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <AdminDashboard /> },
      {
        path: 'clubs',
        element: (
          <RequireAuth roles={['super_admin', 'admin']}>
            <ClubsAdmin />
          </RequireAuth>
        ),
      },
      {
        path: 'coaches',
        element: (
          <RequireAuth roles={['super_admin', 'admin']}>
            <CoachesAdmin />
          </RequireAuth>
        ),
      },
      {
        path: 'athletes',
        element: (
          <RequireAuth roles={['super_admin', 'admin']}>
            <AthletesAdmin />
          </RequireAuth>
        ),
      },
      {
        path: 'news',
        element: (
          <RequireAuth roles={['super_admin', 'admin', 'editor']}>
            <NewsAdmin />
          </RequireAuth>
        ),
      },
      {
        path: 'gallery',
        element: (
          <RequireAuth roles={['super_admin', 'admin', 'editor']}>
            <GalleryAdmin />
          </RequireAuth>
        ),
      },
      {
        path: 'competitions',
        element: (
          <RequireAuth roles={['super_admin', 'admin']}>
            <CompetitionsAdmin />
          </RequireAuth>
        ),
      },
    ],
  },
])
