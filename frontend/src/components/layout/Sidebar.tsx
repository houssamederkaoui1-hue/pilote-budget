import { NavLink } from "react-router-dom";
import { CloseIcon } from "../icons";
import { NAV_ITEMS } from "../../lib/navigation";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      <div
        className={`${styles.backdrop} ${open ? styles.backdropVisible : ""}`}
        onClick={onClose}
        aria-hidden
      />
      <aside className={`${styles.sidebar} ${open ? styles.open : ""}`}>
        <div className={styles.brand}>
          <div className={styles.logo} aria-hidden>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19V11M9.5 19V5M15 19v-6M20.5 19v-9" />
            </svg>
          </div>
          <div className={styles.brandText}>
            <span className={styles.brandName}>Pilote Budget</span>
            <span className={styles.brandTag}>Finance cockpit</span>
          </div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close navigation">
            <CloseIcon size={17} />
          </button>
        </div>

        <nav className={styles.nav}>
          <div className={styles.navGroupLabel}>Overview</div>
          {NAV_ITEMS.filter((item) => item.group === "overview").map((item) => (
            <NavRow key={item.path} item={item} onClose={onClose} />
          ))}

          <div className={styles.navGroupLabel}>Planning</div>
          {NAV_ITEMS.filter((item) => item.group === "planning").map((item) => (
            <NavRow key={item.path} item={item} onClose={onClose} />
          ))}

          <div className={styles.navGroupLabel}>Insights</div>
          {NAV_ITEMS.filter((item) => item.group === "insights").map((item) => (
            <NavRow key={item.path} item={item} onClose={onClose} />
          ))}
        </nav>

        <footer className={styles.footer}>
          <div className={styles.statusRow}>
            <span className={styles.statusDot} aria-hidden />
            <span>Local-first · SQLite</span>
          </div>
          <div className={styles.version}>Foundation build · v0.1.0</div>
        </footer>
      </aside>
    </>
  );
}

function NavRow({ item, onClose }: { item: (typeof NAV_ITEMS)[number]; onClose: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      end={item.path === "/"}
      className={({ isActive }) =>
        `${styles.navRow} ${isActive ? styles.navRowActive : ""}`
      }
      onClick={onClose}
    >
      <span className={styles.navIcon}>
        <Icon size={17} />
      </span>
      <span className={styles.navLabel}>{item.label}</span>
      {item.status === "planned" && <span className={styles.navPill}>soon</span>}
    </NavLink>
  );
}
