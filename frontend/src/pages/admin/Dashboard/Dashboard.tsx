import { Link } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'

const SECTIONS = [
  { to: '/admin/clubs', title: 'Клубы', desc: 'Создание и редактирование клубов федерации.', roles: ['super_admin', 'admin'] },
  { to: '/admin/coaches', title: 'Тренеры', desc: 'Карточки тренеров, привязка к клубам.', roles: ['super_admin', 'admin'] },
  { to: '/admin/athletes', title: 'Спортсмены', desc: 'Профили, видимость на сайте, ручная правка статистики.', roles: ['super_admin', 'admin'] },
  { to: '/admin/news', title: 'Новости', desc: 'Публикации федерации.', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/gallery', title: 'Медиа', desc: 'Альбомы, фото и видео турниров.', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/competitions', title: 'Турниры (инфо)', desc: 'Только описание, афиша, регламент. Сетка и результаты — из десктопа.', roles: ['super_admin', 'admin'] },
]

export function AdminDashboard() {
  const { user } = useAuth()
  const visible = SECTIONS.filter((s) => user && s.roles.includes(user.role_code))

  return (
    <div>
      <p className="text-eyebrow text-rust">Панель управления</p>
      <h1 className="mt-2 font-display text-2xl text-bone">Здравствуйте, {user?.full_name}</h1>
      <p className="mt-2 text-steel">
        Роль «{user?.role_code}». Сетка турниров, участники и результаты матчей редактируются
        только из десктоп-приложения на площадке — здесь только информационная часть сайта.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {visible.map((s) => (
          <Link key={s.to} to={s.to} className="plate rounded-[var(--radius-rivet)] p-5 transition-transform hover:-translate-y-0.5 hover:border-brass/50">
            <h2 className="font-display text-lg text-bone">{s.title}</h2>
            <p className="mt-1 text-sm text-steel">{s.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
