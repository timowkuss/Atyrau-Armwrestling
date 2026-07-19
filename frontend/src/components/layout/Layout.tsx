import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Главная', end: true },
  { to: '/athletes', label: 'Спортсмены' },
  { to: '/competitions', label: 'Соревнования' },
  { to: '/rankings', label: 'Рейтинги' },
  { to: '/news', label: 'Новости' },
]

export function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  // Закрываем мобильное меню при переходе на другую страницу
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  // Блокируем скролл фона, пока открыто мобильное меню
  useEffect(() => {
    document.body.style.overflow = menuOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [menuOpen])

  return (
    <div className="flex min-h-screen flex-col bg-ink text-bone">
      <header className="sticky top-0 z-30 border-b border-steel-dim/30 bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <NavLink to="/" className="flex items-center gap-3">
            <img
              src="/brand/logo-armsport.png"
              alt="Федерация армрестлинга города Атырау"
              className="h-10 w-auto drop-shadow-[0_2px_6px_rgba(0,0,0,0.4)] sm:h-11"
            />
            <span className="hidden font-display text-sm font-bold uppercase leading-tight tracking-wide text-bone sm:block">
              Atyrau
              <br />
              <span className="text-rust">Armwrestling</span>
            </span>
          </NavLink>

          {/* Десктоп-навигация */}
          <nav className="hidden items-center gap-1 md:flex" aria-label="Основная навигация">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-[var(--radius-rivet)] px-3 py-2 text-sm font-medium transition-colors ${
                    isActive ? 'bg-petrol-2 text-brass' : 'text-steel hover:text-bone'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Кнопка мобильного меню */}
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-rivet)] text-bone md:hidden"
            aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
          >
            {menuOpen ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 5L19 19M19 5L5 19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M4 6.5H20M4 12H20M4 17.5H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
        <div className="rivet-line" />

        {/* Мобильное выпадающее меню */}
        {menuOpen && (
          <nav
            id="mobile-nav"
            className="border-b border-steel-dim/30 bg-ink px-5 py-3 md:hidden"
            aria-label="Мобильная навигация"
          >
            <div className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-[var(--radius-rivet)] px-3 py-3 text-base font-medium transition-colors ${
                      isActive ? 'bg-petrol-2 text-brass' : 'text-steel hover:text-bone'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-steel-dim/30 bg-ink-soft">
        <div className="mx-auto max-w-6xl px-5 py-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-4">
              <img
                src="/brand/logo-armsport.png"
                alt="Федерация армрестлинга города Атырау"
                className="h-12 w-auto"
              />
              <div className="h-9 w-px bg-steel-dim/40" aria-hidden="true" />
              <img
                src="/brand/logo-atyrau-city.png"
                alt="Герб города Атырау"
                className="h-11 w-auto"
              />
              <span className="font-display text-xs uppercase leading-snug tracking-wide text-steel">
                Федерация
                <br />
                армрестлинга г. Атырау
              </span>
            </div>

            {/* Соцсети вместо координат */}
            <div className="flex items-center gap-3">
              <a
                href="https://www.instagram.com/atyrau_armsport?igsh=YnMyeGUzenRuc2N4"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Instagram"
                className="flex h-10 w-10 items-center justify-center rounded-full transition-transform hover:scale-105"
                style={{ backgroundColor: '#E4405F', color: '#fff' }}
              >
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="2" y="2" width="20" height="20" rx="5" stroke="currentColor" strokeWidth="1.8" />
                  <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
                  <circle cx="17.4" cy="6.6" r="1.1" fill="currentColor" />
                </svg>
              </a>

              <a
                href="https://wa.me/77023135383"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="WhatsApp"
                className="flex h-10 w-10 items-center justify-center rounded-full transition-transform hover:scale-105"
                style={{ backgroundColor: '#25D366', color: '#fff' }}
              >
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M12 2.5c-5.25 0-9.5 4.25-9.5 9.5 0 1.68.44 3.26 1.22 4.63L2.5 21.5l5.02-1.19A9.46 9.46 0 0 0 12 21.5c5.25 0 9.5-4.25 9.5-9.5S17.25 2.5 12 2.5Z"
                    stroke="currentColor"
                    strokeWidth="1.6"
                  />
                  <path
                    d="M8.3 8.4c.2-.45.4-.46.6-.47h.5c.16 0 .38-.06.6.46s.75 1.8.82 1.93c.07.14.11.3.02.48-.09.18-.13.29-.27.45-.13.15-.28.34-.4.46-.13.13-.27.27-.12.53.16.27.7 1.16 1.51 1.87 1.04.93 1.9 1.22 2.17 1.35.27.14.43.12.6-.07.16-.2.68-.79.86-1.06.18-.27.36-.22.6-.13.25.09 1.58.75 1.85.88.27.14.45.2.52.32.07.12.07.68-.16 1.34-.23.66-1.33 1.26-1.85 1.34-.47.07-1.06.1-1.71-.11-.39-.13-.9-.3-1.55-.58-2.73-1.18-4.51-3.95-4.65-4.14-.14-.18-1.11-1.48-1.11-2.82 0-1.34.7-2 .95-2.27Z"
                    fill="currentColor"
                  />
                </svg>
              </a>
            </div>
          </div>

          <div className="rivet-line my-5" />
          <p className="font-mono text-xs text-steel-dim">
            Официальные результаты матчей и турнирные сетки формируются исключительно
            десктоп-приложением федерации в момент соревнования.
          </p>
        </div>
      </footer>
    </div>
  )
}
